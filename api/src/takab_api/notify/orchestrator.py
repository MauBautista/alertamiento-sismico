"""Pasada del orquestador de notificaciones (T-1.21 · B6).

Dos fases por pasada, bajo un advisory lock propio (serializa instancias):

1. **ENQUEUE**: incidentes recientes (lookback) con ``state≠closed`` y sin
   jobs → ``plan_jobs`` (cascada / crítico paralelo / fail-open) + INSERT
   ``ON CONFLICT DO NOTHING`` (UNIQUE (incident, channel, mode) = idempotente).
2. **DISPATCH**: jobs ``pending`` con ``due_at ≤ now``, en bucle hasta agotar:
   - cascada ya satisfecha (algún cascade 'sent' del incidente) ⇒ ``skipped``;
   - canal SIMULADO (sin proveedor real) ⇒ ``simulated`` (T-2.75, ver abajo);
   - éxito ⇒ ``sent`` + ``incident_actions kind='notify_sent'`` (canal, modo,
     latencia vs t0 y cumplimiento del deadline — evidencia del SLA);
   - fallo CON escalado posible ⇒ ``failed`` + el SIGUIENTE cascade pendiente se
     ADELANTA a ``now`` (escala ya; con proveedor sano el SMS sale en el mismo
     pass ≤30 s);
   - fallo SIN nadie detrás (job paralelo o último salto de la cascada) ⇒ sigue
     ``pending`` con ``attempts+1`` y ``due_at`` aplazado (backoff 30 s / 2 min,
     T-1.62): es la única voz que le queda al incidente, no se tira a la basura.
   El éxito de un cascade marca ``skipped`` el resto de su cascada. Los jobs
   ``parallel`` son independientes (fail-open y email crítico no se skipean).

[T-2.75] **Un canal simulado no entrega, y por tanto no satisface nada.** Hasta
aquí el simulado "triunfaba": marcaba ``sent``, la cascada se daba por cumplida
y el canal REAL que venía detrás no llegaba a dispararse (medido: webhook caído
+ whatsapp simulado ⇒ sms y email ``skipped``, el proveedor de correo llamado
CERO veces). Ahora el simulado es un desenlace propio:

- estado ``simulated`` y ``sent_at`` intacto en NULL — dos candados contra que
  algo aguas abajo lo lea como entregado;
- ``incident_actions kind='notify_simulated'`` (verbo propio, no un
  ``notify_sent`` con bandera dentro: la evidencia se agrupa por ``kind``);
- **escala igual que un fallo** — el siguiente cascade se adelanta a ``now``;
- pero **es TERMINAL y no consume intentos**: ``failed`` es transitorio (el
  proveedor existe y puede volver, por eso hay backoff); ``simulated`` no puede
  volver de ninguna parte, y reintentar contra un proveedor inexistente sería
  martillear la nada hasta agotar los intentos por nada.

[T-2.109] **Un sitio sin un solo teléfono al que despertar lo DICE.** El canal
push elige destinatarios con ``WHERE site_id = <uuid> AND tenant_id = ... AND
revoked_at IS NULL``. La app registraba su token con ``site_id: null`` (llamaba a
``registerDeviceForPush()`` sin argumento, y era su único punto de registro), y
NULL no iguala a un UUID: ningún dispositivo entraba jamás en la lista. Lo que
hacía el orquestador ante esa lista vacía era CALLAR — no encolaba push y la
pasada devolvía verde—, así que un edificio entero sin cobertura era
indistinguible de uno cubierto.

No era una regresión viva: ``push_tokens`` está vacía en producción porque el
canal real sigue detrás de GATE-STORE (T-2.97). Era una MINA — el día que
APNs/FCM aterricen, la acreditación saldría verde sin que sonara un teléfono.
Ahora "cero destinatarios" es un desenlace propio: verbo
``notify_no_recipients`` con el censo de tokens del tenant dentro (incluido
cuántos están registrados SIN inmueble, que es la firma exacta del defecto),
contador propio en la pasada, y terminal en el dispatch — no se reintenta contra
una lista vacía ni se molesta al proveedor con ella.

Corre como ``takab_ingest`` (BYPASSRLS) en el worker ``python -m
takab_api.notify``; cloud-only, jamás en el camino de actuación del edge.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import psycopg

from takab_api.auth.matrix import roles_with_action
from takab_api.notify.config import resolve_destinations, resolve_inspector_emails
from takab_api.notify.plan import plan_jobs, resolve_params
from takab_api.notify.providers import (
    NotifyError,
    NotifyProvider,
    bind_state,
    is_simulated,
    provider_message_id,
)
from takab_api.notify.push import (
    PUSH_CLASS_CRISIS,
    PUSH_CLASS_OPS,
    PUSH_CLASS_PANIC,
    PushDevice,
    build_push_payload,
)
from takab_api.notify.state import PgNotifyState
from takab_api.privacy import store as privacy_store
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.notify")

#: [T-2.147.a] Fase que la app abre al recibir cada clase de push. Tabla y no
#: ternario: el `else` anterior daba «headcount» a toda clase que no fuera
#: CRISIS, así que una clase nueva enrutaba al pase de lista sin que nada se
#: quejara. Una clase sin fase declarada revienta aquí, que es lo correcto.
_PUSH_PHASE = {
    PUSH_CLASS_CRISIS: "alert_active",
    PUSH_CLASS_OPS: "headcount",
    PUSH_CLASS_PANIC: "building_alarm",
}

# Advisory lock propio (≠ engine 0x…1119, ≠ dictamen 0x…1120).
_NOTIFY_LOCK_KEY = 0x7A4B_1121

# [T-1.62] Espera entre envíos de un mismo job (el intento N usa el índice N-1).
# Corto al principio (un AccessDenied recién arreglado entrega en 30 s) y largo
# después (un proveedor caído no se martillea).
_BACKOFF_S = (30.0, 120.0, 600.0)

#: [T-2.147.c] Holgura del borde viejo de la ventana del aviso al SOC, POR
#: ENCIMA de plazo+lookback. Cubre una pasada que se retrase (worker
#: reiniciando, lock ocupado) sin que el incidente se caiga de la ventana
#: justo cuando acababa de volverse elegible. No es infinita a propósito:
#: ver la cota superior en `_PANIC_ACK_TIMEOUT_SQL`.
_MARGEN_VENTANA_S = 600.0

_NEW_INCIDENTS_SQL = """
SELECT i.incident_id, i.tenant_id, i.site_id, i.severity, i.trigger, i.opened_at
FROM incidents i
WHERE i.opened_at >= %(since)s
  AND i.opened_at <= %(now)s
  AND i.state <> 'closed'
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.incident_id = i.incident_id
  )
ORDER BY i.opened_at, i.incident_id
"""

# rule_set activo del sitio (site preferente sobre tenant) — espejo del engine.
_RULESET_SQL = """
SELECT config
FROM rule_sets
WHERE is_active
  AND ( (scope_type = 'site'   AND scope_id = %(site)s)
     OR (scope_type = 'tenant' AND scope_id = %(tenant)s) )
ORDER BY (scope_type = 'site') DESC, version DESC
LIMIT 1
"""

_INSERT_JOB_SQL = """
INSERT INTO notification_jobs
  (tenant_id, incident_id, channel, mode, position, target, due_at, deadline_at)
VALUES (%(tenant)s, %(incident)s, %(channel)s, %(mode)s, %(position)s,
        %(target)s::jsonb, %(due_at)s, %(deadline_at)s)
ON CONFLICT (incident_id, channel, mode) WHERE action_id IS NULL DO NOTHING
"""

# [T-1.61] Solicitudes de dictamen SIN job y SIN dictamen firmado posterior —
# espejo del _PENDING_REQUEST_SQL de incidents_ops.py (409): una solicitud ya
# satisfecha no molesta al inspector.
_DICTAMEN_REQUESTS_SQL = """
SELECT a.action_id, a.incident_id, a.ts, a.actor, a.payload,
       i.tenant_id, i.site_id
