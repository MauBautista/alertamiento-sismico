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

    # Auth (T-1.18): verificación de ID token Cognito. JWKS remoto en prod;
    # JWKS inline (auth_jwks_json) en dev/tests → sin Cognito real.
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    auth_jwks_json: str = ""
    # Clave privada PEM que firma tokens de /dev/token (SOLO dev/test). En prod
    # queda vacía → el endpoint no puede firmar y, además, no se monta (guardado
    # por auth_jwks_json vacío en main.create_app).
    auth_dev_private_key: str = ""

    # --- WebSocket live (T-1.22 · G3) ---
    # Ventana para que el cliente mande el primer frame {"type":"auth",...} tras
    # el upgrade; si se excede, el hub cierra con code 4401.
    ws_auth_timeout_s: float = 5.0
    # Tope de pollers de features (1 Hz c/u, uno por sitio) por socket: acota la
    # carga que un solo cliente autenticado puede generar contra el pool.
    ws_max_feature_pollers: int = 16

    # --- Flota / fleet-status derivado server-side (T-1.22 · G7) ---
    # Minutos sin heartbeat en device_health → estado SIN ENLACE (el gateway dejó
    # de reportar). Debe holgar sobre el espaciado real del heartbeat del edge.
    sin_enlace_min: float = 5.0
    # Umbrales de DEGRADADO: con enlace vivo pero alguna métrica fuera de rango.
    # Batería por debajo de este % → DEGRADADO.
    fleet_battery_min_pct: float = 80.0
    # Certificado mTLS que vence dentro de estos días → DEGRADADO (rotar antes).
    fleet_cert_min_days: int = 30
    # RTT MQTT al broker por encima de esto (ms) → DEGRADADO. Enlace sano << 500 ms;
    # margen amplio para no oscilar por picos puntuales.
    fleet_mqtt_rtt_max_ms: float = 1500.0
    # Lag de SeedLink por encima de esto (s) → DEGRADADO. Lag normal medido ~0.4 s
    # (memoria shake-hardware-seedlink); umbral holgado para evitar flapping.
    fleet_seedlink_lag_max_s: float = 2.0
    # |offset NTP| por encima de esto (ms) → DEGRADADO. Sincronía sana es de pocos
    # a decenas de ms; 100 ms marca reloj a la deriva.
    fleet_ntp_offset_max_ms: float = 100.0
