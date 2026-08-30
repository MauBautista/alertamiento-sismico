"""El pre y el post-proceso del detector (T-3.12.d).

Estas cuentas se prueban **en CI y sin un solo peso**, y esa decisión tiene una razón
medida: un decodificador mal aplicado **no lanza**. Devuelve cero personas. Y un cero se lee
como un punto de reunión vacío, que es exactamente el número que nadie va a cuestionar.

Pasó el 2026-08-30 contra la cámara real: el export oficial de YOLOX no decodifica dentro del
grafo, se interpretó su salida como si sí, y el resultado fue `personas=0` en un fotograma con
una persona a metro y medio de la lente. Cero error, cero traza, cero personas.
"""

from __future__ import annotations

import numpy as np
import pytest
from takab_cctv.detector import (
    CLASE_PERSONA,
    RELLENO,
    STRIDES,
    Caja,
    Montaje,
    _a_cajas,
    _preparar,
    rejilla,
)

ENTRADA = (416, 416)


def _imagen(ancho: int, alto: int, color: int = 200):
    return np.full((alto, ancho, 3), color, np.uint8)


# ------------------------------------------------------------------ letterbox


def test_el_letterbox_no_deforma_y_rellena_lo_que_sobra() -> None:
    """Estirar cambiaría la relación de aspecto y un detector entrenado con personas de pie
    pierde recall con personas achatadas."""
    tensor, escala, _ = _preparar(_imagen(640, 480), ENTRADA, np)

    assert tensor.shape == (1, 3, 416, 416)
    assert escala == pytest.approx(416 / 640)
    # 480 × (416/640) = 312 filas útiles; lo de abajo es relleno.
    lienzo = tensor[0].transpose(1, 2, 0)
    assert lienzo[:312].mean() == pytest.approx(200, abs=1)
    assert lienzo[313:].min() == RELLENO and lienzo[313:].max() == RELLENO


def test_el_relleno_va_abajo_y_a_la_derecha_nunca_centrado() -> None:
    """Con relleno centrado hay que restar un desplazamiento al volver a coordenadas de la
    imagen, y un signo equivocado ahí da detecciones plausibles pero corridas — el error que
    ninguna prueba de humo detecta. Con el origen intacto, deshacer la escala es dividir."""
    tensor, _, (dx, dy) = _preparar(_imagen(640, 480), ENTRADA, np)

    assert (dx, dy) == (0.0, 0.0)
    esquina = tensor[0, :, 0, 0]
    assert esquina.tolist() == [200, 200, 200]  # el origen es imagen, no relleno


def test_una_imagen_mas_alta_que_ancha_rellena_a_la_derecha() -> None:
    tensor, escala, _ = _preparar(_imagen(480, 640), ENTRADA, np)
    lienzo = tensor[0].transpose(1, 2, 0)

    assert escala == pytest.approx(416 / 640)
    assert lienzo[:, 313:].min() == RELLENO
    assert lienzo[:, :312].mean() == pytest.approx(200, abs=1)


# -------------------------------------------------------------------- rejilla


def test_la_rejilla_produce_exactamente_las_anclas_que_el_modelo_emite() -> None:
    """52²+26²+13² = 3549 con entrada 416. Es lo que permite COMPROBAR que la entrada
    declarada le corresponde al modelo en vez de suponerlo."""
    centros, pasos = rejilla(ENTRADA, np)

    assert len(centros) == 3549 == len(pasos)
    assert sorted(set(pasos.ravel().tolist())) == sorted(float(s) for s in STRIDES)


def test_la_rejilla_recorre_filas_antes_que_columnas() -> None:
    """El orden no es negociable: la salida es una lista plana y la única forma de saber a
    qué punto de la imagen corresponde cada fila es reconstruir la MISMA pirámide."""
    centros, _ = rejilla(ENTRADA, np)

    assert centros[0].tolist() == [0.0, 0.0]
    assert centros[1].tolist() == [1.0, 0.0]  # avanza en x primero
    assert centros[52].tolist() == [0.0, 1.0]  # y a la fila siguiente tras 52 (416/8)


# --------------------------------------------------------------- decodificado