FROM incident_actions a
JOIN incidents i ON i.incident_id = a.incident_id
WHERE a.kind = 'dictamen_request'
  AND a.ts >= %(since)s
  AND a.ts <= %(now)s
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.action_id = a.action_id
  )
  AND NOT EXISTS (
    SELECT 1 FROM dictamens d
    WHERE d.incident_id = a.incident_id
      AND d.signed_by IS NOT NULL
      AND d.created_at > a.ts
  )
ORDER BY a.ts, a.action_id
"""

# 1 job por (action_id, channel) — índice único parcial de 0014: los re-runs
# del pass y las re-entregas NOTIFY no duplican el correo del inspector.
_INSERT_ACTION_JOB_SQL = """
INSERT INTO notification_jobs
  (tenant_id, incident_id, channel, mode, position, target, due_at, action_id)
VALUES (%(tenant)s, %(incident)s, 'email', 'parallel', 0,
        %(target)s::jsonb, %(due_at)s, %(action)s)
ON CONFLICT (action_id, channel) WHERE action_id IS NOT NULL DO NOTHING
"""

# [T-2.10] Reportes de daños con PERSONAS EN RIESGO sin notificar todavía —
# prioridad máxima (2.4): el SOC recibe un email INMEDIATO. Mismo patrón que
# dictamen_request pero SIN dedup por "ya atendido": una vida en riesgo se
# notifica siempre (el índice único (action_id, channel) evita duplicados).
_PEOPLE_AT_RISK_SQL = """
SELECT a.action_id, a.incident_id, a.ts, a.actor, a.payload,
       i.tenant_id, i.site_id
FROM incident_actions a
JOIN incidents i ON i.incident_id = a.incident_id
WHERE a.kind = 'damage_people_at_risk'
  AND a.ts >= %(since)s
  AND a.ts <= %(now)s
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.action_id = a.action_id
  )
ORDER BY a.ts, a.action_id
"""

# [T-2.11] "Notificar a no reportados" (2.6): cada ``headcount_notify`` sin job
# ⇒ un push clase OPS a los dispositivos del sitio. Mismo patrón de acción.
_HEADCOUNT_NOTIFY_SQL = """
SELECT a.action_id, a.incident_id, a.ts, a.actor, a.payload,
       i.tenant_id, i.site_id
FROM incident_actions a
JOIN incidents i ON i.incident_id = a.incident_id
WHERE a.kind = 'headcount_notify'
  AND a.ts >= %(since)s
  AND a.ts <= %(now)s
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.action_id = a.action_id
  )
ORDER BY a.ts, a.action_id
"""

# [T-2.12] Dictamen HABITABLE firmado (2.7): cada ``dictamen_signed`` sin job ⇒
# push OPS de CAMBIO DE FASE a los dispositivos del sitio — despierta la app,
# que re-lee mobile-state (reentry_approved) y libera las pantallas 1.5.
_DICTAMEN_SIGNED_SQL = """
SELECT a.action_id, a.incident_id, a.ts, a.actor, a.payload,
       i.tenant_id, i.site_id
FROM incident_actions a
JOIN incidents i ON i.incident_id = a.incident_id
WHERE a.kind = 'dictamen_signed'
  AND a.ts >= %(since)s
  AND a.ts <= %(now)s
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.action_id = a.action_id
  )
ORDER BY a.ts, a.action_id
"""

# 1 push por (action_id, channel): el índice único parcial de 0014 (action) lo
# hace idempotente. El target lleva site_id + clase OPS (el _dispatch_push
# resuelve los dispositivos del sitio FRESCOS y sella/revoca endpoints).
_INSERT_PUSH_ACTION_JOB_SQL = """
INSERT INTO notification_jobs
  (tenant_id, incident_id, channel, mode, position, target, due_at, action_id)
VALUES (%(tenant)s, %(incident)s, 'push', 'parallel', 0,
        %(target)s::jsonb, %(due_at)s, %(action)s)
ON CONFLICT (action_id, channel) WHERE action_id IS NOT NULL DO NOTHING
"""

_DUE_JOBS_SQL = """
SELECT j.job_id, j.tenant_id, j.incident_id, j.channel, j.mode, j.position,
       j.target, j.due_at, j.deadline_at, j.action_id, j.attempts,
       i.severity, i.trigger, i.state, i.opened_at, i.event_id, i.site_id,
       s.name AS site_name, s.code AS site_code,
       a.kind AS action_kind, a.actor AS action_actor, a.payload AS action_payload
FROM notification_jobs j
JOIN incidents i ON i.incident_id = j.incident_id
JOIN sites s ON s.site_id = i.site_id
LEFT JOIN incident_actions a ON a.action_id = j.action_id
WHERE j.status = 'pending' AND j.due_at <= %(now)s
ORDER BY j.due_at, j.position, j.job_id
"""

_CASCADE_SATISFIED_SQL = """
SELECT 1 FROM notification_jobs
WHERE incident_id = %(incident)s AND mode = 'cascade' AND status = 'sent'
LIMIT 1
"""

_SKIP_PENDING_CASCADE_SQL = """
UPDATE notification_jobs SET status = 'skipped'
WHERE incident_id = %(incident)s AND mode = 'cascade' AND status = 'pending'
"""

# [T-2.77.b] `sent_at` sigue significando lo que siempre significó: **el
# proveedor lo aceptó**. Lo nuevo es `provider_message_id`, que es con lo que el
# webhook de estado casará el desenlace TARDÍO —"llegó a las 12:00:19"— contra
# este job. Hasta hoy ese identificador moría en el recibo en memoria del worker
# y no había con qué casar nada.
#
# El `nullif`+`coalesce` no es adorno: los canales sin recibo (correo, webhook
# firmado, push) mandan cadena vacía y no deben BORRAR un identificador ya
# escrito. Un canal sin callback simplemente no tiene desenlace tardío.
_MARK_SENT_SQL = """
UPDATE notification_jobs
SET status = 'sent', sent_at = %(now)s,
    provider_message_id = coalesce(nullif(%(receipt)s, ''), provider_message_id)
WHERE job_id = %(job)s
"""

_MARK_FAILED_SQL = """
UPDATE notification_jobs SET status = 'failed', error = %(error)s, attempts = %(attempts)s
WHERE job_id = %(job)s
"""

# [T-2.75] `sent_at` se queda en NULL A PROPÓSITO: es la marca de "esto llegó".
# Rellenarla sería la misma mentira en otra columna, y así cualquier consulta de
# entregados (`sent_at IS NOT NULL`) excluye lo simulado sin saber que existe.
# `attempts` tampoco se toca: no hubo intento contra nadie.
_MARK_SIMULATED_SQL = """
UPDATE notification_jobs SET status = 'simulated', error = %(note)s
WHERE job_id = %(job)s
"""

_SIMULATED_NOTE = "canal simulado: sin proveedor real configurado, nadie recibió nada"

# [T-1.62] El job sigue 'pending': solo suma el intento, guarda el motivo y se
# aplaza. `_dispatch` no lo re-selecciona en esta pasada (due_at > now, y `now`
# es fijo por pass) — nada de bucles calientes.
_RETRY_SQL = """
UPDATE notification_jobs
SET attempts = %(attempts)s, due_at = %(due_at)s, error = %(error)s
WHERE job_id = %(job)s
"""

_ADVANCE_NEXT_SQL = """
UPDATE notification_jobs SET due_at = %(now)s
WHERE job_id = (
  SELECT job_id FROM notification_jobs
  WHERE incident_id = %(incident)s AND mode = 'cascade' AND status = 'pending'
    AND position > %(position)s
  ORDER BY position
  LIMIT 1
)
"""

# actor distintivo por canal/modo: la clave natural de idempotencia de acks
# (uq_incident_actions_ack: incident, kind, actor, ts) usa el ts de TRANSACCIÓN,
# y varios envíos del mismo incidente en un pass comparten now() — con actor
# plano 'system' colisionarían entre sí.
# [T-2.75] El `kind` es parámetro: 'notify_sent' cuando alguien recibió algo,
# 'notify_simulated' cuando no. Verbos distintos porque la evidencia se lee y se
# agrupa por `kind`, y `incident_actions` es append-only y exenta de poda.
_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(incident)s, %(tenant)s, %(kind)s, %(actor)s, %(payload)s::jsonb)
"""

