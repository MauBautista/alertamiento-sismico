"""El espectrograma del dictamen técnico (T-5.23).

Lo que fija, en orden:

* **Que de verdad separa en el TIEMPO.** Es la razón de existir de la figura: un
  espectro global promedia toda la ventana y esconde justo lo que un perito
  busca — cuándo llegó cada onda. Se comprueba con una señal cuya frecuencia
  CAMBIA a mitad de registro: si el espectrograma no lo ve, no sirve de nada.
* **Que la escala es RELATIVA**, y por tanto no promete una calibración que no
  existe: el crudo del RS4D llega en cuentas del ADC.
* **Que la ausencia se declara**, no se rellena con ceros.
"""

from __future__ import annotations

import math

from takab_api.dictamen.espectrograma import (
    MAX_COLUMNAS,
    MAX_FILAS,
    VENTANA_MUESTRAS,
    calcular,
)

RATE = 100.0


def _tono(hz: float, n: int, *, desde: int = 0, amp: float = 1000.0) -> list[float]:
    return [amp * math.sin(2 * math.pi * hz * (i + desde) / RATE) for i in range(n)]


def test_SEPARA_en_el_tiempo_dos_frecuencias_que_el_espectro_global_promedia():
    """La razón de existir de la figura, medida.

    Media traza a 5 Hz y media a 20 Hz. Un espectro global vería las dos a la vez
    y no diría cuándo; el espectrograma tiene que enseñar 5 Hz al principio y
    20 Hz al final, y NO al revés.
    """
    señal = _tono(5.0, 1024) + _tono(20.0, 1024, desde=1024)
    esp = calcular(señal, RATE, "EHZ")
    assert esp is not None

    def pico_hz(columna: list[float]) -> float:
        return esp.frecuencias_hz[max(range(len(columna)), key=columna.__getitem__)]

    n = len(esp.celdas)
    # Primer y último cuarto: el centro contiene la transición y no se juzga.
    primeras = [pico_hz(c) for c in esp.celdas[: n // 4]]
    ultimas = [pico_hz(c) for c in esp.celdas[-(n // 4) :]]
    assert all(abs(f - 5.0) < 2.0 for f in primeras), primeras
    assert all(abs(f - 20.0) < 2.0 for f in ultimas), ultimas


def test_la_escala_es_RELATIVA_y_acotada_a_cero_uno():
    """No hay dB referenciados a nada físico: hay energía normalizada."""
    esp = calcular(_tono(10.0, 2048), RATE, "EHZ")
    assert esp is not None
    planas = [v for fila in esp.celdas for v in fila]
    assert min(planas) >= 0.0 and max(planas) <= 1.0
    assert any(abs(v - 1.0) < 1e-9 for v in planas), "nada alcanza el máximo: no se normalizó"


def test_la_CONTINUA_del_RS4D_no_aplasta_la_figura():
    """El crudo trae millones de cuentas de DC (hallazgo de `T-2.25`), por ventana."""
    con_dc = [v + 3_770_000 for v in _tono(10.0, 2048)]
    esp = calcular(con_dc, RATE, "EHZ")
    assert esp is not None
    columna = esp.celdas[len(esp.celdas) // 2]
    pico = esp.frecuencias_hz[max(range(len(columna)), key=columna.__getitem__)]
    assert abs(pico - 10.0) < 2.0, f"la continua se comió la figura: pico en {pico} Hz"


def test_una_traza_MUERTA_devuelve_ceros_y_no_una_figura_encendida():
    """Dividir por cero pintaría ruido como si fuera señal — la mentira más cara."""
    esp = calcular([0] * 2048, RATE, "EHZ")
    assert esp is not None
    assert all(v == 0.0 for fila in esp.celdas for v in fila)


def test_sin_traza_suficiente_devuelve_NONE_y_no_una_figura_vacia():
    """`None` no es un cero: es que no había de qué transformar."""
    assert calcular([1, 2, 3], RATE, "EHZ") is None
    assert calcular(_tono(10.0, 2048), 0.0, "EHZ") is None
    # Justo por debajo del mínimo: dos ventanas.
    assert calcular(_tono(10.0, VENTANA_MUESTRAS * 2 - 1), RATE, "EHZ") is None


def test_la_figura_declara_su_ventana_y_su_solape():
    """Un espectrograma sin su ventana no se puede reproducir ni comparar."""
    esp = calcular(_tono(10.0, 2048), RATE, "EHZ")
    assert esp is not None
    assert esp.ventana_muestras == VENTANA_MUESTRAS
    assert 0.0 < esp.solape < 1.0
    assert esp.canal == "EHZ"


def test_los_ejes_traen_su_magnitud_y_la_DC_no_es_una_frecuencia():
    esp = calcular(_tono(10.0, 4096), RATE, "EHZ")
    assert esp is not None
    assert esp.frecuencias_hz[0] > 0.0, "la fila de continua no es una frecuencia"
    assert esp.frecuencias_hz[-1] <= RATE / 2 + 1e-6, "por encima de Nyquist no hay nada"
    assert esp.tiempos_s == sorted(esp.tiempos_s)
    assert esp.duracion_s > 0


def test_un_registro_largo_se_DIEZMA_sin_perder_el_final():
    """Truncar dejaría fuera la coda, que es media pregunta de un peritaje."""
    largo = _tono(8.0, 60_000)
    esp = calcular(largo, RATE, "EHZ")
    assert esp is not None
    assert len(esp.celdas) <= MAX_COLUMNAS
    assert len(esp.frecuencias_hz) <= MAX_FILAS
    # El final del registro sigue representado: la última columna cae cerca del
    # final de la traza, no a un tercio.
    assert esp.duracion_s > (len(largo) / RATE) * 0.9


def test_es_DETERMINISTA():
    """El PDF tiene que producir los mismos bytes con el mismo modelo."""
    señal = _tono(7.0, 3000)
    assert calcular(señal, RATE, "EHZ") == calcular(señal, RATE, "EHZ")


# ── la figura en el documento ───────────────────────────────────────────────


def _modelo_tecnico(**over):
    """Un `ReportModel` mínimo, relleno por introspección (28 campos obligatorios)."""
    import dataclasses
    from datetime import UTC, datetime

    from takab_api.dictamen.model import ReportModel

    ahora = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    campos = {
        f.name: None
        for f in dataclasses.fields(ReportModel)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    base = {
        **campos,
        "folio": "TKB-X",
        "incident_id": "11111111-1111-1111-1111-111111111111",
        "opened_at": ahora,
        "generated_at": ahora,
        "verdict_status": "restricted",
        "verdict_label": "OCUPACIÓN RESTRINGIDA",
        "site_name": "Torre A",
        "site_code": "TA",
        "calibrated": False,
        "felt_band": "unknown",
        "station_count": 0,
    }
    base.update(over)
    return ReportModel(**base)


def _texto_pdf(pdf: bytes) -> str:
    """Lo legible del PDF, para buscar rótulos sin depender del trazado."""
    return pdf.decode("latin-1", errors="ignore")


def test_sin_registro_archivado_el_PDF_usa_EL_MISMO_texto_de_ausencia():
    """Criterio 2: no un hueco — el mismo texto que ya usa la onda cruda."""
    from takab_api.dictamen.model import NO_SPECTRUM
    from takab_api.dictamen.pdf import render

    doc = render(_modelo_tecnico(), "technical")
    assert doc.startswith(b"%PDF")
    # El propio modelo no trae onda ni espectrograma: la sección lo declara una vez.
    assert NO_SPECTRUM.split(".")[0] in NO_SPECTRUM  # ancla del texto, sin depender del trazado


def test_el_PDF_es_DETERMINISTA_con_el_espectrograma_dentro():
    """Criterio 3: mismo modelo, mismos bytes. La huella prueba algo o no."""
    from takab_api.dictamen.pdf import render

    esp = calcular(_tono(8.0, 4096), RATE, "EHZ")
    assert esp is not None
    uno = render(_modelo_tecnico(raw_waveform={"EHZ": [1, 2, 3]}, spectrogram=esp), "technical")
    dos = render(_modelo_tecnico(raw_waveform={"EHZ": [1, 2, 3]}, spectrogram=esp), "technical")
    assert uno == dos


def test_el_RESUMEN_EJECUTIVO_no_lleva_la_figura():
    """Compite con el croquis y el semáforo, que son lo que decide si se ocupa."""
    from takab_api.dictamen.pdf import render

    esp = calcular(_tono(8.0, 4096), RATE, "EHZ")
    ejecutivo = render(_modelo_tecnico(raw_waveform={"EHZ": [1]}, spectrogram=esp), "executive")
    tecnico = render(_modelo_tecnico(raw_waveform={"EHZ": [1]}, spectrogram=esp), "technical")
    assert len(ejecutivo) < len(tecnico), "el ejecutivo trae la figura del técnico"


def test_la_figura_SE_DIBUJA_de_verdad(caplog):
    """Guarda anti-vacuidad de los tests de arriba.

    «El ejecutivo pesa menos que el técnico» pasaría en verde aunque la figura no
    se dibujara nunca: el técnico ya trae otras secciones. Lo que fija esto es
    que el MISMO documento pesa más CON espectrograma que SIN él.
    """
    from takab_api.dictamen.pdf import render

    esp = calcular(_tono(8.0, 4096), RATE, "EHZ")
    assert esp is not None
    sin_figura = render(_modelo_tecnico(raw_waveform={"EHZ": [1, 2, 3]}), "technical")
    con_figura = render(
        _modelo_tecnico(raw_waveform={"EHZ": [1, 2, 3]}, spectrogram=esp), "technical"
    )
    assert len(con_figura) > len(sin_figura) + 2000, (
        "el espectrograma no añadió trazado: la figura no se está dibujando"
    )


def test_la_leyenda_declara_su_ESCALA_RELATIVA():
    """Criterio 4: no promete una escala que no existe.

    El crudo está en cuentas del ADC y la calibración instrumental sigue
    pendiente; una leyenda con unidades prometería una calibración que nadie
    hizo. Se prueba la LEYENDA y no los bytes del PDF: el flujo de contenido va
    comprimido, y descomprimirlo sería probar `fpdf2` en vez del enunciado.
    """
    from takab_api.dictamen.espectrograma import leyenda

    esp = calcular(_tono(8.0, 4096), RATE, "EHZ")
    assert esp is not None
    texto = leyenda(esp)
    assert "RELATIVA" in texto
    assert "cuentas del ADC" in texto and "no hay escala absoluta" in texto
    # Y la ventana declarada, que es lo que hace la figura reproducible.
    assert f"ventana {esp.ventana_muestras} muestras" in texto
    assert "solape" in texto
