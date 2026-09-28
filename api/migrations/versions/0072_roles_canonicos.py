"""T-9.20 · D-42 · los roles vivos pasan a los siete canónicos (SOLO DML)

D-42 bajó los roles de 10 a 7. Los identificadores técnicos no cambian y la RLS no
se toca; lo que se hace aquí es que la **configuración viva** deje de nombrar los
tres roles retirados:

* ``push_tokens.role`` — decide a qué teléfono suena un push por rol
  (``notify/orchestrator.py``, círculo del movimiento). Un aparato registrado como
  ``security_guard`` no sonaría con ``roles_with_action('movement_alert')``, que ya
  solo devuelve canónicos.
* ``user_zone_assignments.role`` — decide quién sale en el directorio del inmueble.

Mapeo (copia CONGELADA de ``auth/roles.ALIAS_HEREDADOS``: T-9.81 quitará los alias
del código, y una migración no puede cambiar de significado cuando cambia la app):
``soc_operator → tenant_admin``, ``security_guard → brigadista``,
``building_admin → brigadista``.

## Lo que NO se toca

La HISTORIA: ``audit_log``, ``incident_actions``, dictámenes, reportes de daños y
PDF guardan el rol que se tenía al firmar. Sus rótulos viven en
``auth/roles.ROL_HISTORICO``. Tampoco los grupos de Cognito (siguen hasta T-9.81:
sin ellos, un token viejo daría «role not in groups» y la ventana no actuaría) ni
el alcance por inmueble (lo mueve el script de T-9.21).

## FORCE ROW LEVEL SECURITY — por qué se declara ``app.role``

Las dos tablas llevan ``FORCE ROW LEVEL SECURITY`` y Alembic conecta como su dueño,
así que un ``UPDATE`` sin contexto de app actualiza CERO filas y no se queja (lo
midió la 0050). Las dos tienen una política ``*_admin`` para ``app_is_takab_internal()``
(``uza_admin``, ``pt_admin``); declarar ``app.role = 'takab_superadmin'`` LOCAL a la
transacción la abre, y se devuelve a vacío en cuanto terminan los ``UPDATE``, por
si Alembic corre la migración siguiente en la misma transacción. No se levanta
``FORCE`` en ninguna tabla.

## Invariantes de este repo

* Idempotente (0002+): cada ``UPDATE`` solo toca filas que TODAVÍA nombran un rol
  viejo; la segunda corrida encuentra cero.
* Sin DDL ⇒ ``db/schema.sql`` no cambia (el esquema FINAL no nombra datos). Sin
  ``SET ROLE``: las tablas son PREEXISTENTES.
* ``downgrade`` no hace nada: tras canonizar ya no se sabe qué ``brigadista`` fue
  guardia y cuál administrador de inmueble, e inventarlo sería peor que no volver.

Revision ID: 0072_roles_canonicos
Revises: 0071_token_del_aparato
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0072_roles_canonicos"
down_revision: str | None = "0071_token_del_aparato"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Copia congelada del mapeo de D-42 (ver el docstring).
MAPEO: dict[str, str] = {
    "soc_operator": "tenant_admin",
    "security_guard": "brigadista",
    "building_admin": "brigadista",
}

_TABLAS = ("push_tokens", "user_zone_assignments")


def _updates() -> list[str]:
    out = []
    for tabla in _TABLAS:
        for viejo, nuevo in MAPEO.items():
            out.append(f"UPDATE {tabla} SET role = '{nuevo}' WHERE role = '{viejo}'")
    return out


#: Lo que corre ``upgrade``, en orden. Lo lee también ``tests/test_migration_0072.py``.
CANONIZAR: tuple[str, ...] = (
    "SELECT set_config('app.role', 'takab_superadmin', true)",
    *_updates(),
    "SELECT set_config('app.role', '', true)",
)


def upgrade() -> None:
    for sentencia in CANONIZAR:
        op.execute(sentencia)


def downgrade() -> None:
    # Irreversible a propósito: ver el docstring.
    pass
