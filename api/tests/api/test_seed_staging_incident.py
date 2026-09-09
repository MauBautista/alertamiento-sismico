"""[T-6.18] EL SEMBRADOR DE STAGING VUELVE A EJERCER LO QUE PROMETE.

`infra/scripts/seed_staging_incident.sh` es el arnés que pone al sitio del
occupant en la fase que cada flujo Maestro necesita (GATE-HW móvil). Cuatro de
los cinco flujos exigen un incidente ACTIVO, y **dejó de producirlo**: el id del
incidente era una constante, así que `crisis` REABRÍA el mismo, y en cuanto una
corrida pasaba por `reentry` ese incidente se quedaba con un dictamen firmado
—`dictamens` es append-only— para siempre. La derivación de `mobile_site.py`
busca el dictamen POR INCIDENTE y `reentry_approved` gana a `alert_active`: a
partir de ahí `PHASE=crisis` devolvía «reingreso aprobado» y el flujo 01 no
podía pasar. Lo cazó la auditoría UI/UX del 2026-09-06 (U-37) cuando hizo falta
un id fresco a mano para poder medir la toma de crisis.

**Por qué este test existe y no un comentario en el script.** Un arnés que nadie
ejerce se pudre en silencio: el script seguía corriendo sin error y devolviendo
la fase equivocada. Aquí se corren **los mismos ficheros SQL** que corre el
script —`infra/scripts/sql/staging-incident/*.sql`, la única copia— contra la
base de tests, y se comprueba la fase por el **endpoint real** que lee la app,
no por la réplica del propio script. Lo que el script no puede traer a CI es su
túnel SSM a la nube; todo lo demás es esto.

La réplica en SQL que el script imprime al operador se compara además con el
endpoint en las cuatro fases: dos derivaciones de la misma cosa que nadie
comparaba, y esa es la forma en que un espejo se separa.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.anyio

#: La ÚNICA copia del SQL del sembrador. Si alguien lo mueve, este test no lo
#: encuentra y se pone rojo en vez de pasar mirando a otro lado.
SQL_DIR = Path(__file__).resolve().parents[3] / "infra" / "scripts" / "sql" / "staging-incident"

# UUIDs propios (prefijo 7e18 — libre en la suite).
SITE_X = "7e180000-0000-0000-0000-00000000015d"
ZONE_X = "7e180000-0000-0000-0000-0000000000e1"
OCC_X = "7e180000-0000-0000-0000-0000000cc001"


def _sustituir(sql: str, variables: dict[str, str]) -> str:
    """Resuelve los `:'nombre'` de psql como los resuelve psql: literal citado.

    Es la única pieza que este test aporta sobre el script, y por eso se afirma
    aparte (`test_la_sustitucion_es_la_de_psql`): si difiere, el test estaría
    ejerciendo un SQL que nadie corre.
    """
    faltan = {m for m in re.findall(r":'([a-z_]+)'", sql)} - set(variables)
    assert not faltan, f"el SQL pide variables que nadie da: {sorted(faltan)}"
    for nombre, valor in variables.items():
        sql = sql.replace(f":'{nombre}'", "'" + valor.replace("'", "''") + "'")
    return sql


async def _correr(fichero: str, variables: dict[str, str]) -> None:
    """Corre un subcomando del sembrador tal cual lo corre `psql -f`.

    El fichero entero de una vez, sin partirlo por `;`: los comentarios del SQL
    llevan puntos y comas (`schema.sql:214-216; event_uuid…`) y trocear por ahí
    ejecutaba prosa. Es lo mismo que hace `psql -f`.
    """
    cuerpo = _sustituir((SQL_DIR / fichero).read_text("utf-8"), variables)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.exec_driver_sql(cuerpo)


async def _replica_del_script(variables: dict[str, str]) -> str:
    """La fase tal como la imprime el script (su réplica en SQL)."""
    cuerpo = _sustituir((SQL_DIR / "phase.sql").read_text("utf-8"), variables)
    engine = get_engine()
    async with engine.begin() as conn:
        linea = (await conn.execute(text(cuerpo.rstrip().rstrip(";")))).scalar_one()
    return str(linea).split("|")[0].replace("phase=", "").strip()


@pytest.fixture(autouse=True)
def _pool_de_ocupantes(monkeypatch: pytest.MonkeyPatch) -> None:
    """El ocupante vive en su propio pool de Cognito: sin esto su token es de
    otro issuer y la API responde 401."""
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
async def sitio_del_occupant(base_data) -> None:
    """El sitio, la zona y el ocupante que el sembrador da por sembrados.

    En staging los pone `db/seeds/prod_fleet.sql` + `seed_mobile_users.sh`; el
    script solo comprueba que existan (y aborta con un mensaje claro si no).
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-SEED18', 'Sitio del sembrador', "
                "ST_SetSRID(ST_MakePoint(-98.2063, 19.0414), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_X, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name) "
                "VALUES (:z, :t, :s, 'PB-A') ON CONFLICT (zone_id) DO NOTHING"
            ),
            {"z": ZONE_X, "t": au.DB_TENANT_PRIV, "s": SITE_X},
        )
        await conn.execute(
            text(
                "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, zone_id, role) "
                "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
            ),
            {"u": OCC_X, "t": au.DB_TENANT_PRIV, "s": SITE_X, "z": ZONE_X},
        )


