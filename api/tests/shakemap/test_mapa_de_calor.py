"""[T-9.50 · T-9.51 · D-44] El mapa SIEMPRE se calcula, y lleva su superficie ESTIMADA.

Contra la base y con el rol del worker, como `test_pasada.py`, cuyo escenario se
reusa: sembrar otra red aquí haría que dos suites midieran cosas distintas.

Lo que fija, por lo que costaría equivocarse:

1. **Ya no hace falta `in_review`** (`T-9.50`). Un sismo sin revisión humana se
   quedaba sin mapa para siempre; ahora basta con que el incidente haya madurado
   `shakemap_espera_s`. Y **no antes**: un mapa pintado a mitad de la sacudida se
   lee como verdad y no lo es.
2. **Un `completo` calculado con la ventana del pico ABIERTA no es definitivo.**
   Se rehace una vez pasados los `dictamen_pga_window_post_s` y luego converge:
   si convergiera antes, el mapa se quedaría con el pico de los primeros 120 s.
3. **La superficie cuenta N y M bien** (`D-44`): N = inmuebles ACTIVOS que
   midieron, M = los calibrados. Un sensor retirado no cuenta, ni para bien ni
   para mal; un inmueble sin sensores activos se sigue pintando como punto pero
   no entra en la superficie.
4. **Sin calibrados no hay superficie, y se dice por qué** (`sin_calibrados`).
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from takab_api.settings import Settings
from takab_api.shakemap import calculo as C
from takab_api.shakemap import servicio as S
from takab_api.shakemap import superficie as SUP
from tests.shakemap.test_pasada import (  # noqa: F401  (fixture de pytest, por nombre)
    ABIERTO,
    NOW,
    PGA_CDMX,
    PGA_PUEBLA,
    Escenario,
    _settings,
    esc,
)

ESPERA_S = Settings().shakemap_espera_s
VENTANA_PICO_S = Settings().dictamen_pga_window_post_s
REFRESCO_S = Settings().shakemap_refresco_s


def _calibra(esc: Escenario, code: str, fuente: str = "stationxml:AM.PRUEBA") -> None:
    esc.conn.execute(
        "UPDATE sensors SET calibration_source = %s WHERE site_id = %s",
        (fuente, esc.sitios[code]),
    )
    esc.conn.commit()


def _retira(esc: Escenario, code: str) -> None:
    esc.conn.execute(
        "UPDATE sensors SET status = 'retired' WHERE site_id = %s", (esc.sitios[code],)
    )
    esc.conn.commit()


def _sensor_retirado_sin_calibrar(esc: Escenario, code: str) -> None:
    """Un segundo sensor del inmueble, RETIRADO y sin calibración declarada."""
    gw = esc.conn.execute(
        "SELECT gateway_id FROM gateways WHERE site_id = %s", (esc.sitios[code],)
    ).fetchone()["gateway_id"]
    esc.conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial,"
        " status) VALUES (gen_random_uuid(),%s,%s,%s,'structural','RS4D',%s,'retired')",
        (esc.tenant, esc.sitios[code], gw, f"RET-{uuid.uuid4().hex[:8]}"),
    )
    esc.conn.commit()


def _superficie(esc: Escenario, inc: str) -> tuple[dict | None, str | None]:
    esc.conn.rollback()
    fila = esc.conn.execute(
        "SELECT superficie, superficie_motivo FROM incident_shakemap WHERE incident_id = %s",
        (inc,),
    ).fetchone()
    assert fila is not None, "no hay snapshot"
    return fila["superficie"], fila["superficie_motivo"]


# ------------------------------------------------------------- T-9.50 · cuándo


def test_se_calcula_SIN_revision_pasada_la_espera_y_no_antes(esc: Escenario) -> None:
    """El sismo que nadie revisó también tiene mapa; el que acaba de abrirse, no."""
    inc = esc.incidente(en_revision=False)
    esc.mide("CDMX", PGA_CDMX)

    assert esc.pasada(now=ABIERTO + timedelta(seconds=ESPERA_S - 5)).calculados == ()
    assert esc.snapshot(inc) is None
    assert esc.pasada(now=ABIERTO + timedelta(seconds=ESPERA_S + 1)).calculados == (inc,)
    assert esc.snapshot(inc)["estado"] == C.ESTADO_COMPLETO


def test_un_completo_con_la_ventana_del_pico_ABIERTA_se_rehace_una_vez(esc: Escenario) -> None:
    """Calculado a los 150 s (dentro de la ventana de 180 s del pico) se rehace
    cuando vence el refresco; el de después ya es definitivo y converge."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)

    temprano = ABIERTO + timedelta(seconds=ESPERA_S + 30)
    assert temprano < ABIERTO + timedelta(seconds=VENTANA_PICO_S)
    assert esc.pasada(now=temprano).calculados == (inc,)
    assert esc.snapshot(inc)["estado"] == C.ESTADO_COMPLETO

    # Dentro del refresco no se toca, aunque sea provisional.
    assert esc.pasada(now=temprano + timedelta(seconds=REFRESCO_S / 2)).calculados == ()
    # Vencido el refresco: se rehace, ya con la ventana del pico cerrada.
    rehecho = temprano + timedelta(seconds=REFRESCO_S + 1)
    assert rehecho >= ABIERTO + timedelta(seconds=VENTANA_PICO_S)
    assert esc.pasada(now=rehecho).calculados == (inc,)
    # Y converge: un `completo` con la ventana cerrada no se vuelve a calcular.
    assert esc.pasada(now=rehecho + timedelta(hours=1)).calculados == ()


