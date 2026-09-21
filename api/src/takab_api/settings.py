"""Configuración de la API/ingesta (T-1.17) — env prefix ``TAKAB_API_``."""

from __future__ import annotations

from pydantic import model_validator
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


#: DSN de desarrollo. Es el default de ``Settings.database_url`` y, a la vez, el
#: valor que en producción NO puede quedarse puesto: si el secreto real no llega,
#: caer aquí es arrancar limpio contra la base equivocada. Vive como constante
#: para que el guardia de producción y el test lo comparen contra la MISMA cadena.
DEFAULT_DEV_DATABASE_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"

# --- [T-2.86.c · hueco RO-6.c] Contrato de configuración de PRODUCCIÓN ---------
#
# EL DEFECTO: los defaults de esta clase son credenciales de desarrollo. Un
# secreto que no llegue a la nube no produce un error, produce un arranque
# limpio con el valor equivocado — y un fallo silencioso no se investiga. La
# regla de oro 6 ("nada de secretos hardcodeados") se sostenía sólo en que
# nadie se olvidara.
#
# POR QUÉ FALLA AL CONSTRUIR ``Settings`` y no dentro de ``create_app``:
# los workers (``ingest``, ``incident``, ``notify``, ``billing``, ``backfill``)
# NO pasan por ``create_app``; cada uno hace su ``Settings()``. Un guardia en el
# constructor cubre las seis entradas con una sola línea, y no hay forma de
# atraparlo y seguir a medias. En el edge se decidió lo contrario para el perfil
# de failsafe, y con razón: allí ``EdgeSettings`` es TAMBIÉN el documento
# firmado que se sincroniza, y levantar una excepción tiraba el documento
# entero, dejando al gabinete sin configuración por un campo malo. Aquí no hay
# documento: ``Settings`` es sólo configuración de un proceso de nube que puede
# —y debe— morir y reintentar. El edge, mientras tanto, sigue actuando sin nube
# (regla de oro 2), así que un crash-loop de la API no apaga ninguna sirena.
#
# LA SEÑAL DE "ESTO ES PRODUCCIÓN", y por qué son DOS cosas y no una:
#
#   (a) ``build_sha`` distinto de ``"unknown"``. ``deploy/cloud/deploy.sh`` lo
#       inyecta en cada despliegue desde T-1.37 (es el commit que publica
#       ``GET /health``); en local, en la suite y en CI vale ``"unknown"``.
#       Nadie tiene que acordarse de nada: ya estaba ahí.
#   (b) …Y al menos un MARCADOR_DE_NUBE. Porque (a) sola es demasiado tosca: un
#       test que quiera comprobar que /health reporta el commit desplegado pone
#       esa variable y NADA más, y con la regla ingenua se volvía "producción" y
#       reventaba. Pasó: ``api/tests/test_health.py`` en rojo a la primera
#       corrida. Una variable suelta es un test; un DESPLIEGUE trae el
#       ``cloud.env`` entero, que deploy.sh escribe de una sola pieza.
#
# No es fail-open: si ``cloud.env`` no llegara, tampoco llegaría ``build_sha`` y
# no habría nube que proteger — los workers ya mueren solos sin las URLs de DLQ
# (GAP-1, T-1.38). El fallo que esto SÍ tiene que cazar es el otro: ``cloud.env``
# presente y el fichero de SECRETOS (takab-secrets.service) ausente o rancio, que
# es cuando ``database_url`` cae al DSN de desarrollo. Ahí (a) y (b) se cumplen.
#
# Ningún marcador está en REQUERIDOS_EN_PRODUCCION, a propósito: si lo estuviera,
# su ausencia apagaría el guardia que debería denunciarla.
#
# ``TAKAB_API_ENV`` fuerza el perfil en los dos sentidos, para correr una imagen
# de nube en local o para ensayar el guardia.
# Que la señal siga existiendo lo ancla ``api/tests/test_settings_produccion.py``
# contra el propio ``deploy.sh``: sin ese anclaje esto sería fail-open.

#: Campos que SÓLO escribe un despliegue real (`cloud.env`, deploy.sh). Ninguno
#: es secreto y ninguno es requerido: sirven para distinguir "un proceso
#: desplegado" de "un test que puso una variable".
MARCADORES_DE_NUBE: tuple[str, ...] = (
    "queue_url_events",
    "evidence_bucket",
    "transfer_bucket",
    "notify_web_base_url",
    "ops_metrics_enabled",
)

#: Campo → por qué su AUSENCIA en producción es un fallo silencioso.
REQUERIDOS_EN_PRODUCCION: dict[str, str] = {
    "database_url": (
        "lo materializa takab-secrets.service desde Secrets Manager; ausente, la API "
        "arranca contra el DSN de desarrollo (usuario `takab`, contraseña `takab_dev`) "
        "en vez de decir que le falta el secreto"
    ),
    "auth_issuer": (
        "sin issuer no se verifica un solo token contra Cognito y la nube se queda sin "
        "ancla de identidad"
    ),
    "auth_audience": (
        "sin audience se acepta cualquier token del issuer, incluidos los de otro cliente "
        "del mismo pool"
    ),
    "auth_jwks_url": (
        "sin JWKS remoto no hay con qué verificar la firma; el único JWKS que quedaría es "
        "el inline de desarrollo, que está prohibido aquí abajo"
    ),
    "command_hmac_secret_prefix": (
        "sin prefijo no hay clave HMAC resoluble para ningún gabinete: la superficie de "
        "comandos responde 503 entera (fail-closed, sí, pero sin un solo aviso al arrancar)"
    ),
    # [T-2.99] El pool de ocupantes es OPCIONAL en el código —issuer vacío ⇒
    # comportamiento single-issuer intacto, que es lo correcto para un test— y por
    # eso su ausencia en la nube no rompió nada visible: simplemente ningún ocupante
    # volvió a entrar. Aquí abajo deja de ser opcional, porque en producción la app
    # del ocupante ES el producto y un lockout total no puede ser un default.
    "auth_occupants_issuer": (
        "sin issuer del pool de OCUPANTES, `decode_verify_any` ni siquiera mira ese pool: "
        "todo id_token de ocupante se verifica contra el pool principal y muere en 401. "
        "El fallo es total y silencioso — la app solo dice «no se pudo verificar la sesión»"
    ),
    "auth_occupants_audience": (
        "sin audience de ese pool se aceptaría cualquier token suyo, incluidos los de otro "
        "cliente del mismo pool: es la misma razón que `auth_audience`, para el segundo pool"
    ),
    "auth_occupants_jwks_url": (
        "sin JWKS remoto propio la verificación cae al del pool principal (conveniencia de "
        "dev/test en `select_jwks_occupants`) y ninguna firma de ocupante casaría"
    ),
}

