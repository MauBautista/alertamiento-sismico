"""[T-9.04] El reingreso PERSISTENTE, contra el endpoint que lee la app.

Tres defectos medidos en `GET /sites/{id}/mobile-state`:

1. **Un NO HABITAR firmado caducaba solo.** Firmar cierra el incidente
   (`incident/lifecycle.py`, vía `dictamen_signed`, `D-33`: tres segundos) y la
   rama de cerrados sólo re-declaraba dictámenes HABITABLES. La app volvía a
   `idle` con el edificio DESBLOQUEADO sin que nadie firmara nada.
2. **«REINGRESO AUTORIZADO» en reposo por incidentes que nunca ordenaron
   evacuar.** La consulta de cerrados no miraba `autoriza_evacuacion` (T-2.105),
   y contaba las 8 h desde el CIERRE, no desde la FIRMA.
3. **Un incidente local nuevo tapaba a uno autorizante más viejo**: la consulta
   de abiertos era `LIMIT 1` el más nuevo, y el filtro de T-2.105 se aplicaba
   DESPUÉS — el SASMEX abierto desaparecía detrás de un camión.

Las reglas puras viven en `takab_api/reingreso.py` (tests en
`tests/test_reingreso.py`); aquí se comprueba que el endpoint las aplica con los
datos de verdad: incidente, cadena de dictámenes y clasificación vigente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app

ZONE = "7d000000-0000-0000-0000-0000000009a4"
OCC = "70000000-0000-0000-0000-0000000094a1"
INSPECTOR = "70000000-0000-0000-0000-0000000094b1"
URL = f"/sites/{au.DB_SITE_PRIV}/mobile-state"


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _occ() -> dict[str, str]:
    return au.bearer(au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC))


def _inspector() -> dict[str, str]:
    return au.bearer(
        au.make_token("inspector", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=INSPECTOR)
    )


async def _enrolar(client) -> None:
    engine = get_engine()
    params = {"zone": ZONE, "tenant": au.DB_TENANT_PRIV, "site": au.DB_SITE_PRIV}
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:zone, :tenant, :site, 'P4-A', 'P4', 'evacuate') "
                "ON CONFLICT (zone_id) DO NOTHING"
            ),
            params,
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES ('CODE-T904', :tenant, :site, :zone, true)"
            ),
            params,
        )
    resp = await client.post("/me/enrollment", json={"code": "CODE-T904"}, headers=_occ())
    assert resp.status_code == 200, resp.text


async def _dictamen(incident_id: str, status: str, *, firmado: bool, hace: timedelta) -> None:
    """Una fila de la cadena con su `created_at` — que ES la hora de la firma."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
                "created_at) VALUES (:t, :i, :st, '{}'::jsonb, :by, :at)"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "i": incident_id,
                "st": status,
                "by": str(uuid.uuid4()) if firmado else None,
                "at": datetime.now(UTC) - hace,
            },
        )


async def _cerrar(incident_id: str, *, hace: timedelta) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE incidents SET state = 'closed', closed_at = :at WHERE incident_id = :i"),
            {"i": incident_id, "at": datetime.now(UTC) - hace},
        )


async def _clasificar(incident_id: str, clasificacion: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incident_classifications "
                "(tenant_id, incident_id, classification, classified_by) "
                "VALUES (:t, :i, :c, :by)"
            ),
            {"t": au.DB_TENANT_PRIV, "i": incident_id, "c": clasificacion, "by": INSPECTOR},
        )


async def _tier(new_tier: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, "
                "prev_tier, new_tier) VALUES (now(), :t, :s, gen_random_uuid(), 'normal', :n)"
            ),
            {"t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "n": new_tier},
        )


