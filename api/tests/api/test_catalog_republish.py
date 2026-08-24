"""[T-2.148 · D-06] Republicar el MISMO catálogo no es publicar.

`D-06` decidió automatizar la ingesta del catálogo del SSN. Antes de poner un job
periódico encima hay que arreglar lo que hoy no duele porque lo llama una persona
a mano: `push_catalog` publicaba SIEMPRE.

LAS TRES CONSECUENCIAS, y ninguna se nota de una en una
--------------------------------------------------------
  · la **versión monótona** escala sin motivo;
  · `audit_log` es **append-only y exenta de poda** (regla de oro 11), así que
    cada renglón de ruido es **permanente**;
  · y cada publish **despierta al gabinete** por IoT y cuesta su línea en la
    política de flota.

Automatizar encima multiplica las tres por la cadencia del job. Por eso esto es
el prerrequisito de `T-2.149` y no un pulido.

LO CONTRARIO DEL SILENCIO
--------------------------
No publicar no puede significar no dejar rastro: sin `last_checked_at`, «el job
corre y no hay novedad» sería indistinguible de «el job murió», que es
exactamente el modo de fallo que `D-06` quería evitar al automatizar contra una
fuente de terceros. Es `D-01` aplicada: se declara lo que se sabe y cuándo.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.anyio

KEY = "clave-catalogo-test"
THING = "gw-catalogo-test"
GW = "7c500000-0000-0000-0000-0000000000d3"
SITE = "7c500000-0000-0000-0000-000000000160"

# El formato REAL del entregable, el que `edge/takab_edge/catalog.py::normalize_catalog`
# sabe leer. Hasta el 2026-08-22 este fixture usaba `{id, mag, prof_km}`, que **no es
# ninguno de los dos formatos**: pasaba la API y el gabinete lo habría rechazado entero.
# Un fixture que no puede existir en producción prueba una conducta que no existe.
CATALOGO = {
    "fuente": "SSN",
    "capturado": "2026-08-16T00:00:00Z",
    "eventos": [
        {
            "m": 5.2,
            "fecha": "2026-08-15",
            "hora": "23:10:00",
            "lat": 16.1,
            "lon": -98.2,
            "prof": 12,
            "loc": "15 km al SUR de PINOTEPA, OAX",
        },
        {
            "m": 4.1,
            "fecha": "2026-08-16",
            "hora": "01:02:03",
            "lat": 17.0,
            "lon": -99.5,
            "prof": 30,
            "loc": "20 km al ESTE de ACAPULCO, GRO",
        },
    ],
    "referencias": [{"n": "CDMX", "lat": 19.43, "lon": -99.13}],
}


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, json.loads(payload)))


@pytest.fixture
def publisher() -> _FakePublisher:
    return _FakePublisher()


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
async def gabinete(base_data) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-CAT', 'Sitio catálogo', "
                "ST_SetSRID(ST_MakePoint(-98.3014, 19.0633), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-CAT', :thing) ON CONFLICT (gateway_id) DO NOTHING"
            ),
            {"g": GW, "t": au.DB_TENANT_PRIV, "s": SITE, "thing": THING},
        )
        await conn.execute(
            text("DELETE FROM gateway_catalog_state WHERE gateway_id = :g"), {"g": GW}
        )
        await conn.execute(
            text("DELETE FROM audit_log WHERE object = :o AND verb = 'catalog_published'"),
            {"o": f"gateway:{GW}"},
        )


def _token() -> str:
    return au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)


async def _push(client, catalogo: dict):
    return await client.post(
        f"/gateways/{GW}/catalog", json={"catalog": catalogo}, headers=au.bearer(_token())
    )


async def _estado() -> dict | None:
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT version, published_at, last_checked_at "
                        "FROM gateway_catalog_state WHERE gateway_id = :g"
                    ),
                    {"g": GW},
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


async def _auditorias() -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE object = :o AND verb = 'catalog_published'"
                ),
                {"o": f"gateway:{GW}"},
            )
        ).scalar_one()


# --- La primera publicación sigue igual --------------------------------------


async def test_el_primer_catalogo_se_publica(client, gabinete, publisher) -> None:
    """Premisa de todo lo demás: lo nuevo sigue saliendo al aire."""
    resp = await _push(client, CATALOGO)
    assert resp.status_code == 202, resp.text
    assert resp.json()["version"] == 1
    assert resp.json()["unchanged"] is False
    assert len(publisher.published) == 1, "el catálogo nuevo no se publicó por IoT"
    assert await _auditorias() == 1


# --- LA PROPIEDAD QUE JUSTIFICA LA FICHA -------------------------------------


async def test_republicar_el_MISMO_catalogo_no_hace_nada(client, gabinete, publisher) -> None:
    """No publica, no quema versión y no audita.

    Las tres a la vez, porque las tres son acumulativas y ninguna se nota de una
    en una. Con el job de `D-06` encima, cada pasada haría las tres.
    """
    await _push(client, CATALOGO)
    antes = await _estado()
    publicados_antes = len(publisher.published)

    resp = await _push(client, CATALOGO)
    assert resp.status_code == 202, resp.text
    assert resp.json()["unchanged"] is True, "la respuesta fingió una publicación que no ocurrió"

    despues = await _estado()
    assert despues["version"] == antes["version"], (
        f"la versión saltó de {antes['version']} a {despues['version']} sin catálogo nuevo: "
        "con un job periódico escala sin motivo"
    )
    assert len(publisher.published) == publicados_antes, (
        "se despertó al gabinete por IoT para mandarle el catálogo que ya tenía"
    )
    assert await _auditorias() == 1, (
        "se escribió otro `catalog_published`: `audit_log` es append-only y EXENTA "
        "DE PODA, así que ese renglón de ruido es permanente"
    )


async def test_republicar_deja_constancia_de_que_se_miro(client, gabinete) -> None:
    """LO CONTRARIO DEL SILENCIO, y es la otra mitad de la ficha.

    Si no publicar significara no dejar rastro, «el job corre y no hay novedad»
    sería indistinguible de «el job murió» — el modo de fallo exacto que `D-06`
    quería evitar al automatizar contra una fuente de terceros.
    """
    await _push(client, CATALOGO)
    antes = await _estado()

    await _push(client, CATALOGO)
    despues = await _estado()

    assert despues["last_checked_at"] is not None, (
        "no quedó constancia de la comprobación: un catálogo que nadie sabe si se "
        "está mirando es un catálogo congelado en silencio"
    )
    assert despues["published_at"] == antes["published_at"], (
        "`published_at` se movió sin publicar: entonces deja de significar «cuándo "
        "se publicó» y ya no distingue las dos cosas"
    )


async def test_reordenar_las_claves_no_es_un_catalogo_nuevo(client, gabinete, publisher) -> None:
    """La comparación es sobre la forma CANÓNICA, la misma que se firma.

    Un feed de terceros puede reordenar claves entre respuestas sin que haya
    cambiado un solo dato. Comparar el JSON crudo convertiría cada reordenación
    en una publicación — y el gabinete se despertaría por nada.
    """
    await _push(client, CATALOGO)
    publicados = len(publisher.published)

    # Se DERIVA del fixture invirtiendo el orden de las claves, en vez de copiarlo a
    # mano. La copia a mano ya se pagó una vez: cuando el fixture se corrigió al
    # formato real, esta literal se quedó con el viejo y el test empezó a probar otra
    # cosa. Derivándolo, «mismos datos, otro orden» es cierto por construcción.
    reordenado = {
        "eventos": [dict(reversed(list(e.items()))) for e in CATALOGO["eventos"]],
        "referencias": [dict(reversed(list(r.items()))) for r in CATALOGO["referencias"]],
        "capturado": CATALOGO["capturado"],
        "fuente": CATALOGO["fuente"],
    }
    assert list(reordenado["eventos"][0]) != list(CATALOGO["eventos"][0]), (
        "el reordenado salió con el MISMO orden de claves: el test no probaría nada"
    )
    resp = await _push(client, reordenado)

    assert resp.json()["unchanged"] is True, (
        "reordenar las claves se leyó como catálogo nuevo: un feed que las "
        "reordene despertaría al gabinete en cada pasada del job"
    )
    assert len(publisher.published) == publicados


# --- Lo distinto sigue saliendo ----------------------------------------------


async def test_un_catalogo_DISTINTO_si_se_publica(client, gabinete, publisher) -> None:
    """NO-VACUIDAD. Sin esto, «no publica» pasaría por no publicar nunca."""
    await _push(client, CATALOGO)

    nuevo = {
        "capturado": "2026-08-16T06:00:00Z",
        "eventos": [
            *CATALOGO["eventos"],
            {
                "m": 6.0,
                "fecha": "2026-08-16",
                "hora": "04:00:00",
                "lat": 15.5,
                "lon": -96.1,
                "prof": 8,
                "loc": "40 km al SUR de HUATULCO, OAX",
            },
        ],
    }
    resp = await _push(client, nuevo)

    assert resp.status_code == 202, resp.text
    assert resp.json()["unchanged"] is False
    assert resp.json()["version"] == 2, "un catálogo nuevo tiene que quemar versión"
    assert len(publisher.published) == 2, "el catálogo nuevo no llegó al gabinete"
    assert await _auditorias() == 2, "un catálogo nuevo SÍ tiene que dejar su renglón"


async def test_solo_cambiar_capturado_ya_es_catalogo_nuevo(client, gabinete, publisher) -> None:
    """El sello de captura forma parte de lo que se firma, así que cuenta.

    Es deliberado: `capturado` es lo que el panel del gabinete pinta como edad
    del catálogo. Ignorarlo dejaría al Pi declarando una antigüedad que ya no es
    la real.
    """
    await _push(client, CATALOGO)
    resp = await _push(client, {**CATALOGO, "capturado": "2026-08-16T12:00:00Z"})

    assert resp.json()["unchanged"] is False
    assert len(publisher.published) == 2
