"""T-2.81 · Política de UPDATE que deja al job de retención anular `geom`.

QUÉ AÑADE, Y POR QUÉ ES TAN POCO
────────────────────────────────
Una sola política de RLS sobre ``life_checkins``. Nada más: ni tablas, ni
funciones, ni privilegios nuevos.

La T-2.80 dejó ``lc_arco_geom``, que exige ``user_id = app_user_id()``: sirve
para que el TITULAR anule la geometría de sus propios check-ins, y es justo lo
que un job de retención no puede usar, porque un job no actúa en nombre de
ninguna persona. Sin esta política el job cuenta las filas que caducaron y
después actualiza cero — que es exactamente cómo lo descubrió su test: la
comprobación "el conteo previo tiene que cuadrar con ROW_COUNT" se puso roja.

POR QUÉ ESTO NO ABRE UN HUECO EN LA EVIDENCIA
─────────────────────────────────────────────
La política dice QUIÉN puede pedir el UPDATE. No dice QUÉ puede hacer, y lo que
se puede hacer no cambia ni un ápice:

* el trigger ``life_checkin_arco_guard()`` sigue admitiendo **una sola**
  mutación —``geom`` deja de ser NULL y pasa a NULL, con el resto de la fila
  idéntica comparada vía ``to_jsonb``— y cubre también al DUEÑO de la tabla;
* ``takab_app`` sigue teniendo ``UPDATE`` **solo sobre la columna ``geom``**;
* el ``DELETE`` lo sigue vetando ``forbid_update_delete()``, sin excepción.

Así que la superficie que esta migración añade es, exactamente: "una sesión
INTERNA puede anular la geometría de los check-ins DE SU TENANT". El confinamiento
por tenant va dentro de la política a propósito y no en el ``WHERE`` del job: así
lo impone la base, no la disciplina de quien escribió el job (regla de oro 5).

El comentario de la T-2.80 que decía "la ÚNICA política de UPDATE de
`life_checkins`" queda superado por esta migración; ``db/schema.sql`` se corrige
en el mismo cambio para que no queden las dos versiones de la verdad.

INVARIANTES DEL PROYECTO
────────────────────────
No se crea ningún objeto nuevo ⇒ **no hay ``SET ROLE takab_migrator``** en toda
la migración. ``life_checkins`` es una tabla PREEXISTENTE y las políticas de RLS
van como usuario de conexión, con ``RESET ROLE`` explícito por delante (mismo
criterio que el bloque final de la 0034). Idempotente: ``DROP POLICY IF EXISTS``
antes del ``CREATE POLICY``, así que aplicarla dos veces —o aplicarla sobre una
base nueva que ya la trae de ``db/schema.sql``— no falla.

Revision ID: 0035_retention_geom_policy
Revises: 0034_privacy_erasure
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0035_retention_geom_policy"
down_revision: str | None = "0034_privacy_erasure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_POLITICA = """
RESET ROLE;

-- [T-2.81] La retención de PII anula la geometría de los check-ins caducados.
-- Convive con `lc_arco_geom` (T-2.80), que es el mismo acto pedido por el
-- titular: una es a petición, la otra por reloj. Ninguna de las dos puede hacer
-- nada más que anular `geom`, porque quien lo impide es el trigger, no la
-- política.
DROP POLICY IF EXISTS lc_retention_geom ON life_checkins;
CREATE POLICY lc_retention_geom ON life_checkins FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_is_takab_internal())
  WITH CHECK (tenant_id = app_tenant_id() AND app_is_takab_internal());
"""


def upgrade() -> None:
    op.execute(_POLITICA)


def downgrade() -> None:
    # Quitarla solo deja al job de retención sin poder anular geometrías: no
    # revierte ningún dato ni afloja ninguna protección. Las filas ya anonimizadas
    # se quedan como están, que es lo correcto — volver a poner una ubicación GPS
    # que ya caducó no es "revertir", es reintroducir dato personal.
    op.execute("RESET ROLE; DROP POLICY IF EXISTS lc_retention_geom ON life_checkins;")
