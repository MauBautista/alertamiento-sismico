"""T-9.05 · el token de push es del APARATO, no de la persona

## El defecto, medido en el Pixel el 2026-09-24 (T-8.13)

El token FCM/APNs identifica un TELÉFONO. `push_tokens` lo guardaba como si
fuera de una persona: la RLS `pt_self` acota cada fila a
`user_sub = app_user_id()`, y el registro era un
`INSERT … ON CONFLICT (token) DO UPDATE`. Cuando el SIGUIENTE usuario del mismo
teléfono registraba ese mismo token, el conflicto caía sobre una fila que su RLS
no le deja ver, y PostgreSQL no lo trata como una actualización: lo trata como
una violación — «new row violates row-level security policy (USING expression)».
El registro fallaba y la app, best-effort, se callaba. El teléfono se quedaba
sin push para el edificio del usuario nuevo: la alarma llegaba al siguiente
sondeo (5–30 s), no al segundo.

Ni abrir `pt_self` ni un `GRANT` lo arreglan: la política es correcta para
LEER (un usuario no tiene por qué ver los aparatos de otro). Lo que hace falta es
UNA operación concreta que pueda saltarla: «este aparato ahora es mío».

## `app_claim_push_token` — por qué SECURITY DEFINER y por qué es seguro

Mismo patrón que `app_notify_delivery` (0040), `gov_ack_incident` y
`app_verify_retire_code`: función `SECURITY DEFINER` con dueño `takab_ingest`
(el ÚNICO rol con BYPASSRLS, `db/schema.sql:49`), `SET search_path` fijo,
`REVOKE … FROM PUBLIC` y `GRANT EXECUTE` sólo a `takab_app`. La superficie que
se abre no es «escribir en push_tokens»: es «quedarme con UN token, a MI nombre».

* **La identidad sale SOLO de la sesión** — `app_user_id()`, `app_tenant_id()`,
  `app_role()`, que la API fija por request desde el JWT verificado. La firma
  es `(p_token, p_platform, p_site)`: no hay por dónde colar otro dueño. Sin
  identidad de sesión no se reclama nada.
* **El sitio se comprueba DENTRO**: si `p_site` no es del tenant de la sesión,
  se rechaza. El router ya lo filtra con `assert_site_access` (404); esto es
  defensa en profundidad, porque una función que salta la RLS no puede fiarse de
  quien la llama.
* **Las lápidas de ARCO no se reclaman**: `privacy_erase_subject` deja el token
  como `arco:<push_token_id>` y revocado. Sin esta guarda, quien supiera ese
  identificador podría resucitar la fila y borrar el rastro de la supresión.
* **`endpoint_arn` se conserva sólo si la plataforma no cambia**: el endpoint de
  SNS está atado al token del aparato, no a la persona, así que un cambio de
  dueño no obliga a recrearlo; uno creado para otra plataforma no sirve.
* **Cambiar de dueño deja DOS filas de bitácora**: `push_token_released` en el
  tenant VIEJO y `push_token_claimed` en el nuevo, con sólo `push_token_id` en
  `meta`. La del tenant viejo NO nombra al usuario nuevo (actor de sistema): la
  bitácora de un cliente no puede enterarse de quién es el usuario de otro. Si
  el dueño no cambia —re-registro, rotación— no se escribe nada aquí: la
  auditoría `push_token_register` del router sigue siendo la de siempre.

**Riesgo aceptado por escrito (revisión de F0, 2026-09-27): quien tiene el token,
tiene el aparato.** La función deja reclamar una fila VIVA de otra persona a
cualquiera que presente su token. No se endurece exigiendo `p_site` ni nada
parecido porque no cerraría nada: quien robó el token también tiene un sitio
propio que presentar. El token FCM/APNs es un secreto que sólo conoce la app del
teléfono —el mismo modelo del proveedor, que entrega a quien lo presente—, y
conseguirlo exige el aparato o una fuga del proveedor. El daño posible es que el
dueño legítimo deje de recibir push hasta que su app vuelva a registrarse (lo
hace en cada arranque) y que el atacante mande sus propios avisos a ese teléfono;
ninguna de las dos cosas cruza datos entre tenants, y el traspaso queda en la
bitácora de los dos. Si algún día el token viajara fuera del teléfono (un
tablero, un log), esto deja de valer y hay que atar el traspaso a una prueba de
posesión.

Carrera conocida y aceptada: si DOS personas distintas registran el MISMO token
por primera vez en el mismo instante, la segunda no ve la fila en el `SELECT …
FOR UPDATE` previo y su traspaso no se audita (la fila queda bien). Exige dos
sesiones distintas en un solo teléfono a la vez.

## `role`

Columna nueva y NULLABLE: el rol de quien tiene el aparato AHORA
(`app_role()` = `claims.role`). Las filas anteriores quedan en NULL — no se
inventa un rol que nadie registró.

## Invariantes de este repo

* Idempotente (0002+): `ADD COLUMN IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`,
  `GRANT`/`REVOKE` repetibles. `db/schema.sql` es el esquema FINAL y la 0001 lo
  aplica antes, así que esta migración se encuentra su trabajo hecho.
* DDL sobre tabla PREEXISTENTE (`push_tokens`) ⇒ como usuario de conexión, sin
  `SET ROLE`.
* **El dueño se fija AQUÍ y se COMPRUEBA**, nunca en `db/schema.sql` (la 0001
  aplica ese fichero bajo `SET ROLE takab_migrator`, que no es miembro de
  `takab_ingest`: el `ALTER … OWNER` mataría la migración inicial). Sin dueño
  `takab_ingest` la función correría como el migrador, la RLS FORCE la dejaría
  sin ver la fila ajena y el traspaso seguiría fallando **en silencio** —la app
  calla—. Un despliegue muerto es mejor que eso, así que la migración revienta.
* `GRANT INSERT ON push_tokens TO takab_ingest`: hoy sólo tenía `SELECT, UPDATE`
  (el worker sella `endpoint_arn` y revoca), y el dueño de la función tiene que
  poder crear la fila del primer registro. **Verde en local no es verde en la
  nube**: en una base nueva la 0001 concede `ALL TABLES` y esto no se notaría.

Revision ID: 0071_token_del_aparato
Revises: 0070_escalada_avisa_a_todos
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_token_del_aparato"
down_revision: str | None = "0070_escalada_avisa_a_todos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIRMA = "app_claim_push_token(text,text,uuid)"

# --- 1 · tabla PREEXISTENTE (sin SET ROLE) -----------------------------------------
_COLUMNA = (
    "ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS role text",
    "COMMENT ON COLUMN push_tokens.role IS "
    "'[T-9.05] Rol de quien tiene el aparato AHORA (app_role() al reclamarlo). "
    "NULL = fila anterior a la 0071: no se inventa un rol que nadie registro.'",
    "GRANT INSERT ON push_tokens TO takab_ingest",
)

# --- 2 · la función ---------------------------------------------------------------
# Los mensajes van con `USING MESSAGE` y sin marcadores de formato de `RAISE`, y el
# prefijo de ARCO se mira con `starts_with` y no con un `LIKE` con comodín: el mismo
# cuerpo se copia a `db/schema.sql`, y cuanto menos dependa de cómo interpreta cada
# cliente el signo de porcentaje, menos formas tiene de separarse (T-7.52).
_FUNCION = """
CREATE OR REPLACE FUNCTION app_claim_push_token(p_token text, p_platform text, p_site uuid)
RETURNS SETOF push_tokens
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_tenant uuid := app_tenant_id();
  v_user   uuid := app_user_id();
  v_role   text := nullif(app_role(), '');
  v_prev   push_tokens%ROWTYPE;
  v_row    push_tokens%ROWTYPE;