#: Campo → por qué su PRESENCIA en producción es una credencial de dev viva.
#: La mitad que se olvida: no basta con que esté lo que tiene que estar.
PROHIBIDOS_EN_PRODUCCION: dict[str, str] = {
    "auth_dev_private_key": (
        "es la llave que firma /dev/token: en la nube es una fábrica de identidades de "
        "cualquier rol y cualquier tenant"
    ),
    "auth_jwks_json": (
        "JWKS inline de desarrollo. deploy.sh lo omite A PROPÓSITO (y lo dice en un "
        "comentario); esto convierte ese comentario en invariante — además de montar "
        "/dev/token, haría verificable un token firmado en la máquina de cualquiera"
    ),
    "auth_occupants_jwks_json": (
        "lo mismo para el pool de OCUPANTES (T-2.03): un JWKS inline ahí firma "
        "identidades de ocupante de cualquier sitio"
    ),
    "command_hmac_keys_json": (
        "mapa HMAC inline que GANA sobre Secrets Manager (ver command_hmac_* abajo): un "
        "mapa olvidado suplanta la clave real de cada gabinete y firma actuaciones "
        "válidas sobre gas, sirena y ascensores"
    ),
    "openrouter_api_key": (
        "clave inline; producción resuelve la suya por openrouter_secret_id. Una clave de "
        "API dentro de una variable de despliegue es justo lo que la regla de oro 6 prohíbe"
    ),
}

#: Perfiles válidos de ``TAKAB_API_ENV``. Un typo (`prod`, `PRODUCTION`) NO puede
#: degradar a "no es producción" en silencio: se rechaza al construir.
PERFILES = ("dev", "production")


class ConfiguracionInvalida(RuntimeError):
    """El proceso NO puede arrancar con esta configuración.

    Es un ``RuntimeError`` y no un ``ValueError`` a propósito: pydantic sólo
    envuelve ``ValueError``/``AssertionError`` en un ``ValidationError``, y ese
    envoltorio imprime un ``input_value=...`` con el diccionario de entrada
    RECORTADO — o sea, un trozo del DSN con su contraseña dentro, en el journal
    del EC2. Dejando propagar una excepción propia el mensaje es exactamente el
    que escribimos aquí: nombres de variable, nunca valores.
    """


