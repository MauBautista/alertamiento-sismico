"""El análisis completo, sin depender de cómo se invoque (T-3.12.b).

Existe porque hay **dos** entradas al mismo trabajo y solo puede haber una verdad:

* el CLI (`python -m takab_cctv`), que ejerce el pipeline a mano contra MinIO;
* el **Lambda de la nube**, que lo corre por cada clip que aterriza en S3.

Duplicar la orquestación entre los dos parecía barato hasta mirar qué se duplicaba: el
**fechado de los fotogramas del clip**, que tiene una sutileza de la que dependen `t50` y
`t90`. El clip empieza en `t0 − clip_pre_s`, no en `t0` — sus primeros fotogramas son el
pre-roll—, así que fecharlos desde la señal corre la curva entera hacia delante y los
tiempos de evacuación salen un minuto tarde. Dos copias de esa línea divergen, y cuando
diverjan **las dos van a seguir devolviendo números**: nadie va a ver un error, solo un
dictamen que dice que la gente tardó de más.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from takab_cctv.aforo import Poligono, a_muestras, serie_de
from takab_cctv.capturas import descargar, elegir, extraer
from takab_cctv.detector import DetectorBackend, Montaje
from takab_cctv.metricas import Sacudida, calcular


@dataclass(frozen=True)
class Analisis:
    """Lo que sale del pipeline. Es lo que el CLI imprime y lo que el Lambda persiste."""

    muestras: int
    detector: str | None
    evacuacion: dict
    correlacion: str
    reingreso: str
    discrepancia: str | None
    capturas: list[dict]
    #: La curva de aforo, instante a instante. El CLI no la imprime —sería ilegible— pero
    #: el Lambda la escribe entera en `cctv_occupancy`: es de donde sale la gráfica del
    #: reporte, y sin ella las métricas serían cuatro números sin nada que los respalde.
    curva: list


def fotogramas_del_clip(
    origen: str,
    *,
    t0: datetime,
    clip_pre_s: float,
    fps: float,
    ffmpeg: str,
    endpoint_url: str | None = None,
) -> list[tuple[datetime, bytes]]:
    """Descarga (si hace falta), extrae fotogramas y **los fecha**. La parte delicada.

    El instante de cada fotograma se **deriva** del muestreo: ffmpeg los numera `1..N` y el
    primero cae en el inicio del clip. Del nombre del fichero no se puede sacar.
    """
    with tempfile.TemporaryDirectory(prefix="takab-cctv-") as tmp:
        carpeta = Path(tmp)
        clip = (
            descargar(origen, carpeta, endpoint_url=endpoint_url)
            if origen.startswith("s3://")
            else Path(origen)
        )
        jpgs = extraer(clip, carpeta, ffmpeg=ffmpeg, fps=fps)
        paso = 1.0 / fps
        base = t0.timestamp() - clip_pre_s
        return [
            (datetime.fromtimestamp(base + i * paso, UTC), j.read_bytes())
            for i, j in enumerate(jpgs)
        ]


def analizar(
    fotogramas: list[tuple[datetime, bytes]],
    detector: DetectorBackend,
    *,
    t0: datetime,
    ancho: int,
    alto: int,
    zona: Poligono | None = None,
    montaje: Montaje = Montaje.PICADO,
    t_dictamen: datetime | None = None,
    checkins: int | None = None,
    sacudida: Sacudida | None = None,
) -> Analisis:
    """Del conjunto de fotogramas al análisis completo. **Fusiona por instante.**

    El clip trae la salida —`t50`/`t90`— y el goteo el reingreso, que ocurre horas después.
    El motor necesita las dos mitades **en una sola curva**, así que se ordenan aquí y no
    en quien llama: es la clase de paso que se olvida en una de las dos entradas.
    """
    fotogramas = sorted(fotogramas, key=lambda par: par[0])
    curva = serie_de(fotogramas, detector, ancho=ancho, alto=alto, zona=zona, montaje=montaje)
    muestras = a_muestras(curva)
    evac = calcular(
        muestras,
        t0=t0,
        t_dictamen=t_dictamen,
        checkins=checkins,
        sacudida=sacudida or Sacudida(None, None),
    )
    return Analisis(
        muestras=len(muestras),
        detector=curva[0].detector if curva else None,
        evacuacion={
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in asdict(evac).items()
            if k not in ("discrepancia", "sacudida")
        },
        correlacion=evac.correlacion(),
        reingreso=evac.veredicto_reingreso(),
        discrepancia=evac.discrepancia.lectura if evac.discrepancia else None,
        capturas=[
            {"papel": e.papel, "ts": e.ts.isoformat() if e.ts else None, "razon": e.razon}
            for e in elegir(muestras, evac, t0=t0)
        ],
        curva=curva,
    )