def test_un_completo_calculado_DESPUES_de_la_ventana_no_se_rehace(esc: Escenario) -> None:
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    tarde = ABIERTO + timedelta(seconds=VENTANA_PICO_S + 1)
    assert esc.pasada(now=tarde).calculados == (inc,)
    assert esc.pasada(now=tarde + timedelta(seconds=REFRESCO_S + 1)).calculados == ()


def test_un_snapshot_ANTERIOR_a_D44_se_rehace_para_estrenar_superficie(esc: Escenario) -> None:
    """Una fila con las dos columnas en NULL es «calculado antes de D-44». Dentro
    de la ventana del worker se rehace una vez y ya no: tras calcular, o hay
    superficie o hay motivo."""
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    assert esc.pasada().calculados == (inc,)
    esc.conn.execute(
        "UPDATE incident_shakemap SET superficie = NULL, superficie_motivo = NULL"
        " WHERE incident_id = %s",
        (inc,),
    )
    esc.conn.commit()

    despues = NOW + timedelta(seconds=REFRESCO_S + 1)
    assert esc.pasada(now=despues).calculados == (inc,)
    assert _superficie(esc, inc) != (None, None)
    assert esc.pasada(now=despues + timedelta(hours=1)).calculados == ()


# ----------------------------------------------------- T-9.51 · la superficie


def test_la_superficie_se_persiste_con_N_y_M(esc: Escenario) -> None:
    _calibra(esc, "CDMX")
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.mide("PUEBLA", PGA_PUEBLA)
    esc.pasada()

    sup, motivo = _superficie(esc, inc)
    assert motivo is None
    assert sup is not None
    assert sup["n_sensores"] == 2, "midieron dos inmuebles activos"
    assert sup["n_calibrados"] == 1, "sólo la Ciudad de México declara calibración"
    assert sup["metodo"] == SUP.METODO
    assert sup["ley"] == C.LEY
    # Se puede reconstruir: es lo que leerán el PNG y el PDF.
    malla = SUP.Superficie.from_json(sup)
    assert malla.ancho * malla.alto == len(sup["pga_ug"])
    assert any(a for fila in malla.ajustada for a in fila)


def test_un_sensor_RETIRADO_sin_calibrar_no_impide_el_ajuste(esc: Escenario) -> None:
    """El `bool_and` es sobre los ACTIVOS (`D-43`): un retirado no le quita la
    calibración al inmueble."""
    _calibra(esc, "CDMX")
    _sensor_retirado_sin_calibrar(esc, "CDMX")
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()

    sup, motivo = _superficie(esc, inc)
    assert motivo is None
    assert sup["n_calibrados"] == 1


def test_un_inmueble_SIN_sensores_activos_se_pinta_pero_no_entra_en_la_superficie(
    esc: Escenario,
) -> None:
    _calibra(esc, "CDMX")
    _calibra(esc, "PUEBLA")
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.mide("PUEBLA", PGA_PUEBLA)
    _retira(esc, "PUEBLA")
    esc.pasada()

    sup, _ = _superficie(esc, inc)
    assert sup["n_sensores"] == 1
    assert sup["n_calibrados"] == 1
    codigos = {p["site_code"].split("-")[-1] for p in esc.snapshot(inc)["puntos"]}
    assert codigos == {"CDMX", "PUEBLA"}, "el punto se sigue pintando"


def test_solo_sensores_sin_calibrar_da_el_motivo_sin_calibrados(esc: Escenario) -> None:
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    assert _superficie(esc, inc) == (None, SUP.MOTIVO_SIN_CALIBRADOS)


def test_una_calibracion_EN_BLANCO_no_es_una_calibracion(esc: Escenario) -> None:
    """Mismo criterio que el dictamen (`T-9.30`): «calibrado» = fuente NO vacía."""
    _calibra(esc, "CDMX", fuente="")
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    assert _superficie(esc, inc) == (None, SUP.MOTIVO_SIN_CALIBRADOS)


def test_sin_epicentro_no_hay_superficie_y_se_dice(esc: Escenario) -> None:
    _calibra(esc, "CDMX")
    inc = esc.incidente(con_epicentro=False)
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    assert _superficie(esc, inc) == (None, SUP.MOTIVO_SIN_EPICENTRO)


# ------------------------------------------------------ T-9.50 · a demanda


def _a_demanda(inc: str) -> C.Mapa | None:
    async def _corre() -> C.Mapa | None:
        settings = _settings()
        motor = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with motor.connect() as conn:
                return await S.calcula_uno(conn, settings, inc)
        finally:
            await motor.dispose()

    return asyncio.run(_corre())


def test_calcula_uno_devuelve_el_mapa_con_superficie_y_NO_persiste(esc: Escenario) -> None:
    """Lo que usará el PDF cuando todavía no hay snapshot."""
    _calibra(esc, "CDMX")
    inc = esc.incidente(en_revision=False)
    esc.mide("CDMX", PGA_CDMX)

    mapa = _a_demanda(inc)
    assert mapa is not None
    assert mapa.estado == C.ESTADO_COMPLETO
    assert mapa.superficie is not None
    assert mapa.superficie.n_calibrados == 1
    assert mapa.superficie_motivo is None
    assert esc.snapshot(inc) is None, "a demanda no escribe"


def test_calcula_uno_de_un_incidente_que_no_existe_es_None(esc: Escenario) -> None:
    assert _a_demanda(str(uuid.uuid4())) is None


def test_calcula_uno_sin_calibrados_trae_el_motivo(esc: Escenario) -> None:
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    mapa = _a_demanda(inc)
    assert mapa is not None
    assert mapa.superficie is None
    assert mapa.superficie_motivo == SUP.MOTIVO_SIN_CALIBRADOS
