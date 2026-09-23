"""SQL de la flota edge (T-1.22 · B1/G7).

Gateways del tenant + LATERAL al último ``device_health`` de cada gateway. La
edad del heartbeat (``age_s``) se calcula con ``now()`` de la transacción para no
depender del reloj de la app. La derivación del estado vive en
``schemas.fleet.derive_fleet_state`` (verdad única). Ambas tablas tienen RLS por
tenant → un tenant nunca ve la flota de otro.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.scope import ConsoleScope, apply_scope

# [A-057 · T-8.09] ¿Esta fila de ``device_health`` (alias ``dh``) es un LATIDO?
#
# ``ingest/handlers.py::handle_status`` —el LWT/beacon de presencia— escribe una
# fila ``reason='transition'`` con SOLO ``ts/tenant/gateway``: todas las métricas
# en NULL, tanto para ``online`` como para ``offline``. La fila se conserva a
# propósito (es la huella de la reconexión y de «retirado + vivo»), pero NO es
# un latido: tomada como «el último», un gabinete recién CAÍDO salía OPERATIVO
# durante ``sin_enlace_min`` (edad ≈ 0, ninguna métrica que degrade), uno en
# batería se «curaba» con el LWT, y SIN ENLACE llegaba a los 5 min del LWT en vez
# de a los 5 min del último latido.
#
# Se reconoce por su FORMA y no por un marcador porque el CHECK de ``reason`` solo
# admite dos valores y el snapshot del gabinete también puede ser ``transition``
# (``HealthSnapshot.transition_reason``): ése SÍ es un latido, y siempre trae
# ``seedlink_lag_s``, ``temperature_c`` y ``ups_status`` por defecto del
# contrato. Una fila de transición sin UNA SOLA medición no es más que presencia.
#
# UNA definición para todas las lecturas del último latido (flota, mapa, salud
# móvil, orden de sirena): cuatro copias acabarían divergiendo. Anclado en
# ``tests/api/test_lwt_no_es_un_latido.py``, que inserta la fila con el SQL del
# propio handler.
LATIDO_REAL = (
    "NOT (dh.reason = 'transition' AND num_nonnulls("
    "dh.seedlink_lag_s, dh.ntp_offset_ms, dh.mqtt_rtt_ms, dh.cpu_temp_c, dh.power_status, "
    "dh.battery_pct, dh.battery_min_left, dh.cert_days_remaining, dh.relays_state, "
    "dh.packet_loss_pct, dh.disk_used_pct, dh.evidence_pending, dh.evidence_oldest_age_s"
    ") = 0)"
)

# [A-057 · T-8.09 · 2ª mitad] ¿El broker dio la sesión por MUERTA después del
# último latido real? Expresión sobre ``g`` (``gateways``) y ``h`` (el LATERAL
# del último latido, ya filtrado con ``LATIDO_REAL``).
#
# Quitar el LWT de «el último latido» no bastaba. En la secuencia REAL
# (``edge/takab_edge/cloud``: latido cada 60 s, ``keep_alive_secs=30``) el broker
# publica el LWT ~45 s después de la caída, cuando el último latido tiene 45–105 s:
# con ``sin_enlace_min=5`` la consola seguía diciendo OPERATIVO otros 195–255 s con
# el gabinete YA marcado ``offline`` por ``handle_status``. El LWT es la única
# señal que dice «se cayó» antes de que el silencio lo demuestre; ignorarla era
# mostrar un dato congelado como vivo (regla de oro 7).
#
# Las dos condiciones importan:
#  · ``status = 'offline'``: un beacon ``online`` posterior (reconexión) lo levanta.
#  · ``status_ts >= h.ts``: un LATIDO posterior también. Si el beacon de vuelta se
#    pierde, ``gateways.status`` se queda en ``offline`` mientras el gabinete late:
#    sin esta comparación lo pintaríamos SIN ENLACE para siempre. Latir es la
#    prueba de vida; el LWT sólo manda sobre lo que es más viejo que él.
# ``status_ts`` es la marca monotónica que escribe ``_STATUS_SQL`` (SQS reordena:
# un LWT viejo no la pisa). Sin marca, o sin latido, no hay nada que comparar ⇒
# ``false``: la ausencia de latido ya es SIN ENLACE por su cuenta.
#
# UNA definición para flota, mapa y móvil (``tests/api/test_lwt_no_es_un_latido.py``).
ENLACE_PERDIDO = (
    "COALESCE(g.status = 'offline' AND (g.metadata->>'status_ts')::timestamptz >= h.ts, false)"
)

#: La edad que DERIVA el enlace: la del último latido real, o NULL si el broker
#: ya declaró la sesión muerta después de él (``derive_fleet_state`` lee NULL como
#: SIN ENLACE). Para las lecturas que sólo derivan el enlace con la edad (mapa,
#: salud móvil, orden de sirena). La flota NO la usa: su edad fecha también la
#: versión, y ahí «perdió el enlace» no es «nunca latió» (``routers/fleet.py``).
EDAD_DEL_ENLACE = (
    f"CASE WHEN {ENLACE_PERDIDO} THEN NULL ELSE EXTRACT(EPOCH FROM (now() - h.ts))::float8 END"
)

# [T-2.35] El JOIN a `sites` y el WHERE no son adorno: eran la ÚNICA query del repo
# que devolvía TODO sin filtrar, y de ahí salían las "estaciones fantasma". Como
# `retire_site` tampoco tocaba `gateways`, cada retiro dejaba una tarjeta indeleble
# cuyo nombre la web tenía que inventar (`SITIO <8 hex>`) — dos huérfanos parecían el
# mismo. Ahora el nombre del sitio VIAJA CON LA FILA: sin join en el cliente no hay
# fallback que fabricar.
#
# El JOIN es INNER a propósito y no pierde filas: `gateways.site_id` es
# `NOT NULL REFERENCES sites` (db/schema.sql). Tampoco ensancha la visibilidad:
# `sites_read` y `gateways_read` tienen políticas equivalentes.
_LIST_SQL = """
    SELECT g.gateway_id, g.site_id, g.serial, g.fw_version, g.fw_running, g.iot_thing,
           g.status, g.has_wr1, g.equipment, g.installed_at, g.xmin::text AS row_version,
           s.name   AS site_name,
           s.code   AS site_code,
           s.status AS site_status,
           h.ts AS health_ts, h.power_status,
           h.battery_pct::float8       AS battery_pct,
           h.cert_days_remaining,
           h.mqtt_rtt_ms::float8       AS mqtt_rtt_ms,
           h.seedlink_lag_s::float8    AS seedlink_lag_s,
           h.packet_loss_pct::float8   AS packet_loss_pct,
           h.ntp_offset_ms::float8     AS ntp_offset_ms,
           -- [T-2.70.a·B1] Si el gabinete pudo mirarse los relés en su último
           -- latido. `unreadable` = nadie contesta como dueño de los pines: sin
           -- sirena, sin cierre de gas, sin retorno de ascensores y sin
           -- retenedores, con todas las demás métricas perfectas.
           h.relays_state,
           -- [T-7.53] La evidencia que el gabinete RETIENE. `evidence_pending`
           -- NULL = no pudo preguntar; 0 = preguntó y no retiene nada.
           h.evidence_pending,
           h.evidence_oldest_age_s::float8 AS evidence_oldest_age_s,
           h.disk_used_pct::float8 AS disk_used_pct,
           EXTRACT(EPOCH FROM (now() - h.ts))::float8 AS age_s,
           -- [A-057] El LWT posterior al último latido (ver `ENLACE_PERDIDO`).
           /*+enlace_perdido*/ AS link_lost,
           r.ts    AS retired_at,
           r.actor AS retired_by
    FROM gateways g
    JOIN sites s ON s.site_id = g.site_id
    LEFT JOIN LATERAL (
        SELECT dh.ts, dh.power_status, dh.battery_pct, dh.cert_days_remaining,
               dh.mqtt_rtt_ms, dh.seedlink_lag_s, dh.ntp_offset_ms, dh.relays_state,
               dh.packet_loss_pct, dh.evidence_pending, dh.evidence_oldest_age_s,
               dh.disk_used_pct
        FROM device_health dh
        WHERE dh.gateway_id = g.gateway_id
          -- [A-057] El LWT no es un latido (ver `LATIDO_REAL`).
          AND /*+latido_real*/
        ORDER BY dh.ts DESC
        LIMIT 1
    ) h ON true
    -- [T-2.60.a] Cuándo y quién lo retiró. Vive SOLO en la bitácora: `gateways`
    -- no tiene `retired_at`, y añadirlo duplicaría un hecho que ya está escrito
    -- en una tabla append-only (la copia y el original acabarían discrepando).
    -- La guarda de estado va PRIMERO para que en un inventario sano —donde nadie
    -- está retirado— este LATERAL no llegue a mirar la bitácora.
    -- Se apoya en idx_audit_log_object_ts (0026); sin ese índice esto sería un
    -- escaneo secuencial de la única tabla que no se poda jamás (regla de oro 11).
    LEFT JOIN LATERAL (
        SELECT a.ts, a.actor
        FROM audit_log a
        WHERE (g.status = 'retired' OR s.status = 'retired')
          AND a.verb IN ('gateway_retire', 'site_retire')
          AND a.object IN ('gateway:' || g.gateway_id::text, 'site:' || s.site_id::text)
        ORDER BY a.ts DESC
        LIMIT 1
    ) r ON true
    WHERE (:include_retired
       OR (g.status <> 'retired' AND s.status <> 'retired')
       -- [T-2.60.a] …O SIGUE LATIENDO. T-2.35 enseñó a esconder lo retirado y
       -- estuvo bien: un gabinete desmontado no puede quedarse en el grid para
       -- siempre. Pero esconder por ESTADO sin mirar si el aparato habla creó el
       -- fallo simétrico, y el 2026-08-04 se lo comió un operador: `gw-dev-0001`
       -- llevaba horas publicando latidos cada 60 s, invisible, porque el retiro
       -- de su sitio se heredó al gabinete. Se supo porque preguntó él.
       -- Esconder al mudo, delatar al que late. El umbral es el MISMO de
       -- `derive_fleet_state` (`SIN ENLACE`), pasado desde el router: dos
       -- definiciones de "vivo" acabarían divergiendo.
       -- [A-057] …y "vivo" es lo MISMO que no-SIN-ENLACE: un retirado cuyo
       -- broker ya publicó el LWT no es un fantasma que habla, es un mudo.
       OR (h.ts > now() - make_interval(secs => :alive_s) AND NOT /*+enlace_perdido*/))
       /*+console_scope*/
    ORDER BY s.name, g.serial, g.gateway_id
    """.replace("/*+latido_real*/", LATIDO_REAL).replace("/*+enlace_perdido*/", ENLACE_PERDIDO)
# [T-2.45] Sin marcador sustituido: la variante que usan los consumidores que no
# pasan por la consola (el espejo `_CONFIG_STATE_ALL` de abajo la deriva de esta).
_LIST = text(_LIST_SQL.replace("/*+console_scope*/", ""))


async def list_gateways_with_health(
    conn: AsyncConnection,
    *,
    include_retired: bool = False,
    alive_s: float,
    scope: ConsoleScope | None = None,
) -> Sequence[Row]:
    """Gateways del tenant + su último heartbeat (RLS por tenant en todas las tablas).

    Por defecto oculta lo retirado —gabinete propio O sitio padre—; los retirados solo
    se piden explícitamente, para poder restaurarlos.

    [T-2.60.a] Con UNA excepción que no se puede desactivar: un retirado cuyo último
    latido sea más nuevo que ``alive_s`` sale SIEMPRE. Esconder a un aparato que está
    hablando no es limpiar el inventario, es perder de vista un edificio.

    ``alive_s`` no tiene defecto a propósito: quien llama tiene que decidirlo con el
    mismo umbral que usa para derivar ``SIN ENLACE``. Un defecto silencioso aquí sería
    una segunda definición de "vivo", y las dos divergirían en cuanto alguien tocase
    ``sin_enlace_min``.
    """
    sql, extra = apply_scope(_LIST_SQL, scope, "g.site_id") if scope else (_LIST_SQL, {})
    params = {"include_retired": include_retired, "alive_s": alive_s, **extra}
    return (await conn.execute(text(sql), params)).all()


# Estado del sync firmado de UN gateway. El rule_set se resuelve EXACTAMENTE como
# en ``commands/sync.py`` (scope site preferente sobre tenant, versión más alta,
# LIMIT 1 ANTES de exigir el bloque 'edge'), para que ``in_sync`` sea la negación
# del predicado de publicación del worker y no una segunda opinión.
#
# [B3] Este bloque es UN ESPEJO, no una segunda opinión: las expresiones de `base`,
# `admin_state` y `doc` de abajo son textualmente las de `_CANDIDATES_SQL`, y
# `tests/commands/test_sync_mirror.py` lo verifica para que una corrección en el
# original no pueda aterrizar en un solo lado. Ahí está anotada la deuda conocida:
# `admin_state` mira solo `g.status`, mientras `is_ghost` y la métrica de fantasmas
# miran `g.status OR s.status` — hay un estado alcanzable (sitio retirado, gabinete
# sin propagar) en el que el panel del gabinete diría ACTIVO y la consola lo pinta
# fantasma. Arreglarlo exige mover las DOS copias en el mismo commit; cambiar solo
# esta dejaría `in_sync` en falso permanente.
_CONFIG_STATE = text(
    """
    -- El COALESCE de `base` es obligatorio por partida doble: sin rule_set activo
    -- el LEFT JOIN deja rs.config NULL, y un NULL colándose a los bool
    -- no-opcionales de GatewayConfigStateOut reventaría con un 500 el endpoint
    -- que promete 200 + PENDIENTE.
    SELECT g.gateway_id,
           st.version,
           st.published_at,
           st.sig,
           -- [B3] "¿hay algo que publicarle?" — el espejo EXACTO del gate de
           -- publicación del worker (`commands/sync.py`: `b.base IS NOT NULL`),
           -- no `rs.config ? 'edge'`. Desde que la base sale de un COALESCE (el
           -- rule_set activo O el último doc publicado, despojado de lo que se
           -- fusiona aquí), las dos frases dejaron de ser la misma: un gabinete
           -- sin rule_set activo pero con doc previo SÍ se publica —al cambiarle
           -- el equipamiento, por ejemplo— y la consola lo pintaba «SIN CONFIG
           -- EDGE», cuyo copy afirma "no hay nada que publicar". El operador
           -- veía negado, sobre su propio cambio, justo lo que el worker estaba
           -- haciendo. El nombre del campo se conserva (es contrato publicado y
           -- el SDK lo consume); lo que se corrige es que vuelva a significarlo.
           (b.base IS NOT NULL)                       AS has_edge_config,
           -- [T-2.65] is_syncable responde "¿PUEDE este gabinete recibir config
           -- firmada?" (identidad IoT + estado administrativo); has_edge_config
           -- responde la otra mitad, "¿hay algo que publicarle?". Mantenerlas
           -- separadas es lo que deja al operador saber a quién llamar.
           -- El retirado sigue siendo sincronizable MIENTRAS no haya recibido su
           -- sobre de baja: ese aviso es justo lo que T-2.65 hace salir. Una vez
           -- avisado (payload con cloud_admin_state='retired') deja el flujo.
           (g.iot_thing IS NOT NULL
            AND (g.status <> 'retired'
                 OR st.payload->>'cloud_admin_state' IS DISTINCT FROM 'retired')) AS is_syncable,
           -- [T-2.31/T-2.65] El worker publica el doc FUSIONADO (equipment +
           -- cloud_admin_state) sobre una base que puede venir del rule_set activo
           -- o del último doc publicado: in_sync compara contra esa MISMA fusión o
           -- mentiría PENDIENTE para siempre. Es la negación exacta del predicado
           -- de diferencia de commands/sync.py::_CANDIDATES_SQL.
           COALESCE(st.gateway_id IS NOT NULL
            AND st.payload IS NOT DISTINCT FROM d.doc,
            false) AS in_sync
    FROM gateways g
    LEFT JOIN LATERAL (
        SELECT r.config
        FROM rule_sets r
        WHERE r.is_active
          AND ( (r.scope_type = 'site'   AND r.scope_id = g.site_id)
             OR (r.scope_type = 'tenant' AND r.scope_id = g.tenant_id) )
        ORDER BY (r.scope_type = 'site') DESC, r.version DESC
        LIMIT 1
    ) rs ON true
    LEFT JOIN gateway_config_state st ON st.gateway_id = g.gateway_id
    CROSS JOIN LATERAL (
        SELECT COALESCE(rs.config->'edge',
                        st.payload - 'equipment' - 'cloud_admin_state') AS base,
               CASE WHEN g.status = 'retired' THEN 'retired' ELSE 'active' END AS admin_state
    ) b
    CROSS JOIN LATERAL (
        SELECT b.base || jsonb_build_object(
                 'equipment', g.equipment, 'cloud_admin_state', b.admin_state) AS doc
    ) d
    WHERE g.gateway_id = :gateway_id
    """
)

# [T-2.37] El MISMO SQL sin el filtro por id. Existe porque la consola necesitaba el
# estado de N gabinetes y lo resolvía con N peticiones en paralelo cada 10 s: con 500
# gabinetes eso son ~50 req/s desde un solo navegador, y como el pie solo se considera
# válido cuando responden TODOS, a esa escala habría dicho "desconocido" casi siempre.
_CONFIG_STATE_ALL = text(str(_CONFIG_STATE).replace("WHERE g.gateway_id = :gateway_id", "").strip())


async def get_config_state(conn: AsyncConnection, gateway_id: str) -> Row | None:
    """Estado del config firmado del gateway. ``None`` si RLS no lo deja verlo."""
    return (await conn.execute(_CONFIG_STATE, {"gateway_id": gateway_id})).first()


async def list_config_states(conn: AsyncConnection) -> Sequence[Row]:
    """Estado del config firmado de TODOS los gateways visibles (RLS por tenant)."""
    return (await conn.execute(_CONFIG_STATE_ALL)).all()


# --- Administración de gabinetes (T-1.32) ------------------------------------
# El ``tenant_id`` no es parámetro del cuerpo: lo hereda del sitio padre, que el
# router ya validó contra los claims. ``xmin::text`` es el testigo de concurrencia.

_ROW_COLS = (
    "gateway_id, tenant_id, site_id, serial, fw_version, iot_thing, "
    "status, has_wr1, equipment, installed_at, xmin::text AS row_version"
)

_GET_ROW = text(f"SELECT {_ROW_COLS} FROM gateways WHERE gateway_id = :id")

# Alta SIEMPRE en 'provisioned': el gabinete no está online hasta que su primer
# heartbeat lo demuestre. La API no crea certificados X.509 (eso es Terraform).
# [T-2.69] Sin `fw_version` en NINGUNA de las dos: el único escritor de esa columna
# es el latido del propio gabinete (`ingest/handlers.py`). Cuando estaba aquí, el
# PUT —que es de reemplazo TOTAL— reenviaba el valor prellenado del formulario con
# cada edición, así que la consola podía anotar o borrar una versión que el aparato
# nunca corrió; en un gabinete SIN ENLACE esa mentira era permanente. En el alta la
# columna queda NULL, que es la verdad: nadie ha visto latir a ese gabinete todavía.
_INSERT = text(
    "INSERT INTO gateways (tenant_id, site_id, serial, iot_thing, "
    "status, has_wr1, equipment, installed_at) "
    "VALUES (CAST(:tenant_id AS uuid), :site_id, :serial, :iot_thing, "
    "'provisioned', :has_wr1, CAST(:equipment AS jsonb), :installed_at) "
    f"RETURNING {_ROW_COLS}"
)

_UPDATE = text(
    "UPDATE gateways SET site_id = :site_id, serial = :serial, "
    "iot_thing = :iot_thing, has_wr1 = :has_wr1, equipment = CAST(:equipment AS jsonb), "
    "installed_at = :installed_at "
    "WHERE gateway_id = :id "
    "  AND (CAST(:base_row_version AS text) IS NULL "
    "       OR xmin::text = CAST(:base_row_version AS text)) "
    f"RETURNING {_ROW_COLS}"
)

_SET_STATUS = text(
    f"UPDATE gateways SET status = :status WHERE gateway_id = :id RETURNING {_ROW_COLS}"
)


async def get_gateway_row(conn: AsyncConnection, gateway_id: UUID) -> Row | None:
    """Fila cruda del gateway, o ``None`` si RLS no lo deja verla."""
    return (await conn.execute(_GET_ROW, {"id": gateway_id})).first()


async def insert_gateway(conn: AsyncConnection, *, tenant_id: str, values: dict) -> Row:
    """Inserta el gabinete en 'provisioned'. ``serial``/``iot_thing`` son únicos GLOBALES."""
    return (await conn.execute(_INSERT, {**values, "tenant_id": tenant_id})).one()


async def update_gateway(
    conn: AsyncConnection, *, gateway_id: UUID, values: dict, base_row_version: str | None
) -> Row | None:
    """Reemplaza el gabinete. ``None`` = otro escritor ganó la carrera (⇒ 409)."""
    params = {**values, "id": gateway_id, "base_row_version": base_row_version}
    return (await conn.execute(_UPDATE, params)).first()


async def set_gateway_status(conn: AsyncConnection, gateway_id: UUID, status: str) -> Row | None:
    """Fija ``status`` (solo 'retired' o 'provisioned' desde la API). Idempotente."""
    return (await conn.execute(_SET_STATUS, {"id": gateway_id, "status": status})).first()