def _salida_cruda(*, ancla: int, cx: float, cy: float, w: float, h: float, obj: float, cls: float):
    """Una salida de YOLOX de mentira con UNA detección en el ancla pedida."""
    p = np.zeros((1, 3549, 85), np.float32)
    p[0, ancla, 0] = cx
    p[0, ancla, 1] = cy
    p[0, ancla, 2] = w
    p[0, ancla, 3] = h
    p[0, ancla, 4] = obj
    p[0, ancla, 5 + CLASE_PERSONA] = cls
    return p


def test_el_decodificado_deshace_rejilla_stride_y_exponencial() -> None:
    """`xy = (crudo + centro) · paso` y `wh = exp(crudo) · paso`. El ancla 0 tiene centro
    (0,0) y paso 8, así que un crudo de 0 en xy cae en el píxel 0."""
    # ancla 0: centro (0,0), stride 8. xy crudo 0.5 -> (0.5)*8 = 4. wh crudo 0 -> e^0*8 = 8.
    salida = _salida_cruda(ancla=0, cx=0.5, cy=0.5, w=0.0, h=0.0, obj=1.0, cls=1.0)
    cajas = _a_cajas(salida, 1.0, 0.0, 0.0, ENTRADA, np)

    assert len(cajas) == 1
    c = cajas[0]
    assert (c.x1, c.y1, c.x2, c.y2) == pytest.approx((0.0, 0.0, 8.0, 8.0))


def test_la_escala_del_letterbox_se_deshace_al_volver_a_la_imagen() -> None:
    """Si no se deshace, las cajas salen del tamaño de la ENTRADA del modelo y no de la
    imagen — y el conteo por zona compara contra un polígono en otra escala."""
    salida = _salida_cruda(ancla=0, cx=0.5, cy=0.5, w=0.0, h=0.0, obj=1.0, cls=1.0)
    cajas = _a_cajas(salida, 0.5, 0.0, 0.0, ENTRADA, np)

    assert (cajas[0].x2, cajas[0].y2) == pytest.approx((16.0, 16.0))  # 8 / 0.5


def test_la_confianza_es_el_PRODUCTO_de_objeto_y_clase() -> None:
    """Contar con una sola de las dos mete muebles en el aforo: `objectness` dice «aquí hay
    algo» y la clase dice «es una persona»."""
    salida = _salida_cruda(ancla=0, cx=0.5, cy=0.5, w=0.0, h=0.0, obj=0.8, cls=0.5)
    cajas = _a_cajas(salida, 1.0, 0.0, 0.0, ENTRADA, np)

    assert cajas[0].confianza == pytest.approx(0.4)


def test_solo_se_devuelve_la_clase_persona() -> None:
    """Menos clases es menos superficie de PII y menos cosas que explicar a un cliente."""
    p = np.zeros((1, 3549, 85), np.float32)
    p[0, 0, 4] = 1.0
    p[0, 0, 5 + 72] = 1.0  # 72 = refrigerator, la que la cámara real confundió con un ropero

    assert _a_cajas(p, 1.0, 0.0, 0.0, ENTRADA, np) == []


def test_una_entrada_que_no_le_corresponde_al_modelo_LANZA_en_vez_de_contar_mal() -> None:
    """Es la diferencia entre «este modelo no es el que dices» y un conteo corrido en
    silencio. 416 da 3549 anclas; 640 daría 8400."""
    salida = np.zeros((1, 3549, 85), np.float32)

    with pytest.raises(ValueError, match="no le corresponde"):
        _a_cajas(salida, 1.0, 0.0, 0.0, (640, 640), np)


# ------------------------------------------------------------------- el ancla


def test_en_picado_el_ancla_son_los_pies_y_en_cenital_el_centro() -> None:
    """El borde inferior significa cosas distintas según desde dónde mire la cámara, y
    elegir mal desplaza el conteo SIEMPRE en la misma dirección — la peor clase de error,
    porque parece una medición."""
    c = Caja(100.0, 100.0, 140.0, 300.0, 0.9)

    assert c.ancla(Montaje.FRONTAL) == (120.0, 300.0)
    assert c.ancla(Montaje.PICADO) == (120.0, 300.0)
    assert c.ancla(Montaje.CENITAL) == (120.0, 200.0)


def test_el_montaje_es_una_declaracion_del_sitio_y_no_se_infiere() -> None:
    """Adivinarlo exigiría un modelo más —que también puede equivocarse— para decidir cómo
    se interpreta la salida del primero."""
    assert [m.value for m in Montaje] == ["frontal", "picado", "cenital"]
