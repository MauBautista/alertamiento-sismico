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
    dlq_url_backfill: str = ""

    evidence_bucket: str = ""
    transfer_bucket: str = ""

    # Seam de S3 (ver routers/_s3.py). Vacío = AWS real (producción). Apuntado a
    # un S3 local compatible (MinIO de docker-compose) permite GENERAR y DESCARGAR
    # el PDF de evidencia en desarrollo, sin credenciales de AWS.
    s3_endpoint_url: str = ""

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

    # --- Quórum de red (T-1.19 · G1) ---
    # Defaults del quórum distance-aware (blueprint §4.5) usados cuando el
    # rule_set no trae la clave 'quorum' (rule_sets.config). min_nodes ≥3
    # estaciones; ventana |Δt| ≤ dist/v_P + margin con tope duro max_window.
    quorum_min_nodes: int = 3
    quorum_v_p_km_s: float = 6.5
    quorum_margin_s: float = 3.0
    quorum_max_window_s: float = 30.0

    # --- Dictamen automático preliminar (T-1.20 · B5) ---
    # Umbrales de PGA del dictamen (placeholders CALIBRABLES por ingeniería;
    # override por rule_sets.config.dictamen). settle_s retrasa la emisión para
    # dar tiempo a la corroboración de red (> tope de ventana del quórum).
    dictamen_pga_no_inhabit_g: float = 0.25
    dictamen_pga_monitor_g: float = 0.05
    dictamen_settle_s: float = 60.0
    # Ventana ASIMÉTRICA del pico de PGA del dictamen (T-1.48): en un incidente
    # SASMEX la sacudida llega DESPUÉS de la alerta (ese es el punto de la
    # alerta temprana) — el ±5 s simétrico perdía el pico. Solo afecta la
    # EVIDENCIA del dictamen; la ventana de asociación del quórum NO se toca.
    dictamen_pga_window_pre_s: float = 5.0
    dictamen_pga_window_post_s: float = 180.0

    # --- Cascada de notificación (T-1.21 · B6, blueprint §5.6) ---
    # step: escalonamiento de la cascada (10 s ⇒ SMS a t0+20, SLA ≤30 s).
    # email_from vacío ⇒ provider de email simulado; con valor ⇒ SES (sandbox
    # en dev: remitente/destinos verificados; DKIM/SPF = TODO de dominio real).
    notify_step_s: float = 10.0
    notify_lookback_s: float = 3600.0
    notify_webhook_timeout_s: float = 5.0
    notify_sms_deadline_s: float = 30.0
    notify_email_critical_deadline_s: float = 10.0
    notify_email_from: str = ""

    # --- Command service + config sync (T-1.23 · B9, RBAC §4.3) ---
    # Clave HMAC POR GABINETE (T-1.38): la firma de un comando/config usa la
    # clave del gateway DESTINO, jamás una compartida de flota.
    #  - command_hmac_secret_prefix (prod): Secrets Manager "{prefix}/{iot_thing}"
    #    (campo hmac_key), leído con el rol de instancia + cache TTL.
    #  - command_hmac_keys_json (dev/tests): mapa inline {"iot_thing": "clave"},
    #    patrón auth_jwks_json — sin AWS. Gana sobre el prefijo.
    # Ambos vacíos ⇒ ninguna clave resoluble ⇒ fail-closed (503 / sync no publica).
    command_hmac_secret_prefix: str = ""
    command_hmac_keys_json: str = ""
    command_hmac_cache_ttl_s: float = 300.0  # rotación visible sin reinicio
    command_hmac_negative_ttl_s: float = 30.0  # thing sin secreto: no martillear SM
    command_ttl_s: float = 30.0  # espejo del edge (regla de oro 8: "JWT corto")
    command_rate_user_site_per_min: int = 6
    command_rate_site_per_min: int = 12

    # --- Backfill por S3 (T-1.25) ---
    # TTL corto del presigned PUT (anti-thundering-herd: un grant caducado se
    # re-solicita; el edge serializa un objeto por gateway).
    backfill_presign_ttl_s: float = 900.0

    # --- Billing/metering (T-1.24 · B10) ---
    # Bytes promedio por fila ingerida para gb_approx (APROXIMACIÓN
    # row-count×avg del plan maestro; calibrar con pg_column_size real).
    billing_row_bytes_estimate: float = 150.0