class Settings(BaseSettings):
    """Valores por defecto de desarrollo; producción los inyecta por entorno."""

    model_config = SettingsConfigDict(env_prefix="TAKAB_API_")

    database_url: str = DEFAULT_DEV_DATABASE_URL
    aws_region: str = "us-east-2"

    # Perfil de despliegue. VACÍO = se deriva de `build_sha` (ver `es_produccion`),
    # que es lo que hace que nadie tenga que acordarse de ponerlo.
    env: str = ""

    # SHA corto del commit con el que se construyó la imagen; lo inyecta
    # deploy/cloud/deploy.sh. Se expone en /health para poder responder "qué está
    # desplegado" sin abrir una sesión SSM contra la instancia.
    build_sha: str = "unknown"

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
    # [T-2.04] Push móvil (SNS platform endpoints, decisión T-2.00). ARNs de las
    # platform applications creadas por infra/terraform/modules/push (vacíos ⇒
    # provider SIMULADO que grita — patrón T-1.62; la llave APNs llega con el
    # entitlement de Apple, GATE-STORE).
    push_apns_application_arn: str = ""
    push_fcm_application_arn: str = ""

    # [T-2.03] Pool de OCUPANTES (decisión #7, T-2.02): segundo issuer verificable
    # con ancla pool→rol (un token de este pool SOLO puede portar role=occupant; uno
    # del pool principal JAMÁS occupant). issuer vacío ⇒ pool deshabilitado y el
    # comportamiento single-issuer queda intacto. Si el JWKS propio queda vacío se
    # reutiliza el del pool principal (conveniencia dev/test: misma clave de firma).
    auth_occupants_issuer: str = ""
    auth_occupants_audience: str = ""
    auth_occupants_jwks_url: str = ""
    auth_occupants_jwks_json: str = ""

    # [T-2.54] Gestión de usuarios (proxy del Admin API de Cognito). Vacío ⇒
    # directorio SIMULADO que grita en cada escritura (patrón T-1.62/T-2.04): la
    # consola es usable sin AWS, pero jamás finge haber creado una identidad real.
    # Es el pool PRINCIPAL; los ocupantes viven en su propio pool y se dan de alta
    # por código de enrolamiento (T-2.53), no por esta pantalla.
    cognito_user_pool_id: str = ""

    # --- WebSocket live (T-1.22 · G3) ---
    # Ventana para que el cliente mande el primer frame {"type":"auth",...} tras
    # el upgrade; si se excede, el hub cierra con code 4401.
    ws_auth_timeout_s: float = 5.0
    # Tope de pollers de features (1 Hz c/u, uno por sitio) por socket: acota la
    # carga que un solo cliente autenticado puede generar contra el pool.
    ws_max_feature_pollers: int = 16

    # --- [T-2.60.a] Métricas de operación a CloudWatch (las emite `notify`) ---
    # APAGADO por defecto: en local no hay CloudWatch ni credenciales, y un worker
    # que intenta hablar con AWS en cada arranque de desarrollo es ruido puro. El
    # despliegue lo enciende (deploy/cloud/deploy.sh).
    ops_metrics_enabled: bool = False
    ops_metrics_namespace: str = "Takab/Ops"
    # Cadencia de publicación. El bucle de `notify` despierta cada 2 s; CloudWatch
    # agrega por minuto, así que publicar más a menudo solo cuesta dinero.
    ops_metrics_interval_s: float = 60.0

    # --- [T-2.71] Ventanas de mantenimiento (silenciar alarmas de operación) ---
    # APAGADO por defecto, y ese default es la decisión: sin él, un despliegue que
    # olvidara configurar la nube seguiría creando ventanas… que no silencian nada
    # mientras la consola dice que sí. Con `false` la ventana se registra y declara
    # `0/N SILENCIADAS`, que es la verdad medible.
    ops_muting_enabled: bool = False
    # Prefijo con el que Terraform nombra las alarmas (`takab-dev-...`). Es la
    # ÚNICA cuerda entre este código y `infra/terraform/modules/observability`:
    # si divergen, la ventana pide silenciar nombres que no existen y el acuse lo
    # dirá — ruidoso, pero del lado seguro (las alarmas siguen sonando).
    ops_alarm_prefix: str = "takab-dev"

    # --- [T-2.78.a] Cadena de OPERACIÓN acreditada (CloudWatch → SNS → on-call) ---
    # El ARN del topic de operación. VACÍO ⇒ el suscriptor HTTPS responde 503 y
    # GRITA: sin él no hay con qué comparar el remitente de un sobre firmado ni de
    # dónde sacar el ÚNICO host al que este servidor tiene permitido salir
    # (`ops/alerts.py` — la puerta de la SSRF deriva la región de este ARN, jamás
    # del cuerpo). No es un secreto: es un identificador público de AWS.
    ops_alert_topic_arn: str = ""
    #: Plazo para que una persona acuse un aviso de operación, en segundos.
    #:
    #: 900 s (15 min) es un DEFAULT, no la política ratificada: la pregunta P-3 del
    #: `RUNBOOK-ses-produccion-y-cadena-oncall.md §4.3` sigue abierta y es la que
    #: fija el número de verdad. Se calibra contra el rasero de esa misma pregunta
    #: —`gateway_offline` detecta en ~10 min por diseño— y NO contra el SLA de
    #: notificación de un sismo (30 s), que es otra cadena. Lo único que este
    #: número decide es cuándo el silencio deja de ser espera; no silencia nada.
    ops_ack_deadline_s: float = 900.0
    #: Tope de las DOS únicas salidas a la red del suscriptor (certificado de firma
    #: y confirmación del alta). Corto a propósito: cuelga un request público.
    ops_sns_timeout_s: float = 5.0

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
    # Lag de SeedLink por encima de esto (s) → DEGRADADO. [T-1.65] El edge ya no manda
    # la latencia del último paquete (que se CONGELABA con el sensor muerto: el Shake
    # estuvo 9 h fuera de la red publicando "1.24 s" y la flota se veía OPERATIVA) sino
    # la ANTIGÜEDAD del dato más reciente, que crece sin límite si el stream muere. Ese
    # valor sube entre registro y registro hasta la duración del propio registro
    # miniSEED (~7 s como techo a 100 sps), así que 2.0 s haría parpadear un stream
    # sano. 15 s no retrasa la detección: al primer heartbeat sin datos el lag vale ≥60 s.
    fleet_seedlink_lag_max_s: float = 15.0
    # |offset NTP| por encima de esto (ms) → DEGRADADO. Sincronía sana es de pocos
    # a decenas de ms; 100 ms marca reloj a la deriva.
    fleet_ntp_offset_max_ms: float = 100.0

    # [T-2.38] Cadencia del latido del edge (`TAKAB_EDGE_HEALTH_HEARTBEAT_S`, hoy 60 s).
    # Solo se usa para el DENOMINADOR de la completitud de latidos: si la flota cambia
    # de cadencia y esto no, el porcentaje miente. No gobierna nada del gabinete.
    fleet_heartbeat_s: float = 60.0

    # --- Código de retiro por tenant (T-2.36) ---
    # Intentos fallidos tolerados por tenant dentro de la ventana antes del 429.
    # El código lo teclea una persona que lo tiene delante: cinco es holgado para
    # un dedazo y estrecho para adivinar. El contador se lleva sobre `audit_log`
    # (verbo `retire_code_denied`), que es append-only y ya se replica y respalda.
    retire_code_max_attempts: int = 5
    # Ventana del contador. 15 min bloquea de sobra un intento de fuerza bruta y
    # no deja a un operador legítimo esperando media jornada.
    retire_code_window_s: float = 900.0

    # --- Quórum de red (T-1.19 · G1) ---
    # Defaults del quórum distance-aware (blueprint §4.5) usados cuando el
    # rule_set no trae la clave 'quorum' (rule_sets.config). min_nodes ≥3
    # estaciones; ventana |Δt| ≤ dist/v_P + margin con tope duro max_window.
    quorum_min_nodes: int = 3
    quorum_v_p_km_s: float = 6.5
    quorum_margin_s: float = 3.0
    quorum_max_window_s: float = 30.0

    # --- Correlación con el catálogo externo (T-5.11) ---
    # Criterio de IDENTIDAD entre un sismo del catálogo y el que abrió el
    # incidente. Hasta T-5.11 era SOLO temporal (±120 s fijos) y por eso casaba
    # cualquier cosa: sin radio, sin magnitud mínima, sin filtro geográfico.
    # La razón de cada número está escrita en `forensics/correlacion.py`; aquí
    # va el resumen de una línea, que es lo que se lee al cambiarlos.
    #
    # v_S y no v_P: el disparo local lo produce la sacudida fuerte (onda S y
    # superficiales), no el primer arribo. Con v_P la cota se queda corta justo
    # en los sismos lejanos y grandes — el M8.2 de Chiapas llegó a 205 s.
    correlation_v_s_km_s: float = 3.6
    # Tolerancia de reloj y de revisión de la hora de origen. Es TAMBIÉN el
    # único margen hacia atrás: un origen posterior a la detección no es
    # tolerancia, es imposible.
    correlation_margin_s: float = 30.0
    # Radio máximo epicentro↔SITIO. Cubre la zona que de verdad sacude a un
    # inmueble mexicano (Chiapas 2017 a 737 km del centro del país) y excluye
    # de forma terminante Sudamérica y el Pacífico occidental (Chile, 6 389 km).
    correlation_max_km: float = 1200.0
    # Piso de PGA estimada por ATTEN-LAW v1 en el sitio. Un orden de magnitud
    # POR DEBAJO del umbral de cautela del gabinete (0.040 g) a propósito: la
    # pregunta no es «¿habría disparado?» sino «¿pudo notarse siquiera aquí?».
    # Con el umbral de disparo se rechazarían las correlaciones de SASMEX, donde
    # el edificio puede no haber sentido casi nada.
    correlation_min_pga_g: float = 0.001

    # --- Consulta a la fuente externa tras el evento (T-7.25) ---
    # APAGADA por defecto y así se despliega, igual que la capa narrativa: con
    # esto en False el worker no abre un socket y no escribe una sola fila, así
    # que todo evento sigue en `sin_dato_externo` — que es lo que hoy es cierto.
    # Encenderla es una decisión de configuración, no un despliegue de código.
    #
    # Sólo USGS. El SSN NO se consulta y la razón no es técnica: su ingesta
    # automática está decidida (`D-06`) pero la atribución de la cifra está sin
    # cerrar, y publicar una magnitud ajena en un dictamen firmado sin poder
    # citarla como la fuente exige es precisamente lo que `T-5.10` existe para
    # impedir. El día que se cierre, esto crece con un segundo proveedor; hasta
    # entonces el papel lo DICE, que es mejor que un silencio.
    catalog_usgs_enabled: bool = False
    catalog_usgs_url: str = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    # Corto a propósito: esta consulta corre DENTRO del ciclo del worker de
    # incidentes, el mismo que mueve fases y dispara dictámenes. Que un tercero
    # lento alargue ese ciclo es peor que quedarse sin la cifra: la cifra vuelve
    # en el siguiente reintento, el ciclo no. Sin reintentos dentro de la
    # llamada; el reintento es la pasada siguiente, y queda ESCRITO en la base.
    catalog_usgs_timeout_s: float = 6.0
    # Tope de la respuesta, DERIVADO de dos respuestas crudas archivadas y del
    # tope de eventos que se piden. Las dos están en
    # `api/tests/catalogo/fixtures/` tal como las devolvió el servicio —con su
    # URL dentro, en `metadata.url`— y las dos llevan la forma exacta de ESTA
    # consulta (círculo de 1 200 km, ventana de ±363 s): la del evento
    # automático de Valdez pesa 1097 B con 1 evento y la hora siguiente al M8.2
    # de Tehuantepec pesa 10900 B con 14 (779 B cada uno).
    #
    # La cota se toma del PEOR de los dos, 1097 B por evento, y no del promedio:
    # el sobre `metadata` va una vez por respuesta, así que cuantos menos
    # eventos trae, más caro sale cada uno — y una cota se calcula con el caso
    # caro. Con `catalog_usgs_limite = 200` la respuesta más pesada que esta
    # consulta puede pedir son 214 KB, y 512 KB deja 2.4× de holgura sin dejar
    # de acotar lo que una respuesta desbocada le cuesta a la memoria del
    # worker. Todas estas cifras salen de los ficheros
    # (`test_el_tope_de_bytes_se_deriva_del_peor_caso_MEDIDO`) y además se
    # comparan con ESTE comentario, palabra por palabra
    # (`test_el_COMENTARIO_de_la_cota_dice_las_mismas_cifras_que_esta_medicion`),
    # los dos en `tests/catalogo/test_fdsn.py`.
    #
    # ⚠️ Aquí ponía «~780 B por evento ⇒ ~156 KB», que es el promedio del fichero
    # de Tehuantepec, mientras el test que el propio comentario citaba hacía
    # `max(pesos)`: 1097 B y 214 KB. Dos aritméticas distintas sobre la misma
    # medición, y sin nadie que las cruzara — una cifra que el test que la
    # respalda no reproduce no es una medición, es una impresión. De ahí sale la
    # segunda prueba, que lee este párrafo.
    #
    # ⚠️ Y antes de aquello, la cifra era «~6 KB medido sobre una ventana global de diez
    # minutos, once eventos») era falsa por los dos lados: esos once eventos
    # salen de una consulta GLOBAL de VEINTICUATRO HORAS con `minmagnitude=5.0`
    # que este worker no hace nunca —el suyo va acotado por radio, y la misma
    # ventana alrededor de la Ciudad de México devuelve UN evento—, y los ~6 KB
    # eran el peso de NUESTRO fichero destilado, no el de una respuesta de la
    # fuente. Una cifra que no se puede re-derivar del árbol no es una medición.
    catalog_usgs_max_bytes: int = 512 * 1024
    # Tope de eventos que se le piden a la fuente. Es una cota de la consulta, no
    # del criterio: quien decide cuál es el nuestro sigue siendo
    # `forensics/correlacion.py`.
    catalog_usgs_limite: int = 200
    # Cuánto se espera antes de volver a preguntar por un incidente cuya consulta
    # no obtuvo respuesta. Quince minutos: bastante para que un corte de red o un
    # mantenimiento de USGS se resuelvan solos, y poco frente a las seis horas que
    # un incidente pasa en revisión (`incident_review_ttl_s`), que es la ventana
    # dentro de la cual la respuesta todavía le sirve a alguien.
    catalog_usgs_reintento_s: float = 900.0
    # Cada cuánto se vuelve a preguntar por un incidente cuya correlación quedó
    # `preliminar`. «PUEDE CAMBIAR» es una afirmación con caducidad: la fuente
    # revisa su propia solución en horas, y sin este reloj un dictamen firmado
    # dentro de esa ventana congelaba el preliminar para siempre —el predicado
    # de candidatos excluía toda consulta con `answered_at` puesto—. Una hora es
    # el orden en que USGS revisa, y dentro de las seis de `incident_review_ttl_s`
    # da hasta seis oportunidades de alcanzar la revisión. Un `confirmado` NO se
    # re-pregunta: la fuente ya declaró que ésa es la solución que sostiene.
    catalog_usgs_refresco_preliminar_s: float = 3600.0
    # Presupuesto de RELOJ DE PARED de la pasada entera, y la razón del número.
    #
    # Esta pasada corre DENTRO del bucle del worker de incidentes, que es serial:
    # en la misma vuelta viven la correlación, la actuación comandada por el
    # quórum, el dictamen y las fases. Lo que la pasada tarda es lo que se
    # retrasa la vuelta siguiente. Con veinte llamadas en serie y 6 s de timeout
    # el peor caso eran DOS MINUTOS de bloqueo, y el bloqueo es real: con esta
    # comprobación quitada, ocho candidatos contra un tercero de 0.25 s miden
    # 2.10 s de bucle parado (`test_la_pasada_NO_bloquea_el_bucle_mas_alla_de_su_presupuesto`).
    #
    # Así que el tope no se promete en un comentario: se comprueba antes de CADA
    # pregunta y con el timeout incluido (sólo se sale a la red si
    # `transcurrido + timeout` sigue cabiendo), de modo que el peor caso de la
    # pasada es este número y no `max_por_pasada × timeout`. 10 s = un timeout
    # completo más el hueco para que quepa una segunda pregunta cuando la
    # primera fue rápida. Lo que no cabe no se pierde: se pregunta en la vuelta
    # siguiente, que llega en segundos, y el corte queda en el log.
    catalog_usgs_presupuesto_s: float = 10.0

    # --- Mini-ShakeMap por evento (T-7.24 · D-08) ---
    #
    # ⚠️ EL RADIO DE REPRESENTATIVIDAD DE UN INMUEBLE INSTRUMENTADO, y de dónde
    # sale. Fuera de él se declara `SIN COBERTURA` (§A.3): no se extrapola color,
    # que es la misma doctrina que `T-3.08` con la deriva de entrepiso —sin dos
    # sensores, no hay número—.
    #
    # 5 km, y el número tiene DOS anclas medidas, no una intuición:
    #
    # 1 · **Lo que la red permite afirmar.** Medido el 2026-09-20 sobre
    #     `db/seeds/sim_fleet.sql` (20 inmuebles, la flota densa de la
    #     demostración) con `geo.haversine_km`: la distancia al vecino más
    #     cercano tiene mediana **3.08 km** (mín 2.38, máx 6.77). Con 5 km los
    #     discos de inmuebles vecinos se tocan y el cúmulo se lee como una zona
    #     cubierta; con 10 km se solaparían tanto que dos edificios en barrios
    #     geotécnicamente distintos se pintarían como uno. Y en la red REAL de
    #     tres ciudades (`db/seeds/demo_red.sql`: Puebla, CDMX, Toluca) el vecino
    #     más cercano está a **57.3 km** y el par más lejano a **148.6 km**: ahí
    #     ningún radio razonable une nada y entre ciudades el mapa dice `SIN
    #     COBERTURA`, que es exactamente la verdad.
    # 2 · **Lo que la física permite afirmar.** ATTEN-LAW v1 hace PGA ∝ 1/R_hipo,
    #     así que a 5 km de un punto que está a 50 km del hipocentro el propio
    #     modelo ya predice un 10 % de diferencia. Más allá, extender el valor
    #     medido afirmaría algo que ni la ley sostiene — y la variabilidad de
    #     sitio (la zonificación geotécnica del valle de México cambia la
    #     amplificación por factores de 5–10 en pocos kilómetros) es mucho mayor
    #     aún, o sea que este radio ya es generoso.
    #
    # Es configurable a propósito: una red urbana densa y una red estatal no
    # tienen el mismo alcance, y el número se guarda EN CADA SNAPSHOT para que un
    # mapa ya impreso no cambie de significado si mañana alguien lo sube.
    shakemap_cobertura_km: float = 5.0
    # Cada cuánto se REHACE un mapa que todavía no está `completo`. No se rehace
    # el `completo`: una vez hay epicentro, magnitud y medidas, el mapa ya no
    # puede mejorar y recalcularlo sería gastar el bucle en confirmar lo mismo.
    # Un `solo_observado` o un `sin_datos` sí: puede llegarle el epicentro del
    # catálogo (T-7.25) o el spool de un gabinete que estaba sin red. Es el mismo
    # patrón que `catalog_usgs_refresco_preliminar_s` — «puede cambiar» es una
    # afirmación con caducidad—, y el que impide que la pasada se convierta en un
    # bucle que recalcula los mismos incidentes cada cinco segundos.
    shakemap_refresco_s: float = 60.0
    # Presupuesto de RELOJ DE PARED de la pasada, por la misma razón que
    # `catalog_usgs_presupuesto_s`: el bucle del worker es serial y lo que esta
    # pasada tarda es lo que se retrasa la vuelta siguiente —correlación,
    # actuación comandada por el quórum, dictamen y fases—. Aquí no hay un
    # tercero, pero sí una consulta de features por inmueble y por incidente, que
    # es lo que puede crecer sin avisar.
    #
    # MEDIDO el 2026-09-20 contra `takab_test_a`, con la pasada real y el rol del
    # worker (`/dev/shm/t/medir.py`, 3 inmuebles por incidente): 1 incidente
    # 0.065 s —incluye abrir la conexión del puente async—, 5 incidentes 0.108 s,
    # y **20 incidentes —el tope entero de la pasada— 0.254 s** (13 ms por mapa).
    # O sea que 5 s son unas VEINTE VECES el peor caso medido: el presupuesto no
    # recorta la operación normal, sólo dice basta cuando algo se sale de escala
    # (una red mucho mayor, una base lenta) en vez de dejar el bucle parado sin
    # explicación. Lo que no cabe se calcula en la vuelta siguiente y el corte se
    # DICE (`PasadaDeShakemap.corte`).
    shakemap_presupuesto_s: float = 5.0

    # --- Reproducción histórica (T-7.14 · D-33) ---
    # Velocidad de la onda S del PLAN de arribos. NO es `correlation_v_s_km_s`
    # (3.6) y no se debe unificar con ella: allí la velocidad acota cuán tarde
    # puede llegar un arribo real y la elección conservadora es la LENTA —una
    # rápida cerraría la ventana antes de tiempo y perdería el evento—; aquí la
    # pregunta es cuándo se ESPERA la onda y hace falta la mejor estimación.
    #
    # 4.0 km/s está anclada a un sismo medido: reproduce los cuatro arribos de
    # referencia del 19-S-2017 de la ficha (Puebla +19.6 s, Tlaxcala +25.3 s,
    # CDMX +32.1 s, Toluca +38.7 s) con 0.08 s de error máximo. Es un evento
    # INTRAPLACA a 48 km: la energía viaja por la placa subducida y la velocidad
    # aparente supera los 3.5-3.6 de la corteza. `v_p` no se configura: sale de
    # ésta por la razón de Poisson (√3), para que no puedan moverse por separado.
    replay_v_s_km_s: float = 4.0

    # --- Fases del incidente (T-7.13 · D-33) ---
    # Hasta T-7.13 NADA cerraba un incidente: un incidente abierto en julio
    # seguía siendo «la alerta» en septiembre. Los dos números de abajo son los
    # únicos que gobiernan cuándo deja de serlo, y ninguno de los dos vive en el
    # cliente: la escena se apaga por lo que el servidor sabe, no por el reloj
    # del navegador (regla de oro 7).
    #
    # RETÉN MÍNIMO de la alerta. Se SUMA a la condición de estado (el tier del
    # sitio de vuelta en `normal`), nunca la sustituye: sin él, un gabinete que
    # repunta y vuelve a normal en 20 s apagaría el banner mientras la gente
    # todavía baja las escaleras. Es el «unos minutos» de `D-33`.
    # [SUPUESTO t-7-13-01] 3 min es el valor de arranque; el definitivo lo da
    # Mauricio (plan §7, aporte de F3) y se cambia por entorno sin tocar código.
    alert_hold_min_s: float = 180.0
    # RED DE SEGURIDAD, no la vía normal. Cierra un incidente que lleva horas en
    # revisión y que nadie clasificó. En HORAS y no en minutos a propósito: un
    # TTL corto esconde un evento real que nadie miró, que es peor que dejarlo
    # en la lista. `0` desactiva esta vía y deja las otras dos (es exactamente
    # cómo se revoca `D-33` si un cliente exige cierre humano siempre).
    # [SUPUESTO t-7-13-01] 6 h cubre un turno completo de SOC.
    incident_review_ttl_s: float = 21600.0

    # --- Dictamen automático preliminar (T-1.20 · B5) ---
    # Umbrales de PGA del dictamen (placeholders CALIBRABLES por ingeniería;
    # override por rule_sets.config.dictamen). settle_s retrasa la emisión para
    # dar tiempo a la corroboración de red (> tope de ventana del quórum).
    dictamen_pga_no_inhabit_g: float = 0.25
    dictamen_pga_monitor_g: float = 0.05
    dictamen_settle_s: float = 60.0
    # [T-7.55] ⚠️ CUÁNTO SIGUE DECLARÁNDOSE «REINGRESO AUTORIZADO» DESPUÉS DE QUE
    # EL INCIDENTE SE CIERRE.
    #
    # Desde `D-33` el motor cierra el incidente por dictamen firmado, y medido el
    # 2026-09-18 tarda TRES SEGUNDOS. Como `mobile-state` sólo miraba incidentes
    # no cerrados, la fase caía a `idle` y al ocupante **la prohibición de
    # reingreso simplemente se le desvanecía**: nadie le decía que ya podía
    # volver. Tenía que inferirlo de la AUSENCIA de un cartel, que es la forma de
    # comunicación que este sistema no usa en ninguna otra parte.
    #
    # El número es para una persona que está FUERA del edificio: se fue a otro
    # sitio y mira el teléfono cuando vuelve. Ocho horas cubren una jornada sin
    # que la afirmación se quede colgada días. Y no hace falta que cubra más:
    # si abre otro incidente, ése manda (ver la precedencia en `mobile_site.py`).
    reentry_declare_s: float = 8 * 3600.0
    # Ventana ASIMÉTRICA del pico de PGA del dictamen (T-1.48): en un incidente
    # SASMEX la sacudida llega DESPUÉS de la alerta (ese es el punto de la
    # alerta temprana) — el ±5 s simétrico perdía el pico. Solo afecta la
    # EVIDENCIA del dictamen; la ventana de asociación del quórum NO se toca.
    dictamen_pga_window_pre_s: float = 5.0
    dictamen_pga_window_post_s: float = 180.0

    # --- Capa narrativa del dictamen (T-2.42) ---
    # APAGADA por defecto y así se despliega: el gate #9 del plan maestro sitúa la IA
    # en Fase 3 y en modo sombra. Con esto en False no se abre un socket, y la prosa
    # la produce el proveedor determinista (que es el suelo, no un relleno).
    #
    # Encenderla exige LAS TRES: flag, clave resoluble y slug de modelo. El slug NO
    # tiene default a propósito — un identificador de modelo hardcodeado caduca en
    # silencio; se verifica contra `GET /api/v1/models` de OpenRouter el día que se
    # encienda. El veredicto y todos los valores medidos siguen siendo deterministas
    # con la capa encendida (regla de oro 1).
    openrouter_enabled: bool = False
    openrouter_model: str = ""
    # Clave inline (dev) o secreto de Secrets Manager (producción), como command_hmac.
    openrouter_api_key: str = ""
    openrouter_secret_id: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Sin reintentos: 8 s ya es mucho dentro de un request que genera evidencia.
    openrouter_timeout_s: float = 8.0

    # --- Alcance por sitio en la consola web (T-2.45) ---
    # Cutover en DOS FASES. `custom:site_scope` no está aprovisionado para usuarios
    # web (nadie lo escribe hasta T-2.54), y `claims.site_scope` es default-deny: con
    # esto en True desde ya, TODO `soc_operator` vería cero sitios. En False un claim
    # vacío significa "sin restricción declarada" y se audita como hueco; un claim que
    # SÍ trae sitios se respeta igual. Se enciende cuando T-2.54 pueda escribirlo.
    #
    # [T-2.54 · 2026-08-04] El BLOQUEANTE ya está levantado: `PATCH /users/{username}`
    # escribe `custom:site_scope` (ver `routers/users.py`), así que la Fase B es
    # ACTIVABLE. Sigue en False a propósito: encenderla antes de que CADA usuario web
    # tenga su claim aprovisionado deja sin datos exactamente a quien no lo tenga, que
    # es el escenario para el que existe el cutover en dos fases. La secuencia es
    # (1) desplegar, (2) recorrer la lista de `scope_gap` del audit_log y fijar el
    # alcance de cada usuario desde la consola, (3) poner esto en True.
    console_scope_enforced: bool = False

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
    #: [T-1.61] Base pública de la consola para links en notificaciones
    #: (p.ej. https://16-58-11-196.sslip.io). Vacío ⇒ el mensaje va sin link.
    notify_web_base_url: str = ""
    #: [T-2.158] ¿Esa base la alcanza el DESTINATARIO, o solo nosotros?
    #:
    #: Tener URL no es lo mismo que ser alcanzable: en dev el 443 de la consola
    #: admite UNA sola IP, así que el enlace de «Atender en la consola» solo lo
    #: abría el operador de esa dirección. El código no puede deducirlo —lo sabe
    #: la red, no el proceso—, así que se DECLARA.
    #:
    #: Nace en `False` a propósito: si nadie lo declara, el correo no promete. Al
    #: revés, cada despliegue nuevo reintroduce el defecto y no se nota hasta que
    #: alguien intenta pulsar, que es tarde.
    notify_web_public: bool = False
    #: [T-1.62] Envíos totales por job antes de darlo por perdido (backoff
    #: 30 s / 2 min entre ellos). Solo aplica a quien no tiene a quién escalar:
    #: un salto de cascada con siguiente canal falla en el acto, como siempre.
    notify_max_attempts: int = 3

    # --- SMS real por Twilio (T-2.76) ---
    # Las TRES piezas (sid + token + from|messaging_service) o el canal cae a
    # SIMULADO y los jobs quedan 'simulated', jamás 'sent' (T-2.75). El token es
    # SECRETO: entorno / Secrets Manager, nunca en git (regla de oro 6).
    # Límites declarados (coste, MPS, tope) en notify/twilio.py.
    notify_sms_account_sid: str = ""
    notify_sms_auth_token: str = ""
    notify_sms_from: str = ""
    notify_sms_messaging_service_sid: str = ""
    notify_sms_timeout_s: float = 5.0
    #: Twilio guarda un SMS encolado 10 h por defecto: un aviso de sismo que
    #: aterriza mañana es ruido. 300 s = el mensaje muere antes de volverse
    #: desinformación. Rango legal de Twilio: 1..36 000 s.
    notify_sms_validity_period_s: float = 300.0
    #: Endpoint público del status callback de Twilio. VACÍO HOY: sin él NO hay
    #: confirmación de entrega, solo aceptación — un `notify_sent` de sms dice
    #: "Twilio lo aceptó", no "el teléfono lo tiene". Ver notify/twilio.py.
    notify_sms_status_callback_url: str = ""

    # --- WhatsApp Business Cloud API (T-2.77) ---
    # Las TRES piezas o el canal cae a SIMULADO (T-2.75). La VERSIÓN DE GRAPH
    # cuenta como credencial y no lleva default a propósito: va dentro de la
    # ruta `/{version}/{phone_number_id}/messages` y Meta retira versiones con
    # el tiempo, así que un default adivinado se vuelve un 400 el día que
    # caduque. El token es SECRETO: entorno / Secrets Manager, nunca en git.
    # Y aunque estén las tres, el canal sigue caído hasta que haya una plantilla
    # APROBADA por Meta: WhatsApp no deja improvisar texto (ver notify/whatsapp.py).
    notify_whatsapp_phone_number_id: str = ""
    notify_whatsapp_access_token: str = ""
    notify_whatsapp_graph_version: str = ""
    notify_whatsapp_timeout_s: float = 5.0
    #: Idioma de la plantilla a usar (debe existir APROBADA en ese idioma; si no,
    #: Meta responde 132001 y aquí ni se intenta).
    notify_whatsapp_language: str = "es_MX"
    #: Directorio de artefactos de plantilla. Vacío ⇒ los que viajan con el
    #: paquete (`notify/whatsapp_templates/`). Se puede apuntar a otro sitio para
    #: cargar el sello de aprobación sin reconstruir la imagen.
    notify_whatsapp_templates_dir: str = ""

    # --- Webhooks de estado de entrega (T-2.77.b) ---
    # LOS DOS SON SECRETOS y son la ÚNICA autenticación de la única superficie
    # pública de la API: entorno / Secrets Manager, jamás en git (regla de oro 6).
    # Vacíos ⇒ el endpoint responde 503 y GRITA al recibir un callback: sin con
    # qué verificar, aceptar sería dejar que cualquiera marque "entregado" lo que
    # no salió. El de Twilio no lleva campo propio: es el mismo
    # `notify_sms_auth_token` con el que Twilio firma `X-Twilio-Signature`, y la
    # URL sobre la que se valida es `notify_sms_status_callback_url` — la MISMA
    # que viaja en cada envío, nunca una reconstruida de las cabeceras.
    #: App secret de la app de Meta: firma `X-Hub-Signature-256` del cuerpo crudo.
    notify_whatsapp_app_secret: str = ""
    #: `hub.verify_token` del alta de la suscripción del webhook de Meta.
    notify_whatsapp_verify_token: str = ""

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

    # ── [T-5.18] Tope de gasto de la IA y freno de la exportación ────────────
    #: Tope mensual de gasto de redacción asistida, POR TENANT y en dólares.
    #: 5 USD es deliberadamente conservador: con el modelo y el techo de tokens
    #: de hoy son cientos de dictámenes al mes, y quien necesite más lo sube a
    #: sabiendas. El defecto de una cuota no puede ser «la que no molesta».
    #:
    #: ⚠️ [T-7.26] **`0` es tope CERO: la IA no sale a la red.** Hasta esta ficha
    #: significaba SIN TOPE —la lectura del ajuste ausente—, y eso convertía el
    #: error de dedo más probable de todos en el peor resultado posible: quien
    #: pone el tope a cero creyendo que apaga el gasto lo dejaba ilimitado.
    #: Equivocarse tiene que dejar el sistema SIN IA (el dictamen sale igual, con
    #: prosa determinista declarada), nunca con la tarjeta abierta. Para pedir
    #: gasto ilimitado se escribe un NEGATIVO (`narrative.quota.SIN_TOPE`), que
    #: nadie teclea sin querer.
    ai_monthly_cap_usd: float = 5.0
    #: Fracción del tope a la que se deja UNA fila de aviso en la bitácora.
    #: `0` o `1` desactivan el aviso sin tocar el corte.
    ai_warn_at: float = 0.8
    #: Exportaciones de PDF por minuto y por USUARIO. Un usuario autenticado podía
    #: reexportar el mismo incidente sin límite, y cada exportación renderiza un
    #: PDF, lo sube a S3 y —con la IA encendida— sale a la red de pago.
    report_rate_user_per_min: int = 6
    #: …y por SITIO. Dos operadores coordinados agotan el presupuesto del
    #: edificio sin que ninguno rebase el suyo: es el mismo par de techos que ya
    #: usan los comandos, y por la misma razón (`RO-8.e`).
    report_rate_site_per_min: int = 20
    #: [T-7.54] Descargas de evidencia por minuto y por USUARIO.
    #:
    #: ⚠️ ESTE TOPE NO PROTEGE DINERO, Y LA FICHA SUPONÍA QUE SÍ. Se midió el
    #: 2026-09-20 sobre el bucket real: el objeto más grande es un miniSEED de
    #: **204 KB** (p95 200 KB), una foto son 53 KB y un dictamen 102 KB, y el
    #: bucket ENTERO pesa **6.8 MB**. A ~$0.09/GB de egreso, descargarlo completo
    #: mil veces cuesta menos de un dólar. Calibrar contra el egreso de S3 sería
    #: teatro, y peor: daría un número con aire de medido que no mide nada.
    #:
    #: Lo que sí acota es la EXTRACCIÓN EN BLOQUE. Un token robado con alcance de
    #: exportación puede pedir una URL por evidencia tan rápido como la API
    #: conteste, y cada URL vive 300 s y sirve descargas ilimitadas mientras dure
    #: (el GET no pasa por aquí). Treinta por minuto deja trabajar a un perito
    #: —el incidente más cargado de la nube dev tiene 22 evidencias, así que cabe
    #: entero en una ráfaga— y convierte vaciar un tenant en una operación lenta
    #: y ruidosa: cada intento deja su fila en `audit_log`.
    #:
    #: ⚠️ Y el número NO sale de tráfico observado, porque no lo hay: el
    #: `audit_log` de la nube dev tiene **cero** filas `download_*` desde que ese
    #: verbo existe. Sale del tamaño del incidente más grande medido, más margen.
    #: El día que haya uso real, se re-mide y se dice contra qué.
    evidence_download_rate_user_per_min: int = 30
    # [T-2.09] Intención firmada del móvil (RBAC §4.3): secreto HMAC de los
    # nonces de intención (FAIL-CLOSED: vacío = la ruta táctica responde 503,
    # jamás comandos sin intención verificable) + TTL corto del nonce.
    command_intent_secret: str = ""
    command_intent_ttl_s: float = 90.0
    # [T-2.13] Pánico del occupant por quórum-de-2 (1.9 · RBAC §4.3): ventana de
    # asociación (2 votos de usuarios DISTINTOS dentro de estos segundos ⇒
    # sirena), radio del geofence best-effort (voto con GPS fuera se descarta;
    # sin GPS cuenta) y rate-limit por usuario para no martillear.
    panic_quorum_window_s: float = 30.0
    panic_geofence_radius_m: float = 500.0
    panic_vote_rate_per_min: int = 4
    # [T-2.147.c · D-05] Cuánto se le da a la BRIGADA para acusar antes de avisar
    # al SOC. `D-05` dijo «~2 min», y aquí está por qué ese orden de magnitud:
    # es el tiempo de mirar el teléfono y responder, no el de bajar al sitio —
    # el aviso pregunta «¿alguien lo vio?», no «¿ya está resuelto?».
    #
    # Y lo que NO pasa al vencer: no se escala al edificio. Se avisa al SOC, que
    # es un humano con contexto; escalar por un temporizador reintroduciría la
    # opción (A) que D-05 descartó, solo que dos minutos después y sin que nadie
    # la hubiera decidido.
    panic_tactical_ack_timeout_s: float = 120.0

    # --- [T-2.150 · D-07] Secretos del sujeto-teléfono del consentimiento ---
    #
    # Los DOS viven FUERA de la base (entorno / Secrets Manager), y ahí está el
    # valor entero: una copia de la base sin ellos no revela un solo teléfono.
    #
    # Sin ellos el camino del `msisdn` se NIEGA a funcionar (503). No cae a texto
    # en claro «por compatibilidad»: eso escribiría el defecto que T-2.150 cierra,
    # en silencio y para siempre, en una tabla que no se puede reescribir. Mismo
    # criterio que «sin clave HMAC resoluble ⇒ 503» de los comandos.
    #
    # `pepper` deriva el ÍNDICE de búsqueda; `master_key` sella el número. Son dos
    # a propósito: rotar la clave de sellado no debe invalidar todos los índices
    # —eso obligaría a reescribir `privacy_consents`, que es append-only—.
    privacy_subject_pepper: str = ""
    privacy_subject_master_key: str = ""
    # [T-2.106] Cuánto tiempo sostiene la app la frase «la alarma del inmueble
    # está sonando» a partir de un `siren/activate` que el gabinete confirmó
    # haber ejecutado. Es una CONSTANTE DECLARADA, y aquí está por qué:
    #
    # · No sale de `command_ttl_s` (30 s), que es el TTL de ENTREGA del comando
    #   —cuánto vale la firma en el cable—, no cuánto suena una sirena. Usarlo
    #   apagaría el aviso medio minuto después de ordenarlo.
    # · No sale del gabinete, porque el relé de sirena ENCLAVA: se sostiene
    #   "hasta que el operador silencie/re-arme" (`edge/takab_edge/gpio`,
    #   semántica de latching real). No existe duración que derivar de él.
    # · No sale de `panic_quorum_window_s`, que es la ventana de asociación de
    #   los DOS votos, y no tiene nada que ver con cuánto dura la emergencia.
    #
    # 30 minutos: holgado para cubrir una evacuación real del inmueble sin que
    # la app enmudezca a mitad del evento, y corto para que un `activate` que
    # nadie revirtió por la nube —el caso común, porque el operador silencia la
    # sirena EN EL PANEL del gabinete y ese silencio no vuelve como comando— no
    # deje al teléfono anunciando una sirena durante días. Caducar NO silencia
    # nada: la app deja de AFIRMAR lo que ya no puede corroborar (regla de oro
    # 7). Los desmentidos fuertes —silencio ejecutado, gabinete mudo, relés
    # ilegibles— llegan antes y por dato real (ver `commands/alarma_inmueble.py`).
    building_alarm_max_s: float = 1800.0

    # --- Backfill por S3 (T-1.25) ---
    # TTL corto del presigned PUT (anti-thundering-herd: un grant caducado se
    # re-solicita; el edge serializa un objeto por gateway).
    backfill_presign_ttl_s: float = 900.0

    # --- Billing/metering (T-1.24 · B10) ---
    # Bytes promedio por fila ingerida para gb_approx (APROXIMACIÓN
    # row-count×avg del plan maestro; calibrar con pg_column_size real).
    billing_row_bytes_estimate: float = 150.0

    # --- [T-2.86.c · RO-6.c] Guardia de configuración de producción ------------

    @property
    def es_produccion(self) -> bool:
        """¿Este proceso corre en la nube? Ver el bloque de arriba para el porqué."""
        if self.env:
            return self.env == "production"
        if self.build_sha == "unknown":
            return False
        return any(bool(getattr(self, m, None)) for m in MARCADORES_DE_NUBE)

    @model_validator(mode="after")
    def _exigir_secretos_en_produccion(self) -> Settings:
        """En producción, un secreto ausente impide arrancar (regla de oro 6).

        Los mensajes nombran la VARIABLE DE ENTORNO, nunca el valor: este error
        acaba en el journal del EC2 y en los logs del contenedor.
        """
        if self.env and self.env not in PERFILES:
            raise ConfiguracionInvalida(
                f"TAKAB_API_ENV={self.env!r} no es un perfil válido "
                f"({'|'.join(PERFILES)}). Un typo aquí degradaría el despliegue a "
                "'no es producción' y apagaría este guardia en silencio."
            )
        if not self.es_produccion:
            return self

        problemas: list[str] = []
        for campo, razon in REQUERIDOS_EN_PRODUCCION.items():
            if not str(getattr(self, campo, "") or "").strip():
                problemas.append(f"falta TAKAB_API_{campo.upper()}: {razon}")
        if self.database_url == DEFAULT_DEV_DATABASE_URL:
            problemas.append(
                "TAKAB_API_DATABASE_URL es el default de desarrollo (usuario `takab`, "
                "contraseña en claro en docker-compose): el secreto real no llegó y "
                "arrancar así es hablar con la base equivocada sin decirlo"
            )
        for campo, razon in PROHIBIDOS_EN_PRODUCCION.items():
            if str(getattr(self, campo, "") or "").strip():
                problemas.append(
                    f"TAKAB_API_{campo.upper()} tiene valor y es una credencial "
                    f"de DESARROLLO: {razon}"
                )
        if problemas:
            detalle = "\n  - ".join(problemas)
            raise ConfiguracionInvalida(
                "configuración de PRODUCCIÓN inválida (perfil derivado de "
                f"TAKAB_API_BUILD_SHA={self.build_sha!r}; fuerza TAKAB_API_ENV=dev si "
                f"esto es una imagen de nube corriendo en local):\n  - {detalle}"
            )
        return self
