"""Flota edge: estado derivado + estado del config firmado (T-1.22 · B1/G7, T-1.30 · C4).

- ``GET /fleet/gateways`` — inventario con ``OPERATIVO|DEGRADADO|SIN ENLACE``.
- ``GET /fleet/gateways/{id}/config-state`` — qué config firmada tiene realmente el
  gabinete, para que la Matriz Multi-Tenant distinga PENDIENTE de SINCRONIZADO.
- ``POST/PUT/DELETE /fleet/gateways`` — administración del inventario (T-1.32).

Autz (RBAC §2 · columna Flota Edge): superficie web + rol con acceso a /fleet
(superadmin/support Total; tenant_admin/soc_operator/gov_operator Lectura). Tanto el
estado de flota (``schemas.fleet.derive_fleet_state``) como ``in_sync`` (mismo
predicado que ``commands/sync.py``) se derivan server-side: la UI solo pinta.

La escritura exige además la acción ``manage_fleet`` (superadmin + tenant_admin), y el
``tenant_id`` del gabinete se hereda del sitio padre: nunca viaja en el cuerpo.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_console_scope, require_roles, require_web_surface
from takab_api.auth.matrix import FLEET, ROLE_ACTION_MATRIX, ROLE_ROUTE_MATRIX
from takab_api.auth.scope import ConsoleScope
from takab_api.queries import fleet as q
from takab_api.queries import fleet_health as qh
from takab_api.queries import fw_releases as qr
from takab_api.retire_code import check_confirmation, require_retire_code
from takab_api.routers._common import (
    http_error,
    integrity_error,
    read_session,
    tenant_of_parent_site,
)
from takab_api.schemas.fleet import (
    DEGRADADO,
    SIN_ENLACE,
    GatewayConfigStateOut,
    GatewayCreate,
    GatewayHealthOut,
    GatewayOut,
    GatewayRowOut,
    GatewayUpdate,
    HealthBucket,
    ReleaseCreate,
    ReleaseOut,
    ReleaseRef,
    derive_fleet_state,
    derive_version_drift,
    fleet_degrade_reasons,
    sig_fingerprint,
)
from takab_api.schemas.retire import GatewayRetire
from takab_api.settings import Settings

# Roles con /fleet en RBAC §2 (vía matrix.py).
_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if FLEET in routes)
)

_MANAGE_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, a in ROLE_ACTION_MATRIX.items() if a["manage_fleet"])
)

_require_manage = require_roles(*_MANAGE_FLEET_ROLES)

router = APIRouter(
    dependencies=[Depends(require_web_surface), Depends(require_roles(*_FLEET_ROLES))]
)

# [T-2.69] Sin ``fw_version``: la versión la DECLARA el gabinete en cada latido y
# ese es su único escritor (``ingest/handlers.py``). Este PUT es de reemplazo total
# y la consola reenviaba el campo prellenado con cada edición, así que un operador
# podía anotar —o borrar— una versión que el aparato nunca corrió; en un gabinete
# SIN ENLACE la mentira era permanente. El schema ya lo rechaza con 422
# (``extra='forbid'``); esta tupla es la segunda cerradura, para que reañadirlo al
# schema no baste para que vuelva a escribirse.
_WRITE_FIELDS = (
    "site_id",
    "serial",
    "iot_thing",
    "has_wr1",
    "equipment",
    "installed_at",
)


def _row_out(row) -> GatewayRowOut:
    return GatewayRowOut(**dict(row._mapping))


def _write_values(body) -> dict:
    """Valores para el SQL de escritura; ``equipment`` viaja como JSON (::jsonb)."""
    values = {f: getattr(body, f) for f in _WRITE_FIELDS}
    values["equipment"] = body.equipment.model_dump_json()
    return values


@router.get(
    "/fleet/gateways/{gateway_id}/config-state",
    response_model=GatewayConfigStateOut,
)
async def get_gateway_config_state(
    gateway_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> GatewayConfigStateOut:
    """Config firmada que el gabinete tiene REALMENTE. 404 si RLS no lo deja verlo.

    Nunca publicado ⇒ 200 con ``version=null, in_sync=false``: la consola pinta
    PENDIENTE, no un error.
    """
    row = await q.get_config_state(conn, str(gateway_id))
    if row is None:
        raise http_error(404, "gateway no encontrado")
    return _config_state_out(dict(row._mapping))


def _config_state_out(m: dict) -> GatewayConfigStateOut:
    return GatewayConfigStateOut(
        gateway_id=m["gateway_id"],
        version=m["version"],
        published_at=m["published_at"],
        sig_fingerprint=sig_fingerprint(m["sig"]),
        in_sync=m["in_sync"],
        has_edge_config=m["has_edge_config"],
        is_syncable=m["is_syncable"],
    )


@router.get("/fleet/config-state", response_model=list[GatewayConfigStateOut])
async def list_gateway_config_states(
    conn: AsyncConnection = Depends(read_session),
) -> list[GatewayConfigStateOut]:
    """Estado del config firmado de TODA la flota visible, en UNA consulta.

    [T-2.37] Sustituye al abanico de N peticiones por gabinete que abría la consola
    cada 10 s. El endpoint por-id se conserva: sigue siendo el diagnóstico de un
    gabinete concreto.
    """
    return [_config_state_out(dict(r._mapping)) for r in await q.list_config_states(conn)]


@router.get("/fleet/health-history", response_model=list[GatewayHealthOut])
async def fleet_health_history(
    hours: int = 24,
    bucket_min: int = 60,
    conn: AsyncConnection = Depends(read_session),
) -> list[GatewayHealthOut]:
    """Historia de salud de la flota: tendencia y REINCIDENCIA (T-2.38).

    La pantalla sabía si un gabinete está bien ahora y nada más: uno que se cae cinco
    veces al día se veía igual que uno que nunca falló. Aquí salen las caídas
    (derivadas del silencio entre latidos, con el umbral de ``derive_fleet_state``) y
    la serie por bucket para la sparkline.

    Ventana acotada a 7 días y bucket a [5, 1440] min: es una vista de operación, no
    un almacén de series — para eso está la telemetría.
    """
    s = Settings()
    hours = max(1, min(hours, 24 * 7))
    bucket_min = max(5, min(bucket_min, 1440))
    sin_enlace_s = s.sin_enlace_min * 60.0

    buckets = await qh.health_buckets(conn, hours=hours, bucket_min=bucket_min)
    outages = await qh.health_outages(conn, hours=hours, sin_enlace_s=sin_enlace_s)

    expected = (hours * 3600.0) / max(s.fleet_heartbeat_s, 1.0)
    by_gateway: dict[str, GatewayHealthOut] = {}
    for row in buckets:
        m = dict(row._mapping)
        gid = str(m["gateway_id"])
        entry = by_gateway.setdefault(gid, GatewayHealthOut(gateway_id=m["gateway_id"]))
        entry.buckets.append(
            HealthBucket(
                ts=m["bucket"],
                heartbeats=m["heartbeats"],
                mqtt_rtt_p95_ms=m["mqtt_rtt_p95_ms"],
                seedlink_lag_max_s=m["seedlink_lag_max_s"],
                ntp_offset_abs_max_ms=m["ntp_offset_abs_max_ms"],
                battery_min_pct=m["battery_min_pct"],
            )
        )
    for row in outages:
        m = dict(row._mapping)
        gid = str(m["gateway_id"])
        entry = by_gateway.setdefault(gid, GatewayHealthOut(gateway_id=m["gateway_id"]))
        entry.outages = m["outages"]
        entry.downtime_s = m["downtime_s"]
        entry.last_outage_end = m["last_outage_end"]

    for entry in by_gateway.values():
        received = sum(b.heartbeats for b in entry.buckets)
        # Acotado a 1.0: un edge que reintenta puede mandar de más, y "112 % de
        # completitud" no significa nada para quien lo lee.
        entry.heartbeat_completeness = min(received / expected, 1.0) if expected > 0 else None
    return list(by_gateway.values())


@router.get("/fleet/gateways", response_model=list[GatewayOut])
async def list_gateways(
    include_retired: bool = False,
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> list[GatewayOut]:
    """Gateways del tenant con su estado derivado del último ``device_health``.

    [T-2.35] Oculta lo retirado por defecto —el gabinete mismo o su sitio padre—,
    espejando ``GET /sites?include_retired``. Sin este filtro el inventario devolvía
    hardware dado de baja que la consola no tenía forma de quitar de la pantalla.
    """
    s = Settings()
    # Un único umbral de "vivo" para las dos decisiones: qué filas trae la query
    # y cuáles se marcan como fantasma. Calcularlo dos veces sería invitar a que
    # una fila salga del filtro y luego no se rotule, o al revés.
    alive_s = s.sin_enlace_min * 60.0
    rows = await q.list_gateways_with_health(
        conn, include_retired=include_retired, alive_s=alive_s, scope=scope
    )
    # [T-2.69] El registro se lee UNA vez por petición, no una por gabinete: es una
    # tabla de plataforma con decenas de filas y la comparación es en memoria (los
    # SHAs solo admiten igualdad, así que no hay nada que empujar al SQL).
    releases = [ReleaseRef(version=r.version, age_s=r.age_s) for r in await qr.list_releases(conn)]
    out: list[GatewayOut] = []
    for r in rows:
        m = dict(r._mapping)
        state = derive_fleet_state(
            age_s=m["age_s"],
            power_status=m["power_status"],
            battery_pct=m["battery_pct"],
            cert_days_remaining=m["cert_days_remaining"],
            mqtt_rtt_ms=m["mqtt_rtt_ms"],
            seedlink_lag_s=m["seedlink_lag_s"],
            ntp_offset_ms=m["ntp_offset_ms"],
            # [T-2.70.a·B1] Sin esto un gabinete sin dueño de pines sale
            # OPERATIVO: late cada 60 s y todas las demás métricas son perfectas.
            relays_state=m["relays_state"],
            sin_enlace_s=s.sin_enlace_min * 60.0,
            battery_min_pct=s.fleet_battery_min_pct,
            cert_min_days=s.fleet_cert_min_days,
            mqtt_rtt_max_ms=s.fleet_mqtt_rtt_max_ms,
            seedlink_lag_max_s=s.fleet_seedlink_lag_max_s,
            ntp_offset_max_ms=s.fleet_ntp_offset_max_ms,
        )
        # Las razones solo aplican a DEGRADADO: en SIN ENLACE el problema es el
        # silencio, no una métrica; en OPERATIVO son vacías por definición.
        reasons = (
            fleet_degrade_reasons(
                power_status=m["power_status"],
                battery_pct=m["battery_pct"],
                cert_days_remaining=m["cert_days_remaining"],
                mqtt_rtt_ms=m["mqtt_rtt_ms"],
                seedlink_lag_s=m["seedlink_lag_s"],
                ntp_offset_ms=m["ntp_offset_ms"],
                relays_state=m["relays_state"],
                battery_min_pct=s.fleet_battery_min_pct,
                cert_min_days=s.fleet_cert_min_days,
                mqtt_rtt_max_ms=s.fleet_mqtt_rtt_max_ms,
                seedlink_lag_max_s=s.fleet_seedlink_lag_max_s,
                ntp_offset_max_ms=s.fleet_ntp_offset_max_ms,
            )
            if state == DEGRADADO
            else []
        )
        # [T-2.69] Mismo umbral de "vivo" que `derive_fleet_state`, y a propósito:
        # si SIN ENLACE y "la versión ya no es de fiar" divergieran, habría una
        # franja en la que la consola diría "sin enlace" y aun así pintaría la
        # versión como actual.
        drift = derive_version_drift(
            fw_version=m["fw_version"],
            # [T-2.70] Qué EJECUTA el proceso, que no es lo que hay en el disco
            # mientras un despliegue no haya reiniciado de verdad. La deriva se
            # mide contra esto; el desajuste entre ambos ES el estado
            # `SIN REINICIAR`. `None` en gabinetes con contrato ≤1.8.0.
            fw_running=m["fw_running"],
            age_s=m["age_s"],
            sin_enlace_s=alive_s,
            releases=releases,
        )
        out.append(
            GatewayOut(
                gateway_id=m["gateway_id"],
                site_id=m["site_id"],
                site_name=m["site_name"],
                site_code=m["site_code"],
                site_status=m["site_status"],
                serial=m["serial"],
                fw_version=m["fw_version"],
                fw_running=m["fw_running"],
                # [T-2.70.a·B1] Crudo además de la pill: la consola pinta S/D en
                # el grid de actuadores con `stopped` y con `None`, no sólo con
                # el `unreadable` que degrada.
                relays_state=m["relays_state"],
                iot_thing=m["iot_thing"],
                status=m["status"],
                has_wr1=m["has_wr1"],
                equipment=m["equipment"],
                installed_at=m["installed_at"],
                row_version=m["row_version"],
                derived_state=state,
                degrade_reasons=reasons,
                # [T-2.60.a] Retirado —él o su sitio— y sin embargo hablando. Se
                # deriva de `state` y no de `age_s` para que "vivo" tenga UNA sola
                # definición en todo el producto: la frontera de SIN ENLACE.
                #
                # [B3] NO se acota con "…y todavía no lo sabe", como sí se acotó la
                # métrica de CloudWatch. La asimetría es deliberada:
                #
                #  · `is_ghost` es un HECHO —dado de baja y aun así enchufado y
                #    hablando—, no un nivel de urgencia, y ese hecho no cambia
                #    porque al gabinete se le haya publicado su sobre de baja.
                #    Sigue exigiendo una decisión: o se desmonta, o se restaura.
                #  · La métrica se acota porque PAGINA: una alarma encendida para
                #    siempre deja de leerse. La consola no paga ese coste — se mira
                #    cuando hay alguien delante, que es cuando se puede actuar.
                #  · Y tras T-2.65 esta es la ÚLTIMA señal automática que le queda
                #    al retirado que late y ya fue avisado. Apagarla "por
                #    coherencia con la métrica" volvería a esconder un edificio con
                #    hardware vivo, que es exactamente el fallo del 2026-08-04.
                #
                # La cifra agregada que dice este MISMO número —y que por eso no
                # puede divergir— es `ops/metrics.py::count_retired_alive`.
                # Anclado en `tests/api/test_fleet_ghosts.py`.
                is_ghost=(m["status"] == "retired" or m["site_status"] == "retired")
                and state != SIN_ENLACE,
                retired_at=m["retired_at"],
                retired_by=m["retired_by"],
                last_heartbeat_ts=m["health_ts"],
                power_status=m["power_status"],
                battery_pct=m["battery_pct"],
                cert_days_remaining=m["cert_days_remaining"],
                mqtt_rtt_ms=m["mqtt_rtt_ms"],
                seedlink_lag_s=m["seedlink_lag_s"],
                ntp_offset_ms=m["ntp_offset_ms"],
                version_state=drift.state,
                releases_behind=drift.releases_behind,
                release_age_s=drift.release_age_s,
                # La versión cabalga en CADA latido, así que su dato es tan viejo
                # como el último latido… pero solo cuando HAY versión. Sin versión
                # no hay nada que fechar y esto vale None (la consola pinta S/D en
                # vez de una antigüedad de un dato inexistente).
                version_age_s=None if m["fw_version"] is None else m["age_s"],
            )
        )
    return out


# --- Registro de releases de firmware (T-2.69) -------------------------------
#
# El registro es DE PLATAFORMA, no de tenant: qué firmware existe lo decide TAKAB,
# no el cliente. Por eso lo lee cualquier rol con /fleet (necesita el registro para
# que su propia deriva signifique algo) y lo escribe SOLO el superadmin.
#
# La escritura NO tiene acción de matriz propia, a diferencia de `manage_fleet` o
# `manage_tenants`, y es deliberado: la matriz existe para no pintar botones que
# darían 403 (regla de oro 7), y aquí no hay botón — publicar un release es una
# superficie de herramienta/CI (el despliegue lo hará T-2.70), no de consola. Si
# algún día la consola publica releases, entonces sí hará falta la acción.
_PUBLISH_RELEASE_ROLES: tuple[str, ...] = ("takab_superadmin",)
_require_publish_release = require_roles(*_PUBLISH_RELEASE_ROLES)


@router.get("/fleet/releases", response_model=list[ReleaseOut])
async def list_releases(
    conn: AsyncConnection = Depends(read_session),
) -> list[ReleaseOut]:
    """Releases publicados, MÁS NUEVO PRIMERO.

    Es la referencia contra la que ``GET /fleet/gateways`` deriva ``version_state``
    y ``releases_behind``. Vacío es un estado legítimo —una plataforma que aún no
    ha publicado nada— y la flota entera sale ``SIN REFERENCIA``: se sabe qué corre
    cada gabinete, no si eso es lo actual.
    """
    return [ReleaseOut(**dict(r._mapping)) for r in await qr.list_releases(conn)]


@router.post("/fleet/releases", response_model=ReleaseOut, status_code=201)
async def publish_release(
    body: ReleaseCreate,
    claims: Claims = Depends(_require_publish_release),
    conn: AsyncConnection = Depends(read_session),
) -> ReleaseOut:
    """Registra un release de firmware. Solo el dueño de la plataforma.

    ``version`` debe ser el valor EXACTO que ``deploy/edge/deploy.sh`` escribirá en
    el ``FW_VERSION`` del gabinete: la comparación con lo que declara el aparato es
    por IGUALDAD, así que un espacio de más aquí volvería ``DESCONOCIDA`` a toda la
    flota que corra ese código.

    Republicar la misma versión da 409: la tabla no admite UPDATE (append-only por
    privilegio) porque reescribir la fecha de un release reescribiría a posteriori
    la deriva de toda la flota.
    """
    try:
        row = await qr.insert_release(
            conn,
            version=body.version,
            released_at=body.released_at,
            notes=body.notes,
            published_by=f"user:{claims.sub}",
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=None,
        actor=f"user:{claims.sub}",
        verb="fw_release_publish",
        obj=f"fw_release:{body.version}",
        meta={"version": body.version},
    )
    return ReleaseOut(**dict(row._mapping))


# --- Administración del inventario (T-1.32) ----------------------------------


@router.post("/fleet/gateways", response_model=GatewayRowOut, status_code=201)
async def create_gateway(
    body: GatewayCreate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Da de alta un gabinete en ``provisioned``. Cero llamadas a AWS.

    ``serial`` e ``iot_thing`` son únicos GLOBALES (no por tenant): un serial repetido
    devuelve 409. Sin ``iot_thing`` el gabinete no es sincronizable y la consola lo
    muestra como PENDIENTE DE APROVISIONAR — que es la verdad hasta que Terraform emita
    su certificado.
    """
    tenant_id = await tenant_of_parent_site(conn, claims, body.site_id)
    values = _write_values(body)
    try:
        row = await q.insert_gateway(conn, tenant_id=tenant_id, values=values)
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_create",
        obj=f"gateway:{row.gateway_id}",
        meta={"serial": body.serial, "site_id": str(body.site_id)},
    )
    return _row_out(row)


