"""Directorio de identidades — proxy del Admin API de Cognito (T-2.54).

Esta es la superficie que faltaba para que ALGUIEN pueda escribir
``custom:site_scope`` (bloqueante declarado de la Fase B de T-2.45). Es también la
más sensible de la consola después de los actuadores: quien escribe
``custom:tenant_id`` o ``custom:role`` decide qué datos ve una persona, porque la
RLS de PostgreSQL se ancla exactamente en esos dos claims
(``auth/claims.py``, regla de oro 5).

Tres invariantes que el código sostiene, no la documentación:

1. **Nunca hay credenciales.** No se envía ``TemporaryPassword`` (Cognito genera y
   entrega la suya por correo), no se lee ninguna, no se devuelve ninguna.
   ``UserRecord`` no tiene dónde ponerla.
2. **Rol y grupo van juntos, siempre.** ``Claims.from_verified`` rechaza un token
   cuyo ``custom:role`` no esté en ``cognito:groups``. Escribir solo el atributo
   produciría un usuario que no puede iniciar sesión — un fantasma. Cada cambio de
   rol mueve el atributo Y la pertenencia al grupo.
3. **Sin credenciales de AWS resolubles, el proveedor GRITA.** ``SimulatedUserDirectory``
   es un stand-in explícito en memoria (mismo patrón que ``commands/keys.py::
   StaticKeyProvider`` y ``notify/push.py::SimulatedPushProvider``), jamás un
   fallback silencioso que aparente haber dado de alta a alguien.

**Limitación real de Cognito, documentada porque cambia el diseño:**
``ListUsers`` solo filtra por atributos estándar — ``custom:*`` **no es filtrable**
(https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_ListUsers.html).
El acotamiento por tenant es por tanto del lado del servidor TAKAB: se piden páginas
al pool y se descartan las de otros clientes. El cursor que se devuelve al cliente es
el ``PaginationToken`` de Cognito, así que la paginación sigue siendo estable; lo que
NO se puede prometer es que cada página traiga exactamente ``limit`` filas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from takab_api.settings import Settings

logger = logging.getLogger("takab_api.users")

#: Atributos custom que TAKAB gobierna. Son los mismos cinco que declara
#: ``infra/terraform/modules/identity/main.tf`` y que lee ``auth/claims.py``.
ATTR_TENANT = "custom:tenant_id"
ATTR_ROLE = "custom:role"
ATTR_SITE_SCOPE = "custom:site_scope"
ATTR_ZONE = "custom:zone_id"
ATTR_SURFACE = "custom:surface"


class DirectoryError(Exception):
    """Fallo del directorio que el router traduce a 4xx/5xx.

    ``code`` es el código de error de Cognito (``UsernameExistsException``,
    ``UserNotFoundException``…). El directorio simulado usa los MISMOS códigos: si
    no, el mapeo a HTTP solo se ejercitaría contra AWS y en dev todo sería 502.
    """

    def __init__(self, message: str, *, code: str = "") -> None:
        super().__init__(message)
        self.code = code


class DirectoryUnavailable(DirectoryError):
    """No hay directorio utilizable (sin pool configurado, o AWS no responde)."""


@dataclass(frozen=True)
class UserRecord:
    """Usuario del pool. Deliberadamente SIN campo de credencial alguno."""

    username: str
    email: str
    tenant_id: str
    role: str
    #: Valor CRUDO del atributo: ``"*"``, CSV de site_id, o ``""`` (sin declarar).
    site_scope: str
    zone_id: str
    surface: str
    enabled: bool
    #: ``UserStatus`` de Cognito (FORCE_CHANGE_PASSWORD, CONFIRMED, …).
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserDirectory(Protocol):
    """Contrato mínimo del directorio. Ninguna firma acepta ni devuelve una clave."""

    #: Etiqueta para la bitácora y para que la UI diga con qué está hablando.
    backend: str

    def list_users(
        self, *, limit: int, cursor: str | None
    ) -> tuple[list[UserRecord], str | None]: ...

    def get_user(self, username: str) -> UserRecord | None: ...

    def create_user(
        self,
        *,
        email: str,
        tenant_id: str,
        role: str,
        site_scope: str,
        zone_id: str,
        surface: str,
    ) -> UserRecord: ...

    def update_user(
        self, username: str, *, attributes: dict[str, str], role: str | None
    ) -> UserRecord: ...

    def set_enabled(self, username: str, enabled: bool) -> UserRecord: ...

    def reset_password(self, username: str) -> None: ...

    def resend_invitation(self, username: str) -> None: ...

    def delete_user(self, username: str) -> None: ...


def _record_from(
    *,
    username: str,
    attributes: dict[str, str],
    enabled: bool,
    status: str,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> UserRecord:
    return UserRecord(
        username=username,
        email=attributes.get("email", ""),
        tenant_id=attributes.get(ATTR_TENANT, ""),
        role=attributes.get(ATTR_ROLE, ""),
        site_scope=attributes.get(ATTR_SITE_SCOPE, ""),
        zone_id=attributes.get(ATTR_ZONE, ""),
        surface=attributes.get(ATTR_SURFACE, ""),
        enabled=enabled,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
    )


class SimulatedUserDirectory:
    """Stand-in en memoria para dev/tests SIN AWS. Registra y GRITA.

    Existe para que la consola sea desarrollable y testeable sin un pool real, no
    para que producción "funcione igual". Cada escritura deja un WARNING que dice
    exactamente que ninguna identidad real cambió: marcar un alta como hecha en
    silencio sería mentir sobre quién tiene acceso al sistema.
    """

    backend = "simulated"

    def __init__(self, seed: list[UserRecord] | None = None) -> None:
        self._users: dict[str, UserRecord] = {u.username: u for u in (seed or [])}
        logger.warning(
            "TAKAB_API_COGNITO_USER_POOL_ID vacío: directorio de usuarios SIMULADO — "
            "ningún alta, cambio de rol o baja llega a Cognito. En la nube esto es un fallo."
        )

    # -- lectura ---------------------------------------------------------------

    def list_users(self, *, limit: int, cursor: str | None) -> tuple[list[UserRecord], str | None]:
        ordered = sorted(self._users.values(), key=lambda u: (u.email, u.username))
        start = 0
        if cursor is not None:
            start = next(
                (i + 1 for i, u in enumerate(ordered) if u.username == cursor), len(ordered)
            )
        page = ordered[start : start + limit]
        nxt = page[-1].username if len(ordered) > start + limit and page else None
        return page, nxt

    def get_user(self, username: str) -> UserRecord | None:
        return self._users.get(username)

    # -- escritura -------------------------------------------------------------

    def create_user(
        self,
        *,
        email: str,
        tenant_id: str,
        role: str,
        site_scope: str,
        zone_id: str,
        surface: str,
    ) -> UserRecord:
        if any(u.email.lower() == email.lower() for u in self._users.values()):
            raise DirectoryError(
                f"ya existe un usuario con el correo {email}", code="UsernameExistsException"
            )
        record = UserRecord(
            username=f"sim-{len(self._users) + 1:04d}",
            email=email,
            tenant_id=tenant_id,
            role=role,
            site_scope=site_scope,
            zone_id=zone_id,
            surface=surface,
            enabled=True,
            status="FORCE_CHANGE_PASSWORD",
        )
        self._users[record.username] = record
        logger.warning("alta SIMULADA de %s: ninguna identidad real se creó", email)
        return record

    def update_user(
        self, username: str, *, attributes: dict[str, str], role: str | None
    ) -> UserRecord:
        current = self._require(username)
        merged = {
            ATTR_TENANT: current.tenant_id,
            ATTR_ROLE: role if role is not None else current.role,
            ATTR_SITE_SCOPE: current.site_scope,
            ATTR_ZONE: current.zone_id,
            ATTR_SURFACE: current.surface,
            "email": current.email,
            **attributes,
        }
        updated = _record_from(
            username=username,
            attributes=merged,
            enabled=current.enabled,
            status=current.status,
            created_at=current.created_at,
        )
        self._users[username] = updated
        logger.warning("cambio SIMULADO sobre %s: Cognito no se enteró", username)
        return updated

    def set_enabled(self, username: str, enabled: bool) -> UserRecord:
        updated = replace(self._require(username), enabled=enabled)
        self._users[username] = updated
        logger.warning("habilitación SIMULADA de %s → %s", username, enabled)
        return updated

    def reset_password(self, username: str) -> None:
        self._require(username)
        logger.warning("reset SIMULADO de %s: no se envió correo alguno", username)

    def resend_invitation(self, username: str) -> None:
        self._require(username)
        logger.warning("reenvío SIMULADO de invitación a %s: no salió correo", username)

    def delete_user(self, username: str) -> None:
        self._require(username)
        del self._users[username]
        logger.warning("baja SIMULADA de %s: la identidad real sigue viva", username)

    def _require(self, username: str) -> UserRecord:
        user = self._users.get(username)
        if user is None:
            raise DirectoryError(f"usuario desconocido: {username}", code="UserNotFoundException")
        return user


class CognitoUserDirectory:
    """Admin API de Cognito, acotado a las nueve operaciones que la consola usa."""

    backend = "cognito"

    def __init__(self, *, user_pool_id: str, region: str, client: Any | None = None) -> None:
        self._pool = user_pool_id
        self._region = region
        self._client = client

    def _api(self) -> Any:
        if self._client is None:
            import boto3  # perezoso: los tests inyectan el cliente y jamás tocan AWS

            self._client = boto3.client("cognito-idp", region_name=self._region)
        return self._client

    # -- lectura ---------------------------------------------------------------

    def list_users(self, *, limit: int, cursor: str | None) -> tuple[list[UserRecord], str | None]:
        kwargs: dict[str, Any] = {"UserPoolId": self._pool, "Limit": limit}
        if cursor:
            kwargs["PaginationToken"] = cursor
        payload = self._call("list_users", **kwargs)
        users = [self._from_list_entry(entry) for entry in payload.get("Users", [])]
        return users, payload.get("PaginationToken")

    def get_user(self, username: str) -> UserRecord | None:
        try:
            payload = self._call("admin_get_user", UserPoolId=self._pool, Username=username)
        except DirectoryError as exc:
            if getattr(exc, "code", "") == "UserNotFoundException":
                return None
            raise
        return _record_from(
            username=payload["Username"],
            attributes=_attrs(payload.get("UserAttributes", [])),
            enabled=bool(payload.get("Enabled", True)),
            status=payload.get("UserStatus", ""),
            created_at=payload.get("UserCreateDate"),
            updated_at=payload.get("UserLastModifiedDate"),
        )

    # -- escritura -------------------------------------------------------------

    def create_user(
        self,
        *,
        email: str,
        tenant_id: str,
        role: str,
        site_scope: str,
        zone_id: str,
        surface: str,
    ) -> UserRecord:
        """Alta con invitación por correo. **No** se envía ``TemporaryPassword``:
        la clave la genera y entrega Cognito, y así no existe en ningún log nuestro."""
        attributes = [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": ATTR_TENANT, "Value": tenant_id},
            {"Name": ATTR_ROLE, "Value": role},
            {"Name": ATTR_SITE_SCOPE, "Value": site_scope},
            {"Name": ATTR_ZONE, "Value": zone_id},
            {"Name": ATTR_SURFACE, "Value": surface},
        ]
        payload = self._call(
            "admin_create_user",
            UserPoolId=self._pool,
            Username=email,
            UserAttributes=attributes,
            DesiredDeliveryMediums=["EMAIL"],
        )
        entry = payload["User"]
        username = entry["Username"]
        # El grupo es lo que hace VÁLIDO el token: `Claims.from_verified` exige
        # `custom:role ∈ cognito:groups`. Sin esto el alta produce un usuario que
        # se autentica y recibe 401 en cada request.
        self._call(
            "admin_add_user_to_group",
            UserPoolId=self._pool,
            Username=username,
            GroupName=role,
        )
        return self._from_list_entry(entry)

    def update_user(
        self, username: str, *, attributes: dict[str, str], role: str | None
    ) -> UserRecord:
        if attributes:
            self._call(
                "admin_update_user_attributes",
                UserPoolId=self._pool,
                Username=username,
                UserAttributes=[{"Name": k, "Value": v} for k, v in sorted(attributes.items())],
            )
        if role is not None:
            # Salir del grupo viejo ANTES de entrar al nuevo dejaría una ventana sin
            # ningún grupo; entrar primero deja una con dos, y `custom:role` decide
            # cuál se usa. Se prefiere la ventana con dos: nunca deja a nadie fuera.
            self._call(
                "admin_add_user_to_group",
                UserPoolId=self._pool,
                Username=username,
                GroupName=role,
            )
            for group in self._groups_of(username):
                if group != role:
                    self._call(
                        "admin_remove_user_from_group",
                        UserPoolId=self._pool,
                        Username=username,
                        GroupName=group,
                    )
        return self._require(username)

    def set_enabled(self, username: str, enabled: bool) -> UserRecord:
        self._call(
            "admin_enable_user" if enabled else "admin_disable_user",
            UserPoolId=self._pool,
            Username=username,
        )
        return self._require(username)

    def reset_password(self, username: str) -> None:
        """Dispara el flujo de recuperación de Cognito. NO fija ninguna contraseña:
        ``admin_set_user_password`` obligaría a inventar (y transportar) un secreto."""
        self._call("admin_reset_user_password", UserPoolId=self._pool, Username=username)

    def resend_invitation(self, username: str) -> None:
        self._call(
            "admin_create_user",
            UserPoolId=self._pool,
            Username=username,
            MessageAction="RESEND",
            DesiredDeliveryMediums=["EMAIL"],
        )

    def delete_user(self, username: str) -> None:
        self._call("admin_delete_user", UserPoolId=self._pool, Username=username)

    # -- interno ---------------------------------------------------------------

    def _groups_of(self, username: str) -> list[str]:
        payload = self._call("admin_list_groups_for_user", UserPoolId=self._pool, Username=username)
        return [g["GroupName"] for g in payload.get("Groups", [])]

    def _require(self, username: str) -> UserRecord:
        user = self.get_user(username)
        if user is None:
            raise DirectoryError(f"usuario desconocido: {username}", code="UserNotFoundException")
        return user

    def _from_list_entry(self, entry: dict) -> UserRecord:
        return _record_from(
            username=entry["Username"],
            attributes=_attrs(entry.get("Attributes", entry.get("UserAttributes", []))),
            enabled=bool(entry.get("Enabled", True)),
            status=entry.get("UserStatus", ""),
            created_at=entry.get("UserCreateDate"),
            updated_at=entry.get("UserLastModifiedDate"),
        )

    def _call(self, operation: str, **kwargs: Any) -> dict:
        try:
            return getattr(self._api(), operation)(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            raise DirectoryError(f"{operation}: {code or exc}", code=code) from exc
        except BotoCoreError as exc:
            raise DirectoryUnavailable(f"{operation}: {exc}") from exc


def build_user_directory(
    settings: Settings, *, client: Any | None = None
) -> CognitoUserDirectory | SimulatedUserDirectory:
    """Cognito real si hay pool configurado; si no, el simulado ruidoso."""
    if settings.cognito_user_pool_id:
        return CognitoUserDirectory(
            user_pool_id=settings.cognito_user_pool_id,
            region=settings.aws_region,
            client=client,
        )
    return SimulatedUserDirectory()


def _attrs(items: list[dict]) -> dict[str, str]:
    return {a["Name"]: a.get("Value", "") for a in items}
