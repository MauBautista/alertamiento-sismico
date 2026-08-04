"""Gestión de usuarios (T-2.54) — proxy acotado del Admin API de Cognito.

Superficie de seguridad NUEVA, tratada como tal:

- **Gate propio** ``manage_users`` (superadmin + tenant_admin). ``takab_support``
  NO la tiene: repartir identidades no es leer la plataforma.
- **Acotada al tenant.** Todo usuario que no pertenezca al tenant en sesión es un
  **404**, no un 403: un 403 confirmaría que la cuenta existe (mismo criterio que
  T-2.45 para los sitios fuera de alcance).
- **Sin escalada.** Un rol de tenant no puede otorgar ``takab_superadmin`` ni
  ``takab_support`` (``schemas/users.PLATFORM_ROLES``), ni escribir en otro tenant,
  ni cambiar el ``tenant_id`` de nadie — ese campo no es editable en absoluto.
- **Auditoría OBLIGATORIA en cada escritura**, con el diff de lo que cambió. La RLS
  de PostgreSQL se ancla en ``custom:tenant_id``/``custom:role`` (regla de oro 5):
  quien los escribe reparte acceso a datos, y eso no puede pasar sin registro.
- **Jamás devuelve credenciales.** No se envía ni se pide contraseña; el reset y la
  invitación los entrega Cognito por correo. Ningún modelo tiene dónde ponerla.

``custom:site_scope`` se escribe aquí — es el bloqueante real de la **Fase B de
T-2.45**. Con esta pantalla desplegada y los usuarios ya aprovisionados,
``TAKAB_API_CONSOLE_SCOPE_ENFORCED=true`` deja de dejar sin datos a los operadores
acotados. **No se activa en esta tarea**: encenderlo antes de que cada usuario web
tenga su claim escrito es exactamente el escenario que el cutover en dos fases
existe para evitar.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

import anyio
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.routers._common import (
    INTERNAL_ROLES,
    clamp_limit,
    http_error,
    resolve_write_tenant,
)
from takab_api.schemas.users import (
    PLATFORM_ROLES,
    UserActionOut,
    UserCreate,
    UserOut,
    UserPage,
    UserUpdate,
)
from takab_api.settings import Settings
from takab_api.users import (
    ATTR_SITE_SCOPE,
    ATTR_SURFACE,
    ATTR_ZONE,
    DirectoryError,
    DirectoryUnavailable,
    UserDirectory,
    UserRecord,
    build_user_directory,
)

log = logging.getLogger("takab_api.users")

_require_manage_users = require_roles(*roles_with_action("manage_users"))

router = APIRouter(dependencies=[Depends(require_web_surface)])

#: Sitios del tenant que existen de verdad. Sin esta comprobación, un
#: ``custom:site_scope`` con un UUID inventado (o de OTRO cliente) se guardaría
#: tal cual y el usuario acabaría viendo cero sitios sin que nadie supiera por qué.
_SITES_OF_TENANT = text(
    "SELECT site_id::text FROM sites "
    "WHERE site_id = ANY(CAST(:ids AS uuid[])) AND tenant_id = CAST(:t AS uuid)"
)


def get_user_directory() -> UserDirectory:
    """Directorio real o simulado según settings; los tests lo sustituyen."""
    return build_user_directory(Settings())


async def _off_thread(fn: Any, /, **kwargs: Any) -> Any:
    """boto3 es síncrono: sacarlo del event loop evita bloquear toda la API."""
    return await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))


def _out(record: UserRecord) -> UserOut:
    return UserOut(**record.__dict__)


def _require_assignable(claims: Claims, role: str | None) -> None:
    """Un rol de tenant no reparte roles de PLATAFORMA. Sin esto, un ``tenant_admin``
    se crearía un ``takab_superadmin`` y saldría de su propio aislamiento."""
    if role is None or claims.role in INTERNAL_ROLES:
        return
    if role in PLATFORM_ROLES:
        raise http_error(403, "solo TAKAB otorga roles de plataforma")


async def _validate_scope(conn: AsyncConnection, *, tenant_id: str, site_scope: str) -> None:
    """Todo site_id del alcance debe existir Y ser de ese cliente."""
    if site_scope in ("", "*"):
        return
    wanted = site_scope.split(",")
    rows = (await conn.execute(_SITES_OF_TENANT, {"ids": wanted, "t": tenant_id})).scalars().all()
    missing = sorted(set(wanted) - set(rows))
    if missing:
        raise http_error(400, f"site_scope: estaciones inexistentes o de otro cliente: {missing}")


async def _visible_user(directory: UserDirectory, claims: Claims, username: str) -> UserRecord:
    """El usuario, o 404. Ajeno al tenant ⇒ 404 (no se confirma que exista)."""
    record = await _off_thread(directory.get_user, username=username)
    if record is None:
        raise http_error(404, "usuario no encontrado")
    if claims.role not in INTERNAL_ROLES and record.tenant_id != claims.tenant_id:
        raise http_error(404, "usuario no encontrado")
    return record


def _directory_error(exc: DirectoryError) -> Exception:
    if isinstance(exc, DirectoryUnavailable):
        return http_error(503, f"directorio de identidades no disponible: {exc}")
    code = getattr(exc, "code", "")
    if code in ("UsernameExistsException", "AliasExistsException"):
        return http_error(409, "ya existe un usuario con ese correo")
    if code == "UserNotFoundException":
        return http_error(404, "usuario no encontrado")
    if code in ("InvalidParameterException", "InvalidPasswordException"):
        return http_error(400, str(exc))
    if code in ("NotAuthorizedException", "AccessDeniedException"):
        # Credenciales de la API sin permiso sobre el pool: es un fallo NUESTRO de
        # despliegue, no del operador. 502 lo dice sin culpar a quien pulsó.
        return http_error(502, "la API no tiene permiso sobre el pool de identidades")
    return http_error(502, f"el directorio de identidades falló: {exc}")


@router.get("/users", response_model=UserPage)
async def list_users(
    claims: Claims = Depends(_require_manage_users),
    directory: UserDirectory = Depends(get_user_directory),
    limit: int | None = Query(None),
    cursor: str | None = Query(None),
) -> UserPage:
    """Usuarios del cliente en sesión (o de todos, para roles internos TAKAB).

    ``ListUsers`` de Cognito **no filtra por atributos custom**, así que el
    acotamiento por tenant se hace aquí sobre la página que devuelve el pool. El
    cursor sigue siendo el ``PaginationToken`` de Cognito (paginación estable); lo
    que no se puede prometer es que cada página traiga exactamente ``limit`` filas.
    Se documenta en vez de simularse: mentir sobre el tamaño de página obligaría a
    barrer el pool entero en cada request.
    """
    size = clamp_limit(limit)
    try:
        records, next_cursor = await _off_thread(directory.list_users, limit=size, cursor=cursor)
    except DirectoryError as exc:
        raise _directory_error(exc) from exc
    if claims.role not in INTERNAL_ROLES:
        records = [r for r in records if r.tenant_id == claims.tenant_id]
    return UserPage(
        items=[_out(r) for r in records],
        next_cursor=next_cursor,
        backend=directory.backend,
    )


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    claims: Claims = Depends(_require_manage_users),
    conn: AsyncConnection = Depends(get_session),
    directory: UserDirectory = Depends(get_user_directory),
) -> UserOut:
    """Da de alta una identidad e invita por correo. Nunca devuelve credenciales."""
    # Misma resolución que cualquier otra escritura con tenancy (`_common`): un rol
    # de tenant escribe SIEMPRE en el suyo (403 si el cuerpo pide otro) y un rol
    # interno debe nombrar el destino explícitamente, que además se comprueba que
    # exista (404). Sin esa comprobación se podría crear una identidad apuntando a un
    # `custom:tenant_id` fantasma: se autenticaría y no vería absolutamente nada,
    # porque la RLS no encontraría filas de ese tenant.
    tenant_id = await resolve_write_tenant(conn, claims, body.tenant_id)
    _require_assignable(claims, body.role)
    await _validate_scope(conn, tenant_id=tenant_id, site_scope=body.site_scope)
    try:
        record = await _off_thread(
            directory.create_user,
            email=body.email,
            tenant_id=tenant_id,
            role=body.role,
            site_scope=body.site_scope,
            zone_id=body.zone_id,
            surface=body.surface,
        )
    except DirectoryError as exc:
        raise _directory_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="user_create",
        obj=f"user:{record.username}",
        meta={
            "email": record.email,
            "role": record.role,
            "site_scope": record.site_scope,
            "surface": record.surface,
            "backend": directory.backend,
        },
    )
    return _out(record)


@router.patch("/users/{username}", response_model=UserOut)
async def update_user(
    username: str,
    body: UserUpdate,
    claims: Claims = Depends(_require_manage_users),
    conn: AsyncConnection = Depends(get_session),
    directory: UserDirectory = Depends(get_user_directory),
) -> UserOut:
    """Edita rol, alcance, zona, superficie y estado. ``tenant_id`` NO es editable.

    Mover a alguien de cliente re-tenantiza su rastro de auditoría, que es evidencia
    inmutable (regla de oro 11) — el camino honesto es dar de baja allá y de alta acá.
    """
    current = await _visible_user(directory, claims, username)
    _require_assignable(claims, body.role)
    if body.site_scope is not None:
        await _validate_scope(conn, tenant_id=current.tenant_id, site_scope=body.site_scope)

    attributes: dict[str, str] = {}
    if body.site_scope is not None:
        attributes[ATTR_SITE_SCOPE] = body.site_scope
    if body.zone_id is not None:
        attributes[ATTR_ZONE] = body.zone_id
    if body.surface is not None:
        attributes[ATTR_SURFACE] = body.surface

    try:
        record = current
        if attributes or body.role is not None:
            record = await _off_thread(
                directory.update_user,
                username=username,
                attributes=attributes,
                role=body.role,
            )
        if body.enabled is not None and body.enabled != current.enabled:
            record = await _off_thread(
                directory.set_enabled, username=username, enabled=body.enabled
            )
    except DirectoryError as exc:
        raise _directory_error(exc) from exc

    # Diff explícito: el valor ANTERIOR y el nuevo de cada campo tocado. El estado
    # final ya se puede leer del pool; lo que solo existe si se registra es qué
    # cambió, cuándo y quién lo cambió.
    changes = {
        field: {"from": getattr(current, field), "to": getattr(record, field)}
        for field in ("role", "site_scope", "zone_id", "surface", "enabled")
        if getattr(current, field) != getattr(record, field)
    }
    await audit_async(
        conn,
        tenant_id=current.tenant_id,
        actor=f"user:{claims.sub}",
        verb="user_update",
        obj=f"user:{username}",
        meta={"changed": sorted(changes), "diff": changes, "backend": directory.backend},
    )
    return _out(record)


@router.post("/users/{username}/reset-password", response_model=UserActionOut)
async def reset_password(
    username: str,
    claims: Claims = Depends(_require_manage_users),
    conn: AsyncConnection = Depends(get_session),
    directory: UserDirectory = Depends(get_user_directory),
) -> UserActionOut:
    """Dispara el flujo de recuperación de Cognito. NO fija ni devuelve una clave."""
    current = await _visible_user(directory, claims, username)
    try:
        await _off_thread(directory.reset_password, username=username)
    except DirectoryError as exc:
        raise _directory_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=current.tenant_id,
        actor=f"user:{claims.sub}",
        verb="user_password_reset",
        obj=f"user:{username}",
        meta={"email": current.email, "backend": directory.backend},
    )
    return UserActionOut(
        username=username,
        action="password_reset",
        detail=f"Cognito envió el código de recuperación a {current.email}.",
    )


@router.post("/users/{username}/resend-invitation", response_model=UserActionOut)
async def resend_invitation(
    username: str,
    claims: Claims = Depends(_require_manage_users),
    conn: AsyncConnection = Depends(get_session),
    directory: UserDirectory = Depends(get_user_directory),
) -> UserActionOut:
    """Reenvía la invitación inicial (usuario que nunca entró)."""
    current = await _visible_user(directory, claims, username)
    try:
        await _off_thread(directory.resend_invitation, username=username)
    except DirectoryError as exc:
        raise _directory_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=current.tenant_id,
        actor=f"user:{claims.sub}",
        verb="user_invitation_resent",
        obj=f"user:{username}",
        meta={"email": current.email, "backend": directory.backend},
    )
    return UserActionOut(
        username=username,
        action="invitation_resent",
        detail=f"Invitación reenviada a {current.email} con una contraseña temporal nueva.",
    )


@router.delete("/users/{username}", status_code=204)
async def delete_user(
    username: str,
    claims: Claims = Depends(_require_manage_users),
    conn: AsyncConnection = Depends(get_session),
    directory: UserDirectory = Depends(get_user_directory),
) -> None:
    """Baja definitiva de la identidad. Su rastro en ``audit_log`` NO se toca.

    La bitácora referencia al actor por ``sub``, no por FK: borrar la cuenta no
    borra lo que hizo (regla de oro 11). Un ``PATCH {"enabled": false}`` es la
    alternativa reversible y es la que la consola ofrece primero.
    """
    current = await _visible_user(directory, claims, username)
    if current.tenant_id == claims.tenant_id and current.username == claims.sub:
        raise http_error(409, "no puedes darte de baja a ti mismo")
    try:
        await _off_thread(directory.delete_user, username=username)
    except DirectoryError as exc:
        raise _directory_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=current.tenant_id,
        actor=f"user:{claims.sub}",
        verb="user_delete",
        obj=f"user:{username}",
        meta={"email": current.email, "role": current.role, "backend": directory.backend},
    )
