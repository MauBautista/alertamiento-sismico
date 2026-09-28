"""[T-9.40 · D-43] Cerrar un evento a propósito: ``POST /incidents/{id}/close``.

Hasta esta ficha un incidente sólo lo cerraba la pasada del ciclo de vida (cabeza
firmada + clasificación, clasificación terminal o TTL de revisión). Aquí la
administración lo cierra desde la consola, y los requisitos se revisan EN ORDEN,
dentro de una transacción y con la fila bloqueada:

1. no existe / otro tenant → 404;
2. ya cerrado → 409 ``ya_cerrado``;
3. sin acusar → 409 ``sin_acuse``;
4. el edificio se sigue moviendo → 409 ``sismo_en_curso`` (D-49 · R1);
5. nadie lo clasificó → 409 ``sin_clasificacion``;
6. ``real``/``indeterminado`` sin cabeza firmada y sin un motivo de ≥ 20
   caracteres → 409 ``sin_dictamen``.

El ``detail`` de los 409 es el CÓDIGO: la web lo traduce.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth.matrix import roles_with_action
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.usefixtures("base_data")

_ADMIN = "c105e000-0000-0000-0000-0000000000a1"
_INSPECTOR = "c105e000-0000-0000-0000-0000000000b2"
_MOTIVO = "el inspector externo firmó en papel; se archiva copia"


def _hdr(
    role: str = "tenant_admin", *, tenant: str = au.DB_TENANT_PRIV, user: str = _ADMIN
) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=user))


async def _sql(sql: str, **params: object) -> list[dict]:
    async with get_engine().begin() as conn:
        r = await conn.execute(text(sql), params)
        return [dict(m) for m in r.mappings().all()] if r.returns_rows else []


async def _tier(site: str, tier: str, *, hace_s: float) -> None:
    await _sql(
        "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier)"
        " VALUES (:ts, :t, :s, gen_random_uuid(), 'normal', :n)",
        ts=datetime.now(UTC) - timedelta(seconds=hace_s),
        t=au.DB_TENANT_PRIV,
        s=site,
        n=tier,
    )


async def _clasifica(iid: str, clase: str, *, tenant: str = au.DB_TENANT_PRIV) -> None:
    await _sql(
        "INSERT INTO incident_classifications (tenant_id, incident_id, classification,"
        " classified_by) VALUES (:t, :i, :c, :by)",
        t=tenant,
        i=iid,
        c=clase,
        by=_ADMIN,
    )


async def _listo(make_incident, *, clase: str | None = "real", state: str = "acked") -> str:
    """Un incidente acusado, en calma y clasificado: sólo falta el dictamen."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state=state)
    if clase is not None:
        await _clasifica(iid, clase)
    return iid


async def _close(client, iid: str, *, headers=None, motivo: str | None = None):
    body = {} if motivo is None else {"motivo": motivo}
    return await client.post(f"/incidents/{iid}/close", headers=headers or _hdr(), json=body)


async def _estado(iid: str) -> dict:
    return (await _sql("SELECT state, closed_at FROM incidents WHERE incident_id = :i", i=iid))[0]


async def _audit(iid: str) -> list[dict]:
    return await _sql(
        "SELECT verb, actor, tenant_id::text AS tenant_id, meta FROM audit_log"
        " WHERE object = :o ORDER BY audit_id",
        o=f"incident:{iid}",
    )


def test_el_circulo_del_cierre_es_administracion_y_takab() -> None:
    assert roles_with_action("close_incident") == ("takab_superadmin", "tenant_admin")


# ───────────────────────────────────────────────────── requisitos, en orden


async def test_1_inexistente_es_404(client) -> None:
    r = await _close(client, str(uuid.uuid4()))
    assert r.status_code == 404, r.text


async def test_1_otro_tenant_es_404_y_no_lo_toca(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2, state="acked")
    await _clasifica(iid, "prueba", tenant=au.DB_TENANT_PRIV2)
    r = await _close(client, iid)  # tenant_admin de DB_TENANT_PRIV
    assert r.status_code == 404, r.text
    assert (await _estado(iid))["state"] == "acked"


async def test_2_ya_cerrado_es_409(client, make_incident) -> None:
    iid = await _listo(make_incident, clase="prueba", state="closed")
    r = await _close(client, iid)
    assert r.status_code == 409
    assert r.json()["detail"] == "ya_cerrado"


