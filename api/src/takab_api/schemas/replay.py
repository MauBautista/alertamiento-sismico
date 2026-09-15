"""[T-7.14] Contratos de la reproducción histórica."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReplayIn(BaseModel):
    """Armar. `catalog_key` es el sismo del catálogo que se va a reproducir."""

    catalog_key: str = Field(min_length=1, max_length=120)
    #: Segundos. Se recorta al techo de 8 h de la base en vez de rechazarse:
    #: pedir de más es querer más tiempo, no un error que valga una 4xx.
    duration_s: int | None = None
    note: str = ""


class ReplayOut(BaseModel):
    """El estado. `armed=False` no lleva el resto: no hay nada que contar."""

    armed: bool
    tenant_id: str
    catalog_key: str | None = None
    armed_by: str | None = None
    armed_at: datetime | None = None
    armed_until: datetime | None = None
    remaining_s: float | None = None
    note: str | None = None


class ArriboOut(BaseModel):
    """Lo que le toca a una estación. Segundos **desde el origen** del sismo."""

    site_id: str
    site_code: str
    epi_km: float
    hypo_km: float
    t_p_s: float
    t_s_s: float
    pga_g: float


class ReproduccionOut(BaseModel):
    """El plan completo de un incidente vestido de reproducción.

    `t0_real` es la hora de origen del sismo histórico y `t0_demo` la del pulso
    que lo reprodujo. Los arribos se cuentan desde el origen: quien pinta la
    animación suma `t0_demo`; quien compara con el sismo real suma `t0_real`.
    Sin los dos, el consumidor tiene que adivinar cuál es el ancla.
    """

    incident_id: str
    event_id: str
    catalog_key: str
    magnitude: float | None
    lat: float | None
    lon: float | None
    depth_km: float | None
    t0_real: datetime
    t0_demo: datetime
    #: [T-7.20] La PROCEDENCIA de la cifra que se va a enseñar, del catálogo. Sin
    #: ella el muro pintaría «M7.1» sin decir quién lo sostiene ni si esa fuente
    #: lo dio por revisado — que es exactamente lo que `T-5.10` cerró. `None`
    #: cuando la fila del catálogo no consta: entonces NO se pinta la cifra.
    place: str | None = None
    catalog_source: str | None = None
    review_status: str | None = None
    v_p_km_s: float
    v_s_km_s: float
    arrivals: list[ArriboOut]
