"""Motor de incidentes de la nube (T-1.19).

Correlación de red + quórum distance-aware (blueprint §4.5) + ciclo de vida del
incidente. Todo cloud-only y post-hoc: NUNCA bloquea ni condiciona la actuación
local del edge. Esta capa (fase 0) es matemática PURA y sin DB; el worker que
escribe seismic_events/quorum_votes/incidents lo añaden las fases siguientes.
"""

from takab_api.incident.engine import IncidentEngine
from takab_api.incident.fail_open import FAILOPEN_CHANNEL, handle_fail_open
from takab_api.incident.lifecycle import (
    IncidentNotFound,
    close_resolved,
    transition_incident,
)
from takab_api.incident.quorum import (
    ClusterResult,
    Detection,
    QuorumParams,
    Vote,
    associates,
    correlate,
    resolve_params,
)
from takab_api.incident.transitions import (
    STATES,
    VALID_TRANSITIONS,
    InvalidTransition,
    is_terminal,
    validate_transition,
)

__all__ = [
    "FAILOPEN_CHANNEL",
    "STATES",
    "VALID_TRANSITIONS",
    "ClusterResult",
    "Detection",
    "IncidentEngine",
    "IncidentNotFound",
    "InvalidTransition",
    "QuorumParams",
    "Vote",
    "associates",
    "close_resolved",
    "correlate",
    "handle_fail_open",
    "is_terminal",
    "resolve_params",
    "transition_incident",
    "validate_transition",
]
