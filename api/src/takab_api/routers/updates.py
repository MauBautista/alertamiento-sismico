"""Actualización remota de un gabinete (T-2.70): activar una release, o volver.

**Esto NO transporta código.** El artefacto viaja por `deploy/edge/deploy.sh` y
queda INERTE en `/opt/takab/releases/<id>/` con su propio venv, verificado y sin
que nadie lo apunte. Lo que estos endpoints ordenan es **estrenarlo** — que es
justo la mitad que la nube necesita gobernar para hacer un canary: desplegar a
veinte gabinetes y activar de uno en uno son dos cosas distintas, y la segunda es
la que decide si una regresión es un incidente o veinte.

Va por `issue_signed_command` como todo lo que comanda un gabinete (regla de
oro 8: HMAC por gateway + nonce UNIQUE + TTL + ack + rate-limit + auditoría), y
**con MFA**, por el mismo criterio que el resto de la superficie sensible.

**El ack dice «orden aceptada», no «funcionó», y eso es deliberado.** Activar
reinicia `takab-edge`, o sea el proceso que recibió el comando: un ack posterior
al reinicio no se publicaría nunca. Así que el gabinete acusa antes de lanzar y
**el resultado viaja por el latido** (`fw_running`, T-2.69) — la única señal que
no miente sobre qué código cargó el proceso, porque el disco cambia con el
`rsync` y la memoria sólo con el reinicio.

**Quién puede:** `deploy_firmware`, SOLO `takab_superadmin` (RBAC §5). El código
es de TAKAB y una release mala deja un edificio sin sirena, sin cierre de gas y
sin retenedores; un `tenant_admin` no tiene el artefacto ni con qué juzgarlo.

**Y el permiso no es lo único que gobierna la actuación física.** En un gabinete
cuyo dueño de pines siga dentro de `takab-edge`, activar cicla `GAS_VALVE` y
`DOOR_RETAINER`: ahí el propio gabinete exige ventana declarada y se niega sin
ella. El rol abre la puerta; el edificio conserva la última palabra.
"""

from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.auth.mfa import require_mfa
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher
from takab_api.commands.service import issue_signed_command
from takab_api.queries import commands as q
from takab_api.routers._common import http_error
from takab_api.routers.commands import get_key_provider, get_publisher
from takab_api.settings import Settings

DEPLOY_ROLES: tuple[str, ...] = roles_with_action("deploy_firmware")

#: Misma disciplina que el resto de la superficie sensible: `require_mfa` rechaza
#: todo token que no venga de un pool con `mfa_configuration = "ON"`.
_require_deploy = require_roles(*DEPLOY_ROLES, inner=require_mfa(get_claims))

router = APIRouter(tags=["updates"])

#: Forma de un id de release, la misma que valida el gabinete. Se comprueba en
#: los DOS lados a propósito: aquí para devolver un 422 que el operador entiende,
#: y allí porque el edge no puede fiarse de que quien firma haya validado.
_RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class ActivateUpdateIn(BaseModel):
    """Orden de estrenar una release YA desplegada en ese gabinete."""

    model_config = ConfigDict(extra="forbid")

    release_id: Annotated[str, Field(min_length=1, max_length=128)]
    #: Declara que el edificio está avisado. Sólo cambia algo en gabinetes cuyo
    #: dueño de pines siga dentro de `takab-edge`: allí activar cicla la válvula
    #: de gas y los retenedores, y sin esta bandera el gabinete se niega. En un
    #: gabinete D3 (`TAKAB_EDGE_GPIO_OWNER=gpio`) la activación no mueve un pin y
    #: la bandera es inocua.
    ventana_de_mantenimiento: bool = False


class RollbackUpdateIn(BaseModel):
    """Orden de volver a la release anterior.

    Existe aunque el gabinete revierta SOLO ante un remojo fallido: el fallo que
    el remojo no puede ver es el que se descubre media hora después desde el SOC
    —latencias raras, un sensor que dejó de reportar—, y ahí la orden tiene que
    poder venir de fuera.
    """

    model_config = ConfigDict(extra="forbid")

    #: Queda escrito en el veredicto del gabinete y en el `audit_log`. Obligatorio
    #: por el mismo criterio que el motivo de una ventana de mantenimiento: una
    #: reversión sin razón registrada es una decisión que nadie puede revisar.
    motivo: Annotated[str, Field(min_length=3, max_length=280)]