_KIND_SENT = "notify_sent"
_KIND_SIMULATED = "notify_simulated"
_KIND_FAILED = "notify_failed"
# [T-2.109] Cuarto verbo. No es entregado, no es simulado (el proveedor existe y
# entrega) y no es fallo (no hay avería que arreglar ni a quién reintentar): es
# que NO HAY A QUIÉN DESPERTAR en este sitio. La reacción del operador es otra
# —conseguir que los teléfonos se registren con su inmueble—, así que el verbo
# también.
_KIND_NO_RECIPIENTS = "notify_no_recipients"

# Evidencia guardada UNA vez por (incidente, actor). `incident_actions` es
# append-only y exenta de poda por retención (regla de oro 11): un incidente que
# se re-mira en cada pasada —tenant sin cascada configurada— no puede dejar una
# fila por pasada en la tabla que existe para reconstruir lo ocurrido.
_NO_RECIPIENTS_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
SELECT %(incident)s::uuid, %(tenant)s::uuid, %(kind)s::text, %(actor)s::text,
       %(payload)s::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM incident_actions
  WHERE incident_id = %(incident)s::uuid AND kind = %(kind)s::text
    AND actor = %(actor)s::text
)
"""

# --- push (T-2.04) — targeting por SITIO al despachar (lista siempre fresca).
_PUSH_EXISTS_SQL = """
SELECT 1 FROM push_tokens
WHERE site_id = %(site)s AND tenant_id = %(tenant)s AND revoked_at IS NULL
LIMIT 1
"""

_PUSH_DEVICES_SQL = """
SELECT push_token_id, token, platform, endpoint_arn
FROM push_tokens
WHERE site_id = %(site)s AND tenant_id = %(tenant)s AND revoked_at IS NULL
ORDER BY created_at
"""

# [T-2.147.c · D-05] Pánicos que la BRIGADA no acusó dentro del plazo.
#
# Tres filtros y una ventana, y cada uno tiene su porqué:
#
#   · `trigger='manual'` — el plazo es del pánico. Un sismo ya tiene su cascada;
#     añadirle esto duplicaría la página del SOC por el mismo hecho.
#   · `state = 'open'` — si el SOC YA acusó, lo tiene delante. Avisarle de que
#     nadie lo tiene delante es ruido, y el ruido en un SOC es lo que enseña a
#     ignorar la bandeja. (Funciona porque T-2.147.b NO mueve el estado: el
#     acuse de la brigada y el del SOC siguen siendo señales independientes.)
#   · sin `tactical_ack` — alguien respondió, y el aviso diría una mentira.
#
# LA VENTANA, que es donde este escaneo podía fallar EN SILENCIO. El aviso solo
# es elegible PASADO el plazo, así que el borde viejo tiene que ser más ancho
# que el plazo: con una ventana más estrecha, el incidente saldría de ella ANTES
# de volverse elegible y el aviso no saltaría JAMÁS — en verde, sin un error, y
# sin descubrirse hasta que una brigada de verdad no contestara. Por eso el
# borde viejo es `plazo + lookback` y no `lookback` a secas.
#
# Y tiene cota superior a propósito: sin ella, restaurar una base vieja
# estrenaría el SOC con una bandeja llena de emergencias de otro año.
_PANIC_ACK_TIMEOUT_SQL = """
SELECT i.incident_id, i.tenant_id, i.site_id, i.opened_at
FROM incidents i
WHERE i.trigger = 'manual'
  AND i.state = 'open'
  AND i.opened_at <= %(elegible_desde)s
  AND i.opened_at >= %(no_mas_viejo_que)s
  AND NOT EXISTS (
        SELECT 1 FROM incident_actions a
        WHERE a.incident_id = i.incident_id AND a.kind = 'tactical_ack'
      )
  AND NOT EXISTS (
        SELECT 1 FROM incident_actions a
        WHERE a.incident_id = i.incident_id AND a.kind = 'tactical_ack_timeout'
      )
ORDER BY i.opened_at
"""

# El aviso EN EL TIMELINE. Va primero, y por dos motivos: es la evidencia que el
# SOC ve en la traza del incidente, y su `action_id` es el ancla que hace
# idempotente el correo (mismo patrón que el dictamen y el «personas en riesgo»).
_INSERT_ACK_TIMEOUT_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(incident)s, %(tenant)s, 'tactical_ack_timeout', 'system', %(payload)s)
RETURNING action_id
"""

# [T-2.147.a · D-11] Pánicos recientes sin push encolado todavía.
#
# `trigger = 'manual'` es la firma del quórum de pánico: los demás incidentes
# nacen del edge (`sasmex`, `local_threshold`, `quorum`). El `NOT EXISTS` es la
# idempotencia — sin él, cada pasada del worker encolaría otro push del mismo
# pánico mientras el incidente siguiera dentro de la ventana.
_PANIC_INCIDENT_PUSH_SQL = """
SELECT i.incident_id, i.tenant_id, i.site_id, i.opened_at
FROM incidents i
WHERE i.trigger = 'manual'
  AND i.opened_at >= %(since)s
  AND NOT EXISTS (
        SELECT 1 FROM notification_jobs j
        WHERE j.incident_id = i.incident_id AND j.channel = 'push'
      )
ORDER BY i.opened_at
"""

_INSERT_PANIC_PUSH_JOB_SQL = """
INSERT INTO notification_jobs
  (tenant_id, incident_id, channel, mode, position, target, due_at)
VALUES (%(tenant)s, %(incident)s, 'push', 'parallel', 0, %(target)s, %(due_at)s)
"""

# [T-2.147.a] Los MISMOS dispositivos, acotados a un conjunto de roles.
#
# `user_zone_assignments` es la ÚNICA tabla que persiste el rol por inmueble: un
# worker de segundo plano no tiene claims de Cognito, así que sin este JOIN la
# nube no puede saber quién es táctico. El `IN` es un array parametrizado y la
# lista la DERIVA quien encola (`roles_with_action`), nunca este SQL.
#
# `DISTINCT` porque `user_zone_assignments` tiene PK `(user_id, site_id)` pero el
# mismo usuario puede tener varios dispositivos; sin él, un táctico con teléfono
# y tablet contaría dos veces en el censo de entregas.
_PUSH_DEVICES_BY_ROLE_SQL = """
SELECT DISTINCT p.push_token_id, p.token, p.platform, p.endpoint_arn, p.created_at
FROM push_tokens p
JOIN user_zone_assignments a
  ON a.user_id = p.user_sub
 AND a.site_id = p.site_id
 AND a.tenant_id = p.tenant_id
WHERE p.site_id = %(site)s
  AND p.tenant_id = %(tenant)s
  AND p.revoked_at IS NULL
  AND a.role = ANY(%(roles)s::text[])
ORDER BY p.created_at
"""

# [T-2.109] Censo de tokens del tenant para poder DECIR por qué no hay nadie.
# `tokens_sin_inmueble` es la firma exacta del defecto que cerró esta ficha: la
# app registraba con `site_id: null` y los dos filtros de arriba comparan
# `site_id = <uuid>`, que NULL no satisface jamás. Un token así existe, parece
# un teléfono cubierto y no recibe nada.
_TENANT_TOKENS_SQL = """
SELECT count(*) AS total,
       count(*) FILTER (WHERE site_id IS NULL) AS sin_sitio
FROM push_tokens
WHERE tenant_id = %(tenant)s AND revoked_at IS NULL
"""

