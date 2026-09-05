"""Contrato de CCTV de un incidente (T-3.12.c).

Misma regla que el contrato forense: **un valor ausente nunca se rellena con 0**. Un `t90`
de cero diría que la gente salió instantáneamente; ausente dice que no lo sabemos. Y cada
ausencia viaja con su razón, porque un hueco sin explicar se lee como un fallo del sistema.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

#: Lo que el reporte y la consola dicen cuando el sitio no tiene cámara. No es un cero, no
#: es una sección vacía: es una afirmación verificable sobre el mundo.
NO_CCTV = "SIN COBERTURA CCTV DECLARADA · este sitio no tiene cámara configurada"

#: Y lo que dicen cuando SÍ hay clip pero nadie lo ha analizado todavía —hoy, mientras el
#: Lambda de conteo espera ventana AWS (`T-3.12.b`)—. Un fallback no puede ser `ok`, y un
#: cero inventado aquí sería peor que el hueco.
ANALISIS_PENDIENTE = "CLIP DISPONIBLE · ANÁLISIS PENDIENTE"


class ClipOut(BaseModel):
    """Un clip del incidente. `disponible=False` cuando la retención ya podó el objeto."""

    clip_id: UUID
    started_at: datetime
    ended_at: datetime
    sha256: str | None = None
    size_bytes: int | None = None
    coverage: float | None = None
    #: **El hecho sobrevive, la imagen no.** Tras la poda el `s3_key` es NULL y esto pasa a
    #: `False`, pero `sha256` y las horas siguen ahí: la cadena de custodia del reporte
    #: puede seguir verificándose contra un objeto que ya no existe.
    disponible: bool = False
    purged_at: datetime | None = None

    @property
    def estado_custodia(self) -> str:
        return "PURGADO (retención de vídeo)" if self.purged_at else "disponible"


class CapturaOut(BaseModel):
    """Una de las cuatro capturas del reporte, o su ausencia con razón."""

    papel: str  # pre | egress | peak | reentry
    still_id: UUID | None = None
    captured_at: datetime | None = None
    sha256: str | None = None
    disponible: bool = False
    purged_at: datetime | None = None
    razon: str | None = None


class DiscrepanciaOut(BaseModel):
    """Aforo por cámara frente al pase de lista. **Nunca se promedian.**"""

    aforo_camara: int | None = None
    checkins: int | None = None
    diferencia: int | None = None
    lectura: str


class EvacuacionOut(BaseModel):
    """Las métricas. `None` es «no medido»; la razón está en `notas`."""

    baseline_n: int | None = None
    peak_n: int | None = None
    peak_at: datetime | None = None
    t50_s: float | None = None
    t90_s: float | None = None
    reentry_start_at: datetime | None = None
    dictamen_lag_s: float | None = None
    reentry_lag_s: float | None = None
    #: `True` cuando la gente reentró ANTES del dictamen firmado. **No es un número
    #: negativo en una tabla: es que el inmueble se reocupó sin certificación.**
    reingreso_antes_del_dictamen: bool = False
    veredicto_reingreso: str
    #: «Sacudió tanto, la gente tardó tanto». El dato que ninguno de los dos da solo.
    correlacion: str
    provenance: str | None = None  # preliminary | final
    notas: list[str] = []


class CctvOut(BaseModel):
    """Todo el CCTV de un incidente. **El mismo objeto va a la pantalla y al PDF.**

    Dos rutas distintas para los mismos hechos acabarían discrepando, y un dictamen que no
    coincide con lo que el operador vio en pantalla es peor que ninguno.
    """

    incident_id: UUID
    #: `False` ⇒ la consola y el reporte dicen `NO_CCTV` y no pintan una sección vacía.
    con_camara: bool = False
    estado: str = NO_CCTV
    clips: list[ClipOut] = []
    capturas: list[CapturaOut] = []
    evacuacion: EvacuacionOut | None = None
    discrepancia: DiscrepanciaOut | None = None
