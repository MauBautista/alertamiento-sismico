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
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.notify.orchestrator import _HEADCOUNT_NOTIFY_SQL

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


async def test_el_pase_de_lista_es_lo_QUE_EL_NOTIFICADOR_BUSCA(
    sitio_del_occupant, variables
) -> None:
    """[T-7.03] `headcount` existe para que suene un teléfono, no para mover la fase.

    Los demás subcomandos mueven la fase que la app DERIVA al sondear
    `mobile-state`, y eso no despierta a nadie: con la app detrás no hay sondeo.
    El único camino a un push real es una fila de `incident_actions` de las dos
    clases que el orquestador busca, y hasta esta ficha el sembrador no producía
    ninguna: se podía «ensayar una crisis» entera sin que ningún teléfono
    recibiera nada, y nada lo decía.

    La afirmación se hace con el SQL DEL ORQUESTADOR, importado, no con una copia
    del literal `'headcount_notify'`: el día que aquel cambie de clase, este test
    se pone rojo en vez de seguir sembrando una acción que ya no mira nadie.
    """
    v = await _crisis(variables)
    await _correr("headcount.sql", v)

    engine = get_engine()
    async with engine.begin() as conn:
        filas = (
            (
                await conn.execute(
                    text(
                        _HEADCOUNT_NOTIFY_SQL.replace("%(since)s", ":desde").replace(
                            "%(now)s", ":ahora"
                        )
                    ),
                    {
                        "desde": datetime.now(UTC) - timedelta(minutes=5),
                        "ahora": datetime.now(UTC) + timedelta(minutes=5),
                    },
                )
            )
            .mappings()
            .all()
        )

    nuestras = [f for f in filas if str(f["incident_id"]) == v["iid"]]
    assert len(nuestras) == 1, (
        "el notificador no ve la acción del sembrador: sin ella no encola push "
        f"(vio {len(nuestras)} para el incidente {v['iid']})"
    )
    assert str(nuestras[0]["site_id"]) == SITE_X


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


# ── [T-7.52 · D-34] LA GUARDA: el arnés no escribe donde hay un gabinete ─────
#
# Hasta el 2026-09-17 el sitio por defecto del arnés era `site-dev` = **Puebla, el
# del gabinete REAL `gw-dev-0001`**, y como `reset`/`crisis` cierran TODOS los
# incidentes abiertos del sitio, el arnés cerraba incidentes de OPERACIÓN. Lo
# destapó `T-7.51`: tres cerrados sin hora, con su dictamen diciendo «EN CURSO».


async def _sitio_para_la_guarda(sufijo: str, *, con_gabinete: bool) -> str:
    """Un sitio propio por prueba. ⚠️ El TRUNCATE del conftest es POR SESIÓN, así
    que un gabinete insertado en una prueba sobrevive a la siguiente: compartir
    sitio hacía que `DEJA_PASAR` abortara por el gabinete de la anterior."""
    site = f"7e180000-0000-0000-0000-00000000c{sufijo}"
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, :c, 'Sitio de la guarda', "
                "ST_SetSRID(ST_MakePoint(-98.2, 19.0), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": site, "t": au.DB_TENANT_PRIV, "c": f"S-GUARDA-{sufijo}"},
        )
        if con_gabinete:
            await conn.execute(
                text(
                    "INSERT INTO gateways "
                    "(gateway_id, tenant_id, site_id, serial, iot_thing, status) VALUES "
                    "(:g, :t, :s, :n, :n, 'provisioned') "
                    "ON CONFLICT (gateway_id) DO NOTHING"
                ),
                {
                    "g": f"7e180000-0000-0000-0000-00000000a{sufijo}",
                    "t": au.DB_TENANT_PRIV,
                    "s": site,
                    "n": f"gw-guarda-{sufijo}",
                },
            )
    return site


def _aborta(exc) -> None:
    """⚠️ La PRIMERA línea del error, no el texto completo.

    Un `ProgrammingError` de psycopg viene **citando el SQL entero**, así que
    buscar la frase en todo el mensaje casa con el propio fichero y la prueba
    pasa por fallar ANTES de la guarda, no por la guarda. Pasó el 2026-09-18 con
    los marcadores de formato de `RAISE`.
    """
    assert "ARNÉS ABORTADO" in str(exc.value).splitlines()[0], str(exc.value)[:300]


async def test_la_guarda_ABORTA_contra_un_sitio_con_gabinete(base_data, variables) -> None:
    """Un guardia que sólo se ha visto en verde no ha demostrado que sepa ponerse rojo."""
    variables = {**variables, "site": await _sitio_para_la_guarda("001", con_gabinete=True)}
    with pytest.raises(Exception) as exc:
        await _correr("guarda.sql", variables)
    _aborta(exc)


async def test_la_guarda_DEJA_PASAR_un_sitio_sin_gabinete(base_data, variables) -> None:
    """La otra mitad: una guarda que no deja pasar nada tampoco sirve."""
    variables = {**variables, "site": await _sitio_para_la_guarda("002", con_gabinete=False)}
    await _correr("guarda.sql", variables)  # no lanza


