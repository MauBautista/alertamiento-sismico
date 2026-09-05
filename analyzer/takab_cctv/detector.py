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
from enum import StrEnum
from typing import Protocol, runtime_checkable

#: Índice de la clase «persona» en COCO, que es con lo que se entrenan YOLOX, RF-DETR y
#: EfficientDet-Lite. Es lo ÚNICO que este sistema mira: no se detectan coches, ni mochilas,
#: ni caras. Menos clases es menos superficie de PII y menos cosas que explicar a un cliente.
CLASE_PERSONA = 0

#: Por debajo de esto una detección no cuenta. Deliberadamente alto: en una zona de reunión
#: interesa MÁS no inventar gente que no perderse a alguien — un aforo inflado exagera la
#: evacuación y un reporte que exagera es un reporte que nadie vuelve a creer.
CONFIANZA_MINIMA = 0.35


class Montaje(StrEnum):
    """Cómo está montada la cámara. **Es un dato del sitio, no una preferencia.**

    Existe porque el punto de la caja que toca el suelo depende del ángulo, y equivocarse
    desplaza el conteo siempre hacia el mismo lado. Lo declara quien instala, y el runbook de
    alta de cámara lo pide antes de dar el sitio por configurado.

    No se infiere de la imagen a propósito: adivinarlo exigiría un modelo más —uno que
    también puede equivocarse— para decidir cómo se interpreta la salida del primero.
    """

    #: Cámara a la altura de la vista. Se ve el cuerpo entero de lado.
    FRONTAL = "frontal"
    #: Montada en alto y girada hacia abajo, pero todavía se ve el cuerpo. **El caso normal
    #: de un punto de reunión**, y el que mejor tolera un detector entrenado con COCO.
    PICADO = "picado"
    #: Mirando casi a plomo. Se ven cabeza y hombros y poco más. Cambia el ancla **y**
    #: degrada la detección: ver la advertencia del runbook de alta.
    CENITAL = "cenital"


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
        """Borde inferior. El ancla correcta **solo con la cámara mirando de frente**.

        Con una cámara frontal o en picado suave, una persona de pie ocupa una caja alta y su
        centro cae por encima del suelo: usar el centro contaría dentro a quien está parado
        justo fuera del polígono —y al revés—, con un error que crece con la altura de la
        caja, o sea con lo cerca que esté de la cámara.

        **Deja de ser cierto en cenital**, y por eso ya no se usa directamente: ver
        :meth:`ancla`.
        """
        return ((self.x1 + self.x2) / 2, self.y2)

    def ancla(self, montaje: Montaje) -> tuple[float, float]:
        """El punto que decide si alguien está DENTRO de la zona, **según cómo se montó**.

        Esto no es configurabilidad por gusto: es que el borde inferior de la caja significa
        cosas distintas según desde dónde mire la cámara, y elegir mal desplaza el conteo de
        forma sistemática —siempre en la misma dirección— que es la peor clase de error,
        porque parece una medición.

        * **`FRONTAL` y `PICADO`** — la caja envuelve un cuerpo de pie visto de lado; su
          borde inferior son los pies, que es donde la persona toca el suelo.
        * **`CENITAL`** — la cámara mira hacia abajo y la caja envuelve **cabeza y hombros**
          vistos desde arriba. Ahí no hay «pies»: el borde inferior es el hombro que quedó
          más lejos del centro óptico, y usarlo empuja a todo el mundo hacia un lado del
          encuadre. El centroide es el punto que corresponde.

        El caso intermedio —picado pronunciado— se declara `PICADO` a propósito: mientras se
        vea el cuerpo, los pies siguen siendo el contacto con el suelo. `CENITAL` se reserva
        para cuando ya no se ven.
        """
        return self.centro if montaje is Montaje.CENITAL else self.pies

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


def cargar_onnx(
    ruta: str, *, ffmpeg: str, entrada: tuple[int, int] = (416, 416)
) -> DetectorBackend:
    """Backend ONNX real (YOLOX / D-FINE, ambos Apache-2.0) sobre `onnxruntime` (MIT).

    Import PEREZOSO y dentro de la función: `onnxruntime` y `numpy` viven en el extra `onnx`,
    que no se instala ni en CI ni en la imagen de la API. El núcleo de este paquete tiene que
    seguir importándose sin ellos — es lo que permite que el motor de métricas se pruebe sin
    tocar un modelo.
    """
    from takab_cctv.imagen import a_rgb  # noqa: PLC0415 — junto al resto del extra

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
            pixeles, _ = a_rgb(imagen, ffmpeg=ffmpeg)
            tensor, escala, (dx, dy) = _preparar(pixeles, entrada, np)
            salida = sesion.run(None, {nombre_entrada: tensor})[0]
            return filtrar(_a_cajas(salida, escala, dx, dy, entrada, np))

    return _Onnx()


#: Valor del relleno del letterbox. Es el que usa YOLOX al entrenar y al evaluar; cambiarlo
#: mueve las detecciones de los bordes, que son justo las que deciden si alguien entró o
#: salió de la zona.
RELLENO = 114

#: Pasos de la pirámide de YOLOX. Con entrada 416 dan 52²+26²+13² = 3549 anclas, que es
#: exactamente la primera dimensión de la salida — y por eso esto se puede COMPROBAR en vez
#: de creerse: si el modelo devuelve otra cantidad, la rejilla no le corresponde.
STRIDES = (8, 16, 32)


