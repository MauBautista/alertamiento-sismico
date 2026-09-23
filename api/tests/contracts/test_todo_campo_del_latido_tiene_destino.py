"""Todo campo de `HealthSnapshot` aterriza, o DECLARA por qué no (T-7.53).

EL DEFECTO QUE CIERRA
---------------------
`disk_used_pct` está en el contrato desde `T-1.53`. El gabinete lo publica en
cada latido, el panel LAN lo pinta… y la nube **no tenía columna**: el handler lo
recibía y lo tiraba. Llevaba meses así y **nada avisaba**, porque un campo del
contrato sin destino no falla — simplemente desaparece.

Es el mismo mecanismo que dejó a la nube sin poder ver que un gabinete retenía
evidencia: el dato no existía arriba, así que nadie podía echarlo de menos.

POR QUÉ ESTO ES UN CENSO
------------------------
Añadir las columnas tarda cinco minutos y deja el hueco abierto para el siguiente
campo. Las dos poblaciones se **derivan**:

1. **Los campos** salen del propio modelo Pydantic del edge.
2. **Las columnas** salen del `CREATE TABLE device_health` de `db/schema.sql`.

Lo único escrito a mano es la **traducción** entre unos y otras —que no es 1:1 y
no puede serlo: `captured_at` es `ts`, `ntp_offset_s` viaja en milisegundos, y de
`relays` no se persiste el censo sino si el gabinete **pudo** obtenerlo— y la
lista de lo que **deliberadamente no se persiste, con su razón**. Un campo nuevo
que no esté en ninguna de las dos cae aquí, que es justo lo que no pasó con
`disk_used_pct`.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.fleet import router as fleet_router
from takab_api.schemas.fleet import GatewayOut

_RAIZ = Path(__file__).resolve().parents[3]
_SCHEMA = _RAIZ / "db" / "schema.sql"

# El contrato vive en el edge, que no es un paquete instalado en el venv del api.
sys.path.insert(0, str(_RAIZ / "edge"))
from takab_edge.contracts import HealthSnapshot  # noqa: E402

#: Cómo se llama en `device_health` cada campo del latido. **No es 1:1 a
#: propósito** y por eso se escribe: hay conversión de unidades (`ntp_offset_s` →
#: `ntp_offset_ms`), de vocabulario (`ups_status` → `power_status`) y de
#: significado (`ups_runtime_s`, en segundos, aterriza en `battery_min_left`, en
#: minutos). De `relays` no se guarda el censo canal a canal sino **si el
#: gabinete pudo obtenerlo**, que es otro hecho.
DESTINO: dict[str, str] = {
    "captured_at": "ts",
    "gateway_id": "gateway_id",
    "transition_reason": "reason",
    "ntp_offset_s": "ntp_offset_ms",
    "seedlink_lag_s": "seedlink_lag_s",
    "packet_loss_pct": "packet_loss_pct",
    "mqtt_rtt_ms": "mqtt_rtt_ms",
    "ups_status": "power_status",
    "battery_pct": "battery_pct",
    "ups_runtime_s": "battery_min_left",
    "temperature_c": "cpu_temp_c",
    "cert_days_remaining": "cert_days_remaining",
    "relays": "relays_state",
    "disk_used_pct": "disk_used_pct",
    "evidence_pending": "evidence_pending",
    "evidence_oldest_age_s": "evidence_oldest_age_s",
    "evidence_oldest_event_id": "evidence_oldest_event_id",
}

#: Lo que **no se persiste, y por qué**. Estar aquí es una decisión escrita, no un
#: olvido: es la diferencia entre «la nube no lo guarda porque nadie lo consume»
#: y «la nube lo tira y nadie se ha dado cuenta», que es lo que le pasó a
#: `disk_used_pct` durante meses.
NO_PERSISTIDO: dict[str, str] = {
    "fw_version": (
        "[T-1.74] Sí se persiste, pero en `gateways.fw_version`, no en la fila fechada: es "
        "un atributo del gabinete, no una medición del instante. Y NUNCA se pisa con un "
        "None — ese campo se llenaba a mano y se habría quedado obsoleto en silencio."
    ),
    "fw_running": (
        "[T-2.70] Ídem, en `gateways.fw_running`. Las dos juntas son lo único que responde "
        "«¿se aplicó la actualización?»: el disco cambia con el rsync, el proceso sólo con "
        "el reinicio."
    ),
    "audio": (
        "[T-2.49] Perfil de tonos EFECTIVO del gabinete. No se persiste porque no hay "
        "consumidor en la nube: lo lee el panel LAN, que es quien decide qué puede sonar. "
        "El día que la consola necesite responder «¿qué gabinetes se quedaron atrás de un "
        "cambio de catálogo?» hará falta columna, y entonces esta línea se borra en vez de "
        "añadirse una excepción."
    ),
}


def _columnas_de_device_health() -> set[str]:
    sql = _SCHEMA.read_text(encoding="utf-8")
    m = re.search(r"CREATE TABLE device_health\s*\((.*?)\n\);", sql, re.S)
    assert m, "no se encontró `CREATE TABLE device_health` en db/schema.sql"
    cuerpo = re.sub(r"--[^\n]*", "", m.group(1))  # fuera los comentarios, que llevan comas
    columnas = set()
    for linea in cuerpo.split(","):
        palabras = linea.split()
        if palabras and palabras[0].isidentifier() and palabras[0] not in {"PRIMARY", "CHECK"}:
            columnas.add(palabras[0])
    return columnas


def test_todo_campo_del_latido_tiene_destino_o_esta_declarado() -> None:
    """⚠️ El censo que habría cazado los meses de `disk_used_pct` en el vacío."""
    campos = set(HealthSnapshot.model_fields)
    cubiertos = set(DESTINO) | set(NO_PERSISTIDO)

    huerfanos = sorted(campos - cubiertos)
    assert not huerfanos, (
        f"campo(s) de `HealthSnapshot` sin destino declarado: {huerfanos}. O se les da "
        "columna en `device_health`, o se declaran en `NO_PERSISTIDO` con su razón. Un campo "
        "del contrato sin destino no falla: el handler lo recibe y lo TIRA, y nada avisa — "
        "es lo que le pasó a `disk_used_pct` desde T-1.53 hasta T-7.53"
    )

    fantasmas = sorted(cubiertos - campos)
    assert not fantasmas, (
        f"este censo nombra campo(s) que `HealthSnapshot` ya no tiene: {fantasmas}. "
        "Una traducción a un campo muerto es una línea que nadie volverá a leer"
    )


def test_los_destinos_declarados_EXISTEN_en_la_tabla() -> None:
    """La otra punta del cable: apuntar a una columna que no existe es lo mismo que nada.

    Sin esto, la traducción podría nombrar una columna imaginaria y el censo de
    arriba aprobaría igual — que es exactamente la forma de ceremonia que este
    repositorio ya ha pagado varias veces.
    """
    columnas = _columnas_de_device_health()
    assert len(columnas) >= 15, (
        f"sólo se leyeron {len(columnas)} columnas de `device_health`: el parser se rompió y "
        "este censo estaría comparando contra casi nada"
    )
    inventadas = sorted({c for c in DESTINO.values() if c not in columnas})
    assert not inventadas, (
        f"la traducción apunta a columna(s) que `device_health` no tiene: {inventadas}. "
        f"Las que hay son: {sorted(columnas)}"
    )


def test_lo_no_persistido_lleva_su_RAZON_escrita() -> None:
    """Una lista de exenciones sin razones es una lista de olvidos con mejor letra."""
    flojas = sorted(campo for campo, razon in NO_PERSISTIDO.items() if len(razon.strip()) < 60)
    assert not flojas, (
        f"campo(s) declarados no persistidos sin una razón que se pueda revocar: {flojas}. "
        "La razón es lo único que permite decidir, dentro de un año, si sigue valiendo"
    )


# --------------------------------------------------------------------------
# [A-056 · T-8.09] …y de la COLUMNA a la SALIDA de la API.
# --------------------------------------------------------------------------
#
# El censo de arriba cerró el hueco «campo del contrato → columna». Quedaba el
# siguiente tramo del mismo cable, y se rompió igual: `GET /fleet/gateways`
# SELECCIONABA `evidence_pending`, `evidence_oldest_age_s` y `disk_used_pct`, el
# schema `GatewayOut` los DECLARABA, y el constructor del router no los pasaba.
# La API respondía `null` siempre, y la consola pintaba en TODAS las tarjetas
# «EVIDENCIA · s/d · el gabinete no pudo mirar» — culpando al gabinete de un
# fallo de la API (regla de oro 7). Este censo sólo miraba la columna, así que
# no lo vio.
#
# La población se DERIVA: toda columna destino de `DESTINO` que `GatewayOut`
# declare con el mismo nombre tiene que llegar a la respuesta con el valor del
# último latido. Lo único escrito a mano es un valor de MUESTRA por columna, y
# una columna nueva sin muestra FALLA pidiéndola — no se salta en silencio.

#: Un valor NO NULO y distinguible por columna. `gateway_id` no lleva muestra:
#: es la llave de la fila y siempre viaja.
MUESTRA: dict[str, object] = {
    "ntp_offset_ms": 7.25,
    "seedlink_lag_s": 0.75,
    "packet_loss_pct": 1.5,
    "mqtt_rtt_ms": 42.5,
    "power_status": "line",
    "battery_pct": 88.0,
    "cert_days_remaining": 123,
    "relays_state": "reported",
    "disk_used_pct": 71.5,
    "evidence_pending": 2,
    "evidence_oldest_age_s": 2940.0,
}

_T = "e7c00000-0000-0000-0000-000000000001"
_S = "e7c10000-0000-0000-0000-000000000001"
_GW = "e7c20000-0000-0000-0000-000000000001"


def _columnas_en_la_salida() -> list[str]:
    return sorted(c for c in DESTINO.values() if c in GatewayOut.model_fields and c != "gateway_id")


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


def test_cada_columna_que_la_API_declara_tiene_MUESTRA() -> None:
    """El censo no puede saltarse una columna nueva por no saber qué sembrar."""
    sin_muestra = sorted(set(_columnas_en_la_salida()) - set(MUESTRA))
    assert not sin_muestra, (
        f"columna(s) del latido que `GatewayOut` declara y este censo no sabe sembrar: "
        f"{sin_muestra}. Añade un valor NO NULO en `MUESTRA`"
    )
    assert len(_columnas_en_la_salida()) >= 10, "el cruce DESTINO × GatewayOut salió casi vacío"


@pytest.fixture
def _latido_completo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    if os.environ.get("DATABASE_URL"):
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", os.environ["DATABASE_URL"])
    deps._reset_caches()
    get_engine.cache_clear()
    columnas = _columnas_en_la_salida()
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) "
            "VALUES (%s, 'T809C', 'T-8.09 censo', 'private') ON CONFLICT DO NOTHING",
            (_T,),
        )
        cur.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES (%s, %s, 'S809C', "
            "'Censo', ST_SetSRID(ST_MakePoint(-98.2, 19.0), 4326)::geography) "
            "ON CONFLICT DO NOTHING",
            (_S, _T),
        )
        cur.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
            "VALUES (%s, %s, %s, 'GW-CENSO-809') ON CONFLICT DO NOTHING",
            (_GW, _T, _S),
        )
        cur.execute(
            f"INSERT INTO device_health (ts, tenant_id, gateway_id, reason, {', '.join(columnas)}) "
            f"VALUES (%s, %s, %s, 'heartbeat', {', '.join(['%s'] * len(columnas))})",
            (datetime.now(tz=UTC), _T, _GW, *[MUESTRA[c] for c in columnas]),
        )
    yield columnas
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM device_health WHERE tenant_id = %s", (_T,))
        cur.execute("DELETE FROM gateways WHERE tenant_id = %s", (_T,))
        cur.execute("DELETE FROM sites WHERE tenant_id = %s", (_T,))
        cur.execute("DELETE FROM tenants WHERE tenant_id = %s", (_T,))
    deps._reset_caches()


async def test_cada_campo_del_latido_que_la_API_declara_LLEGA_a_la_respuesta(
    _latido_completo: list[str],
) -> None:
    """⚠️ El censo que habría cazado la evidencia y el disco en `null` para siempre."""
    app = create_app()
    app.include_router(fleet_router)
    try:
        async with au.client_for(app) as c:
            r = await c.get(
                "/fleet/gateways",
                headers=au.bearer(au.make_token("soc_operator", tenant=_T, surface="web")),
            )
    finally:
        await get_engine().dispose()
        get_engine.cache_clear()
    assert r.status_code == 200, r.text
    fila = {g["gateway_id"]: g for g in r.json()}[_GW]
    perdidas = sorted(c for c in _latido_completo if fila.get(c) != MUESTRA[c])
    assert not perdidas, (
        f"`GET /fleet/gateways` declara {perdidas} y NO los entrega (salen "
        f"{ {c: fila.get(c) for c in perdidas} }): la columna existe y el schema la "
        "declara, pero el constructor del router no la pasa. Es lo que dejó a la consola "
        "diciendo «el gabinete no pudo mirar» de TODOS los gabinetes"
    )
