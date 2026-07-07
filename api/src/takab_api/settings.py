"""Configuración de la API/ingesta (T-1.17) — env prefix ``TAKAB_API_``."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# Orden total de tiers del motor de reglas edge (blueprint §4.5).
# Mayor rango = mayor criticidad; el UPSERT de incidents nunca degrada (G3).
RANK: dict[str, int] = {
    "normal": 0,
    "watch": 1,
    "restricted": 2,
    "evacuate_or_hold": 3,
    "manual_only": 4,
}

# Severidades válidas del CHECK de incidents.severity (db/schema.sql), de menor a mayor.
SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "watch": 1,
    "warning": 2,
    "critical": 3,
}

# tier del edge → incidents.severity (valores exactos del CHECK; monótono con RANK).
TIER_SEVERITY: dict[str, str] = {
    "normal": "info",
    "watch": "watch",
    "restricted": "warning",
    "evacuate_or_hold": "critical",
    "manual_only": "critical",
}


class Settings(BaseSettings):
    """Valores por defecto de desarrollo; producción los inyecta por entorno."""

    model_config = SettingsConfigDict(env_prefix="TAKAB_API_")

    database_url: str = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    aws_region: str = "us-east-2"

    queue_url_events: str = ""
    queue_url_telemetry: str = ""
    queue_url_backfill: str = ""
    dlq_url_events: str = ""
    dlq_url_telemetry: str = ""

    evidence_bucket: str = ""
    transfer_bucket: str = ""

    registry_ttl_s: float = 30.0
