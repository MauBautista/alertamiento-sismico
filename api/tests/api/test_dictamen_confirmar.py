"""[T-9.31 · D-43] CONFIRMAR el dictamen de la regla: POST .../dictamens/{id}/confirm.

La regla ``dictamen-v2`` emite AMARILLO sin firmar; quien tiene
``confirm_dictamen`` (brigada, inspector, administración) lo confirma insertando una
fila NUEVA con el mismo status y banda, ``signature_kind='confirmation'``. Un ROJO no
se confirma (403: lo firma el inspector); sólo la CABEZA vigente (409) y sólo si
nadie la firmó ya (409).
"""

from __future__ import annotations

from sqlalchemy import text

import auth_utils as au
from takab_api.auth.matrix import roles_with_action

_BRIGADISTA = "abcabcab-0000-0000-0000-0000000000b1"


def _tok(role: str, user: str = _BRIGADISTA) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=user))


async def _fetch(sql: str, **params: object) -> list[dict]:
    from takab_api.db.engine import get_engine

    async with get_engine().begin() as conn:
        return [dict(r) for r in (await conn.execute(text(sql), params)).mappings().all()]


def test_el_circulo_de_la_confirmacion_es_brigada_inspector_y_administracion() -> None:
    assert roles_with_action("confirm_dictamen") == ("brigadista", "inspector", "tenant_admin")


async def test_confirmar_la_cabeza_AMARILLA_inserta_fila_de_confirmacion(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")

    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm", headers=_tok("brigadista")
    )

    assert resp.status_code == 201, resp.text
    fila = resp.json()
    assert fila["status"] == "inhabit_monitor"
    assert fila["band"] == "amarillo"
    assert fila["signature_kind"] == "confirmation"
    assert fila["signed_by"] == _BRIGADISTA
    assert fila["supersedes_dictamen_id"] == head

    cadena = (await client.get(f"/incidents/{iid}/dictamens", headers=_tok("inspector"))).json()[
        "items"
    ]
    assert cadena[0]["dictamen_id"] == fila["dictamen_id"], "la confirmación es la cabeza"

    audit = await _fetch(
        "SELECT actor, meta FROM audit_log WHERE verb = 'dictamen_confirmed' AND object = :o",
        o=f"incident:{iid}",
    )
    assert len(audit) == 1
    assert audit[0]["actor"] == f"user:{_BRIGADISTA}"
    assert audit[0]["meta"]["band"] == "amarillo"
    assert audit[0]["meta"]["supersedes"] == head

    acciones = await _fetch(
        "SELECT kind, payload FROM incident_actions "
        "WHERE incident_id = CAST(:i AS uuid) AND kind = 'dictamen_confirmed'",
        i=iid,
    )
    assert len(acciones) == 1
    assert acciones[0]["payload"]["folio"] == fila["dictamen_id"]


