"""[T-2.147.b · D-05] El acuse de la BRIGADA, que no es el acuse del SOC.

`D-05` eligió despertar solo a los tácticos, y añadió que **si ninguno acusa en
~2 min se avisa al SOC**. Ese escalado (`T-2.147.c`) no se puede medir sin una
señal de «lo tengo»: hoy no existía ninguna.

POR QUÉ NO SE REUSÓ `POST /incidents/{id}/ack`
-----------------------------------------------
Aquel mueve el incidente `open→acked` y lo firman los roles de MONITOREO
(`ack_incident`: superadmin, tenant_admin, soc_operator, gov_operator). Conflarlo
con el acuse de la brigada costaría en las DOS direcciones:

  · un brigadista vaciaría la cola del SOC desde el teléfono;
  · y el acuse del SOC contaría como respuesta de la brigada, apagando el
    escalado de `T-2.147.c` **sin que nadie hubiera bajado a mirar** — que es
    exactamente el fallo que ese escalado existe para impedir.

Son dos hechos distintos, y por eso son dos filas distintas y dos rótulos
distintos en la consola.

LA INVARIANTE DE LOS DOS CÍRCULOS
----------------------------------
Quien RECIBE el push (`T-2.147.a`) y quien puede ACUSARLO se derivan de la misma
acción de la matriz, `manual_activate`. Que coincidan no es economía de código:
si divergieran, alguien despertado a las 3 a.m. sin permiso para acusar
parecería «sin respuesta» para siempre y dispararía el aviso al SOC por un fallo
de permisos. `test_los_dos_circulos_son_el_mismo` lo fija.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, roles_with_action
from takab_api.db.engine import get_engine
from takab_api.routers.incidents import TACTICAL_ACK_ROLES

pytestmark = pytest.mark.anyio

SITE = "7c500000-0000-0000-0000-00000000015f"
INCIDENT = "7c500000-0000-0000-0000-0000000000f1"
TACTICO = "brigadista"


@pytest.fixture(autouse=True)
def _pool_de_ocupantes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Habilita el pool de ocupantes en el app bajo test.

    Sin esto, el token del occupant se rechaza por EMISOR (401) y el test de
    permisos aprobaría sin haber ejercido nunca la guarda de rol — mediría el
    montaje del pool, no la regla que dice que un occupant no atiende alarmas.
    """
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
async def incidente(base_data) -> None:
    """Un incidente `manual` abierto en un sitio del tenant privilegiado."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-TACK', 'Sitio acuse', "
                "ST_SetSRID(ST_MakePoint(-98.3014, 19.0633), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text("DELETE FROM incident_actions WHERE incident_id = :i"), {"i": INCIDENT}
        )
        await conn.execute(text("DELETE FROM incidents WHERE incident_id = :i"), {"i": INCIDENT})
        await conn.execute(
            text(
                "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
                "opened_at, severity, state, trigger) "
                "VALUES (:i, gen_random_uuid(), :t, :s, now(), 'critical', 'open', 'manual')"
            ),
            {"i": INCIDENT, "t": au.DB_TENANT_PRIV, "s": SITE},
        )


def _tactico(user_id: str) -> str:
    return au.make_token(
        TACTICO, surface="mobile", site_scope=SITE, user_id=user_id, tenant=au.DB_TENANT_PRIV
    )


async def _ack(client, token: str):
    return await client.post(f"/incidents/{INCIDENT}/tactical-ack", headers=au.bearer(token))


async def _acuses() -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT actor, kind, payload FROM incident_actions "
                    "WHERE incident_id = :i AND kind = 'tactical_ack' ORDER BY ts"
                ),
                {"i": INCIDENT},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def _estado() -> str:
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            await conn.execute(
                text("SELECT state FROM incidents WHERE incident_id = :i"), {"i": INCIDENT}
            )
        ).scalar_one()


# --- El acuse ----------------------------------------------------------------


async def test_un_tactico_puede_acusar(client, incidente) -> None:
    """La señal que `T-2.147.c` necesita para saber que alguien respondió."""
    resp = await _ack(client, _tactico("70000000-0000-0000-0000-0000000ac001"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["acked"] is True
    assert body["already"] is False

    acuses = await _acuses()
    assert len(acuses) == 1, f"se esperaba un acuse, hay {len(acuses)}"
    assert acuses[0]["kind"] == "tactical_ack"


async def test_el_acuse_de_la_brigada_NO_mueve_el_estado_del_incidente(client, incidente) -> None:
    """LA SEPARACIÓN QUE JUSTIFICA LA FICHA.

    Si el acuse táctico moviera `open→acked`, un brigadista vaciaría la cola del
    SOC desde el teléfono — y el SOC dejaría de ver como pendiente algo que nadie
    de monitoreo ha mirado.
    """
    assert await _estado() == "open", "premisa: el incidente nace abierto"

    resp = await _ack(client, _tactico("70000000-0000-0000-0000-0000000ac002"))
    assert resp.status_code == 200, resp.text

    assert await _estado() == "open", (
        "el acuse de la brigada movió el estado del incidente: eso es el acuse "
        "del SOC, y no lo firma quien baja a mirar sino quien monitorea"
    )
    assert resp.json()["incident_state"] == "open"


async def test_acusar_dos_veces_no_cuenta_dos_personas(client, incidente) -> None:
    """Idempotencia POR PERSONA.

    Lo que `T-2.147.c` mide es cuántas PERSONAS respondieron. Sin esta guarda, un
    dedo nervioso o un reintento de la app inflaría el conteo y el escalado al
    SOC se apagaría con una sola persona pulsando dos veces.
    """
    token = _tactico("70000000-0000-0000-0000-0000000ac003")
    primero = await _ack(client, token)
    segundo = await _ack(client, token)

    assert primero.json()["already"] is False
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["already"] is True, (
        "el segundo acuse del MISMO táctico no se declaró como repetido"
    )
    assert len(await _acuses()) == 1, "una sola persona dejó dos acuses"


async def test_dos_tacticos_distintos_cuentan_dos(client, incidente) -> None:
    """No-vacuidad de la idempotencia: la guarda es por PERSONA, no por incidente.

    Sin este test, un `NOT EXISTS` demasiado amplio —que bloqueara cualquier
    segundo acuse— pasaría el test anterior y dejaría al SOC creyendo que solo
    respondió una persona cuando respondió media brigada.
    """
    await _ack(client, _tactico("70000000-0000-0000-0000-0000000ac004"))
    await _ack(client, _tactico("70000000-0000-0000-0000-0000000ac005"))

    acuses = await _acuses()
    assert len(acuses) == 2, f"dos tácticos distintos dejaron {len(acuses)} acuses"
    assert len({a["actor"] for a in acuses}) == 2


# --- Guardas de acceso -------------------------------------------------------


async def test_un_occupant_no_puede_acusar(client, incidente) -> None:
    """El occupant vota el pánico; no lo atiende.

    Dejarle acusar apagaría el escalado al SOC con la respuesta de quien pulsó
    la alarma, que es justo lo contrario de lo que el escalado comprueba.
    """
    resp = await _ack(client, au.occupant_token(tenant=au.DB_TENANT_PRIV))
    assert resp.status_code == 403, resp.text
    assert await _acuses() == []


async def test_un_tactico_fuera_de_alcance_recibe_404(client, incidente) -> None:
    """Mismo 404 que «no existe»: no se filtra la existencia del incidente."""
    otro_sitio = "7c500000-0000-0000-0000-0000000001ff"
    token = au.make_token(
        TACTICO,
        surface="mobile",
        site_scope=otro_sitio,
        user_id="70000000-0000-0000-0000-0000000ac006",
        tenant=au.DB_TENANT_PRIV,
    )
    resp = await _ack(client, token)
    assert resp.status_code == 404, resp.text
    assert await _acuses() == []


# --- La invariante de los dos círculos ---------------------------------------


def test_los_dos_circulos_son_el_mismo() -> None:
    """Quien RECIBE el push y quien puede ACUSARLO salen de la misma acción.

    Si divergieran, alguien despertado a las 3 a.m. sin permiso para acusar
    parecería «sin respuesta» para siempre y dispararía el aviso al SOC por un
    fallo de permisos, no por una brigada ausente.
    """
    assert set(TACTICAL_ACK_ROLES) == set(roles_with_action("manual_activate")), (
        "el círculo que acusa dejó de ser el que recibe el push: un táctico "
        "despertado sin poder acusar escalaría al SOC por un fallo de permisos"
    )
    assert TACTICAL_ACK_ROLES, "el círculo salió vacío: nadie podría acusar jamás"


def test_los_roles_de_MONITOREO_no_entran_por_esta_puerta() -> None:
    """El SOC tiene su propio acuse; este no es el suyo.

    Guarda sobre la MATRIZ: el día que un rol de monitoreo ganara
    `manual_activate`, su acuse contaría como respuesta de la brigada y
    `T-2.147.c` quedaría derogada por un cambio de permisos.
    """
    monitoreo = {r for r, acts in ROLE_ACTION_MATRIX.items() if acts.get("ack_incident")}
    solapan = monitoreo & set(TACTICAL_ACK_ROLES)
    assert not solapan, (
        f"{solapan} pueden acusar por las DOS puertas: su acuse de monitoreo "
        "apagaría el escalado al SOC sin que nadie bajara a mirar"
    )
