"""Modelos de respuesta de eventos sísmicos y votos de quórum (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from takab_api.procedencia import SIN_DATO_EXTERNO


class SeismicEventOut(BaseModel):
    """Fila de ``seismic_events`` (dato de red; epicentro aplanado a lon/lat)."""

    event_id: str
    source: str
    magnitude: float | None
    epicenter_lon: float | None
    epicenter_lat: float | None
    depth_km: float | None
    detected_at: datetime
    meta: dict[str, Any]
    # --- [T-5.10] Procedencia de la cifra EXTERNA ----------------------------
    #
    # `magnitude`, `epicenter_*`, `depth_km` y la hora de origen NO los mide TAKAB:
    # los publica una fuente oficial. En la misma pantalla que la sacudida medida
    # por el sensor del inmueble, **una cifra sin procedencia se lee como propia**.
    #
    # La regla es **con procedencia, o no se pinta**, y viaja en el contrato para
    # que las tres superficies la apliquen igual en vez de decidir cada una.
    # El vocabulario es `shared/glossary/procedencia.json` (cinco estados).
    #
    # HOY vale `sin_dato_externo` para todo evento, y no es un placeholder: no hay
    # ingesta de catálogo —`incident/engine.py` inserta la magnitud en NULL— así
    # que ninguna cifra externa consta. Cuando `T-5.11` fije el criterio de
    # correlación, este campo dirá `confirmado` o `sin_correlacion`.
    #: Uno de los cinco estados de `shared/glossary/procedencia.json`.
    procedencia: str = SIN_DATO_EXTERNO
    #: Qué fuente publicó la cifra (`SSN`, `USGS`). `None` = no consta.
    procedencia_fuente: str | None = None
    #: Cuándo se le preguntó A LA FUENTE. `None` = no consta ⇒ no se pinta cifra.
    procedencia_consultada_en: datetime | None = None


class EventPage(BaseModel):
    """Página keyset de eventos sísmicos."""

    items: list[SeismicEventOut]
    next_cursor: str | None = None


class QuorumVoteOut(BaseModel):
    """Voto de ``quorum_votes``: arribo por sensor/estación con ``delta_s``.

    [T-2.39] ``station_serial``/``site_code`` son OPCIONALES y su nulidad significa
    algo: el voto viene de una estación que la RLS de este tenant no deja ver. La
    consola lo rotula "OTRA RED" — que es el hecho — en vez de un uuid truncado.
    """

    event_id: str
    sensor_id: UUID
    detected_at: datetime
    pga_g: float
    delta_s: float | None
    counted: bool
    station_serial: str | None = None
    site_code: str | None = None


class EventDetailOut(SeismicEventOut):
    """Detalle de evento: campos del evento + sus votos de quórum."""

    quorum_votes: list[QuorumVoteOut]