_SET_ENDPOINT_ARN_SQL = """
UPDATE push_tokens SET endpoint_arn = %(arn)s WHERE push_token_id = %(id)s
"""

# Endpoint deshabilitado (token rotado / app desinstalada): revocación honesta —
# el dispositivo vivo re-registra su token nuevo vía el upsert de /me/push-tokens.
_REVOKE_PUSH_TOKEN_SQL = """
UPDATE push_tokens SET revoked_at = %(now)s
WHERE push_token_id = %(id)s AND revoked_at IS NULL
"""


def run_notify_pass(
    conn: psycopg.Connection,
    settings: Settings,
    providers: dict[str, NotifyProvider],
    *,
    now: datetime | None = None,
    lookback_s: float | None = None,
) -> dict[str, int]:
    """Encola y despacha; devuelve {enqueued, sent, failed, skipped, retried}.
    Un COMMIT al final si hubo escrituras; si no, ROLLBACK (solo lectura)."""
    now = now or datetime.now(tz=UTC)
    lookback = settings.notify_lookback_s if lookback_s is None else lookback_s
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_NOTIFY_LOCK_KEY,))

    config_cache: dict[tuple[str, str], dict | None] = {}
    counts = {
        "enqueued": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "retried": 0,
        # [T-2.75] Cuenta propia: sumarlo a `sent` habría sido el mismo embuste
        # una capa más arriba, y sumarlo a `failed` diría "hay que arreglar el
        # proveedor" cuando lo que falta es CONTRATAR uno.
        "simulated": 0,
        # [T-2.109] Sitios que se quedaron sin un solo teléfono al que despertar.
        # El contador es la señal VIVA de la pasada (se repite mientras siga sin
        # haber nadie); la fila de `incident_actions` es la evidencia permanente
        # y se escribe una sola vez. Antes esto no existía: la push simplemente
        # no se encolaba y la pasada devolvía verde.
        "no_recipients": 0,
    }

    counts["enqueued"] = _enqueue(
        conn, settings, config_cache, counts, now=now, lookback_s=lookback
    )
    counts["enqueued"] += _enqueue_dictamen_requests(
        conn, config_cache, now=now, lookback_s=lookback
    )
    counts["enqueued"] += _enqueue_people_at_risk(conn, config_cache, now=now, lookback_s=lookback)
    counts["enqueued"] += _enqueue_push_for_actions(
        conn, _HEADCOUNT_NOTIFY_SQL, now=now, lookback_s=lookback
    )
    counts["enqueued"] += _enqueue_push_for_actions(
        conn, _DICTAMEN_SIGNED_SQL, now=now, lookback_s=lookback
    )
    # [T-2.147.a] El pánico va en su propia función y no por `_enqueue_push_for_actions`:
    # aquel encola por ACCIÓN de incidente (`action_id`), y un pánico no genera
    # ninguna — el hecho es el incidente mismo.
    counts["enqueued"] += _enqueue_panic_push(conn, now=now, lookback_s=lookback)
    # [T-2.147.c] Va DESPUÉS del push: el aviso al SOC solo tiene sentido
    # sobre pánicos que ya recibieron su push — si el push ni se encoló, lo
    # que falla es otra cosa y el aviso mandaría al operador a mirar a la
    # brigada en vez de al canal.
    counts["enqueued"] += _enqueue_panic_ack_timeout(
        conn, settings, config_cache, now=now, lookback_s=lookback
    )
    # [T-2.77.c] Lo que los providers recordaban EN RAM pasa a recordarse aquí,
    # sobre la conexión de esta pasada: sobrevive al reinicio del worker y lo
    # comparten las instancias. Se ata por el registro, sin nombrar canales —
    # quien no tenga nada que recordar ni se entera.
    state = PgNotifyState(conn, now=now)
    bind_state(providers, state)
    _dispatch(conn, settings, providers, config_cache, counts, state, now=now)

    if any(counts.values()):
        conn.commit()
    else:
        conn.rollback()
    return counts


# --------------------------------------------------------------------- fases


def _enqueue(
    conn: psycopg.Connection,
    settings: Settings,
    config_cache: dict,
    counts: dict[str, int],
    *,
    now: datetime,
    lookback_s: float,
) -> int:
    params = resolve_params(settings)
    rows = conn.execute(
        _NEW_INCIDENTS_SQL, {"since": now - timedelta(seconds=lookback_s), "now": now}
    ).fetchall()
    inserted = 0
    for row in rows:
        destinations = resolve_destinations(_config_for(conn, config_cache, row))
        # [T-2.04] Push CRISIS si el sitio tiene dispositivos registrados: el
        # target solo lleva el site_id (la lista de dispositivos se resuelve
        # FRESCA al despachar, como el secret del webhook). Un tenant sin
        # cascada pero con app instalada igual despierta teléfonos.
        has_devices = conn.execute(
            _PUSH_EXISTS_SQL, {"site": row["site_id"], "tenant": row["tenant_id"]}
        ).fetchone()
        if has_devices is not None:
            destinations = {**destinations, "push": {"site_id": str(row["site_id"])}}
        else:
            # [T-2.109] Aquí estaba el silencio: sin dispositivos no se encolaba
            # push y la pasada seguía como si nada, así que un edificio entero
            # sin un solo teléfono alcanzable era indistinguible de uno cubierto.
            _record_no_recipients(
                conn,
                counts,
                incident_id=row["incident_id"],
                tenant_id=row["tenant_id"],
                site_id=row["site_id"],
                actor="system:notify:push:enqueue",
            )
        if not destinations:
            continue  # tenant sin cascada configurada: nada que encolar
        specs = plan_jobs(
            severity=row["severity"],
            trigger=row["trigger"],
            opened_at=row["opened_at"],
            destinations=destinations,
            params=params,
        )
        for spec in specs:
            result = conn.execute(
                _INSERT_JOB_SQL,
                {
                    "tenant": row["tenant_id"],
                    "incident": row["incident_id"],
                    "channel": spec.channel,
                    "mode": spec.mode,
                    "position": spec.position,
                    "target": json.dumps(spec.target),
                    "due_at": spec.due_at,
                    "deadline_at": spec.deadline_at,
                },
            )
            inserted += result.rowcount
    return inserted


def _enqueue_dictamen_requests(
    conn: psycopg.Connection,
    config_cache: dict,
    *,
    now: datetime,
    lookback_s: float,
) -> int:
    """[T-1.61] Un email al inspector por cada ``dictamen_request`` sin atender.

    El wake sale gratis: el trigger NOTIFY de 0004 ya cubre el INSERT en
    ``incident_actions`` y el worker ya escucha ``takab_live``.
    """
    rows = conn.execute(
        _DICTAMEN_REQUESTS_SQL, {"since": now - timedelta(seconds=lookback_s), "now": now}
    ).fetchall()
    inserted = 0
    for row in rows:
        emails = resolve_inspector_emails(_config_for(conn, config_cache, row))
        if not emails:
            logger.warning(
                "dictamen_request %s sin notifications.inspector_emails: se omite",
                row["action_id"],
            )
            continue
        result = conn.execute(
            _INSERT_ACTION_JOB_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "target": json.dumps({"to": emails}),
                "due_at": row["ts"],  # vence YA: paralelo, sin cascada
                "action": row["action_id"],
            },
        )
        inserted += result.rowcount
    return inserted


