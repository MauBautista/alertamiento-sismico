"""Segundo factor para retirar una estación (T-2.36).

Retirar un gabinete lo saca del config sync firmado (``commands/sync.py``) y de los
comandos de actuación (``queries/commands.py``): el edificio deja de estar protegido.
Por eso el retiro exige, además del permiso ``manage_fleet``, un **código del tenant**
que TAKAB entrega fuera de banda y solo el superadmin rota.

Orden de comprobaciones, y el porqué de cada posición:

1. **Confirmación del identificador** (``serial``/``code``) — la hace el router antes
   de llamar aquí. No es secreto (está en pantalla), así que un dedazo no debe quemar
   un intento del segundo factor.
2. **Rate-limit** — antes de tocar el hash: un atacante bloqueado no puede seguir
   sondeando, y el bloqueo aplica también al código correcto (si no, agotar los
   intentos revelaría que el siguiente es el bueno).
3. **¿Hay código configurado?** — si no, 409. **Fail-closed**: la ausencia de
   credencial nunca es un bypass.
4. **¿Coincide?** — vía ``app_verify_retire_code`` (SECURITY DEFINER). El hash nunca
   cruza la frontera de la base; la API pregunta y recibe un booleano.

El hash JAMÁS se registra, ni el código en claro: la bitácora guarda el hecho, no la
credencial.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from takab_api.audit import audit_out_of_band_async
from takab_api.db.session import SessionCtx
from takab_api.routers._common import http_error
from takab_api.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from takab_api.auth.claims import Claims

_DENIED_VERB = "retire_code_denied"

# El contador vive en audit_log (append-only, sin poda por retención): no hace falta
# una tabla de estado nueva y el bloqueo queda auditado por construcción.
_RECENT_DENIALS = text(
    "SELECT count(*) FROM audit_log "
    "WHERE tenant_id = CAST(:tenant_id AS uuid) "
    "  AND verb = :verb "
    "  AND ts > now() - make_interval(secs => :window_s)"
)

_STATE = text("SELECT version, rotated_at FROM app_retire_code_state(CAST(:tenant_id AS uuid))")

_VERIFY = text("SELECT app_verify_retire_code(CAST(:tenant_id AS uuid), :candidate) AS ok")

_UPSERT = text(
    "INSERT INTO tenant_retire_codes (tenant_id, code_hash, rotated_by) "
    "VALUES (CAST(:tenant_id AS uuid), crypt(:code, gen_salt('bf', 12)), "
    "        CAST(:rotated_by AS uuid)) "
    "ON CONFLICT (tenant_id) DO UPDATE "
    "   SET code_hash = EXCLUDED.code_hash, "
    "       rotated_by = EXCLUDED.rotated_by, "
    "       rotated_at = now(), "
    "       version = tenant_retire_codes.version + 1 "
    "RETURNING version, rotated_at"
)


async def retire_code_state(conn: AsyncConnection, tenant_id: str) -> tuple[int, object] | None:
    """``(version, rotated_at)`` del código del tenant, o ``None`` si no hay."""
    row = (await conn.execute(_STATE, {"tenant_id": tenant_id})).first()
    return None if row is None else (row.version, row.rotated_at)


async def rotate_retire_code(
    conn: AsyncConnection, *, tenant_id: str, code: str, rotated_by: str
) -> tuple[int, object]:
    """Fija/rota el código. El hash lo calcula Postgres: nunca viaja por Python."""
    row = (
        await conn.execute(
            _UPSERT, {"tenant_id": tenant_id, "code": code, "rotated_by": rotated_by}
        )
    ).one()
    return row.version, row.rotated_at


def check_confirmation(*, typed: str, expected: str, label: str) -> None:
    """Primer factor: teclear el identificador exacto. 400 si no coincide."""
    if typed.strip() != expected:
        raise http_error(400, f"el {label} tecleado no coincide con el de la estación")


async def require_retire_code(
    conn: AsyncConnection,
    claims: Claims,
    *,
    tenant_id: str,
    code: str,
    obj: str,
    settings: Settings | None = None,
) -> None:
    """Exige el código del tenant. Lanza 429/409/403; no devuelve nada si pasa."""
    s = settings or Settings()

    denials = await conn.scalar(
        _RECENT_DENIALS,
        {"tenant_id": tenant_id, "verb": _DENIED_VERB, "window_s": s.retire_code_window_s},
    )
    if (denials or 0) >= s.retire_code_max_attempts:
        minutes = int(s.retire_code_window_s // 60)
        raise http_error(
            429,
            f"demasiados intentos fallidos: el retiro queda bloqueado {minutes} min "
            "para este cliente",
        )

    if await retire_code_state(conn, tenant_id) is None:
        raise http_error(
            409,
            "este cliente no tiene código de retiro configurado; solicítalo a TAKAB "
            "antes de retirar hardware",
        )

    ok = await conn.scalar(_VERIFY, {"tenant_id": tenant_id, "candidate": code})
    if ok:
        return

    # Fuera de banda: el 403 de abajo hace rollback y se llevaría esta fila.
    await audit_out_of_band_async(
        SessionCtx.from_claims(claims),
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb=_DENIED_VERB,
        obj=obj,
        meta={"remaining": max(0, s.retire_code_max_attempts - (denials or 0) - 1)},
    )
    raise http_error(403, "código de retiro incorrecto")
