"""Simulador de la cámara ONVIF **y de la frontera de ffmpeg** (T-3.11).

Modela las dos cosas que separan a `takab-cctv` de poder ejercerse en una máquina de
desarrollo, y las modela juntas porque por separado no sirven de nada:

- **la cámara**: unas `Fuentes` que apuntan a ninguna parte, con la forma exacta que
  devuelve `GetStreamUri`/`GetSnapshotUri`;
- **ffmpeg**: la llamada `correr(cmd)` que el cliente usa para mantener el anillo, recortar
  el clip y tomar capturas. El simulador la reconoce por sus banderas y **escribe los
  ficheros que ese comando habría escrito**.

Con las dos, el cliente corre **sin cambiar una línea**: graba el anillo, corta el clip en
`pendientes/` con su metadato, gotea capturas y las sube. Es lo que hace ejecutable el E2E
completo —gabinete → grant → S3/MinIO → analizador → métricas → reporte— sin cámara, sin
ffmpeg y sin AWS.

LO QUE ESTE SIMULADOR **NO** ACREDITA
─────────────────────────────────────
Los segmentos del anillo **no son vídeo decodificable**: son bytes con el tamaño y el
nombre que tendrían. Eso basta para el camino del gabinete —que remuxea con ``-c copy`` y
nunca decodifica— pero significa que aquí NO se prueba nada de lo que solo un ffmpeg real
puede fallar: que el substream de la cámara traiga keyframes donde hacen falta, que el
recorte no empiece en gris, o que el `concat` acepte la lista. Eso es `GATE-HW`, con la
cámara delante.

Las capturas **sí son JPEG válidos** —un gris de 16×16, embebido más abajo— para que nada
reviente al intentar decodificarlas. Pero no son fotos de personas: un detector real no
verá a nadie en ellas, y por eso la «historia» de cuánta gente hay va aparte, en
:meth:`CamaraSimulada.guion`, en vez de escondida en los píxeles. Fingir que un detector
podría leerla del JPEG sería exactamente el tipo de verde mentiroso que este árbol persigue.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from takab_edge.cctv.onvif import Fuentes
from takab_edge.cctv.recorder import SEGMENTO_S, nombre_de

#: JPEG real de 16×16 en gris, 159 bytes. Se embebe ya codificado a propósito: generarlo
#: exigiría Pillow, que en este árbol solo existe como dependencia TRANSITIVA de obspy y
#: `simulators/` viaja dentro del wheel. Un import que hoy funciona por casualidad es un
#: arranque roto el día que obspy cambie de dependencias.
_JPEG_MINIMO = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6eHJm"
    "cG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/wAALCAAQABABAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAAAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AAP/Z"
)

#: Tamaño de un segmento del anillo. Del orden de lo que ocupan 10 s de substream H.264 a
#: ~512 kbps: importa porque la cuota de disco del cliente se prueba con estos bytes, y con
#: segmentos de 10 bytes esa guarda nunca se ejercería.
_BYTES_POR_SEGMENTO = 640 * 1024


@dataclass
class CamaraSimulada:
    """La cámara y el ffmpeg del gabinete, en memoria y sobre `directorio`.

    Se inyecta por constructor —como todos los dobles de este árbol— y no parchea nada::

        camara = CamaraSimulada(directorio=tmp)
        cliente = ClienteCctv(..., fuentes=camara.fuentes(), correr=camara.correr)
    """

    directorio: Path
    #: Cuánta gente hay en la zona en cada captura, en orden. Es la HISTORIA que el
    #: analizador tiene que ver, y vive aquí —explícita— porque en los píxeles no está.
    guion: list[int] = field(default_factory=list)

    #: Comandos que el cliente pidió, para que un test pueda afirmar sobre ellos.
    comandos: list[list[str]] = field(default_factory=list)
    #: Capturas tomadas, en orden. Su índice es el que indexa `guion`.
    capturas: list[Path] = field(default_factory=list)
    #: Fallar el siguiente comando, para ejercer los caminos de error del cliente.
    falla_siguiente: bool = False

    # ------------------------------------------------------------------ cámara

    def fuentes(self, *, con_instantanea: bool = True) -> Fuentes:
        """Lo que devolvería `descubrir()`. Con credencial, como la cámara real.

        `con_instantanea=False` modela la cámara barata que no ofrece `GetSnapshotUri`:
        el goteo tiene que salir del RTSP y **decodificar**, que es un coste muy distinto.
        Es un caso que conviene poder probar, no una rareza.
        """
        return Fuentes(
            rtsp_principal="rtsp://takab:no-es-un-secreto@camara.sim/main",
            rtsp_substream="rtsp://takab:no-es-un-secreto@camara.sim/sub",
            snapshot="http://takab:no-es-un-secreto@camara.sim/snap.jpg"
            if con_instantanea
            else None,
        )

    # ------------------------------------------------------------------ ffmpeg

    def correr(self, cmd: list[str]) -> int:
        """Sustituye a ffmpeg. Reconoce el comando por sus banderas y escribe la salida.

        Distinguir los tres por su forma —y no por un parámetro— es deliberado: si alguien
        cambia el comando del anillo por uno que decodifica, este simulador deja de
        reconocerlo y el test se entera. Un doble que acepte cualquier cosa no vigila nada.
        """
        self.comandos.append(list(cmd))
        if self.falla_siguiente:
            self.falla_siguiente = False
            return 1

        salida = Path(cmd[-1])
        if "-frames:v" in cmd:
            salida.write_bytes(_JPEG_MINIMO)
            self.capturas.append(salida)
            return 0
        if "concat" in cmd:
            # El recorte cose segmentos: su tamaño sale de cuántos entraron en la lista.
            lista = Path(cmd[cmd.index("-i") + 1])
            trozos = len(lista.read_text(encoding="utf-8").splitlines()) if lista.exists() else 1
            salida.write_bytes(b"\0" * (_BYTES_POR_SEGMENTO * max(trozos, 1)))
            return 0
        # El anillo es un proceso de larga vida: aquí no escribe nada. Los segmentos los
        # produce `avanzar()`, que es quien controla el tiempo.
        return 0

    # -------------------------------------------------------------------- reloj

    def avanzar(self, desde: datetime, hasta: datetime) -> list[Path]:
        """Escribe los segmentos del anillo que ffmpeg habría escrito en ese intervalo.

        Va aparte de `correr()` porque el anillo NO es un comando que termina: es un
        proceso que lleva minutos grabando cuando llega la alerta. Modelarlo como una
        llamada daría un anillo vacío justo en el instante que importa — el pre-roll.
        """
        self.directorio.mkdir(parents=True, exist_ok=True)
        escritos: list[Path] = []
        instante = desde
        while instante < hasta:
            ruta = self.directorio / nombre_de(instante)
            if not ruta.exists():
                ruta.write_bytes(b"\0" * _BYTES_POR_SEGMENTO)
                escritos.append(ruta)
            instante += timedelta(seconds=SEGMENTO_S)
        return escritos

    def preparar_preroll(self, t0: datetime, *, segundos: float = 180.0) -> list[Path]:
        """Deja el anillo como estaría en el instante de la señal: ya lleno hacia atrás.

        Es el estado normal del gabinete y el que hace que el clip pueda cubrir su `T−60 s`.
        Un test que no lo prepare está probando un gabinete recién arrancado, que es un caso
        distinto y también vale — pero conviene que sea una elección.
        """
        return self.avanzar(t0 - timedelta(seconds=segundos), t0)

    # ------------------------------------------------------------------ historia

    def personas_en(self, indice: int) -> int:
        """Cuánta gente hay en la captura número `indice`, según el guion.

        Es lo que un `DetectorFalso` tiene que devolver para que el analizador vea la misma
        historia que el simulador escribió. Fuera del guion, cero: la evacuación terminó.
        """
        return self.guion[indice] if 0 <= indice < len(self.guion) else 0
