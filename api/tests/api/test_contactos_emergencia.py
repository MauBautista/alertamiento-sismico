"""[T-9.80 · D-48] Contactos de emergencia: el titular los registra y NADIE más los ve.

Hasta tres personas, con su nombre, su correo y —opcional— su teléfono, a quienes
TAKAB avisa por correo si el titular marca «NECESITO AYUDA» tras un sismo. Son datos
de TERCEROS que el titular declara con su consentimiento, así que la superficie es
la mínima:

* ``GET/PUT/DELETE /me/emergency-contacts``, sólo sobre la fila PROPIA. La RLS filtra
  por ``user_sub`` y no sólo por tenant: el administrador del mismo cliente tampoco
  los lee (se mide abajo contra la base, no contra el router).
* ``PUT`` REEMPLAZA la lista entera y exige la versión VIGENTE del aviso: un
  consentimiento dado sobre un texto que ya no es el que se sirve no vale (409).
* La auditoría cuenta cuántos y con qué aviso; **ni un correo ni un nombre**.

Y el disparo: un check-in PROPIO ``need_help`` de alguien con contactos deja, en la
misma transacción, UNA acción ``need_help_contacts`` por persona e incidente — la que
el orquestador convierte en el correo (``tests/notify/test_aviso_a_contactos.py``).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app

OCC = "70000000-0000-0000-0000-0000000ec001"
OCC_2 = "70000000-0000-0000-0000-0000000ec002"
BRIG = "70000000-0000-0000-0000-0000000ec0b1"
ZONA = "7d000000-0000-0000-0000-0000000ec0d1"
VIGENTE = "contactos-v1-2026-09"

ANA = {"display_name": "Ana Contacto Ecatepec", "email": "ana.contacto@example.mx"}
BETO = {
    "display_name": "Beto Contacto Tlalpan",
    "email": "beto.contacto@example.mx",
    "phone": "+525511112222",
}


@pytest.fixture(autouse=True)
def _pool_de_ocupantes(monkeypatch: pytest.MonkeyPatch):
    from takab_api.auth import deps

    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _occ(user: str = OCC) -> dict[str, str]:
    return au.bearer(au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=user))


def _brig() -> dict[str, str]:
    return au.bearer(
        au.make_token(
            "brigadista",
            tenant=au.DB_TENANT_PRIV,
            user_id=BRIG,
            surface="mobile",
            site_scope=au.DB_SITE_PRIV,
        )
    )


def _cuerpo(*contactos: dict, version: str = VIGENTE) -> dict:
    return {"consentimiento_version": version, "contactos": list(contactos)}


async def _auditoria(verbo: str) -> list[dict]:
    async with get_engine().begin() as conn:
        filas = (
            await conn.execute(
                text("SELECT actor, object, meta FROM audit_log WHERE verb = :v ORDER BY ts"),
                {"v": verbo},
            )
        ).all()
    return [dict(f._mapping) for f in filas]


# ---------------------------------------------------------------------- el CRUD


@pytest.mark.anyio
async def test_sin_contactos_el_get_trae_la_lista_vacia_y_el_aviso_provisional(base_data) -> None:
    async with au.client_for(create_app()) as client:
        r = await client.get("/me/emergency-contacts", headers=_occ())
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["contactos"] == []
    aviso = cuerpo["aviso"]
    assert aviso["version"] == VIGENTE
    # BORRADOR sin revisión legal: viaja marcado y lo dice en el propio texto.
    assert aviso["provisional"] is True
    assert "TEXTO PROVISIONAL" in aviso["texto"]
    assert "NECESITO AYUDA" in aviso["texto"]


@pytest.mark.anyio
async def test_put_reemplaza_la_lista_entera_y_la_posicion_es_el_orden(base_data) -> None:
    async with au.client_for(create_app()) as client:
        r = await client.put("/me/emergency-contacts", json=_cuerpo(ANA, BETO), headers=_occ())
        assert r.status_code == 200, r.text
        assert [(c["posicion"], c["email"]) for c in r.json()["contactos"]] == [
            (1, ANA["email"]),
            (2, BETO["email"]),
        ]

        leido = (await client.get("/me/emergency-contacts", headers=_occ())).json()["contactos"]
        assert [c["display_name"] for c in leido] == [ANA["display_name"], BETO["display_name"]]
        assert leido[0]["phone"] is None
        assert leido[1]["phone"] == BETO["phone"]
        assert {c["consent_version"] for c in leido} == {VIGENTE}
        assert all(c["consented_at"] for c in leido)

        # Otra vez, al revés y con uno solo: no se ACUMULA, se reemplaza.
        r = await client.put("/me/emergency-contacts", json=_cuerpo(BETO), headers=_occ())
        assert r.status_code == 200
        leido = (await client.get("/me/emergency-contacts", headers=_occ())).json()["contactos"]
        assert [(c["posicion"], c["email"]) for c in leido] == [(1, BETO["email"])]

        # La lista vacía equivale a borrarlos.
        r = await client.put("/me/emergency-contacts", json=_cuerpo(), headers=_occ())
        assert r.status_code == 200
        assert r.json()["contactos"] == []


@pytest.mark.anyio
async def test_el_cuarto_contacto_es_422(base_data) -> None:
    cuatro = [{"display_name": f"Persona {i}", "email": f"p{i}@example.mx"} for i in range(4)]
    async with au.client_for(create_app()) as client:
        r = await client.put("/me/emergency-contacts", json=_cuerpo(*cuatro), headers=_occ())
        assert r.status_code == 422
        assert (await client.get("/me/emergency-contacts", headers=_occ())).json()[
            "contactos"
        ] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "malo",
    [
        {"display_name": "", "email": "a@example.mx"},
        {"display_name": "X", "email": "no-es-un-correo"},
        {"display_name": "X", "email": "a@example.mx", "phone": "5511112222"},
    ],
)
async def test_un_contacto_mal_formado_es_422(base_data, malo: dict) -> None:
    async with au.client_for(create_app()) as client:
        r = await client.put("/me/emergency-contacts", json=_cuerpo(malo), headers=_occ())
    assert r.status_code == 422


@pytest.mark.anyio
async def test_un_consentimiento_sobre_otra_version_es_409_y_no_escribe(base_data) -> None:
    async with au.client_for(create_app()) as client:
        r = await client.put(
            "/me/emergency-contacts",
            json=_cuerpo(ANA, version="contactos-v0-viejo"),
            headers=_occ(),
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "consentimiento_desactualizado"
        assert (await client.get("/me/emergency-contacts", headers=_occ())).json()[
            "contactos"
        ] == []


@pytest.mark.anyio
async def test_delete_los_borra_y_deja_constancia(base_data) -> None:
    async with au.client_for(create_app()) as client:
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA), headers=_occ())
        r = await client.delete("/me/emergency-contacts", headers=_occ())
        assert r.status_code == 204
        assert (await client.get("/me/emergency-contacts", headers=_occ())).json()[
            "contactos"
        ] == []
    [fila] = await _auditoria("emergency_contacts_deleted")
    assert fila["actor"] == f"user:{OCC}"


# ------------------------------------------------------------- quién los ve


@pytest.mark.anyio
async def test_otro_usuario_del_MISMO_tenant_no_los_ve(base_data) -> None:
    async with au.client_for(create_app()) as client:
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA, BETO), headers=_occ())
        ajeno = await client.get("/me/emergency-contacts", headers=_occ(OCC_2))
        assert ajeno.json()["contactos"] == []
        # Y su PUT/DELETE no toca los del otro: sólo reescribe su propia lista.
        await client.delete("/me/emergency-contacts", headers=_occ(OCC_2))
        assert (
            len((await client.get("/me/emergency-contacts", headers=_occ())).json()["contactos"])
            == 2
        )


@pytest.mark.anyio
@pytest.mark.parametrize("rol", ["tenant_admin", "brigadista", "takab_superadmin"])
async def test_la_RLS_filtra_por_usuario_y_no_solo_por_tenant(base_data, rol: str) -> None:
    """Medido contra la BASE, con la sesión que fija la API: ni el administrador del
    cliente ni el de TAKAB leen los contactos de un ocupante."""
    async with au.client_for(create_app()) as client:
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA), headers=_occ())
    async with get_engine().connect() as conn:
        await conn.execute(text("SET LOCAL ROLE takab_app"))
        for clave, valor in (
            ("app.tenant_id", au.DB_TENANT_PRIV),
            ("app.role", rol),
            ("app.user_id", str(uuid.uuid4())),
        ):
            await conn.execute(text("SELECT set_config(:k, :v, true)"), {"k": clave, "v": valor})
        n = (await conn.execute(text("SELECT count(*) FROM emergency_contacts"))).scalar_one()
        await conn.rollback()
    assert n == 0, f"{rol} ve contactos de emergencia ajenos"


@pytest.mark.anyio
async def test_la_auditoria_cuenta_pero_no_guarda_un_solo_dato_personal(base_data) -> None:
    async with au.client_for(create_app()) as client:
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA, BETO), headers=_occ())
        await client.delete("/me/emergency-contacts", headers=_occ())
    [fila] = await _auditoria("emergency_contacts_updated")
    assert fila["meta"] == {"n": 2, "consent_version": VIGENTE}
    crudo = json.dumps(
        await _auditoria("emergency_contacts_updated")
        + await _auditoria("emergency_contacts_deleted"),
        default=str,
    )
    for aguja in (*ANA.values(), *BETO.values()):
        assert aguja not in crudo, f"la auditoría guarda {aguja!r}"


# -------------------------------------------------- el disparo desde el check-in


async def _enrolar(client, headers: dict[str, str], codigo: str) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:z, :t, :s, 'Piso 3 · Ala Norte', 'P3', 'shelter') "
                "ON CONFLICT (zone_id) DO NOTHING"
            ),
            {"z": ZONA, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES (:c, :t, :s, :z, true)"
            ),
            {"c": codigo, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "z": ZONA},
        )
    r = await client.post("/me/enrollment", json={"code": codigo}, headers=headers)
    assert r.status_code == 200, r.text


async def _avisos(incidente: str) -> list[dict]:
    async with get_engine().begin() as conn:
        filas = (
            await conn.execute(
                text(
                    "SELECT actor, payload FROM incident_actions "
                    "WHERE incident_id = CAST(:i AS uuid) AND kind = 'need_help_contacts'"
                ),
                {"i": incidente},
            )
        ).all()
    return [dict(f._mapping) for f in filas]


def _checkin(status: str, **extra) -> dict:
    return {"status": status, "ts_device": datetime.now(UTC).isoformat(), **extra}


@pytest.mark.anyio
async def test_need_help_propio_con_contactos_deja_UNA_accion_aunque_se_repita(
    base_data, make_incident
) -> None:
    incidente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    url = f"/incidents/{incidente}/checkins"
    async with au.client_for(create_app()) as client:
        await _enrolar(client, _occ(), "EC-CODE-1")
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA), headers=_occ())

        primero = await client.post(
            url, json=_checkin("need_help", location=[-99.13, 19.43]), headers=_occ()
        )
        assert primero.status_code == 201, primero.text
        # Reenviar (otro check-in, sin ubicación) no manda un segundo aviso.
        segundo = await client.post(url, json=_checkin("need_help"), headers=_occ())
        assert segundo.status_code == 201

    [aviso] = await _avisos(incidente)
    assert aviso["actor"] == f"user:{OCC}"
    assert aviso["payload"] == {
        "user_sub": OCC,
        "checkin_id": primero.json()["checkin_id"],
        "con_ubicacion": True,
    }
    # Sin PII en la acción (es append-only y ARCO no la reescribe): ni el correo
    # del contacto ni las coordenadas.
    crudo = json.dumps(aviso, default=str)
    assert ANA["email"] not in crudo and "19.43" not in crudo


@pytest.mark.anyio
async def test_el_user_sub_del_aviso_va_en_forma_CANONICA(base_data, make_incident) -> None:
    """[T-9.80 · 0078] ARCO, la política de borrado y la retención comparan el
    `user_sub` del aviso como TEXTO con `app_user_id()::text`. Un sub escrito tal cual
    llegó —en mayúsculas— dejaría el aviso fuera de su alcance para siempre: la acción
    es append-only y no se puede corregir después."""
    incidente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    mayusculas = _occ(OCC.upper())
    async with au.client_for(create_app()) as client:
        await _enrolar(client, mayusculas, "EC-CODE-9")
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA), headers=mayusculas)
        r = await client.post(
            f"/incidents/{incidente}/checkins", json=_checkin("need_help"), headers=mayusculas
        )
        assert r.status_code == 201, r.text

    [aviso] = await _avisos(incidente)
    assert aviso["payload"]["user_sub"] == OCC.lower()


@pytest.mark.anyio
async def test_safe_no_avisa_a_nadie(base_data, make_incident) -> None:
    incidente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        await _enrolar(client, _occ(), "EC-CODE-2")
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA), headers=_occ())
        r = await client.post(
            f"/incidents/{incidente}/checkins", json=_checkin("safe"), headers=_occ()
        )
        assert r.status_code == 201
    assert await _avisos(incidente) == []


@pytest.mark.anyio
async def test_sin_contactos_no_hay_accion(base_data, make_incident) -> None:
    incidente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        await _enrolar(client, _occ(), "EC-CODE-3")
        r = await client.post(
            f"/incidents/{incidente}/checkins", json=_checkin("need_help"), headers=_occ()
        )
        assert r.status_code == 201
    assert await _avisos(incidente) == []


@pytest.mark.anyio
async def test_un_need_help_DELEGADO_no_avisa_a_los_contactos(base_data, make_incident) -> None:
    """Quien marca es el brigadista: la persona no pidió nada con su teléfono, y el
    aviso a su familia es algo que sólo decide ella."""
    incidente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with au.client_for(create_app()) as client:
        await _enrolar(client, _occ(), "EC-CODE-4")
        await client.put("/me/emergency-contacts", json=_cuerpo(ANA), headers=_occ())
        r = await client.post(
            f"/incidents/{incidente}/checkins",
            json=_checkin("need_help", subject_user_id=OCC),
            headers=_brig(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["via"] == "delegated"
    assert await _avisos(incidente) == []
