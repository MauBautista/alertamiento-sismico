"""Directorio de identidades (T-2.54): proxy acotado del Admin API de Cognito."""

from takab_api.users.directory import (
    ATTR_ROLE,
    ATTR_SITE_SCOPE,
    ATTR_SURFACE,
    ATTR_TENANT,
    ATTR_ZONE,
    CognitoUserDirectory,
    DirectoryError,
    DirectoryUnavailable,
    SimulatedUserDirectory,
    UserDirectory,
    UserRecord,
    build_user_directory,
)

__all__ = [
    "ATTR_ROLE",
    "ATTR_SITE_SCOPE",
    "ATTR_SURFACE",
    "ATTR_TENANT",
    "ATTR_ZONE",
    "CognitoUserDirectory",
    "DirectoryError",
    "DirectoryUnavailable",
    "SimulatedUserDirectory",
    "UserDirectory",
    "UserRecord",
    "build_user_directory",
]