def _enqueue_people_at_risk(
    conn: psycopg.Connection,
    config_cache: dict,
    *,
    now: datetime,
    lookback_s: float,
) -> int:
    """[T-2.10] Un email INMEDIATO al SOC por cada reporte con personas en
    riesgo. Reusa el destino operativo (``notifications.inspector_emails``) y
    el mismo INSERT idempotente por acción que el dictamen."""
    rows = conn.execute(
        _PEOPLE_AT_RISK_SQL, {"since": now - timedelta(seconds=lookback_s), "now": now}
    ).fetchall()
    inserted = 0
    for row in rows:
        emails = resolve_inspector_emails(_config_for(conn, config_cache, row))
        if not emails:
            logger.warning(
                "damage_people_at_risk %s sin notifications.inspector_emails: se omite",
                row["action_id"],
            )
            continue
        result = conn.execute(
            _INSERT_ACTION_JOB_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "target": json.dumps({"to": emails}),
                "due_at": row["ts"],  # vence YA: prioridad máxima, sin cascada
                "action": row["action_id"],
            },
        )
        inserted += result.rowcount
    return inserted


def _enqueue_panic_ack_timeout(
    conn: psycopg.Connection,
    settings: Settings,
    config_cache: dict,
    *,
    now: datetime,
    lookback_s: float,
) -> int:
    """[T-2.147.c · D-05] La brigada no acusó: se avisa al SOC. **No al edificio.**

    `D-05` eligió despertar solo a los tácticos. El agujero conocido de esa
    opción es que la brigada no conteste, y la salida elegida fue avisar al SOC
    en vez de escalar a todo el mundo: escalar por un temporizador reintroduce
    «despertar a 400» con dos minutos de retraso, y encima **la decisión la
    habría tomado un reloj**. Un humano con contexto decide si esto merece
    despertar al edificio.

    Deja DOS rastros, y el orden importa: primero la fila del timeline —que es
    lo que el SOC ve en la traza— y con su ``action_id`` se ancla el correo, que
    así hereda la idempotencia por acción del resto del módulo.
    """
    plazo = settings.panic_tactical_ack_timeout_s
    rows = conn.execute(
        _PANIC_ACK_TIMEOUT_SQL,
        {
            "elegible_desde": now - timedelta(seconds=plazo),
            # Ancho DELIBERADO: ver la nota larga sobre la ventana en el SQL.
            # Con `lookback` a secas, un plazo mayor que la ventana haría que el
            # aviso no saltara nunca.
            "no_mas_viejo_que": now - timedelta(seconds=plazo + lookback_s + _MARGEN_VENTANA_S),
        },
    ).fetchall()
    inserted = 0
    for row in rows:
        emails = resolve_inspector_emails(_config_for(conn, config_cache, row))
        if not emails:
            # Mismo criterio que «personas en riesgo»: sin destino configurado no
            # se inventa uno. Pero se DICE — un SOC sin correo operativo es una
            # brigada sin red de seguridad, y callarlo lo vuelve invisible.
            logger.warning(
                "pánico %s sin acuse de la brigada y SIN notifications.inspector_emails: "
                "nadie va a enterarse de que la brigada no contestó",
                row["incident_id"],
            )
            continue
        action_id = conn.execute(
            _INSERT_ACK_TIMEOUT_ACTION_SQL,
            {
                "incident": row["incident_id"],
                "tenant": row["tenant_id"],
                "payload": json.dumps(
                    {
                        # Lo que el operador necesita para decidir SIN abrir otra
                        # pantalla: cuánto plazo se dio, cuántos respondieron
                        # (cero, por construcción) y a qué edificio mirar.
                        "timeout_s": plazo,
                        "tactical_acks": 0,
                        "site_id": str(row["site_id"]),
                        "source": "panic_quorum",
                    }
                ),
            },
        ).fetchone()["action_id"]
        result = conn.execute(
            _INSERT_ACTION_JOB_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "target": json.dumps({"to": emails}),
                "due_at": now,  # vence YA: el plazo ya se agotó
                "action": action_id,
            },
        )
        inserted += result.rowcount
    return inserted


def _enqueue_panic_push(conn: psycopg.Connection, *, now: datetime, lookback_s: float) -> int:
    """[T-2.147.a · D-05 · D-11] Un push a los TÁCTICOS por cada pánico reciente.

    El router del voto no puede encolar esto: `notification_jobs` tiene RLS que
    solo admite escrituras de los roles internos, y una petición de occupant no
    lo es. Debilitar esa política para que el teléfono de un ocupante encolara
    notificaciones sería mover la frontera equivocada. Lo que el router deja es
    el HECHO —un incidente `trigger='manual'`—; el resto es de aquí.

    **El círculo se DERIVA de la matriz**: `manual_activate` es quien ya puede
    disparar la sirena a mano, o sea quien tiene algo que hacer con el aviso.
    Escribirlo a mano divergiría el día que entre un rol nuevo.

    **A quién NO va, que es el punto de `D-05`:** al resto del edificio. La
    sirena ya suena y la app ya explica la alarma; el push solo añade valor para
    quien tiene que actuar. Dos personas no deben poder despertar a 400.

    Idempotente por el `NOT EXISTS`: la pasada siguiente no duplica el job.
    """
    rows = conn.execute(
        _PANIC_INCIDENT_PUSH_SQL, {"since": now - timedelta(seconds=lookback_s)}
    ).fetchall()
    inserted = 0
    for row in rows:
        result = conn.execute(
            _INSERT_PANIC_PUSH_JOB_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "target": json.dumps(
                    {
                        "site_id": str(row["site_id"]),
                        "push_class": PUSH_CLASS_PANIC,
                        "roles": list(roles_with_action("manual_activate")),
                    }
                ),
                "due_at": row["opened_at"],  # vence YA: es una emergencia
            },
        )
        inserted += result.rowcount
    return inserted


def _enqueue_push_for_actions(
    conn: psycopg.Connection, sql: str, *, now: datetime, lookback_s: float
) -> int:
    """[T-2.11/2.12] Un push OPS por cada acción reciente sin job (headcount o
    dictamen firmado). El push va a los dispositivos del sitio (best-effort R5);
    el índice único (action_id, channel) evita duplicados entre passes."""
    rows = conn.execute(sql, {"since": now - timedelta(seconds=lookback_s), "now": now}).fetchall()
    inserted = 0
    for row in rows:
        result = conn.execute(
            _INSERT_PUSH_ACTION_JOB_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "target": json.dumps({"site_id": str(row["site_id"]), "push_class": "OPS"}),
                "due_at": row["ts"],  # vence YA (paralelo)
                "action": row["action_id"],
            },
        )
        inserted += result.rowcount
    return inserted


def _dispatch(
    conn: psycopg.Connection,
    settings: Settings,
    providers: dict[str, NotifyProvider],
    config_cache: dict,
    counts: dict[str, int],
    state: PgNotifyState,
    *,
    now: datetime,
) -> None:
    # Bucle hasta agotar: cada job procesado sale de 'pending' o se aplaza a
    # futuro (reintento), y un fallo puede ADELANTAR el siguiente cascade a
    # `now` → re-select hasta vacío. `now` fijo ⇒ un reintento nunca reentra.
    while True:
        rows = conn.execute(_DUE_JOBS_SQL, {"now": now}).fetchall()
        if not rows:
            return
        for row in rows:
            _dispatch_one(conn, settings, providers, config_cache, counts, state, row, now=now)