BEGIN
  IF v_tenant IS NULL OR v_user IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '42501',
      MESSAGE = 'app_claim_push_token: sin identidad de sesion (app.tenant_id / app.user_id)';
  END IF;
  IF starts_with(coalesce(p_token, ''), 'arco:') THEN
    RAISE EXCEPTION USING ERRCODE = '42501',
      MESSAGE = 'app_claim_push_token: una lapida de ARCO no se reclama';
  END IF;
  IF p_site IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM sites s WHERE s.site_id = p_site AND s.tenant_id = v_tenant) THEN
    RAISE EXCEPTION USING ERRCODE = '42501',
      MESSAGE = 'app_claim_push_token: el sitio no pertenece al tenant de la sesion';
  END IF;

  SELECT * INTO v_prev FROM push_tokens t WHERE t.token = p_token FOR UPDATE;

  INSERT INTO push_tokens AS pt (tenant_id, user_sub, role, platform, token, site_id)
  VALUES (v_tenant, v_user, v_role, p_platform, p_token, p_site)
  ON CONFLICT (token) DO UPDATE SET
    tenant_id    = EXCLUDED.tenant_id,
    user_sub     = EXCLUDED.user_sub,
    role         = EXCLUDED.role,
    site_id      = EXCLUDED.site_id,
    platform     = EXCLUDED.platform,
    last_seen_at = now(),
    revoked_at   = NULL,
    endpoint_arn = CASE WHEN pt.platform = EXCLUDED.platform THEN pt.endpoint_arn END
  RETURNING * INTO v_row;

  IF v_prev.push_token_id IS NOT NULL
     AND (v_prev.tenant_id IS DISTINCT FROM v_tenant
          OR v_prev.user_sub IS DISTINCT FROM v_user) THEN
    INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES
      (v_prev.tenant_id, 'system:app_claim_push_token', 'push_token_released',
       'push_token:' || v_row.push_token_id::text,
       jsonb_build_object('push_token_id', v_row.push_token_id)),
      (v_tenant, 'user:' || v_user::text, 'push_token_claimed',
       'push_token:' || v_row.push_token_id::text,
       jsonb_build_object('push_token_id', v_row.push_token_id));
  END IF;

  RETURN NEXT v_row;