async def _estado(client) -> dict:
    resp = await client.get(URL, headers=_occ())
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1 · NO HABITAR no caduca ─────────────────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("hace", [timedelta(hours=9), timedelta(days=3)], ids=["9h", "3d"])
async def test_un_NO_HABITAR_firmado_SIGUE_bloqueando(base_data, make_incident, hace) -> None:
    """El defecto 1. Antes: `idle` a los 3 segundos de firmar. Ahora: bloqueado,
    con la razón, y sin caducidad — ni a las 9 h (pasada la ventana de 8 h de la
    autorización) ni a los tres días."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(iid, "no_inhabit_inspect", firmado=True, hace=hace)
    await _cerrar(iid, hace=hace - timedelta(seconds=3))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "reentry_blocked", (
        f"un NO HABITAR firmado hace {hace} dejó de bloquear (fase {estado['phase']!r}): "
        "el edificio se desbloquea solo en la pantalla de quien está fuera"
    )
    assert estado["reentry"] == {
        "blocked": True,
        "dictamen_status": "no_inhabit_inspect",
        "dictamen_signed": True,
        "incident_id": iid,
        "reason": "no_habitable",
    }
    # No se resucita el incidente: lo que persiste es el HECHO del veredicto.
    assert estado["incident"] is None


@pytest.mark.anyio
async def test_una_firma_habitable_POSTERIOR_lo_levanta(base_data, make_incident) -> None:
    """La ÚNICA forma de levantar un NO HABITAR: firmar habitable después, sobre
    ese incidente. Se firma por el endpoint real para dejar anclado que
    `sign_dictamen` no mira el estado — el incidente está cerrado desde hace días."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(iid, "no_inhabit_inspect", firmado=True, hace=timedelta(days=3))
    await _cerrar(iid, hace=timedelta(days=3))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        assert (await _estado(client))["phase"] == "reentry_blocked"

        firma = await client.post(
            f"/incidents/{iid}/dictamens",
            json={"status": "normal_operation", "notes": "reparado y reinspeccionado"},
            headers=_inspector(),
        )
        assert firma.status_code == 201, firma.text
        estado = await _estado(client)

    assert estado["phase"] == "reentry_approved"
    assert estado["reentry"]["blocked"] is False
    assert estado["reentry"]["reason"] is None
    assert estado["reentry"]["dictamen_status"] == "normal_operation"
    assert estado["reentry"]["incident_id"] == iid


# ── 2 · sólo lo que ordenó evacuar; 8 h desde la FIRMA ───────────────────────────────


@pytest.mark.anyio
async def test_un_incidente_SOLO_LOCAL_con_habitable_firmado_es_idle(
    base_data, make_incident
) -> None:
    """El defecto 2. Una estación sola no ordenó evacuar a nadie (T-2.105): no
    hay reingreso que autorizar, y decir «REINGRESO AUTORIZADO» en reposo le
    dice al ocupante que hubo algo de lo que volver."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold")
    await _dictamen(iid, "inhabit_monitor", firmado=True, hace=timedelta(minutes=5))
    await _cerrar(iid, hace=timedelta(minutes=5))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "idle", (
        f"un incidente de UNA estación declaró reingreso (fase {estado['phase']!r})"
    )
    assert estado["incident"] is None
    assert estado["reentry"]["blocked"] is False
    assert estado["reentry"]["dictamen_signed"] is False
    assert estado["reentry"]["reason"] is None


@pytest.mark.anyio
async def test_habitable_firmado_hace_9_h_ya_no_se_declara(base_data, make_incident) -> None:
    """La ventana de `reentry_declare_s` cuenta desde la FIRMA. Aquí el cierre es
    reciente (el TTL, una limpieza) y la firma tiene 9 h: contarlo desde el cierre
    resucitaría una autorización que su firmante dio hace un día de trabajo."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(iid, "inhabit_monitor", firmado=True, hace=timedelta(hours=9))
    await _cerrar(iid, hace=timedelta(minutes=10))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "idle"
    assert estado["reentry"]["blocked"] is False


@pytest.mark.anyio
async def test_cerrado_sin_dictamen_firmado_queda_PENDIENTE(base_data, make_incident) -> None:
    """Un SASMEX cerrado sin veredicto (TTL de revisión) no deja el edificio en
    calma: nadie lo ha inspeccionado. La espera tiene cota
    (`reentry_pendiente_lookback_s`) para no colgarse para siempre."""
    reciente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(reciente, "inhabit_monitor", firmado=False, hace=timedelta(hours=2))
    await _cerrar(reciente, hace=timedelta(hours=1))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)
        assert estado["phase"] == "reentry_blocked"
        assert estado["reentry"]["reason"] == "pendiente_dictamen"
        assert estado["reentry"]["dictamen_signed"] is False
        assert estado["reentry"]["incident_id"] == reciente

        # Pasada la cota, ya no se sostiene.
        await _cerrar(reciente, hace=timedelta(days=31))
        assert (await _estado(client))["phase"] == "idle"