def _dispatch_one(
    conn: psycopg.Connection,
    settings: Settings,
    providers: dict[str, NotifyProvider],
    config_cache: dict,
    counts: dict[str, int],
    state: PgNotifyState,
    row: dict,
    *,
    now: datetime,
) -> None:
    # [T-2.158] Sin `notify_web_public` no se pasa base, así que `_message()` no
    # compone enlace. El corte va AQUÍ y no en el proveedor de correo porque el
    # problema es el mismo en SMS y WhatsApp: un enlace que no se abre es inútil
    # en cualquier canal, y componerlo para tirarlo después invita a que alguien
    # lo reutilice sin saber que está muerto.
    base_url = settings.notify_web_base_url if settings.notify_web_public else ""
    max_attempts = settings.notify_max_attempts
    incident_id = row["incident_id"]
    if row["mode"] == "cascade":
        satisfied = conn.execute(_CASCADE_SATISFIED_SQL, {"incident": incident_id}).fetchone()
        if satisfied is not None:
            conn.execute(_SKIP_PENDING_CASCADE_SQL, {"incident": incident_id})
            counts["skipped"] += 1
            return

    provider = providers.get(row["channel"])
    if provider is None:  # canal sin provider cableado: cuenta como fallo
        _fail(conn, counts, row, "provider no configurado", now=now, max_attempts=max_attempts)
        return

    # [T-2.75] ANTES de bifurcar por canal: la pregunta se le hace al PROVIDER,
    # no a una lista de nombres. Así el push —que despacha por su propia rama
    # con deliver()— y cualquier canal futuro quedan cubiertos sin tocar esto.
    if is_simulated(provider):
        _simulate(conn, counts, row, now=now)
        return

    if row["channel"] == "push":
        _dispatch_push(conn, counts, row, provider, now=now, max_attempts=max_attempts)
        return

    target = dict(row["target"])
    if row["channel"] == "webhook":
        # El secret vive en el rule_set, jamás en el job: se re-resuelve aquí.
        destinations = resolve_destinations(_config_for(conn, config_cache, row))
        secret = destinations.get("webhook", {}).get("secret")
        if secret:
            target["secret"] = secret
    elif row["channel"] == "whatsapp":
        opt_in, error = _whatsapp_opt_in(conn, row, target)
        if error is not None:
            _fail(conn, counts, row, error, now=now, max_attempts=max_attempts)
            return
        # Se PISA siempre, incluso con `opt_in` ausente: un job encolado por la
        # versión anterior lleva la constancia del rule_set congelada en su
        # jsonb, y fiarse de ella sería enviar con un papel viejo el primer
        # sismo tras el despliegue.
        target.pop("opt_in", None)
        if opt_in is not None:
            target["opt_in"] = {"at": opt_in.isoformat(), "source": "privacy_consents"}

    # [T-2.77.c] Este job es el que tiene guarda mientras dure este envío. La
    # guarda del provider decide CUÁNDO recordar (ambiguo sí, rechazo explícito
    # no) exactamente como antes; lo único que cambia es que el recuerdo se
    # escribe en la fila del job y no en la RAM de esta instancia.
    state.enter_job(row["job_id"])
    try:
        provider.send(target, _message(row, base_url=base_url))
    except NotifyError as exc:
        _fail(conn, counts, row, str(exc), now=now, max_attempts=max_attempts)
        return

    # [T-2.77.b] El identificador del proveedor sale del RECIBO, con el mismo
    # nombre en todos los canales: aquí no hay —ni puede haber— una rama que
    # sepa cómo lo llama cada uno.
    conn.execute(
        _MARK_SENT_SQL,
        {"job": row["job_id"], "now": now, "receipt": provider_message_id(provider)},
    )
    if row["mode"] == "cascade":
        counts["skipped"] += conn.execute(
            _SKIP_PENDING_CASCADE_SQL, {"incident": incident_id}
        ).rowcount
    latency_s = (now - row["opened_at"]).total_seconds()
    deadline_met = row["deadline_at"] is None or now <= row["deadline_at"]
    # [T-1.61] Actor único por acción: un email de incidente y uno de dictamen
    # en el MISMO pass comparten el ts de transacción — con actor plano
    # colisionarían contra uq_incident_actions_ack.
    actor_suffix = f":{row['action_id']}" if row.get("action_id") else ""
    conn.execute(
        _ACTION_SQL,
        {
            "incident": incident_id,
            "tenant": row["tenant_id"],
            "kind": _KIND_SENT,
            "actor": f"system:notify:{row['channel']}:{row['mode']}{actor_suffix}",
            "payload": json.dumps(
                {
                    "job_id": str(row["job_id"]),
                    "channel": row["channel"],
                    "mode": row["mode"],
                    "latency_s": latency_s,
                    "deadline_met": deadline_met,
                }
            ),
        },
    )
    counts["sent"] += 1
    logger.info(
        "notify sent %s/%s incidente %s (latencia %.1fs, SLA %s)",
        row["channel"],
        row["mode"],
        incident_id,
        latency_s,
        "OK" if deadline_met else "VENCIDO",
    )


def _dispatch_push(
    conn: psycopg.Connection,
    counts: dict[str, int],
    row: dict,
    provider,
    *,
    now: datetime,
    max_attempts: int,
) -> None:
    """[T-2.04] Rama propia del canal push (lote por dispositivo + limpieza).

    El provider expone ``deliver()`` (resultado POR dispositivo) en vez de
    ``send()``: hay que sellar los endpoint ARN recién creados y REVOCAR los
    muertos. ≥1 entrega = sent (best-effort, R5); 0 entregas con dispositivos
    vivos = fallo → backoff (es un job paralelo: única voz push del incidente).
    """
    target = row["target"] or {}
    site_id = str(target.get("site_id") or row["site_id"])
    # [T-2.147.a] `roles` acota el push a un círculo (hoy: los tácticos del
    # quórum de pánico, D-05). Ausente = TODO el inmueble, que es la conducta de
    # siempre y la que quiere una crisis sísmica.
    roles = target.get("roles")
    if roles:
        sql, params = (
            _PUSH_DEVICES_BY_ROLE_SQL,
            {
                "site": site_id,
                "tenant": row["tenant_id"],
                "roles": list(roles),
            },
        )
    else:
        sql, params = _PUSH_DEVICES_SQL, {"site": site_id, "tenant": row["tenant_id"]}
    devices = [
        PushDevice(
            push_token_id=str(r["push_token_id"]),
            token=r["token"],
            platform=r["platform"],
            endpoint_arn=r["endpoint_arn"],
        )
        for r in conn.execute(sql, params).fetchall()
    ]
    if not devices:
        # [T-2.109] Nadie a quien entregar NO es una avería del proveedor. Antes
        # caía en `_fail`, que sin nadie a quien escalar reintenta con backoff:
        # tres pasadas martilleando una lista vacía para acabar escribiendo
        # `notify_failed`, un verbo que manda al operador a revisar SNS cuando lo
        # que falta son teléfonos registrados con su inmueble. Es el mismo
        # argumento de T-2.75 con el canal simulado: desenlace propio y terminal.
        _no_recipients_job(conn, counts, row)
        return

    # [T-2.11] La clase del push la fija el job (CRISIS al abrir incidente;
    # OPS para el "notificar a no reportados" del headcount). Default CRISIS por
    # retrocompatibilidad con los jobs de T-2.04.
    push_class = str(target.get("push_class") or PUSH_CLASS_CRISIS)
    # [T-2.147.a] La fase la declara la clase, en una tabla y no en un ternario:
    # con `else "headcount"`, una clase nueva heredaba en silencio la fase del
    # pase de lista — y la app enruta por fase, así que un pánico habría abierto
    # la pantalla equivocada.
    phase = _PUSH_PHASE[push_class]
    payload = build_push_payload(
        push_class=push_class,
        site_id=site_id,
        incident_id=str(row["incident_id"]),
        phase=phase,
    )
    outcome = provider.deliver(devices, payload)

    for token_id, arn in outcome.created_arns.items():
        conn.execute(_SET_ENDPOINT_ARN_SQL, {"id": token_id, "arn": arn})
    for token_id in outcome.disabled_ids:
        conn.execute(_REVOKE_PUSH_TOKEN_SQL, {"id": token_id, "now": now})

    if outcome.delivered == 0:
        error = "; ".join(outcome.errors) or "todos los endpoints deshabilitados"
        _fail(conn, counts, row, error[:500], now=now, max_attempts=max_attempts)
        return

    # El push entrega por dispositivo y no devuelve UN identificador con el que
    # casar nada: no hay callback de estado que esperar, así que no hay recibo.
    conn.execute(_MARK_SENT_SQL, {"job": row["job_id"], "now": now, "receipt": ""})
    latency_s = (now - row["opened_at"]).total_seconds()
    # [T-2.11] El actor distingue por action_id cuando lo hay: dos push del
    # MISMO incidente en un pass (CRISIS al abrir + OPS del headcount) escriben
    # su notify_sent sin colisionar en uq_incident_actions_ack (incident, kind,
    # actor, ts). Sin action_id (CRISIS) el actor queda como en T-2.04.
    actor = f"system:notify:push:{row['mode']}"
    if row.get("action_id"):
        actor = f"{actor}:{row['action_id']}"
    conn.execute(
        _ACTION_SQL,
        {
            "incident": row["incident_id"],
            "tenant": row["tenant_id"],
            "kind": _KIND_SENT,
            "actor": actor,
            "payload": json.dumps(
                {
                    "job_id": str(row["job_id"]),
                    "channel": "push",
                    "mode": row["mode"],
                    "class": push_class,
                    "latency_s": latency_s,
                    "devices_delivered": outcome.delivered,
                    "devices_revoked": len(outcome.disabled_ids),
                }
            ),
        },
    )
    counts["sent"] += 1
    logger.info(
        "notify sent push/%s incidente %s (%d dispositivo(s), %d revocado(s), latencia %.1fs)",
        row["mode"],
        row["incident_id"],
        outcome.delivered,
        len(outcome.disabled_ids),
        latency_s,
    )