async def test_la_guarda_ABORTA_aunque_el_gabinete_lleve_MESES_MUDO(base_data, variables) -> None:
    """⚠️ Por qué la condición es EXISTENCIA y no «latido reciente».

    La ficha y `D-34` decían «un gateway con latido reciente». Eso deja el agujero
    justo donde más duele: mientras `gw-dev-0001` está CAÍDO —ha pasado dos veces,
    la energía del 28-jul y el hilo de reconexión que lo dejó mudo—, Puebla no
    tiene latido y una guarda con reloj **dejaría pasar al arnés contra el sitio
    real**. Un gabinete apagado no deja de ser un gabinete.
    """
    site = await _sitio_para_la_guarda("003", con_gabinete=True)
    engine = get_engine()
    async with engine.begin() as conn:
        # Ni una sola fila en `device_health`: este gabinete nunca ha reportado.
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM device_health dh JOIN gateways g USING (gateway_id) "
                    "WHERE g.site_id = :s"
                ),
                {"s": site},
            )
        ).scalar_one()
    assert n == 0, "el gabinete de la prueba tiene latidos: no mide lo que dice medir"

    with pytest.raises(Exception) as exc:
        await _correr("guarda.sql", {**variables, "site": site})
    _aborta(exc)


def test_la_guarda_NO_depende_de_interpolar_dentro_de_un_bloque() -> None:
    """⚠️ La trampa que la habría dejado VERDE EN CI E INERTE EN LA NUBE.

    **Medido el 2026-09-18 contra Postgres:** psql NO interpola sus variables
    dentro de un cuerpo con comillas de dólar —llega el literal `:'site'`—, pero
    el `_sustituir` de este fichero SÍ las sustituye. Una guarda escrita de la
    forma obvia pasaría estas pruebas y no protegería nada donde importa: el
    mismo patrón de espejo que este repositorio ya ha pagado cuatro veces.

    Por eso el valor entra con `set_config` FUERA del bloque y se lee con
    `current_setting` DENTRO, y por eso esto se comprueba leyendo el fichero.
    """
    sql = (SQL_DIR / "guarda.sql").read_text("utf-8")
    cuerpos = re.findall(r"\$[a-z_]*\$(.*?)\$[a-z_]*\$", sql, re.S)
    assert cuerpos, "no se encontró ningún bloque con comillas de dólar en guarda.sql"
    dentro = [v for cuerpo in cuerpos for v in re.findall(r":'([a-z_]+)'", cuerpo)]
    assert not dentro, (
        f"`guarda.sql` interpola {sorted(set(dentro))} DENTRO de un bloque: psql no lo hace "
        "(llega el literal), pero `_sustituir` de este test sí. La guarda pasaría en CI y "
        "llegaría INERTE a la nube. Mete el valor con `set_config` fuera y léelo con "
        "`current_setting` dentro"
    )
    assert "set_config(" in sql and "current_setting(" in sql, (
        "`guarda.sql` dejó de usar el par `set_config`/`current_setting`, que es lo único que "
        "hace que el valor llegue de verdad al cuerpo del bloque"
    )


def test_la_guarda_no_lleva_marcadores_de_formato() -> None:
    """El mismo fichero lo corre `psql -f` y lo corre **psycopg** desde el test.

    psycopg toma el signo de porcentaje como marcador suyo y revienta con «only
    's', 'b', 't' are allowed» ANTES de ejecutar nada — y **escanea también los
    comentarios**, así que ni siquiera se puede explicar el problema usándolo.
    Medido el 2026-09-18: con el signo dentro, las dos pruebas de aborto pasaban
    por casar su texto contra el SQL que el error viene citando.
    """
    sql = (SQL_DIR / "guarda.sql").read_text("utf-8")
    assert "%" not in sql, (
        "`guarda.sql` tiene un signo de porcentaje: psycopg lo toma como marcador suyo y el "
        "fichero deja de poder correrse desde el arnés de pruebas — con lo que lo que se "
        "prueba deja de ser lo que se corre"
    )


def test_la_ventana_de_reingreso_no_se_separa_del_ajuste() -> None:
    """[T-7.55] Tres sitios dicen lo mismo con números distintos, y ninguno vigilaba al otro.

    - `Settings.reentry_declare_s` — cuánto sigue el ENDPOINT declarando el reingreso.
    - `phase.sql` — la réplica que el arnés imprime al operador.
    - `reset.sql` — cuánto retrodata el cierre para que el sitio vuelva a `idle`.

    Si la réplica se quedara corta diría `idle` donde la app dice «REINGRESO
    AUTORIZADO», que es la divergencia que `T-6.18` puso a vigilar. Y si el
    retrodatado no superara la ventana, **`reset` dejaría de resetear**: el sitio
    seguiría declarando el reingreso durante horas después de limpiarlo.

    Los tres se leen de su fuente; ninguno se teclea aquí.
    """
    from takab_api.settings import Settings

    ventana_s = Settings().reentry_declare_s

    replica = (SQL_DIR / "phase.sql").read_text("utf-8")
    m = re.search(r"closed_at > now\(\) - interval '(\d+) hours'", replica)
    assert m, "la réplica dejó de acotar la ventana de reingreso: ya no puede coincidir"
    assert int(m.group(1)) * 3600 == ventana_s, (
        f"la réplica usa {m.group(1)} h y `reentry_declare_s` vale {ventana_s / 3600:.0f} h: "
        "el arnés diría una fase y la app otra"
    )

    reset = (SQL_DIR / "reset.sql").read_text("utf-8")
    r = re.search(r"closed_at = now\(\) - interval '(\d+) days'", reset)
    assert r, (
        "`reset.sql` volvió a cerrar con `now()`: con la ventana de reingreso viva, el sitio "
        "seguiría diciendo «REINGRESO AUTORIZADO» después de resetearlo"
    )
    assert int(r.group(1)) * 86400 > ventana_s, (
        f"`reset` retrodata {r.group(1)} d y la ventana es de {ventana_s / 3600:.0f} h: "
        "no la supera, así que resetear no devuelve el sitio a `idle`"
    )
