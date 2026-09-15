"""[T-7.17] Cómo lo detectó CADA estación: lo medido junto a lo esperado.

Las dos columnas van juntas a propósito. Un pico suelto no dice nada —¿mucho o
poco para esta distancia?—, y un valor teórico suelto es una simulación. Puestos
uno al lado del otro, la fila se lee sola: la estación midió lo que le tocaba, o
no, y en ese caso hay algo que mirar.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EstacionOut(BaseModel):
    """Una estación de la red frente a este incidente."""

    site_id: str
    #: [T-6.04] El código va SIEMPRE: `SiteLabel` decide con él si pinta la cinta
    #: de demostración. Un nombre sin código no se puede rotular.
    site_code: str
    site_name: str
    sensor_code: str | None = None

    #: Epicentro → sitio. `None` cuando el evento no tiene epicentro localizado:
    #: sin él no hay distancia, y una distancia inventada ordena mal la tabla.
    dist_km: float | None = None

    #: Segundos desde el ancla hasta el arribo de la onda S **según el plan**.
    #: `None` sin epicentro.
    t_arribo_teorico_s: float | None = None
    #: Segundos desde el ancla hasta el primer segundo que la estación midió por
    #: encima del umbral de SU inmueble. `None` si nunca lo cruzó.
    t_arribo_medido_s: float | None = None

    peak_pga_g: float | None = None
    peak_ts: datetime | None = None

    #: El umbral contra el que se decidió «sobre umbral», con su procedencia:
    #: sin ella, el número parece del edificio aunque sea el de referencia.
    umbral_pga_g: float | None = None
    umbral_origen: str

    #: Tier más alto que el gabinete REAL declaró en la ventana. `None` = no
    #: publicó ninguna transición: no es `normal`, es que no se sabe.
    tier: str | None = None

    #: ¿Contó en el cuórum de red? `None` cuando no hay evento de red que contar.
    counted: bool | None = None


class EstacionesOut(BaseModel):
    """La tabla completa, en ORDEN DE ARRIBO."""

    incident_id: str
    event_id: str | None
    #: `true` si el evento enlazado es una reproducción (`meta.reproduccion`).
    #: La consola sustituye con esto la tabla de cuórum: en una reproducción no
    #: hubo votos que enseñar, y enseñar una tabla de votos vacía parecería que
    #: la red no corroboró.
    reproduccion: bool = False
    #: Desde dónde se cuentan los arribos: `event` = `seismic_events.detected_at`
    #: (el origen del sismo); `incident` = la apertura del incidente, cuando no
    #: hay evento. Sin declararlo, dos tablas con anclas distintas se compararían
    #: como si midieran lo mismo.
    ancla: str
    ancla_ts: datetime
    epicentro_lat: float | None = None
    epicentro_lon: float | None = None
    magnitude: float | None = None
    items: list[EstacionOut]