async def _fase(client) -> str:
    """La fase por el ENDPOINT REAL: lo que la app lee, no lo que el script cree."""
    token = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_X)
    resp = await client.get(f"/sites/{SITE_X}/mobile-state", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text
    return str(resp.json()["phase"])


async def _crisis(variables: dict[str, str]) -> dict[str, str]:
    """`crisis` con un incidente fresco, como lo genera el script (en la base)."""
    engine = get_engine()
    async with engine.begin() as conn:
        iid = str((await conn.execute(text("SELECT gen_random_uuid()"))).scalar_one())
        euuid = str((await conn.execute(text("SELECT gen_random_uuid()"))).scalar_one())
    nuevas = {**variables, "iid": iid, "euuid": euuid}
    await _correr("crisis.sql", nuevas)
    return nuevas


@pytest.fixture
def variables() -> dict[str, str]:
    return {
        "tenant": au.DB_TENANT_PRIV,
        "site": SITE_X,
        "zone": ZONE_X,
        "iid": "",
        "euuid": "",
        "uid": OCC_X,
    }


async def test_la_sustitucion_es_la_de_psql() -> None:
    """Sin esto, el test podría estar ejerciendo un SQL que nadie corre."""
    assert _sustituir("WHERE x = :'site'", {"site": "abc"}) == "WHERE x = 'abc'"
    assert _sustituir("v = :'a' AND w = :'a'", {"a": "1"}) == "v = '1' AND w = '1'"
    # Una comilla en el valor no puede cerrar el literal.
    assert _sustituir(":'a'", {"a": "o'brien"}) == "'o''brien'"
    with pytest.raises(AssertionError):
        _sustituir("WHERE x = :'desconocida'", {"site": "abc"})


async def test_el_sembrador_recorre_las_cuatro_fases(client, sitio_del_occupant, variables) -> None:
    """crisis → conclude → reentry → reset, por el endpoint que lee la app."""
    assert await _fase(client) == "idle"

    v = await _crisis(variables)
    assert await _fase(client) == "alert_active"

    await _correr("conclude.sql", v)
    assert await _fase(client) == "shaking_concluded"

    await _correr("reentry.sql", v)
    assert await _fase(client) == "reentry_approved"

    await _correr("reset.sql", v)
    assert await _fase(client) == "idle"


async def test_crisis_vuelve_a_la_toma_de_crisis_tras_un_dictamen_firmado(
    client, sitio_del_occupant, variables
) -> None:
    """EL DEFECTO DE U-37, en una prueba.

    Con el id constante, esta segunda `crisis` reabría el incidente que ya tenía
    el dictamen firmado y la app seguía en `reentry_approved`: el flujo 01 de
    Maestro —la toma de crisis— no podía pasar nunca más en ese sitio, y no había
    nada que lo dijera. Ahora `crisis` cierra lo abierto y abre uno NUEVO, que
    todavía no tiene dictamen.
    """
    primera = await _crisis(variables)
    await _correr("reentry.sql", primera)
    assert await _fase(client) == "reentry_approved"

    segunda = await _crisis(variables)
    assert segunda["iid"] != primera["iid"], "`crisis` reusó el incidente anterior"
    assert await _fase(client) == "alert_active"

    # …y el anterior quedó CERRADO: dos incidentes abiertos en el mismo sitio
    # harían que la fase dependiera de cuál gana el ORDER BY.
    engine = get_engine()
    async with engine.begin() as conn:
        abiertos = (
            await conn.execute(
                text("SELECT count(*) FROM incidents WHERE site_id = :s AND state <> 'closed'"),
                {"s": SITE_X},
            )
        ).scalar_one()
    assert abiertos == 1


async def test_la_replica_del_script_no_se_separa_del_endpoint(
    client, sitio_del_occupant, variables
) -> None:
    """El script imprime su propia derivación en SQL; el endpoint es la verdad.

    Son dos copias de la misma regla y nadie las comparaba. Se comparan en las
    cuatro fases: el día que `mobile_site.py` cambie de criterio, el operador no
    se quedará leyendo una fase que ya no existe.
    """
    v = await _crisis(variables)
    assert await _replica_del_script(v) == await _fase(client) == "alert_active"

    await _correr("conclude.sql", v)
    assert await _replica_del_script(v) == await _fase(client) == "shaking_concluded"

    await _correr("reentry.sql", v)
    assert await _replica_del_script(v) == await _fase(client) == "reentry_approved"

    await _correr("reset.sql", v)
    assert await _replica_del_script(v) == await _fase(client) == "idle"
