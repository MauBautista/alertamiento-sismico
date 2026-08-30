"""Analítica de evacuación a partir de la curva de aforo (T-3.12).

Este módulo es **aritmética pura**: recibe una serie de `(instante, personas)` y devuelve
los números que van al reporte del incidente. No sabe de vídeo, ni de modelos, ni de S3, y
por eso se prueba entero sin descargar un solo peso.

LA CURVA ES LA MEDIDA; EL CRUCE DE LÍNEA NO
───────────────────────────────────────────
Todo lo que el reporte necesita —cuánta gente salió, cuánto tardó la mayor parte, cuándo
empezó el reingreso— sale de **cuántas personas hay en la zona en cada instante**. Es un
conteo por fotograma: no exige seguir a nadie entre fotogramas, así que no depende de que
el seguimiento asocie bien a 1 fps ni de que la cámara vea a la gente de frente.

El conteo direccional por cruce de línea daría *entradas* y *salidas* por separado, que es
más rico — y también mucho más frágil: exige un tracker calibrado contra ESA escena. Es lo
que mide `T-3.12.d` cuando exista la cámara. Construirlo antes sería fijar un default por
opinión, que es justo lo que la ficha prohíbe.

QUÉ SIGNIFICA `None` AQUÍ
─────────────────────────
`None` es «no se pudo medir», y **nunca** se degrada a `0`. Un `t90` de cero diría que la
gente salió instantáneamente; un `t90` ausente dice que no lo sabemos. Cada ausencia viaja
además con su razón en `notas`, porque un hueco sin explicar se lee como un fallo del
sistema y no como lo que suele ser: una cámara que no vio nada porque no había nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

#: Ventana anterior a la señal con la que se estima el aforo NORMAL de la zona. Se corta 10 s
#: antes de la señal a propósito: los segundos inmediatamente anteriores ya pueden tener
#: gente moviéndose por la alerta de un vecino o por el propio sismo, y meterlos en la línea
#: base inflaría el «antes» y encogería la evacuación medida.
BASE_DESDE_S = 60.0
BASE_HASTA_S = 10.0

#: Fracción del pico que marca «la mayor parte ya salió». `t90` es la que va al reporte.
FRACCION_MEDIA = 0.5
FRACCION_MAYORIA = 0.9

#: El reingreso se declara cuando el aforo cae bajo esta fracción del pico **y se
#: mantiene** durante `MUESTRAS_HISTERESIS` muestras seguidas. Sin la histéresis, una
#: persona que sale de cuadro un instante declararía iniciado el reingreso.
FRACCION_REINGRESO = 0.5
MUESTRAS_HISTERESIS = 3

#: Por debajo de esto no hay evacuación que medir: es ruido de detección sobre una zona
#: vacía. Devolver `t90` sobre un pico de dos personas sería inventar una métrica.
PICO_MINIMO = 3


@dataclass(frozen=True)
class Muestra:
    """Personas vistas en la zona de reunión en un instante."""

    ts: datetime
    n: int


@dataclass(frozen=True)
class Discrepancia:
    """Aforo por cámara frente a check-in de vida. **Nunca se promedian.**

    Son dos estimaciones independientes de la misma cosa, y `T-3.12` es explícita: la
    diferencia ES la información. Promediarlas produciría un número que no corresponde a
    ninguna medición y que oculta el único caso que importa —que no cuadren—.
    """

    aforo_camara: int | None
    checkins: int | None

    @property
    def diferencia(self) -> int | None:
        if self.aforo_camara is None or self.checkins is None:
            return None
        return self.aforo_camara - self.checkins

    @property
    def lectura(self) -> str:
        """Qué significa la diferencia, en palabras. Un número solo no acciona nada."""
        d = self.diferencia
        if d is None:
            return "SIN CRUCE · falta una de las dos estimaciones"
        if d == 0:
            return "las dos estimaciones coinciden"
        if d > 0:
            return (
                f"{d} persona(s) MÁS en cámara que en el pase de lista: "
                "puede haber gente fuera que no confirmó"
            )
        return (
            f"{-d} persona(s) MÁS en el pase de lista que en cámara: "
            "puede haber gente que confirmó desde otro punto, o fuera del encuadre"
        )


@dataclass(frozen=True)
class Sacudida:
    """Cuánto se movió el inmueble. **Sale del sismómetro, no de la cámara.**

    Va aquí, pegado a la evacuación, porque el número que interesa no es ninguno de los dos
    por separado: es «sacudió TANTO y la gente tardó TANTO». Medirlo por visión era la otra
    opción y se descartó —una cámara que se sacude a la vez mide su propio movimiento, no el
    del edificio— así que estos valores vienen de `incidents.max_pga_g`/`max_pgv_cms`, que
    ya están medidos y acreditados.
    """

    max_pga_g: float | None = None
    max_pgv_cms: float | None = None

    @property
    def declarada(self) -> bool:
        return self.max_pga_g is not None or self.max_pgv_cms is not None


@dataclass(frozen=True)
class Evacuacion:
    """Lo que el reporte publica. Todo `None` es «no medido», jamás cero."""

    baseline_n: int | None = None
    peak_n: int | None = None
    peak_at: datetime | None = None
    t50_s: float | None = None
    t90_s: float | None = None
    reentry_start_at: datetime | None = None
    dictamen_lag_s: float | None = None
    reentry_lag_s: float | None = None
    discrepancia: Discrepancia | None = None
    #: La sacudida medida por el sismómetro, para leerla AL LADO de `t90_s`.
    sacudida: Sacudida | None = None
    notas: tuple[str, ...] = field(default_factory=tuple)

    def correlacion(self) -> str:
        """«Sacudió tanto, la gente tardó tanto», en una línea.

        Es la frase que el reporte necesita y que ninguno de los dos números da solo.
        """
        if self.t90_s is None:
            return "SIN TIEMPO DE SALIDA · no se pudo medir la evacuación"
        if self.sacudida is None or not self.sacudida.declarada:
            return (
                f"la mayor parte salió en {self.t90_s:.0f} s · "
                "SIN SACUDIDA DECLARADA para correlacionar"
            )
        partes = []
        if self.sacudida.max_pga_g is not None:
            partes.append(f"PGA {self.sacudida.max_pga_g:.3f} g")
        if self.sacudida.max_pgv_cms is not None:
            partes.append(f"PGV {self.sacudida.max_pgv_cms:.1f} cm/s")
        return f"sacudida {' · '.join(partes)} — la mayor parte salió en {self.t90_s:.0f} s"

    @property
    def reingreso_antes_del_dictamen(self) -> bool:
        """**Un hallazgo de seguridad, no un número negativo.**

        Si la gente volvió a entrar antes de que hubiera un dictamen firmado, el edificio se
        reocupó sin que nadie certificara que era habitable. El reporte tiene que decirlo con
        palabras (ver :meth:`veredicto_reingreso`), porque un `-412.0` en una tabla no lo dice.
        """
        return self.reentry_lag_s is not None and self.reentry_lag_s < 0

    def veredicto_reingreso(self) -> str:
        if self.reentry_lag_s is None:
            return "SIN DATO · no se observó el inicio del reingreso"
        if self.reingreso_antes_del_dictamen:
            return (
                f"⚠ EL REINGRESO EMPEZÓ {abs(self.reentry_lag_s):.0f} s ANTES del dictamen "
                "firmado: el inmueble se reocupó sin certificación de habitabilidad"
            )
        return f"el reingreso empezó {self.reentry_lag_s:.0f} s después del dictamen firmado"


def _primer_cruce(serie: list[Muestra], umbral: float, desde: datetime) -> datetime | None:
    return next((m.ts for m in serie if m.ts >= desde and m.n >= umbral), None)


def _inicio_de_reingreso(serie: list[Muestra], pico: int, t_pico: datetime) -> datetime | None:
    """Primera caída SOSTENIDA bajo la mitad del pico, después del pico."""
    umbral = pico * FRACCION_REINGRESO
    seguidas = 0
    candidato: datetime | None = None
    for m in serie:
        if m.ts <= t_pico:
            continue
        if m.n < umbral:
            seguidas += 1
            if candidato is None:
                candidato = m.ts
            if seguidas >= MUESTRAS_HISTERESIS:
                return candidato
        else:
            seguidas = 0
            candidato = None
    return None


def calcular(
    serie: list[Muestra],
    *,
    t0: datetime,
    t_dictamen: datetime | None = None,
    checkins: int | None = None,
    sacudida: Sacudida | None = None,
) -> Evacuacion:
    """Deriva la analítica de evacuación. `t0` es la señal (`incidents.opened_at`)."""
    notas: list[str] = []
    if not serie:
        return Evacuacion(
            sacudida=sacudida, notas=("SIN SERIE · no hay conteo para este incidente",)
        )

    orden = sorted(serie, key=lambda m: m.ts)

    previas = [
        m.n
        for m in orden
        if t0 - timedelta(seconds=BASE_DESDE_S) <= m.ts <= t0 - timedelta(seconds=BASE_HASTA_S)
    ]
    baseline = int(median(previas)) if previas else None
    if baseline is None:
        notas.append(
            "SIN LÍNEA BASE · el clip no cubre los segundos previos a la señal; "
            "el aforo pico no se puede leer como «gente que salió»"
        )

    posteriores = [m for m in orden if m.ts >= t0]
    if not posteriores:
        notas.append("SIN MUESTRAS POSTERIORES A LA SEÑAL")
        return Evacuacion(baseline_n=baseline, sacudida=sacudida, notas=tuple(notas))

    cima = max(posteriores, key=lambda m: m.n)
    if cima.n < PICO_MINIMO:
        notas.append(
            f"SIN EVACUACIÓN OBSERVABLE · el aforo pico fue {cima.n}, por debajo del mínimo "
            f"de {PICO_MINIMO}: no hay curva de la que derivar tiempos"
        )
        return Evacuacion(
            baseline_n=baseline,
            peak_n=cima.n,
            peak_at=cima.ts,
            discrepancia=Discrepancia(cima.n, checkins) if checkins is not None else None,
            sacudida=sacudida,
            notas=tuple(notas),
        )

    t50 = _primer_cruce(posteriores, cima.n * FRACCION_MEDIA, t0)
    t90 = _primer_cruce(posteriores, cima.n * FRACCION_MAYORIA, t0)
    reingreso = _inicio_de_reingreso(orden, cima.n, cima.ts)
    if reingreso is None:
        notas.append(
            "REINGRESO NO OBSERVADO · el aforo no cayó de forma sostenida antes de que "
            "acabara la serie (¿se agotó el goteo de capturas?)"
        )

    dictamen_lag = (t_dictamen - t0).total_seconds() if t_dictamen else None
    if t_dictamen is None:
        notas.append("SIN DICTAMEN FIRMADO · no hay latencia de dictamen ni de reingreso")
    reentry_lag = (reingreso - t_dictamen).total_seconds() if (reingreso and t_dictamen) else None

    return Evacuacion(
        baseline_n=baseline,
        peak_n=cima.n,
        peak_at=cima.ts,
        t50_s=(t50 - t0).total_seconds() if t50 else None,
        t90_s=(t90 - t0).total_seconds() if t90 else None,
        reentry_start_at=reingreso,
        dictamen_lag_s=dictamen_lag,
        reentry_lag_s=reentry_lag,
        discrepancia=Discrepancia(cima.n, checkins) if checkins is not None else None,
        sacudida=sacudida,
        notas=tuple(notas),
    )