def _simulate(
    conn: psycopg.Connection,
    counts: dict[str, int],
    row: dict,
    *,
    now: datetime,
) -> None:
    """[T-2.75] Desenlace de un canal SIN proveedor real. Nadie recibió nada.

    Ni ``sent`` (sería mentir) ni ``failed`` (mandaría a arreglar un proveedor
    que no existe, y arrastraría el backoff a martillear la nada hasta agotar
    los tres intentos). Estado propio, terminal, con evidencia propia — y
    escalando al siguiente canal exactamente como escala un fallo, porque a
    efectos de "¿llegó a un humano?" un simulado es un NO ENTREGADO.
    """
    conn.execute(_MARK_SIMULATED_SQL, {"job": row["job_id"], "note": _SIMULATED_NOTE})
    if row["mode"] == "cascade":
        conn.execute(
            _ADVANCE_NEXT_SQL,
            {"incident": row["incident_id"], "position": row["position"], "now": now},
        )
    actor_suffix = f":{row['action_id']}" if row.get("action_id") else ""
    conn.execute(
        _ACTION_SQL,
        {
            "incident": row["incident_id"],
            "tenant": row["tenant_id"],
            "kind": _KIND_SIMULATED,
            "actor": f"system:notify:{row['channel']}:{row['mode']}{actor_suffix}",
            "payload": json.dumps(
                {
                    "job_id": str(row["job_id"]),
                    "channel": row["channel"],
                    "mode": row["mode"],
                    "latency_s": (now - row["opened_at"]).total_seconds(),
                    "simulated": True,
                    # El SLA mide una ENTREGA. Sin entrega no hay plazo que
                    # cumplir ni que incumplir: null es "no aplica", y no se
                    # confunde con el False de "llegó tarde" (regla de oro 7).
                    "deadline_met": None,
                }
            ),
        },
    )
    counts["simulated"] += 1
    logger.warning(
        "notify SIMULADO %s/%s incidente %s: nadie recibió nada por este canal",
        row["channel"],
        row["mode"],
        row["incident_id"],
    )


def _no_recipients_job(
    conn: psycopg.Connection,
    counts: dict[str, int],
    row: dict,
) -> None:
    """[T-2.109] Un job de push que se encontró el sitio VACÍO.

    Termina aquí: no se reintenta (no hay proveedor caído que pueda volver, ni
    lista que se llene en los 30 s del backoff — un teléfono se registra al abrir
    la app o al enrolarse, no en mitad de un sismo) y no se molesta al proveedor
    con una lista vacía. El estado del job es ``failed`` porque el schema no
    tiene otro terminal que diga "no llegó" —añadir uno pedía migración, y el
    candado real es que ``sent_at`` se queda en NULL—, pero el ``error`` y el
    verbo de la evidencia dicen la verdad completa: faltan destinatarios.
    """
    actor = f"system:notify:push:{row['mode']}"
    if row.get("action_id"):
        actor = f"{actor}:{row['action_id']}"
    site_id = (row["target"] or {}).get("site_id") or row["site_id"]
    extra: dict[str, object] = {
        "job_id": str(row["job_id"]),
        "mode": row["mode"],
        # Sin entrega no hay plazo que cumplir: null es "no aplica", nunca el
        # False de "llegó tarde" (regla de oro 7).
        "deadline_met": None,
    }
    if row.get("action_id"):
        extra["action_id"] = str(row["action_id"])
    detail = _record_no_recipients(
        conn,
        counts,
        incident_id=row["incident_id"],
        tenant_id=row["tenant_id"],
        site_id=site_id,
        actor=actor,
        extra=extra,
    )
    conn.execute(
        _MARK_FAILED_SQL,
        {"job": row["job_id"], "error": detail[:500], "attempts": (row["attempts"] or 0) + 1},
    )


def _record_no_recipients(
    conn: psycopg.Connection,
    counts: dict[str, int],
    *,
    incident_id,
    tenant_id,
    site_id,
    actor: str,
    extra: dict[str, object] | None = None,
) -> str:
    """[T-2.109] Deja ESCRITO que este sitio no tiene a quién despertar.

    Devuelve el motivo en texto (sirve de ``error`` del job). El payload lleva el
    censo de tokens del tenant porque "cero" tiene dos causas muy distintas y el
    operador reacciona distinto a cada una:

    * ``tokens_del_tenant = 0`` — nadie instaló la app todavía. Esperable
      mientras el canal real siga detrás de GATE-STORE (T-2.97): se registra
      igual, pero sin gritar.
    * ``tokens_sin_inmueble > 0`` — hay teléfonos registrados que NO apuntan a
      ningún sitio. Esa es la avería de esta ficha: el registro mandaba
      ``site_id: null`` y ningún filtro por sitio los alcanza jamás. Se grita.

    La distinción es el punto entero: sin ella, el día que GATE-STORE aterrice la
    acreditación saldría verde con todos los teléfonos huérfanos y nadie sabría
    por qué no sonó ninguno.
    """
    census = conn.execute(_TENANT_TOKENS_SQL, {"tenant": tenant_id}).fetchone()
    total = int(census["total"]) if census else 0
    sin_sitio = int(census["sin_sitio"]) if census else 0
    huerfanos = sin_sitio > 0
    detail = "sin destinatarios de push para el sitio: " + (
        f"{sin_sitio} token(s) del tenant registrados SIN inmueble "
        "(un token sin site_id no es destinatario de ningún sitio)"
        if huerfanos
        else f"{total} token(s) en el tenant, ninguno de este sitio"
    )
    payload: dict[str, object] = {
        "channel": "push",
        "site_id": str(site_id),
        "tokens_del_sitio": 0,
        "tokens_del_tenant": total,
        "tokens_sin_inmueble": sin_sitio,
        "reason": detail,
    }
    payload.update(extra or {})
    conn.execute(
        _NO_RECIPIENTS_ACTION_SQL,
        {
            "incident": incident_id,
            "tenant": tenant_id,
            "kind": _KIND_NO_RECIPIENTS,
            "actor": actor,
            "payload": json.dumps(payload),
        },
    )
    counts["no_recipients"] += 1
    log = logger.warning if huerfanos else logger.info
    log(
        "notify push SIN DESTINATARIOS sitio %s (incidente %s): %s",
        site_id,
        incident_id,
        detail,
    )
    return detail


