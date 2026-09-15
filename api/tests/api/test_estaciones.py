"""[T-7.17] Cómo lo detectó cada estación: lo medido junto a lo esperado.

Lo que fija, por orden de lo que costaría equivocarse:

1. **El orden es el de ARRIBO, no el alfabético.** La tabla narra una secuencia;
   ordenarla por nombre obliga a cada lector a reordenarla mentalmente.
2. **`tier = null` no es `normal`.** Un gabinete que no publicó ninguna
   transición no dijo que estuviera en calma: no dijo nada (regla de oro 7).
3. **El ancla se declara.** Con evento, los arribos se cuentan desde el origen
   del sismo; sin evento, desde la apertura del incidente. Dos tablas con anclas
   distintas comparadas como si midieran lo mismo es un error invisible.
4. **Sin epicentro, las columnas teóricas van en `null`** — no se rellenan con
   una estimación: se midió esto, y no hay contra qué compararlo.
5. **El umbral viaja con su procedencia.** Un umbral de fábrica presentado como
   del edificio es el defecto que cerró `T-7.35`.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.estaciones import router as estaciones_router

#: 19-S de 2017, solución USGS: el epicentro que usa la reproducción.
EPI_LAT, EPI_LON, PROF_KM, MAG = 18.5499, -98.4887, 48.0, 7.1
T0 = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)

#: Tres sitios a distancias crecientes del epicentro: Puebla, Tlaxcala, Toluca.
#: Se dan DESORDENADOS respecto al arribo a propósito, y con códigos cuyo orden
#: alfabético es el contrario: si la tabla saliera ordenada por nombre, la prueba
#: del orden pasaría por casualidad.
SITIOS = [
    ("c-toluca", "Planta Toluca", 19.2826, -99.6557),
    ("b-puebla", "Edificio Puebla", 19.05, -98.22),
    ("a-tlaxcala", "Centro Tlaxcala", 19.3139, -98.2404),
]
ESPERADO = ["b-puebla", "a-tlaxcala", "c-toluca"]  # por arribo: 19.7, 25.3, 38.7 s


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(estaciones_router)
    return application


def _token(role: str = "soc_operator") -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope="*"))


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


class Escenario:
    def __init__(self) -> None:
        self.sitios: dict[str, str] = {}
        self.sensores: dict[str, str] = {}
        self.event_id: str | None = None
        self.incident_id = str(uuid.uuid4())

    async def red(self) -> None:
        for code, name, lat, lon in SITIOS:
            sid, gid, sen = (str(uuid.uuid4()) for _ in range(3))
            self.sitios[code] = sid
            self.sensores[code] = sen
            await _sql(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES"
                " (:s, :t, :c, :n, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)",
                s=sid,
                t=au.DB_TENANT_PRIV,
                c=code,
                n=name,
                lat=lat,
                lon=lon,
            )
            await _sql(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status)"
                " VALUES (:g, :t, :s, :ser, 'online')",
                g=gid,
                t=au.DB_TENANT_PRIV,
                s=sid,
                ser=f"GW-{code}",
            )
            await _sql(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model, serial)"
                " VALUES (:x, :t, :s, 'ground', 'RS4D', :ser)",
                x=sen,
                t=au.DB_TENANT_PRIV,
                s=sid,
                ser=f"SIM-{code}",
            )

    async def evento(self, *, con_epicentro: bool = True, reproduccion: bool = True) -> None:
        self.event_id = f"EVT-T717-{uuid.uuid4().hex[:8]}"
        meta = (
            json.dumps(
                {
                    "reproduccion": {
                        "catalog_key": "USGS-2017-09-19-PUE",
                        "t0_real": "2017-09-19T18:14:38+00:00",
                        "t0_demo": T0.isoformat(),
                    },
                    "v_p_km_s": 6.928203230275509,
                    "v_s_km_s": 4.0,
                }
            )
            if reproduccion
            else "{}"
        )
        if con_epicentro:
            await _sql(
                "INSERT INTO seismic_events (event_id, source, magnitude, epicenter, depth_km,"
                " detected_at, meta) VALUES (:e, 'external', :m,"
                " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :d, :t,"
                " CAST(:meta AS jsonb))",
                e=self.event_id,
                m=MAG,
                lon=EPI_LON,
                lat=EPI_LAT,
                d=PROF_KM,
                t=T0,
                meta=meta,
            )
        else:
            await _sql(
                "INSERT INTO seismic_events (event_id, source, detected_at, meta)"
                " VALUES (:e, 'sasmex', :t, CAST(:meta AS jsonb))",
                e=self.event_id,
                t=T0,
                meta=meta,
            )

    async def incidente(self) -> str:
        await _sql(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id,"
            " opened_at, severity, state, trigger)"
            " VALUES (:i, :u, :t, :s, :e, :o, 'critical', 'open', 'sasmex')",
            i=self.incident_id,
            u=str(uuid.uuid4()),
            t=au.DB_TENANT_PRIV,
            s=self.sitios["b-puebla"],
            e=self.event_id,
            o=T0,
        )
        return self.incident_id

    async def midio(self, code: str, *, pga: float, hace_s: float) -> None:
        await _sql(
            "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g)"
            " VALUES (:ts, :t, :s, :x, 'ENZ', :p)",
            ts=T0 + timedelta(seconds=hace_s),
            t=au.DB_TENANT_PRIV,
            s=self.sitios[code],
            x=self.sensores[code],
            p=pga,
        )

    async def tier(self, code: str, tier: str, *, hace_s: float) -> None:
        await _sql(
            "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier,"
            " new_tier) VALUES (:ts, :t, :s, gen_random_uuid(), 'normal', :n)",
            ts=T0 + timedelta(seconds=hace_s),
            t=au.DB_TENANT_PRIV,
            s=self.sitios[code],
            n=tier,
        )


@pytest.fixture
async def esc():
    e = Escenario()
    await e.red()
    yield e
    await _sql("SET session_replication_role = 'replica'")
    await _sql("DELETE FROM waveform_features_1s WHERE tenant_id = :t", t=au.DB_TENANT_PRIV)
    await _sql("DELETE FROM rule_evaluations WHERE tenant_id = :t", t=au.DB_TENANT_PRIV)
    await _sql("DELETE FROM incidents WHERE incident_id = :i", i=e.incident_id)
    if e.event_id:
        await _sql("DELETE FROM quorum_votes WHERE event_id = :e", e=e.event_id)
        await _sql("DELETE FROM seismic_events WHERE event_id = :e", e=e.event_id)
    for code in e.sitios:
        await _sql("DELETE FROM sensors WHERE site_id = :s", s=e.sitios[code])
        await _sql("DELETE FROM gateways WHERE site_id = :s", s=e.sitios[code])
        await _sql("DELETE FROM sites WHERE site_id = :s", s=e.sitios[code])
    await _sql("SET session_replication_role = 'origin'")


async def _tabla(client, incident_id: str, rol: str = "soc_operator"):
    r = await client.get(f"/incidents/{incident_id}/estaciones", headers=_token(rol))
    assert r.status_code == 200, r.text
    return r.json()


async def test_la_tabla_va_en_orden_de_ARRIBO_y_no_alfabetico(client, base_data, esc):
    await esc.evento()
    inc = await esc.incidente()

    cuerpo = await _tabla(client, inc)

    # La tabla trae TODAS las estaciones del cliente, y en la suite completa hay
    # sitios de otras pruebas en este mismo tenant. Lo que se fija es el orden
    # RELATIVO de las tres de este escenario: comparar la lista entera por
    # igualdad haría que esta prueba dependiera de quién corrió antes.
    mios = [i for i in cuerpo["items"] if i["site_code"] in ESPERADO]
    assert [i["site_code"] for i in mios] == ESPERADO
    teoricos = [i["t_arribo_teorico_s"] for i in mios]
    assert teoricos == sorted(teoricos), "el orden no sigue a los arribos que él mismo declara"
    assert abs(teoricos[0] - 19.6) < 0.2, teoricos

    # Y el orden global tampoco es alfabético por casualidad: la lista entera va
    # ordenada por el arribo que ella misma declara.
    con_teorico = [
        i["t_arribo_teorico_s"] for i in cuerpo["items"] if i["t_arribo_teorico_s"] is not None
    ]
    assert con_teorico == sorted(con_teorico)


async def test_lo_medido_va_junto_a_lo_esperado(client, base_data, esc):
    await esc.evento()
    inc = await esc.incidente()
    # Tlaxcala mide por encima de su umbral a partir de su arribo teórico.
    await esc.midio("a-tlaxcala", pga=0.0005, hace_s=5)
    await esc.midio("a-tlaxcala", pga=0.056, hace_s=26)
    await esc.midio("a-tlaxcala", pga=0.030, hace_s=40)

    fila = next(i for i in (await _tabla(client, inc))["items"] if i["site_code"] == "a-tlaxcala")

    assert fila["peak_pga_g"] == pytest.approx(0.056, rel=1e-3)
    assert fila["t_arribo_medido_s"] == pytest.approx(26.0, abs=0.01)
    assert abs(fila["t_arribo_teorico_s"] - 25.3) < 0.2
    assert fila["dist_km"] > 0
    assert fila["sensor_code"] == "SIM-a-tlaxcala"


async def test_el_segundo_por_DEBAJO_del_umbral_no_cuenta_como_arribo(client, base_data, esc):
    """Si contara, cualquier ruido de fondo daría un arribo a los cero segundos."""
    await esc.evento()
    inc = await esc.incidente()
    await esc.midio("c-toluca", pga=0.0008, hace_s=2)

    fila = next(i for i in (await _tabla(client, inc))["items"] if i["site_code"] == "c-toluca")

    assert fila["t_arribo_medido_s"] is None
    assert fila["peak_pga_g"] == pytest.approx(0.0008, rel=1e-3)
    assert fila["umbral_pga_g"] > 0.0008
    assert fila["umbral_origen"], "el umbral sin procedencia parece del edificio aunque no lo sea"


async def test_tier_NULL_no_es_normal(client, base_data, esc):
    await esc.evento()
    inc = await esc.incidente()
    await esc.tier("b-puebla", "evacuate_or_hold", hace_s=20)

    items = {i["site_code"]: i for i in (await _tabla(client, inc))["items"]}

    assert items["b-puebla"]["tier"] == "evacuate_or_hold"
    assert items["c-toluca"]["tier"] is None, "un gabinete mudo no declaró estar en calma"


async def test_el_tier_que_sale_es_el_MAS_ALTO_de_la_ventana(client, base_data, esc):
    await esc.evento()
    inc = await esc.incidente()
    for tier, hace in (("watch", 10), ("evacuate_or_hold", 20), ("normal", 90)):
        await esc.tier("b-puebla", tier, hace_s=hace)

    items = {i["site_code"]: i for i in (await _tabla(client, inc))["items"]}

    assert items["b-puebla"]["tier"] == "evacuate_or_hold"


async def test_manual_only_NO_encabeza_la_severidad(client, base_data, esc):
    """Es un modo de operación, no una medida de cuánto sintió el edificio."""
    await esc.evento()
    inc = await esc.incidente()
    await esc.tier("b-puebla", "manual_only", hace_s=10)
    await esc.tier("b-puebla", "watch", hace_s=20)

    items = {i["site_code"]: i for i in (await _tabla(client, inc))["items"]}

    assert items["b-puebla"]["tier"] == "watch"


async def test_SIN_epicentro_las_columnas_teoricas_van_en_NULL(client, base_data, esc):
    """Rellenarlas con una estimación sería presentar una simulación como medida."""
    await esc.evento(con_epicentro=False, reproduccion=False)
    inc = await esc.incidente()
    await esc.midio("b-puebla", pga=0.2, hace_s=15)

    cuerpo = await _tabla(client, inc)

    assert cuerpo["reproduccion"] is False
    assert cuerpo["epicentro_lat"] is None
    for i in cuerpo["items"]:
        assert i["t_arribo_teorico_s"] is None
        assert i["dist_km"] is None
    puebla = next(i for i in cuerpo["items"] if i["site_code"] == "b-puebla")
    assert puebla["peak_pga_g"] == pytest.approx(0.2, rel=1e-3), "lo medido SIGUE estando"


async def test_el_ANCLA_se_declara(client, base_data, esc):
    await esc.evento()
    inc = await esc.incidente()

    cuerpo = await _tabla(client, inc)

    assert cuerpo["ancla"] == "event"
    assert cuerpo["ancla_ts"].startswith("2026-09-15T12:00:00")
    assert cuerpo["reproduccion"] is True


async def test_un_incidente_INVISIBLE_da_404(client, base_data):
    r = await client.get(f"/incidents/{uuid.uuid4()}/estaciones", headers=_token())
    assert r.status_code == 404
