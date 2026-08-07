"""T-2.71 · `/maintenance-windows`: silenciar alarmas de OPERACIÓN, jamás la actuación.

Esta es la superficie más sensible que el proyecto ha abierto después de la de
actuadores, y por una razón que conviene dejar escrita: **abrir una ventana no
mueve un relé, pero apaga la vigilancia de un edificio**. La regla de oro 8 exige
comando firmado + MFA + nonce + ack para tocar un actuador desde la nube; aquí no
hay actuador, pero sí hay un correo de on-call que deja de llegar.

Cinco cosas que este router hace, y que no son opcionales:

1. **Deriva los nombres de alarma; nunca los acepta.** La frontera multi-tenant
   de esta superficie NO es un check de permisos: es el ORIGEN de la lista. Las
   alarmas de CloudWatch se identifican por nombre y no llevan dimensión de
   tenant, así que aceptarlos del body convertiría esto en un silenciador
   universal — incluidas las tres que ``ops/muting.ALARM_CATALOG`` declara
   intocables. ``MaintenanceWindowIn`` es ``extra="forbid"`` y la derivación sale
   de un ``SELECT`` que ya pasó por RLS.

2. **Archiva la ventana bajo el DUEÑO de lo intervenido, no bajo quien
   interviene.** Es la regla de oro 5 y llegó a estar rota: la fila guardaba el
   ``tenant_id`` del OPERADOR, así que el dueño del edificio cuyas alarmas
   quedaban mudas no la veía —y un tenant ajeno sí, y podía cerrarla—. El matiz
   que impide arreglarlo prohibiendo el cruce es que un ``takab_support`` o un
   ``takab_superadmin`` intervienen gabinetes ajenos LEGÍTIMAMENTE: lo que hay
   que separar no es el permiso, es el dueño del registro. Ver ``_derive_names``.
   Y ojo con confiar en la RLS para esto: ``gateways_read`` incluye
   ``app_can_view_meta``, o sea que un grant de metadatos deja VER inventario
   ajeno — leerlo es el permiso concedido, callar sus alarmas no.

3. **Acusa recibo, y distingue medido de supuesto.** ``PutAlarmMuteRule``
   devolviendo 200 NO es "las alarmas están silenciadas": el nombre puede no
   existir (prefijo de env distinto, ``iot_thing`` NULL, gabinete fuera de
   ``paged_gateways``). Se relee la regla y se contrasta contra
   ``describe_alarms``; lo que sale es ``N/M``, no un "ok". Y si esa
   comprobación no se pudo hacer, ``mute_verified`` lo marca en vez de dar la
   cifra por buena.

4. **Un éxito parcial no se reporta como fracaso total.** Si AWS falla DESPUÉS
   del ``PutAlarmMuteRule``, las alarmas están mudas: declarar ``0/N`` con
   ``mute_rule = NULL`` afirmaría que la vigilancia sigue viva con la vigilancia
   apagada, y dejaría el botón REABRIR sin nada que borrar durante hasta 4 h. Y
   si lo que falla es la escritura de la FILA, el silencio se DESHACE: alarmas
   mudas sin registro es peor que una ventana que no se pudo abrir. El único
   ``0/N`` que se declara es el MEDIDO: sin cliente, o cuando se sabe que la
   petición no silenció nada (AWS contestó 4xx, o ni llegó a salir de la
   máquina — ``ops/muting.no_se_silencio_nada``).

4b. **Y cerrar es la misma afirmación al revés.** ``closed_at`` dice "la
   vigilancia volvió" y quita la ventana de pantalla; si el ``DeleteAlarmMuteRule``
   no salió bien, no volvió. El cierre solo se declara cuando el silencio se
   deshizo de verdad, o cuando la ventana ya había vencido sola (ahí no queda
   nada que deshacer). Ver ``close_window`` y ``_reabrir_o_fallar``.

5. **La actuación no se entera de nada.** Una ventana es un concepto de NUBE:
   no viaja en el sobre de config al edge, no toca ``EdgeSettings`` y por tanto
   no puede alcanzar ``GpioController._desired_energized()``. Está medido con
   relés en ``edge/tests/test_supervisor.py``, no afirmado aquí.

Lo que este router deliberadamente NO tiene: ventanas recurrentes (una mute rule
con ``cron(...)`` y sin ``expire_date`` no vence jamás) y worker de cierre (la
pregunta "¿y si el job muere?" se contesta borrando el job: ``active`` es un
predicado SQL y ``Duration`` la expira AWS).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.ops.muting import (
    MuteAck,
    MuteClient,
    apply_mute,
    delete_mute,
    mute_names_for_gateways,
    mute_names_for_platform,
    mute_start,
)
from takab_api.routers._common import INTERNAL_ROLES, http_error
from takab_api.schemas.maintenance import (
    MaintenanceWindowIn,
    MaintenanceWindowList,
    MaintenanceWindowOut,
)
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.maintenance")

router = APIRouter(prefix="/maintenance-windows", tags=["maintenance"])

WINDOW_ROLES: tuple[str, ...] = roles_with_action("maintenance_window")
PLATFORM_WINDOW_ROLES: tuple[str, ...] = roles_with_action("platform_maintenance_window")

# La ruta admite a cualquiera que pueda abrir ALGUNA ventana; el alcance
# (gabinete vs plataforma) se decide dentro, contra la acción concreta. Así el
# 403 de "no puedes callar las alarmas de la plataforma" es distinguible del de
# "no puedes abrir ventanas", que es información que el operador necesita.
_require_window = require_roles(*sorted({*WINDOW_ROLES, *PLATFORM_WINDOW_ROLES}))
# Leer QUÉ está silenciado no es apagar nada: lo puede ver cualquiera que llegue
# a la consola. Es justo lo contrario de un secreto — una ventana invisible es
# el modo de fallo que el criterio 2 existe para evitar.
_require_read = require_roles(
    *sorted({*WINDOW_ROLES, *PLATFORM_WINDOW_ROLES, "soc_operator", "takab_support"})
)

# `active` DERIVADO: sin cierre manual y dentro de la ventana (sin worker de
# cierre — calcado de `drills`, api/src/takab_api/routers/drills.py).
_ACTIVE = "(w.closed_at IS NULL AND now() < w.starts_at + make_interval(secs => w.duration_s))"

_COLS = (
    "w.window_id, w.tenant_id, w.gateway_id, w.scope, w.opened_by, w.reason, "
    "w.duration_s, w.opened_at, w.starts_at, w.closed_at, w.alarm_names, w.missing_names, "
    "w.requested, w.silenced, w.mute_rule, w.mute_verified, "
    "w.starts_at + make_interval(secs => w.duration_s) AS ends_at, "
    f"{_ACTIVE} AS active, "
    "g.serial AS gateway_serial, s.name AS site_name"
)

_FROM = (
    "FROM maintenance_windows w "
    "LEFT JOIN gateways g ON g.gateway_id = w.gateway_id "
    "LEFT JOIN sites s    ON s.site_id    = g.site_id"
)

_SELECT_ALL = text(
    f"SELECT {_COLS} {_FROM} ORDER BY w.starts_at DESC, w.window_id DESC LIMIT :limit"
)

_SELECT_ACTIVE = text(
    f"SELECT {_COLS} {_FROM} WHERE {_ACTIVE} "
    "ORDER BY w.starts_at DESC, w.window_id DESC LIMIT :limit"
)

_SELECT_ONE = text(f"SELECT {_COLS} {_FROM} WHERE w.window_id = CAST(:w AS uuid)")

# El gabinete que el llamante VE (la RLS acota la tabla): de aquí sale el
# `iot_thing` del que se derivan los nombres de alarma **y el `tenant_id` que
# archiva la ventana**. Ver `_derive_names`: VER un gabinete y poder callar sus
# alarmas no son el mismo permiso, así que su dueño se lee, no se supone.
_SELECT_GATEWAY = text(
    "SELECT g.gateway_id, g.tenant_id, g.iot_thing FROM gateways g "
    "WHERE g.gateway_id = CAST(:g AS uuid)"
)

_INSERT = text(
    "INSERT INTO maintenance_windows (tenant_id, gateway_id, scope, opened_by, reason, "
    "duration_s, starts_at, alarm_names, requested, silenced, mute_rule) "
    "VALUES (CAST(:tenant AS uuid), CAST(:gateway AS uuid), :scope, CAST(:user AS uuid), "
    ":reason, :duration, :starts, :names, :requested, :silenced, :rule) "
    "RETURNING window_id"
)

# Se escribe DESPUÉS de hablar con AWS, porque hasta entonces no se sabe qué se
# silenció. Es constante de módulo (y no SQL inline) para que un test pueda
# romperlo a propósito: si esta escritura falla, la transacción se lleva por
# delante la fila y hay que DESHACER el silencio ya aplicado — ver `open_window`.
_UPDATE_ACK = text(
    "UPDATE maintenance_windows SET silenced = :s, mute_rule = :r, missing_names = :m, "
    "mute_verified = :v WHERE window_id = CAST(:w AS uuid)"
)

# El doble guardia `closed_at IS NULL` es lo que hace idempotente al cierre: la
# segunda llamada no devuelve fila y el router responde 409 en vez de reescribir
# la hora del primero (el registro de cuándo se reabrió la vigilancia no se pisa).
#
# `seguia_activa` se lee EN LA MISMA sentencia que cierra, no después: dice si la
# mute rule podía seguir callando algo en el instante del cierre, y de eso depende
# si "cerrada" es una afirmación sobre el presente o pura contabilidad de algo que
# ya venció (ver `close_window`).
_CLOSE = text(
    "UPDATE maintenance_windows SET closed_at = now() "
    "WHERE window_id = CAST(:w AS uuid) AND closed_at IS NULL "
    "RETURNING window_id, tenant_id, mute_rule, "
    "(now() < starts_at + make_interval(secs => duration_s)) AS seguia_activa"
)


@lru_cache(maxsize=1)
def _cloudwatch() -> MuteClient | None:
    """Cliente de CloudWatch, o ``None`` si no hay AWS (local/tests).

    ``None`` NO es un fallo silencioso: la ventana se crea igual —el registro
    vale— pero declara ``0`` silenciadas, que es la verdad. Fingir el silencio
    sería exactamente el fallo que esta tarea existe para no cometer.
    """
    settings = Settings()
    if not settings.ops_muting_enabled:
        return None
    try:  # pragma: no cover - depende de boto3 + credenciales reales
        import boto3

        return boto3.client("cloudwatch", region_name=settings.aws_region)
    except Exception:
        logger.warning("sin cliente de CloudWatch: las ventanas no silenciarán", exc_info=True)
        return None


def get_mute_client() -> MuteClient | None:
    """Seam de inyección (los tests lo sobrescriben con un doble)."""
    return _cloudwatch()


def _out(row: Any) -> MaintenanceWindowOut:
    """Fila → modelo. ``missing_names`` sale de la COLUMNA, nunca de la cifra.

    Reconstruirlos a partir de ``requested - silenced`` (cogiendo N nombres de
    la lista) daría un dato inventado con cara de medido: qué alarma concreta no
    quedó muda solo se sabe en el instante de aplicar, y por eso se guarda.
    """
    datos = dict(row)
    datos["alarm_names"] = list(datos.get("alarm_names") or [])
    datos["missing_names"] = list(datos.get("missing_names") or [])
    return MaintenanceWindowOut(**datos)


@dataclass(frozen=True)
class _Objetivo:
    """Sobre QUÉ se abre la ventana, y de QUIÉN es.

    ``owner_tenant_id`` no es el tenant de quien pide: es el del gabinete
    intervenido, leído de su fila. Son sus alarmas las que se quedan mudas, así
    que es SUYA la ventana (regla de oro 5) — aunque quien la abra sea un
    ``takab_superadmin`` de plataforma, que interviene inventario ajeno
    legítimamente. Una ventana de PLATAFORMA no tiene dueño de cliente: los dos
    campos van a ``None`` (lo exige ``mw_scope_coherente``).
    """

    alarm_names: tuple[str, ...]
    gateway_id: UUID | None
    owner_tenant_id: str | None


async def _derive_names(
    body: MaintenanceWindowIn, claims: Claims, conn: AsyncConnection, *, env: str
) -> _Objetivo:
    """Los nombres de alarma y el DUEÑO de lo intervenido, leídos de la DB."""
    if body.scope == "platform":
        if claims.role not in PLATFORM_WINDOW_ROLES:
            raise http_error(
                403,
                "las alarmas de plataforma (ec2_*) vigilan la infraestructura común de "
                "todos los clientes: solo el dueño de la plataforma puede callarlas",
            )
        return _Objetivo(mute_names_for_platform(env=env), None, None)

    if claims.role not in WINDOW_ROLES:
        raise http_error(403, "sin permiso para abrir ventanas de mantenimiento")
    if body.gateway_id is None:
        raise http_error(422, "una ventana de gabinete exige gateway_id")
    fila = (
        (await conn.execute(_SELECT_GATEWAY, {"g": str(body.gateway_id)})).mappings().one_or_none()
    )
    if fila is None:
        # 404 y no 403: la RLS ya lo escondió, y confirmar la existencia de
        # inventario ajeno sería filtrar el hecho de que existe.
        raise http_error(404, "gabinete no encontrado")

    dueno = str(fila["tenant_id"])
    # VER un gabinete ajeno y poder CALLAR sus alarmas no son el mismo permiso, y
    # la RLS sola nunca separó las dos cosas: `gateways_read` incluye
    # `app_can_view_meta`, así que un grant de METADATOS (T-1.73) hace que este
    # SELECT devuelva el gabinete del vecino. Leer su inventario es lo concedido;
    # apagar su vigilancia es un acto sobre el edificio de otro. Solo un rol
    # interno (`takab_*`) interviene fuera de su tenant, y aun así la ventana se
    # archiva a nombre del dueño, no del suyo.
    if dueno != claims.tenant_id and claims.role not in INTERNAL_ROLES:
        raise http_error(404, "gabinete no encontrado")
    return _Objetivo(
        mute_names_for_gateways(env=env, things=[fila["iot_thing"]]), body.gateway_id, dueno
    )


@router.post("", response_model=MaintenanceWindowOut, status_code=201)
async def open_window(
    body: MaintenanceWindowIn,
    claims: Claims = Depends(_require_window),
    conn: AsyncConnection = Depends(get_session),
    client: MuteClient | None = Depends(get_mute_client),
) -> MaintenanceWindowOut:
    settings = Settings()
    env = settings.ops_alarm_prefix
    objetivo = await _derive_names(body, claims, conn, env=env)
    nombres, gateway_id = objetivo.alarm_names, objetivo.gateway_id

    starts = mute_start(datetime.now(tz=UTC))
    # El id de la regla se fija ANTES de insertar para que el nombre en AWS y la
    # fila sean el mismo objeto: sin eso, una regla huérfana en CloudWatch no
    # tendría a quién reclamarle.
    window_id = (
        (
            await conn.execute(
                _INSERT,
                {
                    # El DUEÑO de lo intervenido, no quien interviene (regla de
                    # oro 5): son las alarmas de ESE edificio las que se callan,
                    # y su dueño tiene que verlo en pantalla mientras dure.
                    "tenant": objetivo.owner_tenant_id,
                    "gateway": str(gateway_id) if gateway_id else None,
                    "scope": body.scope,
                    "user": claims.sub,
                    "reason": body.reason,
                    "duration": body.duration_s,
                    "starts": starts,
                    "names": list(nombres),
                    "requested": len(nombres),
                    "silenced": 0,
                    "rule": None,
                },
            )
        )
        .mappings()
        .one()
    )["window_id"]

    ack = _silence(
        client,
        rule_name=f"{env}-mw-{window_id}",
        names=nombres,
        duration_s=body.duration_s,
        starts_at=starts,
        env=env,
    )
    try:
        await conn.execute(
            _UPDATE_ACK,
            {
                "s": ack.silenced,
                "r": ack.rule_name,
                "m": list(ack.missing_names),
                "v": ack.verified,
                "w": str(window_id),
            },
        )
        await audit_async(
            conn,
            tenant_id=objetivo.owner_tenant_id,
            actor=f"user:{claims.sub}",
            verb="maintenance_window_open",
            obj=f"maintenance_window:{window_id}",
            meta={
                "scope": body.scope,
                "gateway_id": str(gateway_id) if gateway_id else None,
                # Quién OPERA, separado de a quién PERTENECE (la fila `tenant_id`).
                # Un `takab_*` interviene inventario ajeno legítimamente y el rastro
                # tiene que poder contar las dos cosas sin confundirlas.
                "operator_tenant_id": claims.tenant_id,
                "operator_role": claims.role,
                "reason": body.reason,
                "duration_s": body.duration_s,
                "starts_at": starts.isoformat(),
                "alarm_names": list(nombres),
                "requested": ack.requested,
                "silenced": ack.silenced,
                "missing": ack.missing,
                "mute_verified": ack.verified,
            },
        )
    except Exception:
        # Si no se puede dejar CONSTANCIA del silencio, no puede quedar silencio:
        # la transacción se revierte y la fila desaparece, así que unas alarmas
        # mudas sobrevivirían sin registro, sin dueño y sin nadie que sepa el
        # nombre de la regla. Deshacer es la única salida honesta.
        _unsilence(client, ack.rule_name)
        raise
    fila = (await conn.execute(_SELECT_ONE, {"w": str(window_id)})).mappings().one()
    return _out(fila)


def _silence(
    client: MuteClient | None,
    *,
    rule_name: str,
    names: tuple[str, ...],
    duration_s: int,
    starts_at: datetime,
    env: str,
) -> MuteAck:
    """Aplica el silencio, o declara honestamente que no silenció nada.

    Un fallo de CloudWatch NO tumba la apertura: la fila y su rastro en la
    bitácora valen igual. Lo que cambia es QUÉ se declara, y aquí solo se llega
    a ``0/N`` cuando eso está MEDIDO:

    - sin cliente (``ops_muting`` apagado, sin boto3) no se llamó a nadie ⇒ las
      alarmas suenan, y la fila lo dice;
    - ``apply_mute`` solo levanta cuando AWS **contestó rechazando** (4xx): la
      regla no existe ⇒ las alarmas suenan, y la fila lo dice;
    - cualquier otro fallo NO llega hasta aquí. ``apply_mute`` lo resuelve
      dentro asumiendo silencio y conservando el nombre de la regla, porque un
      éxito parcial reportado como fracaso total deja el sistema callado y sin
      marcha atrás. Ver ``ops/muting.apply_mute``.
    """
    if client is None or not names:
        return MuteAck(requested=len(names), silenced=0, missing_names=tuple(names), rule_name=None)
    try:
        return apply_mute(
            client,
            rule_name=rule_name,
            alarm_names=names,
            duration_s=duration_s,
            starts_at=starts_at,
            env=env,
        )
    except Exception:
        logger.warning(
            "AWS rechazó la mute rule %s: las alarmas SIGUEN sonando",
            rule_name,
            exc_info=True,
        )
        return MuteAck(requested=len(names), silenced=0, missing_names=tuple(names), rule_name=None)


def _unsilence(client: MuteClient | None, rule_name: str | None) -> None:
    """Deshace un silencio que no se pudo registrar. No propaga: ya se propaga otro.

    Si además falla el borrado, lo peor está acotado por la ``Duration`` de la
    propia regla —como mucho ``MAX_WINDOW_S``— pero el log tiene que llevar el
    nombre: es lo único que quedará para borrarla a mano.
    """
    if client is None or not rule_name:
        return
    try:
        delete_mute(client, rule_name=rule_name)
    except Exception:
        logger.error(
            "quedó la mute rule %s en AWS SIN fila que la registre y no se pudo borrar: "
            "hay alarmas mudas sin dueño hasta que expire su Duration",
            rule_name,
            exc_info=True,
        )


def _reabrir_o_fallar(client: MuteClient | None, rule_name: str) -> None:
    """Desilencia de verdad, o impide que el cierre se declare. Nunca traga.

    Es el gemelo de ``_unsilence`` con el signo cambiado, y la diferencia es toda
    la tarea: allí ya se propaga otro error y el silencio sobrante es lo que se
    intenta limpiar; aquí **el fallo es el hecho principal**. Tragárselo escribe
    en pantalla que la vigilancia volvió cuando no volvió, que es exactamente la
    familia de mentira que T-2.71 existe para no cometer.

    Al levantar, la transacción del request se revierte y ``closed_at`` vuelve a
    ``NULL``: la ventana sigue visible, activa y con su ``mute_rule``, o sea con
    todo lo necesario para reintentar. El log lleva el nombre de la regla porque
    si AWS no vuelve, es lo único que queda para borrarla a mano.
    """
    if client is None:
        # Único camino: la ventana se abrió con `ops_muting` encendido y se cierra
        # con él apagado. Sin cliente no hay forma de desilenciar NI de comprobarlo.
        logger.error(
            "cierre de ventana sin cliente de CloudWatch: la mute rule %s sigue viva y no "
            "hay con qué borrarla; las alarmas seguirán mudas hasta que expire su Duration",
            rule_name,
        )
        raise http_error(
            503,
            "no hay cliente de CloudWatch con el que desilenciar: la ventana NO se cerró "
            "porque las alarmas siguen mudas hasta que expire su Duration",
        )
    try:
        delete_mute(client, rule_name=rule_name)
    except Exception as exc:
        logger.error(
            "no se pudo borrar la mute rule %s: la ventana NO se cierra, porque cerrarla "
            "diría que la vigilancia volvió con las alarmas todavía mudas",
            rule_name,
            exc_info=True,
        )
        raise http_error(
            502,
            "AWS no confirmó el desilenciado: la ventana sigue ABIERTA a propósito. "
            "Reintenta REABRIR VIGILANCIA (el borrado es idempotente); si AWS no "
            "responde, el silencio expira solo al terminar la ventana.",
        ) from exc


@router.get("", response_model=MaintenanceWindowList)
async def list_windows(
    active: bool = True,
    limit: int = 50,
    claims: Claims = Depends(_require_read),
    conn: AsyncConnection = Depends(get_session),
) -> MaintenanceWindowList:
    """Ventanas visibles para el llamante (la RLS acota; plataforma solo interno)."""
    sql = _SELECT_ACTIVE if active else _SELECT_ALL
    filas = (await conn.execute(sql, {"limit": max(1, min(limit, 200))})).mappings().all()
    return MaintenanceWindowList(items=[_out(f) for f in filas])


@router.post("/{window_id}/close", response_model=MaintenanceWindowOut)
async def close_window(
    window_id: UUID,
    claims: Claims = Depends(_require_window),
    conn: AsyncConnection = Depends(get_session),
    client: MuteClient | None = Depends(get_mute_client),
) -> MaintenanceWindowOut:
    """Cierre ANTICIPADO: reabre la vigilancia, y es la ÚNICA vía que lo garantiza.

    ``DeleteAlarmMuteRule`` desilencia en el acto y, si alguna alarma quedó en
    ALARM, sus acciones disparan — literal en el modelo de servicio del CLI
    (``ops/muting.CLI_SERVICE_MODEL``). Lo que **no** dice ninguna documentación
    legible offline es que eso pase cuando la ventana expira sola, así que cerrar
    a mano no es solo cortesía: es el camino con re-disparo documentado.

    Quién puede cerrar lo decide la RLS sobre ``tenant_id``, que desde el arreglo
    de la fuga es el del gabinete INTERVENIDO: el dueño del edificio recupera su
    vigilancia, y el tenant de quien operó no puede tocarla.

    **Cerrar es una AFIRMACIÓN, no un botón.** Dice "la vigilancia volvió", y la
    fila deja de salir en pantalla. Este cierre llegó a hacer lo simétrico del
    bloqueante de la apertura: cerraba la fila y luego intentaba el borrado dentro
    de un ``try`` que solo dejaba un ``warning``, así que la ventana DESAPARECÍA de
    la consola con las alarmas todavía mudas hasta que expirase la ``Duration`` —
    hasta 4 h de edificio sin vigilancia y sin nada en pantalla que lo dijera.

    Ahora solo se cierra si la afirmación es cierta, con el mismo criterio que la
    apertura (ante la duda, el estado más PELIGROSO: sigue muda):

    - el borrado salió bien ⇒ desilenciado, se cierra;
    - el borrado falló, o no hay cliente con el que hacerlo, y la ventana **seguía
      activa** ⇒ 5xx y la transacción se revierte: la fila sigue abierta, con su
      ``mute_rule``, y REABRIR VIGILANCIA se puede reintentar (``DeleteAlarmMuteRule``
      es idempotente);
    - la ventana **ya había vencido** ⇒ se cierra igual. Vencida la fila, vencida
      la regla: la ``Duration`` de AWS y el ``ends_at`` cuentan desde el mismo borde
      (``mute_start``), así que ahí no queda nada que desilenciar y el cierre es
      contabilidad, no una afirmación sobre el presente. Sin esta salida, un
      registro abierto con AWS caído no se podría cerrar nunca.
    """
    fila = (await conn.execute(_CLOSE, {"w": str(window_id)})).mappings().one_or_none()
    if fila is None:
        # No distingue "no existe" de "ya cerrada" a propósito: la RLS ya decidió
        # la visibilidad, y un 404/409 diferenciado revelaría inventario ajeno.
        raise http_error(409, "la ventana no existe o ya estaba cerrada")
    if fila["mute_rule"] and fila["seguia_activa"]:
        _reabrir_o_fallar(client, str(fila["mute_rule"]))
    await audit_async(
        conn,
        # Del DUEÑO de la ventana, no de quien la cierra: el rastro de "durante
        # estas horas tu edificio estuvo sin vigilancia" tiene que quedar donde el
        # afectado pueda leerlo (misma razón que en la apertura).
        tenant_id=str(fila["tenant_id"]) if fila["tenant_id"] else None,
        actor=f"user:{claims.sub}",
        verb="maintenance_window_close",
        obj=f"maintenance_window:{window_id}",
        meta={
            "mute_rule": fila["mute_rule"],
            "operator_tenant_id": claims.tenant_id,
            "operator_role": claims.role,
        },
    )
    return _out((await conn.execute(_SELECT_ONE, {"w": str(window_id)})).mappings().one())