END
$fn$
"""

# --- 3 · el dueño, y su comprobación ---------------------------------------------
_DUENO = f"""
DO $mig$
DECLARE
  v_dueno text;
BEGIN
  IF pg_has_role(current_user, 'takab_ingest', 'USAGE') THEN
    ALTER FUNCTION {_FIRMA} OWNER TO takab_ingest;
  END IF;

  SELECT pg_get_userbyid(proowner) INTO v_dueno
    FROM pg_proc WHERE oid = '{_FIRMA}'::regprocedure;
  IF v_dueno IS DISTINCT FROM 'takab_ingest' THEN
    RAISE EXCEPTION USING MESSAGE =
      '0071: app_claim_push_token debe pertenecer a takab_ingest (es SECURITY DEFINER y '
      || 'necesita BYPASSRLS para reclamar la fila de OTRO usuario). Dueno actual: '
      || coalesce(v_dueno, 'ninguno') || '. Falta GRANT takab_ingest TO ' || current_user
      || ' y GRANT CREATE ON SCHEMA public TO takab_ingest (los abre deploy.sh).';
  END IF;
END
$mig$
"""

_PERMISOS = (
    f"REVOKE ALL ON FUNCTION {_FIRMA} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {_FIRMA} TO takab_app",
)

# La vuelta atrás quita la función y la columna. El `GRANT INSERT` NO se revoca a
# propósito: en una base creada desde cero ese privilegio lo dio la 0001 (`ALL
# TABLES`), y revocarlo aquí quitaría algo que existía antes de esta migración.
_DOWN = (
    f"DROP FUNCTION IF EXISTS {_FIRMA}",
    "ALTER TABLE push_tokens DROP COLUMN IF EXISTS role",
)


def _exec(sql: str) -> None:
    """Por el cursor psycopg crudo: el cuerpo lleva `%ROWTYPE` y `:=`, que el
    binding de SQLAlchemy tomaría por marcadores."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    for sentencia in _COLUMNA:
        _exec(sentencia)
    _exec(_FUNCION)
    _exec(_DUENO)
    for sentencia in _PERMISOS:
        _exec(sentencia)


def downgrade() -> None:
    for sentencia in _DOWN:
        _exec(sentencia)