async def test_confirmar_lo_que_NO_es_la_cabeza_es_409(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    vieja = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    await make_dictamen(
        au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo", supersedes=vieja
    )

    resp = await client.post(
        f"/incidents/{iid}/dictamens/{vieja}/confirm", headers=_tok("brigadista")
    )

    assert resp.status_code == 409, resp.text
    assert (
        await _fetch(
            "SELECT 1 FROM dictamens WHERE incident_id = CAST(:i AS uuid) "
            "AND signature_kind = 'confirmation'",
            i=iid,
        )
        == []
    )


async def test_confirmar_una_cabeza_YA_FIRMADA_es_409(client, make_incident, make_dictamen) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    firmada = await make_dictamen(
        au.DB_TENANT_PRIV,
        iid,
        status="inhabit_monitor",
        band="amarillo",
        signed_by="abcabcab-0000-0000-0000-0000000000d1",
        signature_kind="inspector",
    )

    resp = await client.post(
        f"/incidents/{iid}/dictamens/{firmada}/confirm", headers=_tok("inspector")
    )

    assert resp.status_code == 409, resp.text


async def test_un_ROJO_no_se_confirma_es_403(client, make_incident, make_dictamen) -> None:
    """Lo firma el inspector por la vía de siempre. Tampoco una fila HISTÓRICA sin
    banda cuyo status es rojo: la banda se deriva del status (default-deny)."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    rojo = await make_dictamen(au.DB_TENANT_PRIV, iid, status="no_inhabit_inspect", band="rojo")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{rojo}/confirm", headers=_tok("inspector")
    )
    assert resp.status_code == 403, resp.text

    otro = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    historico = await make_dictamen(au.DB_TENANT_PRIV, otro, status="restricted")
    resp = await client.post(
        f"/incidents/{otro}/dictamens/{historico}/confirm", headers=_tok("brigadista")
    )
    assert resp.status_code == 403, resp.text


async def test_un_OCUPANTE_no_confirma_403(client, make_incident, make_dictamen) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")

    resp = await client.post(f"/incidents/{iid}/dictamens/{head}/confirm", headers=_tok("occupant"))

    assert resp.status_code == 403, resp.text


async def test_otro_tenant_es_404(client, make_incident, make_dictamen) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)
    head = await make_dictamen(au.DB_TENANT_PRIV2, iid, status="inhabit_monitor", band="amarillo")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm", headers=_tok("brigadista")
    )
    assert resp.status_code == 404, resp.text


async def test_la_firma_del_inspector_escribe_tipo_y_banda_por_el_endpoint(
    client, make_incident
) -> None:
    """El INSERT compartido: la firma de siempre queda como ``inspector``."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    resp = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "normal_operation"},
        headers=_tok("inspector", user="abcabcab-0000-0000-0000-0000000000d1"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["signature_kind"] == "inspector"
    assert resp.json()["band"] == "verde"


# ------------------------------------------------ F3·r2: alcance, daño ROJO, rol

_OTRO_SITIO = "11111111-1111-4111-8111-111111111111"


def _tok_sitio(role: str, site_scope: str, user: str = _BRIGADISTA) -> dict[str, str]:
    return au.bearer(
        au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope=site_scope, user_id=user)
    )


async def _dano(iid: str, *keys: str) -> None:
    import json
    import uuid

    from takab_api.db.engine import get_engine

    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO damage_reports (tenant_id, incident_id, site_id, user_sub, "
                "categories) VALUES (:t, CAST(:i AS uuid), :s, :u, CAST(:c AS jsonb))"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "i": iid,
                "s": au.DB_SITE_PRIV,
                "u": str(uuid.uuid4()),
                "c": json.dumps([{"key": k, "severity": "high"} for k in keys]),
            },
        )


async def test_confirmar_FUERA_del_alcance_por_inmueble_es_404(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm",
        headers=_tok_sitio("brigadista", _OTRO_SITIO),
    )
    assert resp.status_code == 404, resp.text
    assert (
        await _fetch(
            "SELECT 1 FROM dictamens WHERE incident_id = CAST(:i AS uuid) "
            "AND signature_kind = 'confirmation'",
            i=iid,
        )
        == []
    )
    # dentro de su alcance, sí
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm",
        headers=_tok_sitio("brigadista", au.DB_SITE_PRIV),
    )
    assert resp.status_code == 201, resp.text


async def test_con_un_dano_ROJO_reportado_no_se_confirma_409(
    client, make_incident, make_dictamen
) -> None:
    """El daño entró y la regla aún no subió la banda: confirmar el AMARILLO liberaría
    el reingreso con un daño estructural reportado. Lo decide un inspector."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    await _dano(iid, "water_leak", "structural")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm", headers=_tok("brigadista")
    )
    assert resp.status_code == 409, resp.text
    assert "inspector" in resp.json()["detail"]


async def test_un_dano_AMARILLO_no_impide_confirmar(client, make_incident, make_dictamen) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    await _dano(iid, "water_leak")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm", headers=_tok("brigadista")
    )
    assert resp.status_code == 201, resp.text


async def test_la_confirmacion_guarda_el_ROL_en_el_basis_y_lo_expone(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{head}/confirm", headers=_tok("brigadista")
    )
    assert resp.status_code == 201, resp.text
    fila = resp.json()
    assert fila["basis"]["confirmacion"]["rol"] == "brigadista"
    assert fila["confirmed_by_role"] == "brigadista"
    cadena = (await client.get(f"/incidents/{iid}/dictamens", headers=_tok("inspector"))).json()[
        "items"
    ]
    assert cadena[0]["confirmed_by_role"] == "brigadista"
    assert cadena[1]["confirmed_by_role"] is None


# --------------------------------------------- F3·r2: la firma y el orden (punto 3)


async def test_la_firma_queda_DETRAS_de_una_cabeza_con_reloj_adelantado(
    client, make_incident, make_dictamen
) -> None:
    """La cabeza del worker nace con ``clock_timestamp()`` ≥ cabeza+1 µs: puede ir
    por delante del ``now()`` de la transacción de la firma. La firma tiene que quedar
    DETRÁS de ella (``created_at`` monótono), si no, no sería la cabeza nueva."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    head = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    from takab_api.db.engine import get_engine

    async with get_engine().begin() as conn:
        # append-only: se mueve el reloj de la CABEZA recreándola adelantada
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(
            text(
                "UPDATE dictamens SET created_at = now() + interval '1 hour' "
                "WHERE dictamen_id = CAST(:d AS uuid)"
            ),
            {"d": head},
        )
    resp = await client.post(
        f"/incidents/{iid}/dictamens",
        json={"status": "normal_operation"},
        headers=_tok("inspector", user="abcabcab-0000-0000-0000-0000000000d1"),
    )
    assert resp.status_code == 201, resp.text
    cadena = (await client.get(f"/incidents/{iid}/dictamens", headers=_tok("inspector"))).json()[
        "items"
    ]
    assert cadena[0]["dictamen_id"] == resp.json()["dictamen_id"]
    assert cadena[0]["supersedes_dictamen_id"] == head