async def test_3_sin_acuse_es_409_aunque_falte_todo_lo_demas(client, make_incident) -> None:
    """El orden importa: sin acuse, no se pregunta por el tier ni la clasificación."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="open")
    await _tier(au.DB_SITE_PRIV, "evacuate_or_hold", hace_s=1)
    r = await _close(client, iid)
    assert r.status_code == 409
    assert r.json()["detail"] == "sin_acuse"
    assert (await _estado(iid))["state"] == "open"


@pytest.mark.parametrize("tier", ["evacuate_or_hold", "restricted", "watch"])
async def test_4_edificio_en_movimiento_es_409(client, make_incident, tier: str) -> None:
    iid = await _listo(make_incident, clase="prueba")
    await _tier(au.DB_SITE_PRIV, tier, hace_s=1)
    r = await _close(client, iid, motivo=_MOTIVO)
    assert r.status_code == 409
    assert r.json()["detail"] == "sismo_en_curso"


async def test_4_manda_el_ULTIMO_tier_no_la_calma_anterior(client, make_incident) -> None:
    """La calma de ANTES del sismo sigue en la tabla: preguntar si hubo un `normal`
    la encuentra y cerraría con el edificio moviéndose."""
    iid = await _listo(make_incident, clase="prueba")
    await _tier(au.DB_SITE_PRIV, "normal", hace_s=60)
    await _tier(au.DB_SITE_PRIV, "evacuate_or_hold", hace_s=5)
    r = await _close(client, iid)
    assert r.json()["detail"] == "sismo_en_curso"


async def test_4_de_vuelta_en_normal_si_cierra(client, make_incident) -> None:
    iid = await _listo(make_incident, clase="prueba")
    await _tier(au.DB_SITE_PRIV, "evacuate_or_hold", hace_s=60)
    await _tier(au.DB_SITE_PRIV, "normal", hace_s=5)
    r = await _close(client, iid)
    assert r.status_code == 200, r.text


async def test_5_sin_clasificacion_es_409(client, make_incident, make_dictamen) -> None:
    iid = await _listo(make_incident, clase=None)
    await make_dictamen(au.DB_TENANT_PRIV, iid, signed_by=_INSPECTOR, signature_kind="inspector")
    r = await _close(client, iid, motivo=_MOTIVO)
    assert r.status_code == 409
    assert r.json()["detail"] == "sin_clasificacion"


@pytest.mark.parametrize("clase", ["real", "indeterminado"])
async def test_6_sin_dictamen_ni_motivo_es_409(client, make_incident, clase: str) -> None:
    iid = await _listo(make_incident, clase=clase)
    r = await _close(client, iid)
    assert r.status_code == 409
    assert r.json()["detail"] == "sin_dictamen"


async def test_6_un_motivo_de_relleno_no_cuenta(client, make_incident) -> None:
    """Se cuentan los caracteres TRAS ``strip()``: 19 visibles rodeados de espacios no
    llegan a 20."""
    iid = await _listo(make_incident)
    r = await _close(client, iid, motivo="   " + "x" * 19 + "      ")
    assert r.json()["detail"] == "sin_dictamen"


async def test_6_manda_la_CABEZA_no_alguna_firmada(client, make_incident, make_dictamen) -> None:
    """Un daño tras la firma sube la banda en una fila SIN firmar: ese incidente ya no
    está dictaminado aunque exista una firma más vieja en la cadena."""
    iid = await _listo(make_incident)
    vieja = await make_dictamen(
        au.DB_TENANT_PRIV, iid, signed_by=_INSPECTOR, signature_kind="inspector"
    )
    await make_dictamen(au.DB_TENANT_PRIV, iid, status="restricted", supersedes=vieja)
    r = await _close(client, iid)
    assert r.json()["detail"] == "sin_dictamen"


# ───────────────────────────────────────────────────────────── cierres felices


async def test_cierre_con_cabeza_firmada(client, make_incident, make_dictamen) -> None:
    iid = await _listo(make_incident, clase="real")
    await make_dictamen(au.DB_TENANT_PRIV, iid, signed_by=_INSPECTOR, signature_kind="inspector")

    r = await _close(client, iid)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["incident_id"] == iid
    assert body["state"] == "closed"
    assert body["reason"] == "explicit"
    assert body["classification"] == "real"
    assert body["signature_kind"] == "inspector"
    assert body["sin_dictamen"] is False
    assert body["closed_at"]
    fila = await _estado(iid)
    assert fila["state"] == "closed" and fila["closed_at"] is not None

    acciones = await _sql(
        "SELECT kind, actor, payload FROM incident_actions WHERE incident_id = :i", i=iid
    )
    assert len(acciones) == 1
    (accion,) = acciones
    assert accion["kind"] == "close"
    assert accion["actor"] == f"user:{_ADMIN}"
    assert accion["payload"] == {
        "from": "acked",
        "to": "closed",
        "reason": "explicit",
        "classification": "real",
        "signature_kind": "inspector",
    }
    verbos = [a["verb"] for a in await _audit(iid)]
    assert verbos == ["close"]


async def test_cierre_con_motivo_deja_el_rastro_de_que_no_hubo_dictamen(
    client, make_incident
) -> None:
    iid = await _listo(make_incident, clase="indeterminado", state="in_review")

    r = await _close(client, iid, motivo=f"  {_MOTIVO}  ")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sin_dictamen"] is True
    assert body["signature_kind"] is None
    (accion,) = await _sql(
        "SELECT payload FROM incident_actions WHERE incident_id = :i AND kind = 'close'", i=iid
    )
    assert accion["payload"]["motivo"] == _MOTIVO
    assert accion["payload"]["from"] == "in_review"
    auditoria = await _audit(iid)
    assert [a["verb"] for a in auditoria] == ["close", "cierre_sin_dictamen"]
    assert auditoria[1]["meta"] == {"motivo": _MOTIVO, "classification": "indeterminado"}


async def test_con_cabeza_firmada_el_motivo_viaja_pero_no_hay_cierre_sin_dictamen(
    client, make_incident, make_dictamen
) -> None:
    iid = await _listo(make_incident)
    await make_dictamen(au.DB_TENANT_PRIV, iid, signed_by=_INSPECTOR, signature_kind="inspector")
    r = await _close(client, iid, motivo=_MOTIVO)
    assert r.status_code == 200, r.text
    assert r.json()["sin_dictamen"] is False
    assert [a["verb"] for a in await _audit(iid)] == ["close"]


@pytest.mark.parametrize("clase", ["falso_positivo", "prueba", "reproduccion"])
async def test_clasificacion_terminal_no_pide_dictamen(client, make_incident, clase: str) -> None:
    iid = await _listo(make_incident, clase=clase)
    r = await _close(client, iid)
    assert r.status_code == 200, r.text
    assert r.json()["classification"] == clase
    assert r.json()["sin_dictamen"] is False
    assert [a["verb"] for a in await _audit(iid)] == ["close"]


async def test_la_clasificacion_VIGENTE_es_la_que_cuenta(client, make_incident) -> None:
    """Corregir INSERTA: una PRUEBA corregida a REAL ya no se cierra sin dictamen."""
    iid = await _listo(make_incident, clase="prueba")
    (primera,) = await _sql(
        "SELECT classification_id::text AS id FROM incident_classifications WHERE incident_id = :i",
        i=iid,
    )
    await _sql(
        "INSERT INTO incident_classifications (tenant_id, incident_id, classification,"
        " classified_by, supersedes_id) VALUES (:t, :i, 'real', :by, :sup)",
        t=au.DB_TENANT_PRIV,
        i=iid,
        by=_ADMIN,
        sup=primera["id"],
    )
    r = await _close(client, iid)
    assert r.json()["detail"] == "sin_dictamen"


async def test_superadmin_cierra_y_la_auditoria_es_del_tenant_del_incidente(
    client, make_incident
) -> None:
    """⚠️ Con el token en el MISMO tenant del incidente. La RLS de
    ``incident_classifications`` (0055) no tiene rama ``app_is_takab_internal``: un
    superadmin situado en OTRO tenant no ve la clasificación y recibe
    ``sin_clasificacion``, igual que hoy no puede clasificar ahí."""
    iid = await _listo(make_incident, clase="prueba")
    r = await _close(client, iid, headers=_hdr("takab_superadmin", tenant=au.DB_TENANT_PRIV))
    assert r.status_code == 200, r.text
    (fila,) = await _audit(iid)
    assert fila["tenant_id"] == au.DB_TENANT_PRIV


async def test_el_timeline_muestra_el_cierre_explicito(client, make_incident) -> None:
    iid = await _listo(make_incident, clase="prueba")
    assert (await _close(client, iid)).status_code == 200
    acts = await client.get(f"/incidents/{iid}/actions", headers=_hdr())
    assert acts.status_code == 200, acts.text
    cierres = [a for a in acts.json() if a["kind"] == "close"]
    assert len(cierres) == 1
    assert cierres[0]["payload"]["reason"] == "explicit"


# ─────────────────────────────────────────────────────────────── puerta de rol


@pytest.mark.parametrize(
    "role", ["brigadista", "inspector", "gov_operator", "takab_support", "occupant"]
)
async def test_roles_sin_la_accion_son_403(client, make_incident, role: str) -> None:
    iid = await _listo(make_incident, clase="prueba")
    r = await _close(client, iid, headers=_hdr(role))
    assert r.status_code == 403, r.text
    assert (await _estado(iid))["state"] == "acked"


async def test_motivo_demasiado_largo_es_422(client, make_incident) -> None:
    iid = await _listo(make_incident)
    r = await _close(client, iid, motivo="x" * 1001)
    assert r.status_code == 422
