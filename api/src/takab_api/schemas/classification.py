"""Contrato de la clasificación de incidentes (T-5.12)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from takab_api.incident.classification import CLASIFICACIONES


class ClassificationIn(BaseModel):
    """Clasificar. **Sin valor por defecto: se elige.**"""

    model_config = ConfigDict(extra="forbid")

    #: Uno del catálogo cerrado. Obligatorio a propósito — que `indeterminado`
    #: fuera el default convertiría «nadie lo revisó» en «se revisó y no se supo».
    classification: str = Field(pattern=f"^({'|'.join(CLASIFICACIONES)})$")
    note: str = Field(default="", max_length=500)
    #: A cuál sustituye. Corregir INSERTA: la anterior no se borra ni se edita.
    supersedes_id: UUID | None = None


class ClassificationOut(BaseModel):
    classification_id: UUID
    incident_id: UUID
    classification: str
    note: str
    classified_by: UUID
    classified_at: datetime
    supersedes_id: UUID | None
    #: ¿Es la vigente? La que nadie sustituye. Se DERIVA de la cadena, no se
    #: guarda: una bandera guardada sería una segunda verdad sobre lo mismo.
    current: bool


class ClassificationChainOut(BaseModel):
    incident_id: UUID
    #: Más reciente primero. Vacía = **sin clasificar**, que es un hecho distinto
    #: de `indeterminado` y por eso no se rellena con nada.
    items: list[ClassificationOut]


class ClassificationStatsOut(BaseModel):
    """Desglose de una ventana, con los sin clasificar SIEMPRE a la vista."""

    since: datetime
    until: datetime
    #: Incidentes abiertos en la ventana, clasificados o no.
    total: int
    #: Los que nadie miró. Van aparte del denominador, nunca escondidos.
    unclassified: int
    by_classification: dict[str, int]
    #: `null` —y no cero— cuando no hay nada clasificado: un cero afirmaría que no
    #: hubo falsos positivos, y lo que ocurre es que nadie miró.
    false_positive_rate: float | None
