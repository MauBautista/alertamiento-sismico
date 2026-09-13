"""[T-7.35] No se presume «aviso ganado» de una sacudida que el papel llama leve.

MEDIDO EN EL REPORTE DEL ACTO 4 de la demostración, y en la misma página: el
documento imprimía

    §5  BANDA · SACUDIDA LEVE (por debajo de los umbrales del inmueble)
    §7  TIEMPO DE AVISO GANADO · 149.2 s

`_lead_time` toma como «pico» el máximo de la ventana del incidente **haya habido
sismo o no**: en una prueba del WR-1 o en una falsa alarma ese máximo es ruido
ambiente, y el papel lo presenta como un logro — «avisamos con 149 segundos» de
algo que el propio documento clasifica como no significativo.

El arreglo NO borra el dato ni inventa otro: declara la razón, como ya hacía con
`not_sasmex`, `no_peak` y `peak_before_alert`. Un tiempo de aviso sin sacudida
que avisar no es un cero: es un «no aplica» con motivo.

⚠️ Lo que este arreglo NO puede hacer, y por eso no lo intenta: decidir si el
pico fue una llegada sísmica. Eso pide análisis de forma de onda. Lo que sí se
puede afirmar sin inventar nada es que **no superó el umbral de vigilancia del
propio inmueble**, que es exactamente lo que el §5 ya imprime.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_api.forensics import _lead_time

ABIERTO = datetime(2026, 9, 13, 3, 28, 3, tzinfo=UTC)
PICO = ABIERTO + timedelta(seconds=149.2)


def test_con_sacudida_de_verdad_el_aviso_se_mide() -> None:
    """El caso que la ficha NO puede romper: un SASMEX con sacudida real."""
    segundos, razon = _lead_time("sasmex", ABIERTO, PICO, "trip")
    assert razon is None
    assert segundos is not None and abs(segundos - 149.2) < 0.01


def test_sin_sacudida_sobre_los_umbrales_NO_se_presume_aviso() -> None:
    """El defecto medido: banda `normal` y 149 s de «aviso ganado» en la misma página."""
    segundos, razon = _lead_time("sasmex", ABIERTO, PICO, "normal")
    assert segundos is None
    assert razon == "sin_sacudida"


def test_la_banda_de_vigilancia_SÍ_cuenta_como_sacudida() -> None:
    """`watch` supera el umbral de vigilancia del inmueble: hubo algo que avisar.

    El corte va en `normal`, no en `trip`: negar el aviso de una sacudida
    moderada sería el error contrario — esconder un aviso que sí valió.
    """
    segundos, _ = _lead_time("sasmex", ABIERTO, PICO, "watch")
    assert segundos is not None


def test_las_razones_de_siempre_siguen_ganando() -> None:
    """El orden importa: sin SASMEX no se llega a preguntar por la sacudida."""
    assert _lead_time("local_threshold", ABIERTO, PICO, "trip")[1] == "not_sasmex"
    assert _lead_time("sasmex", ABIERTO, None, "trip")[1] == "no_peak"
    assert _lead_time("sasmex", ABIERTO, ABIERTO - timedelta(seconds=5), "trip")[1] == (
        "peak_before_alert"
    )


def test_la_razon_nueva_se_puede_IMPRIMIR() -> None:
    """Una razón sin texto sale como código en un documento con peso legal."""
    from takab_api.dictamen.model import LEAD_REASONS, lead_time_text  # noqa: PLC0415

    assert "sin_sacudida" in LEAD_REASONS
    texto = lead_time_text(None, "sin_sacudida")
    assert "sin_sacudida" not in texto, f"salió el código en vez de la frase: {texto!r}"
    assert "sacudida" in texto.lower()