@router.put("/fleet/gateways/{gateway_id}", response_model=GatewayRowOut)
async def update_gateway(
    gateway_id: UUID,
    body: GatewayUpdate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Reemplaza el gabinete. ``base_row_version`` viejo ⇒ 409.

    El sitio destino debe ser del mismo tenant que el gabinete: mudarlo a un sitio ajeno
    haría que su telemetría (y sus actuadores) quedaran bajo otro tenant.
    """
    current = await q.get_gateway_row(conn, gateway_id)
    if current is None:
        raise http_error(404, "gateway no encontrado")

    site_tenant = await tenant_of_parent_site(conn, claims, body.site_id)
    if site_tenant != str(current.tenant_id):
        raise http_error(403, "el sitio destino pertenece a otro tenant")

    values = _write_values(body)
    try:
        row = await q.update_gateway(
            conn, gateway_id=gateway_id, values=values, base_row_version=body.base_row_version
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    if row is None:
        raise http_error(409, "el gateway cambió en el servidor; recarga y reintenta")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_update",
        obj=f"gateway:{gateway_id}",
        meta={"serial": body.serial, "site_id": str(body.site_id)},
    )
    return _row_out(row)


@router.post("/fleet/gateways/{gateway_id}/retire", response_model=GatewayRowOut)
async def retire_gateway(
    gateway_id: UUID,
    body: GatewayRetire,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Retiro lógico (idempotente) con DOBLE FRICCIÓN (T-2.36).

    Retirar un gabinete lo saca de los comandos de actuación de la nube y, tras
    entregarle un último sobre firmado que se lo DICE, del config sync.

    **El edificio NO deja de estar protegido** (T-2.65, opción A ratificada el
    2026-08-05): el gabinete sigue leyendo el sensor y el reflejo SASMEX→sirena
    sigue actuando, porque ese camino no depende de la nube ni puede hacerlo
    (reglas de oro 1 y 2). Que un clic de inventario apagara la protección física
    de un edificio con gente dentro sería el fallo, no la función. Lo que cambia
    es que ahora el gabinete lo declara en su panel local en vez de quedar
    latiendo invisible, que es lo que pasó con `gw-dev-0001` el 2026-08-04.

    Exige, además de ``manage_fleet``, teclear el ``serial`` exacto (visible en
    pantalla) y el código de retiro del cliente (secreto que entrega TAKAB).

    Es ``POST`` y no ``DELETE`` porque ahora lleva cuerpo, y un ``DELETE`` con cuerpo
    no atraviesa proxies de forma fiable. Espeja el ``POST …/restore`` ya existente.
    """
    current = await q.get_gateway_row(conn, gateway_id)
    if current is None:
        raise http_error(404, "gateway no encontrado")

    # El serial primero: está en pantalla, no es secreto, y un dedazo no debe
    # consumir un intento del código.
    check_confirmation(typed=body.confirm_serial, expected=current.serial, label="serial")
    await require_retire_code(
        conn,
        claims,
        tenant_id=str(current.tenant_id),
        code=body.retire_code,
        obj=f"gateway:{gateway_id}",
    )

    row = await q.set_gateway_status(conn, gateway_id, "retired")
    if row is None:
        raise http_error(403, "sin permiso para retirar este gateway")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_retire",
        obj=f"gateway:{gateway_id}",
        meta={"serial": row.serial},
    )
    return _row_out(row)


@router.post("/fleet/gateways/{gateway_id}/restore", response_model=GatewayRowOut)
async def restore_gateway(
    gateway_id: UUID,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Deshace un retiro: vuelve a ``provisioned``, NO a ``online``.

    El estado vivo lo demuestra el siguiente heartbeat; la API no puede afirmarlo.
    """
    if await q.get_gateway_row(conn, gateway_id) is None:
        raise http_error(404, "gateway no encontrado")
    row = await q.set_gateway_status(conn, gateway_id, "provisioned")
    if row is None:
        raise http_error(403, "sin permiso para restaurar este gateway")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_restore",
        obj=f"gateway:{gateway_id}",
        meta={"serial": row.serial},
    )
    return _row_out(row)