class UpdateCommandOut(BaseModel):
    """Lo que se pudo prometer: la orden salió firmada y el gabinete la acusará.

    NO lleva un `success` de la actualización, y esa ausencia es el punto: aquí
    nadie sabe todavía si la release nueva levanta. Eso se mira en la flota
    (`fw_running` vs `fw_version`, T-2.69).
    """

    command_id: UUID
    site_id: UUID
    action: str
    release_id: str | None = None


async def _sitio_visible(site_id: UUID, claims: Claims, conn: AsyncConnection) -> str:
    """Tenant del sitio, o 4xx. Mismo orden que `routers/commands.py`: primero el
    ALCANCE del portador (403) y luego la existencia bajo RLS (404), donde «no
    existe» y «no es tuyo» se responden IGUAL a propósito."""
    scope = scope_filter(claims)
    if scope is not None and str(site_id) not in scope:
        raise http_error(403, "sitio fuera del alcance del usuario")
    site = (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first()
    if site is None:
        raise http_error(404, "sitio no encontrado")
    return str(site.tenant_id)


@router.post("/sites/{site_id}/update", response_model=UpdateCommandOut, status_code=202)
async def activate_release(
    site_id: UUID,
    body: ActivateUpdateIn,
    claims: Claims = Depends(_require_deploy),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> UpdateCommandOut:
    """Ordena a UN gabinete estrenar una release ya desplegada y verificada.

    **202 y no 201**: lo aceptado es la orden, no el resultado. El gabinete
    repunta su symlink, reinicia al cliente y mide salud sostenida durante el
    remojo; si falla, vuelve solo. Nada de eso cabe en la respuesta de esta
    llamada, y fingir que sí sería el defecto que `fw_running` existe para
    cerrar: un despliegue que se declara bueno porque alguien lo ordenó.
    """
    if not _RELEASE_ID.fullmatch(body.release_id):
        raise http_error(422, "release_id inválido")
    tenant_id = await _sitio_visible(site_id, claims, conn)
    row = await issue_signed_command(
        conn,
        settings=Settings(),
        publisher=publisher,
        keys=keys,
        claims=claims,
        site_id=site_id,
        tenant_id=tenant_id,
        channel="system",
        action="update_activate",
        event_id=None,
        payload_extra={
            "release_id": body.release_id,
            "ventana_de_mantenimiento": body.ventana_de_mantenimiento,
        },
        audit_meta={
            "release_id": body.release_id,
            "ventana_de_mantenimiento": body.ventana_de_mantenimiento,
        },
    )
    return UpdateCommandOut(
        command_id=row["command_id"],
        site_id=site_id,
        action="update_activate",
        release_id=body.release_id,
    )


@router.post("/sites/{site_id}/update/rollback", response_model=UpdateCommandOut, status_code=202)
async def rollback_release(
    site_id: UUID,
    body: RollbackUpdateIn,
    claims: Claims = Depends(_require_deploy),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> UpdateCommandOut:
    """Ordena a UN gabinete volver a su release anterior.

    No se pasa a qué versión volver: la sabe el gabinete, y sólo él. La nube
    podría equivocarse de id —o nombrar una release ya podada— y una reversión a
    ninguna parte es peor que ninguna reversión.
    """
    tenant_id = await _sitio_visible(site_id, claims, conn)
    row = await issue_signed_command(
        conn,
        settings=Settings(),
        publisher=publisher,
        keys=keys,
        claims=claims,
        site_id=site_id,
        tenant_id=tenant_id,
        channel="system",
        action="update_rollback",
        event_id=None,
        payload_extra={"motivo": body.motivo},
        audit_meta={"motivo": body.motivo},
    )
    return UpdateCommandOut(
        command_id=row["command_id"],
        site_id=site_id,
        action="update_rollback",
    )