@pytest.mark.anyio
async def test_clasificado_como_REPRODUCCION_es_idle(base_data, make_incident) -> None:
    """Una reproducción de un sismo histórico no ocurrió en este edificio: ni su
    NO HABITAR (firmado en la demostración) lo bloquea."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(iid, "no_inhabit_inspect", firmado=True, hace=timedelta(minutes=30))
    await _cerrar(iid, hace=timedelta(minutes=30))
    await _clasificar(iid, "reproduccion")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "idle"
    assert estado["reentry"]["blocked"] is False


# ── 3 · un local nuevo no tapa a un autorizante más viejo ────────────────────────────


@pytest.mark.anyio
async def test_un_local_NUEVO_abierto_no_tapa_a_un_SASMEX_abierto_mas_viejo(
    base_data, make_incident
) -> None:
    """El defecto 3. `LIMIT 1` el más nuevo + el filtro de T-2.105 DESPUÉS: el
    SASMEX vivo desaparecía detrás de un umbral instrumental posterior, y el
    ocupante pasaba de «EVACÚE» a la calma en plena alerta."""
    sasmex = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(minutes=4),
    )
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold")
    await _tier("evacuate_or_hold")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "alert_active", (
        f"un local nuevo tapó al SASMEX abierto (fase {estado['phase']!r})"
    )
    assert estado["incident"]["incident_id"] == sasmex
    assert estado["incident"]["trigger"] == "sasmex"
    assert estado["reentry"]["blocked"] is True


@pytest.mark.anyio
async def test_un_ABIERTO_que_autoriza_gana_al_NO_HABITAR_cerrado(base_data, make_incident) -> None:
    """La garantía de T-7.55, extendida al bloqueo: con alerta viva manda la
    alerta. El bloqueo sólo se mira cuando no hay nada abierto que autorice."""
    viejo = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(viejo, "no_inhabit_inspect", firmado=True, hace=timedelta(days=1))
    await _cerrar(viejo, hace=timedelta(days=1))
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _tier("evacuate_or_hold")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "alert_active"
    assert estado["reentry"]["reason"] is None


@pytest.mark.anyio
async def test_un_local_abierto_no_levanta_el_NO_HABITAR(base_data, make_incident) -> None:
    """El local abierto no se le enseña al ocupante (T-2.105), pero tampoco
    borra lo que sí sabe: el edificio sigue dictaminado inhabitable."""
    viejo = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex")
    await _dictamen(viejo, "restricted", firmado=True, hace=timedelta(days=2))
    await _cerrar(viejo, hace=timedelta(days=2))
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="local_threshold")
    await _tier("evacuate_or_hold")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "reentry_blocked"
    assert estado["incident"] is None
    assert estado["reentry"]["reason"] == "no_habitable"
    assert estado["reentry"]["incident_id"] == viejo


# ── 4 · ningún LIMIT ciego tapa lo que sí cuenta (refutaciones de F0) ────────────────
#
# Los tests puros de `deriva_reingreso` no ven la consulta: pasaban mientras el
# endpoint cortaba con `LIMIT 5`/`LIMIT 10` sobre incidentes de CUALQUIER tipo y
# filtraba después, en Python. Aquí se amontonan incidentes que no cuentan
# —locales, pruebas del WR-1— delante del que sí, contra la base de verdad.


@pytest.mark.anyio
async def test_SASMEX_abierto_tras_6_locales_abiertos(base_data, make_incident) -> None:
    """Réplicas sentidas sólo por la estación abren incidentes `local_threshold`
    detrás de un SASMEX que sigue abierto (en revisión, TTL de 6 h). Con
    `LIMIT 5` y el filtro después, el SASMEX desaparecía a partir del quinto local
    y el ocupante leía la calma en un edificio pendiente de inspección."""
    ahora = datetime.now(UTC)
    sasmex = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=ahora - timedelta(minutes=30),
    )
    for n in range(6):
        await make_incident(
            au.DB_TENANT_PRIV,
            au.DB_SITE_PRIV,
            trigger="local_threshold",
            opened_at=ahora - timedelta(minutes=20 - n),
        )
    await _tier("watch")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "alert_active", (
        f"seis locales abiertos taparon al SASMEX abierto (fase {estado['phase']!r})"
    )
    assert estado["incident"]["incident_id"] == sasmex
    assert estado["reentry"]["blocked"] is True


async def _no_habitar_de_hace(make_incident, hace: timedelta) -> str:
    iid = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex", opened_at=datetime.now(UTC) - hace
    )
    await _dictamen(iid, "no_inhabit_inspect", firmado=True, hace=hace - timedelta(minutes=30))
    await _cerrar(iid, hace=hace - timedelta(minutes=30))
    return iid


@pytest.mark.anyio
@pytest.mark.parametrize("que", ["locales", "pruebas_del_WR1", "replicas_SASMEX_sin_dictamen"])
async def test_NO_HABITAR_tras_11_cerrados_posteriores(base_data, make_incident, que) -> None:
    """Un NO HABITAR firmado hace 3 días y, después, 11 incidentes cerrados.

    · réplicas de la estación sola, o pruebas del WR-1 clasificadas «prueba»: no
      dicen nada del edificio. Con `LIMIT 10` sobre todos los cerrados el NO
      HABITAR se caía de la ventana y la app pintaba «SEGURO» sin cartel:
      caducaba, contra lo que el docstring promete.
    · réplicas SASMEX que el TTL cerró sin dictamen: ésas SÍ cuentan, y llenan
      solas cualquier ventana ordenada por apertura. Sólo las salva que los NO
      HABITAR vigentes se lean aparte, sin límite (`q.NO_HABITAR_VIGENTES`)."""
    viejo = await _no_habitar_de_hace(make_incident, timedelta(days=3))
    ahora = datetime.now(UTC)
    for n in range(11):
        iid = await make_incident(
            au.DB_TENANT_PRIV,
            au.DB_SITE_PRIV,
            trigger="local_threshold" if que == "locales" else "sasmex",
            state="closed",
            opened_at=ahora - timedelta(days=2) + timedelta(hours=n),
        )
        if que == "pruebas_del_WR1":
            await _clasificar(iid, "prueba")

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "reentry_blocked", (
        f"11 {que} cerrados después hicieron caducar el NO HABITAR (fase {estado['phase']!r})"
    )
    assert estado["reentry"]["reason"] == "no_habitable"
    assert estado["reentry"]["incident_id"] == viejo
    assert estado["reentry"]["blocked"] is True


@pytest.mark.anyio
async def test_NO_HABITAR_tapado_por_un_SASMEX_posterior_sin_dictamen(
    base_data, make_incident
) -> None:
    """La réplica SASMEX de hace 6 h se cerró por TTL sin dictamen —el edificio ya
    estaba cerrado—. Antes el endpoint paraba en ella: `pendiente_dictamen`, con
    su `incident_id`, y la app bajaba el cartel rojo a una franja ámbar sobre un
    edificio dictaminado inhabitable."""
    viejo = await _no_habitar_de_hace(make_incident, timedelta(days=2))
    replica = await make_incident(
        au.DB_TENANT_PRIV,
        au.DB_SITE_PRIV,
        trigger="sasmex",
        opened_at=datetime.now(UTC) - timedelta(hours=6),
    )
    await _cerrar(replica, hace=timedelta(hours=1))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["reentry"] == {
        "blocked": True,
        "dictamen_status": "no_inhabit_inspect",
        "dictamen_signed": True,
        "incident_id": viejo,
        "reason": "no_habitable",
    }
    assert estado["phase"] == "reentry_blocked"


@pytest.mark.anyio
async def test_NO_HABITAR_firmado_TARDE_sobre_un_incidente_mas_viejo(
    base_data, make_incident
) -> None:
    """A se abre hace 3 días y B hace 2; B se firma habitable hace 2 días. Hoy el
    inspector firma NO HABITAR sobre A —el daño se descubrió tarde—, por el
    endpoint real. Mandar por `opened_at` hacía que B, abierto después, dejara
    el edificio en calma."""
    ahora = datetime.now(UTC)
    a = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex", opened_at=ahora - timedelta(days=3)
    )
    await _cerrar(a, hace=timedelta(days=3))
    b = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex", opened_at=ahora - timedelta(days=2)
    )
    await _dictamen(b, "normal_operation", firmado=True, hace=timedelta(days=2))
    await _cerrar(b, hace=timedelta(days=2))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        firma = await client.post(
            f"/incidents/{a}/dictamens",
            json={"status": "no_inhabit_inspect", "notes": "grietas en muro de carga"},
            headers=_inspector(),
        )
        assert firma.status_code == 201, firma.text
        estado = await _estado(client)

    assert estado["phase"] == "reentry_blocked", (
        f"el NO HABITAR firmado hoy sobre A no bloqueó (fase {estado['phase']!r})"
    )
    assert estado["reentry"]["reason"] == "no_habitable"
    assert estado["reentry"]["incident_id"] == a


@pytest.mark.anyio
async def test_el_ULTIMO_CIERRE_decide_aunque_diez_se_abrieran_despues(
    base_data, make_incident
) -> None:
    """A (SASMEX) se abrió hace 3 días y el TTL lo cerró hace una hora sin dictamen.
    Entre medias se abrieron diez SASMEX más, firmados habitables y cerrados hace un
    día. La función decide por el último CIERRE (A ⇒ pendiente), pero la consulta
    ordenaba por APERTURA con `LIMIT 10`: los diez sacaban a A de la ventana y la
    app pintaba la calma sobre un edificio que nadie ha inspeccionado."""
    ahora = datetime.now(UTC)
    a = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, trigger="sasmex", opened_at=ahora - timedelta(days=3)
    )
    await _cerrar(a, hace=timedelta(hours=1))
    for n in range(10):
        b = await make_incident(
            au.DB_TENANT_PRIV,
            au.DB_SITE_PRIV,
            trigger="sasmex",
            opened_at=ahora - timedelta(days=2) + timedelta(hours=n),
        )
        await _dictamen(b, "normal_operation", firmado=True, hace=timedelta(days=1))
        await _cerrar(b, hace=timedelta(days=1))

    async with au.client_for(create_app()) as client:
        await _enrolar(client)
        estado = await _estado(client)

    assert estado["phase"] == "reentry_blocked", (
        f"diez abiertos después taparon al último cierre (fase {estado['phase']!r})"
    )
    assert estado["reentry"]["reason"] == "pendiente_dictamen"
    assert estado["reentry"]["incident_id"] == a


# ── 5 · la regla de autoridad en SQL es LA MISMA que en Python ─────────────────────────


@pytest.mark.anyio
async def test_la_regla_de_autoridad_en_SQL_es_la_de_Python(base_data) -> None:
    """Las consultas de `mobile_state` filtran EN SQL lo que puede autorizar,
    antes de cualquier orden o límite. Esa copia de la regla no puede divergir de
    `autoriza_evacuacion` —la única que decide—: se evalúan las dos sobre la misma
    rejilla, incluido el `NULL` de un incidente sin evento enlazado."""
    from takab_api.incident.autoridad import (
        autoriza_evacuacion,
        autoriza_evacuacion_sql,
        params_autoriza_evacuacion_sql,
    )

    triggers = ["sasmex", "quorum", "local_threshold", "manual", "origen_del_futuro"]
    nodos: list[int | None] = [None, 0, 2, 3, 4]
    rejilla = [(t, n) for t in triggers for n in nodos]
    valores = ", ".join(f"(:t{k}, CAST(:n{k} AS int))" for k in range(len(rejilla)))
    params: dict[str, object] = {}
    for k, (t, n) in enumerate(rejilla):
        params[f"t{k}"] = t
        params[f"n{k}"] = n
    for min_nodes in (2, 3):
        sql = text(
            f"SELECT x.origen, x.nodos, {autoriza_evacuacion_sql('x.origen', 'x.nodos')} AS ok "
            f"FROM (VALUES {valores}) AS x(origen, nodos)"
        )
        async with get_engine().connect() as conn:
            filas = (
                await conn.execute(sql, {**params, **params_autoriza_evacuacion_sql(min_nodes)})
            ).all()
        assert len(filas) == len(rejilla)
        for fila in filas:
            # (`Row.t` es un atributo de SQLAlchemy: por eso las columnas no se llaman así.)
            assert fila.ok is autoriza_evacuacion(fila.origen, fila.nodos, min_nodes), (
                fila.origen,
                fila.nodos,
                min_nodes,
            )