# ----------------------------------------- F3·r2: la brigada lee la cadena (punto 4)


async def test_la_BRIGADA_lee_la_cadena_de_su_inmueble(
    client, make_incident, make_dictamen
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor", band="amarillo")
    resp = await client.get(
        f"/incidents/{iid}/dictamens", headers=_tok_sitio("brigadista", au.DB_SITE_PRIV)
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1
    fuera = await client.get(
        f"/incidents/{iid}/dictamens", headers=_tok_sitio("brigadista", _OTRO_SITIO)
    )
    assert fuera.status_code == 404, fuera.text
    ocupante = await client.get(f"/incidents/{iid}/dictamens", headers=_tok("occupant"))
    assert ocupante.status_code == 403, ocupante.text


async def test_la_BRIGADA_puede_pedir_el_dictamen_tecnico_de_su_inmueble(
    client, make_incident
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    fuera = await client.post(
        f"/incidents/{iid}/dictamen-request",
        json={"note": "grieta"},
        headers=_tok_sitio("brigadista", _OTRO_SITIO),
    )
    assert fuera.status_code == 404, fuera.text
    resp = await client.post(
        f"/incidents/{iid}/dictamen-request",
        json={"note": "grieta"},
        headers=_tok_sitio("brigadista", au.DB_SITE_PRIV),
    )
    assert resp.status_code == 201, resp.text


# ── F3·r3 · sólo se confirma un AMARILLO ─────────────────────────────────────────


async def test_un_VERDE_sin_firmar_NO_se_confirma_409(client, make_incident, make_dictamen) -> None:
    """Medido en la ronda 2: un brigadista confirmaba un VERDE en plena sacudida y la
    app pasaba a REINGRESO AUTORIZADO, saltándose la gracia de 300 s y el tier normal
    que D-43 exige al VERDE automático. El VERDE lo firma el sistema (o el inspector)."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    verde = await make_dictamen(au.DB_TENANT_PRIV, iid, status="normal_operation", band="verde")
    resp = await client.post(
        f"/incidents/{iid}/dictamens/{verde}/confirm", headers=_tok("brigadista")
    )
    assert resp.status_code == 409, resp.text
    assert "el VERDE lo firma el sistema tras la gracia" in resp.text
    filas = await _fetch("SELECT 1 FROM dictamens WHERE incident_id = CAST(:i AS uuid)", i=iid)
    assert len(filas) == 1, "no se insertó ninguna confirmación"


async def test_una_fila_HISTORICA_sin_banda_habitable_NO_se_confirma_409(
    client, make_incident, make_dictamen
) -> None:
    """Una fila v1 (band NULL) no es una salida de la regla v2: no hay AMARILLO que
    confirmar, aunque su status sea habitable."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    v1 = await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor")
    resp = await client.post(f"/incidents/{iid}/dictamens/{v1}/confirm", headers=_tok("brigadista"))
    assert resp.status_code == 409, resp.text