def rejilla(entrada: tuple[int, int], np):
    """Centro y paso de cada ancla, en el orden en que el modelo las emite.

    El orden importa y no es negociable: la salida es una lista plana de anclas y la única
    forma de saber a qué punto de la imagen corresponde cada fila es reconstruir la misma
    pirámide, del paso más fino al más grueso, recorriendo filas antes que columnas.
    """
    ancho, alto = entrada
    centros, pasos = [], []
    for paso in STRIDES:
        h, w = alto // paso, ancho // paso
        yv, xv = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        centros.append(np.stack((xv, yv), 2).reshape(-1, 2))
        pasos.append(np.full((h * w, 1), paso))
    return np.concatenate(centros).astype(np.float32), np.concatenate(pasos).astype(np.float32)


def _preparar(imagen, entrada: tuple[int, int], np):
    """Letterbox: redimensiona SIN deformar y rellena. Compartido por las dos orillas.

    Estirar la imagen a la entrada del modelo cambia la relación de aspecto de las personas,
    y un detector entrenado con personas de pie pierde recall con personas achatadas. El
    relleno se descuenta después, al devolver las coordenadas.

    Recibe **píxeles ya decodificados** —`(alto, ancho, 3)` en RGB— y no bytes: quien los
    obtiene es `imagen.a_rgb`, que necesita ffmpeg y por tanto una decisión de despliegue.
    Separarlo deja esta función pura y comprobable sin un binario delante.

    El relleno va **abajo y a la derecha**, nunca centrado. Con relleno centrado hay que
    restar un desplazamiento en las dos direcciones al volver a coordenadas de la imagen, y
    un signo equivocado ahí produce detecciones plausibles pero corridas — el error que
    ninguna prueba de humo detecta. Con el origen intacto, deshacer la escala es dividir.
    """
    alto, ancho = imagen.shape[:2]
    ancho_d, alto_d = entrada
    escala = min(ancho_d / ancho, alto_d / alto)
    nw, nh = max(1, int(ancho * escala)), max(1, int(alto * escala))

    # Vecino más cercano con indexado de numpy: sin dependencia de remuestreo y determinista.
    # Un remuestreo mejor (bilineal) cambiaría poco el recall y sí el resultado entre
    # versiones de la librería que lo implemente — y estos números acaban en un dictamen.
    yi = np.minimum((np.arange(nh) / escala).astype(np.int32), alto - 1)
    xi = np.minimum((np.arange(nw) / escala).astype(np.int32), ancho - 1)
    lienzo = np.full((alto_d, ancho_d, 3), RELLENO, np.uint8)
    lienzo[:nh, :nw] = imagen[yi][:, xi]

    tensor = lienzo.transpose(2, 0, 1)[None].astype(np.float32)
    return tensor, escala, (0.0, 0.0)


def _a_cajas(
    salida, escala: float, dx: float, dy: float, entrada: tuple[int, int], np
) -> list[Caja]:
    """Decodifica la salida cruda de YOLOX a cajas en píxeles de la imagen original.

    **El export oficial de YOLOX NO decodifica dentro del grafo**, y esto costó una tarde
    entera: sus `xywh` salen como offsets crudos —medido, en rango `-2…3`— y no como píxeles.
    Interpretarlos directamente da cero detecciones **sin error ninguno**, que es la forma más
    cara de equivocarse: un conteo de cero personas parece un punto de reunión vacío.

    La transformación es la de la publicación:

        xy = (crudo + centro_del_ancla) · paso
        wh = exp(crudo) · paso

    y el `exp` es la señal de que estaba sin decodificar: unas anchuras que caben en `-2…3`
    no son píxeles de nada.

    La confianza es `objectness × probabilidad_de_clase`, no una de las dos: la primera dice
    «aquí hay algo» y la segunda «es una persona», y contar con una sola de ellas mete
    muebles en el aforo.
    """
    p = salida[0].astype(np.float32, copy=True)
    centros, pasos = rejilla(entrada, np)
    if len(centros) != len(p):
        # Se comprueba en vez de suponerse: es lo que distingue «este modelo no es el que
        # dices» de un conteo silenciosamente corrido. 416 da 3549 anclas; 640 da 8400.
        raise ValueError(
            f"el modelo devolvió {len(p)} anclas y la rejilla de {entrada[0]}×{entrada[1]} "
            f"produce {len(centros)}: la entrada declarada no le corresponde a este modelo"
        )
    p[:, :2] = (p[:, :2] + centros) * pasos
    p[:, 2:4] = np.exp(p[:, 2:4]) * pasos

    objeto = p[:, 4]
    clases = p[:, 5:]
    mejor = clases.argmax(1)
    confianza = objeto * clases[np.arange(len(clases)), mejor]

    # `> 0` además de la clase, y no es una micro-optimización: con todas las
    # puntuaciones a cero `argmax` devuelve 0, que **es** `CLASE_PERSONA`. Sin este filtro,
    # un tensor degenerado —un modelo mal cargado, una salida que no es la que se cree—
    # produce 3549 «personas» de confianza cero en vez de ninguna. `filtrar()` las tiraría
    # después, pero esta función estaría mintiendo sobre lo que devuelve, y el error solo se
    # vería al contar. Lo cazó su propio test.
    #
    # El UMBRAL de producto sigue viviendo en `filtrar()`: aquí solo se descarta lo que no
    # es una detección en absoluto.
    es_persona = (mejor == CLASE_PERSONA) & (confianza > 0)
    xy, wh = p[es_persona][:, :2], p[es_persona][:, 2:4]
    x1y1 = (xy - wh / 2 - np.array([dx, dy], np.float32)) / escala
    x2y2 = (xy + wh / 2 - np.array([dx, dy], np.float32)) / escala
    return [
        Caja(float(a), float(b), float(c), float(d), float(s))
        for (a, b), (c, d), s in zip(x1y1, x2y2, confianza[es_persona], strict=True)
    ]
