"""[T-7.15] Las estaciones simuladas SIENTEN la onda — y no publican un solo evento.

Lo que fija, por orden de lo que costaría equivocarse:

1. **Ni con `--replay` sale un `LocalEvent`.** Es la invariante del bloque VIII:
   un evento simulado abre un incidente de verdad, el cuórum forma con estaciones
   que no midieron nada y la cascada manda una alerta real a los teléfonos del
   sitio. `--replay` y `--quake` se rechazan juntos al construir.
2. **Antes del arribo, ruido de fondo; después, el pico de ATTEN-LAW.** Y cada
   estación en SU instante: si todas sintieran a la vez, la demostración estaría
   enseñando algo que la física no hace.
3. **Determinista.** Dos corridas idénticas dan la misma rampa: una demostración
   tiene que salir igual dos veces, y una rampa aleatoria no se puede comparar
   con lo que el mapa pinta.
4. **Una estación sin coordenadas es un error CON SU NOMBRE**, no ruido de fondo
   silencioso mientras el mapa pinta el frente pasándole por encima.
5. **El latido sigue intacto**: la reproducción cambia lo que miden los sensores,
   no si el gabinete está vivo.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from simulators.fleet import (
    EVENTS_TOPIC,
    FEATURES_TOPIC,
    HEALTH_TOPIC,
    STA_LTA_FONDO_MAX,
    Estacion,
    FleetSimulator,
    esperar_pulso_wr1,
    flota_de_fichero,
    reproduccion_de_fichero,
)

_AQUI = Path(__file__).resolve().parents[1] / "simulators"
_FLOTA = _AQUI / "demo_red.json"
_SISMO = _AQUI / "replay_19s.json"

T0 = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)

#: Lo que declara `T-7.14`, en segundos desde el origen, por código de ESTACIÓN.
#: Aquí se comprueban solo las tres simuladas: la de Puebla es el gabinete REAL y
#: publica por su cuenta.
REFERENCIA_S = {"SIM101": 25.3, "SIM102": 32.1, "SIM103": 38.7}


@pytest.fixture
def flota() -> list[Estacion]:
    _, estaciones = flota_de_fichero(_FLOTA)
    return estaciones


def _sim(flota: list[Estacion], **kw) -> FleetSimulator:
    return FleetSimulator(
        rate=1.0,
        estaciones=flota,
        tenant="tenant-dev",
        no_events=True,
        t0=T0,
        replay=reproduccion_de_fichero(_SISMO, flota),
        **kw,
    )


def _features(batch, station: str) -> list[dict]:
    return [
        m.payload for m in batch if m.topic == FEATURES_TOPIC and m.payload["station"] == station
    ]


# ───────────────────────────────────────────────── el plan


def test_el_fichero_de_la_flota_trae_las_COORDENADAS(flota: list[Estacion]) -> None:
    """Sin ellas no hay cuándo llega la onda. Espejo de `db/seeds/demo_red.sql`."""
    assert len(flota) == 3
    for e in flota:
        assert e.lat is not None and e.lon is not None, e.station


def test_los_arribos_de_la_demostracion_son_los_de_la_FICHA(flota: list[Estacion]) -> None:
    rep = reproduccion_de_fichero(_SISMO, flota)
    assert rep.catalog_key == "USGS-2017-09-19-PUE"
    for estacion, esperado in REFERENCIA_S.items():
        obtenido = rep.arribos[estacion].t_s_s
        assert abs(obtenido - esperado) < 0.1, f"{estacion}: {obtenido:.2f}s vs {esperado}s"


def test_una_estacion_SIN_coordenadas_revienta_con_su_nombre() -> None:
    """Publicar ruido de fondo mientras el mapa pinta el frente pasando por
    encima parecería que la estación no sintió nada: es la peor forma de fallar."""
    coja = [Estacion("SIM999", "gw-sim-0999", "site-sim-999")]
    with pytest.raises(ValueError, match="SIM999"):
        reproduccion_de_fichero(_SISMO, coja)


def test_un_sismo_sin_epicentro_se_RECHAZA(tmp_path: Path, flota: list[Estacion]) -> None:
    roto = tmp_path / "sismo.json"
    roto.write_text(json.dumps({"catalog_key": "X", "magnitude": 7.1}), encoding="utf-8")
    with pytest.raises(ValueError, match="lat"):
        reproduccion_de_fichero(roto, flota)


# ───────────────────────────────────────────── la forma de la onda


def test_ANTES_del_arribo_cada_estacion_esta_en_su_ruido(flota: list[Estacion]) -> None:
    sim = _sim(flota)
    batch = sim.window_batch(0)  # t = 0 s: la onda no ha salido del epicentro
    assert min(REFERENCIA_S.values()) > 0, "el control: ninguna estación siente en t=0"
    for f in [m.payload for m in batch if m.topic == FEATURES_TOPIC]:
        assert f["sta_lta"] <= STA_LTA_FONDO_MAX, f["station"]
        assert f["pga"] < 1e-2, "eso no es ruido de fondo"


def test_cada_estacion_siente_en_SU_instante_y_no_todas_a_la_vez(
    flota: list[Estacion],
) -> None:
    sim = _sim(flota)
    # A los 26 s ya llegó a Tlaxcala (25.3) y todavía no a CDMX (32.1).
    batch = sim.window_batch(26)
    tlax = _features(batch, "SIM101")[0]
    cdmx = _features(batch, "SIM102")[0]
    assert tlax["sta_lta"] > STA_LTA_FONDO_MAX, "Tlaxcala no sintió su propio arribo"
    assert cdmx["sta_lta"] <= STA_LTA_FONDO_MAX, "CDMX sintió una onda que no ha llegado"
    assert tlax["pga"] > cdmx["pga"] * 10


def test_el_pico_es_el_de_ATTEN_LAW_y_DECAE(flota: list[Estacion]) -> None:
    rep = reproduccion_de_fichero(_SISMO, flota)
    esperado = rep.arribos["SIM101"].pga_g
    sim = _sim(flota)

    justo = _features(sim.window_batch(26), "SIM101")[0]  # ~0.7 s tras el arribo
    despues = _features(sim.window_batch(60), "SIM101")[0]  # ~35 s después

    assert justo["pga"] == pytest.approx(esperado, rel=0.05)
    assert despues["pga"] < justo["pga"] / 4, "la coda no decae"
    assert despues["sta_lta"] < justo["sta_lta"]


def test_mas_lejos_sacude_MENOS(flota: list[Estacion]) -> None:
    """Se comparan los PICOS, cada uno en su arribo, no el valor simultáneo.

    Mirar las tres a la vez en un instante cualquiera da el orden al revés a
    ratos, y no es un defecto: a los 45 s Tlaxcala lleva veinte segundos
    decayendo y CDMX acaba de recibir el suyo. El hecho que fija la atenuación es
    cuánto sacude cada una CUANDO le llega.
    """
    sim = _sim(flota)
    picos = [
        _features(sim.window_batch(int(REFERENCIA_S[s]) + 1), s)[0]["pga"]
        for s in ("SIM101", "SIM102", "SIM103")
    ]
    assert picos == sorted(picos, reverse=True), "la atenuación va al revés"


def test_la_rampa_es_DETERMINISTA(flota: list[Estacion]) -> None:
    """Dos corridas iguales, la misma onda: si no, no se puede comparar con el mapa."""
    a = _features(_sim(flota).window_batch(30), "SIM101")[0]
    b = _features(_sim(flota).window_batch(30), "SIM101")[0]
    assert a["pga"] == b["pga"] and a["sta_lta"] == b["sta_lta"]


# ──────────────────────────────────────────── lo que NO puede pasar


def test_ni_con_replay_sale_un_LOCAL_EVENT(flota: list[Estacion]) -> None:
    """La invariante del bloque VIII, comprobada sobre la corrida entera."""
    sim = _sim(flota, with_health=True)
    for w in range(0, 80):
        for m in sim.window_batch(w):
            assert m.topic != EVENTS_TOPIC, f"ventana {w}: {m.payload}"


def test_replay_y_quake_juntos_se_RECHAZAN(flota: list[Estacion]) -> None:
    """Serían dos sismos a la vez, y el de `--quake` abre incidentes de verdad."""
    with pytest.raises(ValueError, match="dos sismos"):
        FleetSimulator(
            estaciones=flota,
            quake="SIM101",
            replay=reproduccion_de_fichero(_SISMO, flota),
            t0=T0,
        )


def test_el_LATIDO_sigue_intacto_durante_la_reproduccion(flota: list[Estacion]) -> None:
    """La reproducción cambia lo que miden los sensores, no si el gabinete vive."""
    sim = _sim(flota, with_health=True)
    latidos = [m for m in sim.window_batch(0) if m.topic == HEALTH_TOPIC]
    assert len(latidos) == 3, "un gabinete dejó de latir por estar reproduciendo"


def test_SIN_replay_el_simulador_sigue_dando_ruido(flota: list[Estacion]) -> None:
    """El control de ceguera: si el ruido de fondo también subiera, las pruebas de
    arriba pasarían sobre un simulador que siempre sacude."""
    sim = FleetSimulator(estaciones=flota, tenant="tenant-dev", no_events=True, t0=T0)
    for f in [m.payload for m in sim.window_batch(45) if m.topic == FEATURES_TOPIC]:
        assert f["sta_lta"] <= STA_LTA_FONDO_MAX
        assert f["pga"] < 1e-2


# ─────────────────────────────────────────────── el ancla del t0


def test_armar_espera_el_pulso_del_WR1_y_lo_ve() -> None:
    lecturas = iter([{"sasmex_active": False}, {"sasmex_active": False}, {"sasmex_active": True}])
    reloj = iter(range(100))
    assert (
        esperar_pulso_wr1(
            "http://x/api/status",
            timeout_s=10.0,
            leer=lambda _u: next(lecturas),
            clock=lambda: next(reloj),
            sleep=lambda _s: None,
        )
        is True
    )


def test_armar_NO_aborta_por_una_lectura_fallida() -> None:
    """El panel puede reiniciarse a mitad; rendirse por eso sería peor."""
    estado = {"n": 0}

    def leer(_u):
        estado["n"] += 1
        if estado["n"] < 3:
            raise OSError("panel reiniciándose")
        return {"sasmex_active": True}

    reloj = iter(range(100))
    assert (
        esperar_pulso_wr1(
            "http://x/api/status",
            timeout_s=50.0,
            leer=leer,
            clock=lambda: next(reloj),
            sleep=lambda _s: None,
        )
        is True
    )


def test_armar_se_rinde_al_vencer_el_plazo_y_lo_DICE() -> None:
    """Devolver `False` y no colgarse: quien llama decide, y el guion no se queda
    esperando para siempre delante del cliente."""
    reloj = iter([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    assert (
        esperar_pulso_wr1(
            "http://x/api/status",
            timeout_s=5.0,
            leer=lambda _u: {"sasmex_active": False},
            clock=lambda: next(reloj),
            sleep=lambda _s: None,
        )
        is False
    )
