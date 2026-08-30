"""El adaptador del detector de personas (T-3.12 · `D-24`).

UN PROTOCOLO, NO UNA LIBRERÍA
─────────────────────────────
El motor no importa un detector: recibe uno. Esa costura existe por tres razones concretas,
y ninguna es abstracción por gusto:

1. **Licencias.** `ultralytics` —el camino más rápido y mejor documentado— es AGPL-3.0 y
   está PROHIBIDO en este árbol (`D-24`, vigilado por `ci/licencias.py`). El día que alguien
   quiera probar otro modelo, cambia el backend y no el motor.
2. **`T-3.12.d` compara varios** contra la cámara real —YOLOX-nano, YOLOX-tiny, RF-DETR nano,
   EfficientDet-Lite0— y **la medición fija el default, no la opinión**. Sin esta costura la
   comparativa sería reescribir el pipeline cuatro veces.
3. **Los tests no descargan pesos.** `DetectorFalso` produce detecciones deterministas, así
   que CI prueba el motor entero sin red y sin ONNX.

EL MISMO PRE Y POST-PROCESO EN LAS DOS ORILLAS
──────────────────────────────────────────────
`D-24` deja el conteo preliminar del borde APLAZADO, no descartado. El día que exista el
equipo de campo, el conteo local tiene que producir números **comparables** con los de la
nube — si no, el «final sobrescribe al preliminar» cambiaría de unidades a mitad de una
curva. Por eso el redimensionado con letterbox y el NMS viven aquí, en el adaptador
compartido, y no dentro de cada backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Índice de la clase «persona» en COCO, que es con lo que se entrenan YOLOX, RF-DETR y
#: EfficientDet-Lite. Es lo ÚNICO que este sistema mira: no se detectan coches, ni mochilas,
#: ni caras. Menos clases es menos superficie de PII y menos cosas que explicar a un cliente.
CLASE_PERSONA = 0

#: Por debajo de esto una detección no cuenta. Deliberadamente alto: en una zona de reunión
#: interesa MÁS no inventar gente que no perderse a alguien — un aforo inflado exagera la
#: evacuación y un reporte que exagera es un reporte que nadie vuelve a creer.
CONFIANZA_MINIMA = 0.35


@dataclass(frozen=True)
class Caja:
    """Una detección. Coordenadas en píxeles del fotograma original."""

    x1: float
    y1: float
    x2: float
    y2: float
    confianza: float

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def pies(self) -> tuple[float, float]:
        """El punto que decide si alguien está DENTRO de la zona.

        Se usa el borde inferior y no el centro: una persona de pie ocupa una caja alta, y
        su centro cae por encima del suelo. Con el centro, alguien parado justo fuera del
        polígono se contaría dentro —y al revés—, y el error crece con la altura de la caja,
        o sea con lo cerca que esté de la cámara.
        """
        return ((self.x1 + self.x2) / 2, self.y2)

    def iou(self, otra: Caja) -> float:
        ix1, iy1 = max(self.x1, otra.x1), max(self.y1, otra.y1)
        ix2, iy2 = min(self.x2, otra.x2), min(self.y2, otra.y2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        area = (self.x2 - self.x1) * (self.y2 - self.y1)
        area_otra = (otra.x2 - otra.x1) * (otra.y2 - otra.y1)
        return inter / (area + area_otra - inter)


@runtime_checkable
class DetectorBackend(Protocol):
    """Lo único que el motor necesita saber de un detector.

    `imagen` son los bytes del fotograma ya codificado (JPEG). Se pasa codificado y no como
    array a propósito: es lo que llega de la cámara y del goteo de capturas, y evita que el
    motor tenga que depender de NumPy para hablar con el backend.
    """

    #: Para que el reporte pueda declarar CON QUÉ se contó. Un número de aforo sin decir qué
    #: modelo lo produjo no es auditable — y `T-3.12.d` puede cambiar el default.
    nombre: str

    def detectar(self, imagen: bytes) -> list[Caja]: ...


class DetectorFalso:
    """Backend determinista para tests. **No mira la imagen**: devuelve lo que se le dijo.

    Existe para que CI pruebe el motor entero sin descargar un peso ni instalar ONNX, que es
    un criterio literal de la ficha.
    """

    nombre = "falso"

    def __init__(self, guion: list[list[Caja]] | None = None) -> None:
        self._guion = list(guion or [])
        self.llamadas = 0

    def detectar(self, imagen: bytes) -> list[Caja]:  # noqa: ARG002 — el doble ignora la imagen
        salida = self._guion[self.llamadas] if self.llamadas < len(self._guion) else []
        self.llamadas += 1
        return salida


def nms(cajas: list[Caja], *, umbral_iou: float = 0.45) -> list[Caja]:
    """Supresión de no-máximos, compartida por TODOS los backends.

    Vive aquí y no dentro de cada backend para que el borde y la nube produzcan el mismo
    número sobre el mismo fotograma. Si cada uno trajera el suyo, «el conteo final
    sobrescribe al preliminar» estaría mezclando dos formas de contar.
    """
    quedan = sorted(cajas, key=lambda c: c.confianza, reverse=True)
    elegidas: list[Caja] = []
    while quedan:
        mejor = quedan.pop(0)
        elegidas.append(mejor)
        quedan = [c for c in quedan if mejor.iou(c) < umbral_iou]
    return elegidas


def filtrar(cajas: list[Caja], *, confianza_minima: float = CONFIANZA_MINIMA) -> list[Caja]:
    """Umbral de confianza + NMS, en ese orden. El post-proceso común de las dos orillas."""
    return nms([c for c in cajas if c.confianza >= confianza_minima])


def cargar_onnx(ruta: str, *, entrada: tuple[int, int] = (640, 384)) -> DetectorBackend:
    """Backend ONNX real (YOLOX / D-FINE, ambos Apache-2.0) sobre `onnxruntime` (MIT).

    Import PEREZOSO y dentro de la función: `onnxruntime` y `numpy` viven en el extra `onnx`,
    que no se instala ni en CI ni en la imagen de la API. El núcleo de este paquete tiene que
    seguir importándose sin ellos — es lo que permite que el motor de métricas se pruebe sin
    tocar un modelo.
    """
    try:
        import numpy as np  # noqa: PLC0415
        import onnxruntime as ort  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — depende del extra
        raise RuntimeError(
            "falta el extra `onnx` del analizador. Instálalo con `uv sync --extra onnx` "
            "en la máquina que procesa vídeo"
        ) from exc

    sesion = ort.InferenceSession(ruta, providers=["CPUExecutionProvider"])
    nombre_entrada = sesion.get_inputs()[0].name

    class _Onnx:
        nombre = f"onnx:{ruta.rsplit('/', 1)[-1]}"

        def detectar(self, imagen: bytes) -> list[Caja]:
            tensor, escala, (dx, dy) = _preparar(imagen, entrada, np)
            salida = sesion.run(None, {nombre_entrada: tensor})[0]
            return filtrar(_a_cajas(salida, escala, dx, dy))

    return _Onnx()


def _preparar(imagen: bytes, entrada: tuple[int, int], np):  # pragma: no cover — necesita el extra
    """Letterbox: redimensiona SIN deformar y rellena. Compartido por las dos orillas.

    Estirar la imagen a la entrada del modelo cambia la relación de aspecto de las personas,
    y un detector entrenado con personas de pie pierde recall con personas achatadas. El
    relleno se descuenta después, al devolver las coordenadas.
    """
    raise NotImplementedError(
        "el pre-proceso real llega con T-3.12.d, que es quien mide qué modelo y qué entrada "
        "acierta contra la cámara de verdad. Fijarlo antes sería elegir por opinión."
    )


def _a_cajas(salida, escala: float, dx: float, dy: float) -> list[Caja]:  # pragma: no cover
    raise NotImplementedError("ídem: el post-proceso se fija con el modelo que gane T-3.12.d")