def _fail(
    conn: psycopg.Connection,
    counts: dict[str, int],
    row: dict,
    error: str,
    *,
    now: datetime,
    max_attempts: int,
) -> None:
    """Fallo de un envío. Dos desenlaces, y el criterio es *quién queda detrás*.

    Si es un salto de cascada CON siguiente canal, muere en el acto y adelanta al
    de atrás (reintentarlo retrasaría llegar al humano: eso es la cascada).
    Si no hay a quién escalar —job paralelo, o el último salto—, este envío es la
    única voz que queda: se reintenta con backoff hasta agotar los intentos. Antes
    se convertía en lápida, y un AccessDenied de SES bastó para dejar un dictamen
    real sin correo y sin forma de re-pedirlo (T-1.62).
    """
    escalated = 0
    if row["mode"] == "cascade":
        escalated = conn.execute(
            _ADVANCE_NEXT_SQL,
            {"incident": row["incident_id"], "position": row["position"], "now": now},
        ).rowcount

    attempts = (row["attempts"] or 0) + 1
    if not escalated and attempts < max_attempts:
        backoff = _BACKOFF_S[min(attempts, len(_BACKOFF_S)) - 1]
        conn.execute(
            _RETRY_SQL,
            {
                "job": row["job_id"],
                "attempts": attempts,
                "due_at": now + timedelta(seconds=backoff),
                "error": error[:500],
            },
        )
        counts["retried"] += 1
        logger.warning(
            "notify retry %s/%s incidente %s (intento %d/%d, en %.0fs): %s",
            row["channel"],
            row["mode"],
            row["incident_id"],
            attempts,
            max_attempts,
            backoff,
            error,
        )
        return

    conn.execute(
        _MARK_FAILED_SQL, {"job": row["job_id"], "error": error[:500], "attempts": attempts}
    )
    # [T-2.75] Evidencia del NO ENTREGADO, solo en el desenlace TERMINAL. Un
    # reintento todavía puede acabar entregando, y `incident_actions` es
    # append-only y exenta de poda por retención (regla de oro 11): una fila por
    # intento inflaría para siempre la tabla que existe para reconstruir lo
    # ocurrido. Así el operador ve las TRES cosas y reacciona distinto a cada
    # una — entregado (nada), simulado (falta contratar el canal), no entregado
    # (el proveedor está caído AHORA).
    actor_suffix = f":{row['action_id']}" if row.get("action_id") else ""
    conn.execute(
        _ACTION_SQL,
        {
            "incident": row["incident_id"],
            "tenant": row["tenant_id"],
            "kind": _KIND_FAILED,
            "actor": f"system:notify:{row['channel']}:{row['mode']}{actor_suffix}",
            "payload": json.dumps(
                {
                    "job_id": str(row["job_id"]),
                    "channel": row["channel"],
                    "mode": row["mode"],
                    "attempts": attempts,
                    "error": error[:500],
                    # Sin entrega no hay plazo que cumplir: null es "no aplica",
                    # nunca el False de "llegó tarde" (regla de oro 7).
                    "deadline_met": None,
                }
            ),
        },
    )
    counts["failed"] += 1
    logger.warning(
        "notify failed %s/%s incidente %s (intento %d/%d): %s",
        row["channel"],
        row["mode"],
        row["incident_id"],
        attempts,
        max_attempts,
        error,
    )


# ------------------------------------------------------------------ helpers


def _whatsapp_opt_in(
    conn: psycopg.Connection, row: dict, target: dict
) -> tuple[datetime | None, str | None]:
    """[T-2.79.a] La constancia que autoriza el envío, leída FRESCA del motor.

    Devuelve ``(instante, error)``:

    * ``(fecha, None)`` — hay consentimiento vigente: el destino lo lleva y el
      provider envía.
    * ``(None, None)`` — no lo hay (nunca lo hubo, o se RETIRÓ). El destino sale
      SIN ``opt_in`` y el provider —que no cambia— se niega con su motivo de
      siempre. Un canal de compliance tiene una sola voz de rechazo.
    * ``(None, motivo)`` — no se pudo LEER. También se niega, pero con el motivo
      verdadero: anotar "no consintió" cuando lo que falló fue la base es mentir
      en un registro de cumplimiento.

    **Se lee aquí y no en `resolve_destinations` por dos razones.** Una: esa
    función es el parser PURO del `rule_set` y no tiene conexión. Y otra, más
    importante: lo que autoriza tiene que estar VIGENTE en el instante del
    envío. Resolverlo al encolar lo congelaría en el `target` del job y
    reproduciría, una capa más abajo, el defecto exacto que esta tarea cierra —
    un instante que no puede enterarse de que lo retiraron. Es el mismo motivo
    por el que el `secret` del webhook se re-resuelve aquí y no se guarda.

    El SAVEPOINT no es decorativo: en psycopg un error deja la transacción
    envenenada, y sin él el ``notify_failed`` que este fallo debe dejar escrito
    moriría con ella. El desenlace tiene que quedar en la consola, no en un log.
    """
    msisdn = str(target.get("to") or "").strip()
    try:
        with conn.transaction():
            at = privacy_store.whatsapp_opt_in_at_sync(
                conn, tenant_id=str(row["tenant_id"]), msisdn=msisdn
            )
    except Exception as exc:  # noqa: BLE001 - ante la duda NO se envía, y se escribe
        logger.exception(
            "whatsapp: no se pudo leer el opt-in del tenant %s (job %s)",
            row["tenant_id"],
            row["job_id"],
        )
        return None, (
            "whatsapp: no se pudo leer el opt-in en el motor de consentimiento "
            f"({type(exc).__name__}). Sin constancia verificable no se envía: hacerlo "
            "degradaría la calidad del número y puede tumbar el canal para todos los tenants"
        )
    if at is None:
        logger.warning(
            "whatsapp: sin consentimiento vigente para %s (tenant %s) — no se envía",
            _mask(msisdn),
            row["tenant_id"],
        )
    return at, None


def _mask(msisdn: str) -> str:
    """Un teléfono es dato personal: en el log van los últimos 4 dígitos."""
    return f"…{msisdn[-4:]}" if len(msisdn) > 4 else "…"


def _config_for(conn: psycopg.Connection, cache: dict, row: dict) -> dict | None:
    key = (str(row["site_id"]), str(row["tenant_id"]))
    if key not in cache:
        found = conn.execute(
            _RULESET_SQL, {"site": row["site_id"], "tenant": row["tenant_id"]}
        ).fetchone()
        cache[key] = found["config"] if found else None
    return cache[key]


def _message(row: dict, *, base_url: str = "") -> dict:
    """Payload de notificación (MVP §8: sin T-MINUS ni magnitud preliminar).

    [T-1.61] Un job con ``action_id`` es una SOLICITUD DE DICTAMEN al
    inspector: headline propio, quién la pidió, su nota y el link directo al
    Triage (si hay base pública configurada).
    """
    message = {
        "source": "takab-ailert",
        "incident_id": str(row["incident_id"]),
        "site_id": str(row["site_id"]),
        "site_name": row["site_name"],
        "site_code": row["site_code"],
        "severity": row["severity"],
        "trigger": row["trigger"],
        "state": row["state"],
        "opened_at": row["opened_at"].isoformat(),
        "event_id": row["event_id"],
        "headline": f"TAKAB Ailert · Incidente {row['severity']} · {row['site_name']}",
    }
    if row.get("action_id"):
        payload = row.get("action_payload") or {}
        kind = row.get("action_kind")
        if kind == "damage_people_at_risk":
            # [T-2.10] Prioridad máxima: el SOC ve al frente "personas en riesgo".
            message["headline"] = f"TAKAB Ailert · PERSONAS EN RIESGO · {row['site_name']}"
            message["kind"] = "damage_people_at_risk"
            message["reported_by"] = row.get("action_actor")
            message["report_id"] = payload.get("report_id")
        else:
            message["headline"] = f"TAKAB Ailert · Solicitud de dictamen · {row['site_name']}"
            message["kind"] = "dictamen_request"
            message["requested_by"] = payload.get("requested_by") or row.get("action_actor")
            message["note"] = payload.get("note")
        if base_url:
            message["link"] = f"{base_url.rstrip('/')}/triage?incident={row['incident_id']}"
    return message
