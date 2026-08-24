"""Canary por cohortes (T-2.70): primero uno, se observa, luego el resto.

*«Un despliegue a toda la flota a la vez es un incidente a toda la flota a la
vez.»* El gabinete ya sabe activar con remojo y volver atrás solo (`bin/canary.sh`),
y la nube ya sabe ordenárselo firmado (`routers/updates.py`). Lo que falta aquí es
la disciplina de ORDEN entre gabinetes.

## Lo avanza una PERSONA, no un reloj

Podría hacerlo un temporizador: activar el canary, esperar N minutos, soltar el
resto. **No se hace, y no es por falta de infraestructura.** Este repo ya
decidió lo mismo para los simulacros —*«aquí no hay temporizador que dispare
nada: un actuador que se activa solo por reloj rompería la regla de oro 8»*— y
aquí el argumento es más fuerte, porque lo que se suelta no es un banner: es
código nuevo en el proceso que sostiene la sirena de otros edificios.

Un reloj sólo puede leer lo que se le enseñó a leer. El fallo que el remojo del
gabinete NO ve —latencias raras, un sensor que dejó de reportar, un cliente que
llama— se descubre mirando, y quien mira decide. Así que:

* `POST /fleet/rollouts` activa **UNO** y se para;
* `GET /fleet/rollouts/{id}` dice, sin adornos, qué SHA declara cada gabinete;
* `POST /fleet/rollouts/{id}/advance` **se niega** (409) mientras el canary no
  esté CONFIRMADO — y confirmado significa que su `fw_running` es el SHA
  esperado, no que la orden llegara;
* `POST /fleet/rollouts/{id}/abort` manda revertir a todo lo ya activado.

## Por qué un rollout es POR TENANT

Actualizar toda la flota de golpe es justo lo que esta ficha existe para
impedir. Que el modelo obligue a un rollout por cliente no es una limitación:
es la política escrita donde no se puede saltar, y además deja la regla de oro 5
sin excepciones que justificar.

## `ack` no es `fw_running`, y confundirlos es el defecto que T-2.69 cerró

El ack dice «el gabinete recibió y aceptó la orden». El SHA en ejecución dice
«el gabinete ARRANCÓ ese código». Entre los dos caben todos los fallos que
importan: la release que no levanta, la que levanta y cicla, la que ni siquiera
se llegó a repuntar. Este router nunca da por bueno un ack.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.auth.mfa import require_mfa
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher
from takab_api.commands.service import issue_signed_command
from takab_api.queries import rollouts as q
from takab_api.routers._common import http_error
from takab_api.routers.commands import get_key_provider, get_publisher
from takab_api.routers.updates import _RELEASE_ID, DEPLOY_ROLES
from takab_api.settings import Settings

_require_deploy = require_roles(*DEPLOY_ROLES, inner=require_mfa(get_claims))
#: Lectura: el mismo rol, SIN MFA. Mirar qué SHA declara un gabinete no mueve
#: nada, y exigir el segundo factor para consultar el estado de un despliegue en
#: curso empujaría a mirarlo por otro sitio — o a no mirarlo.
_require_lectura = require_roles(*DEPLOY_ROLES)

router = APIRouter(tags=["rollouts"])

#: NO confundir con `fw_releases`, que es el CATÁLOGO de versiones publicadas
#: (T-2.69) y se indexa por el SHA. Aquí `release_id` es el nombre del directorio
#: que `deploy.sh` dejó EN EL GABINETE, y `target_fw` —el SHA que lleva dentro—
#: es justo lo que casaría con `fw_releases.version`. No hay FK entre ambos a
#: propósito: la release existe en el disco del gabinete la haya catalogado
#: alguien o no, y exigir el catálogo bloquearía el rollback de una versión que
#: nadie llegó a anotar.
#:
#: El `release_id` que `deploy.sh` crea: `<AAAAMMDDTHHMMSSZ>-<sha>`. El SHA es lo
#: que `gateways.fw_running` declara, así que se extrae de ahí y se GUARDA.
#: Una release `heredada-<ts>` no es blanco de un rollout —es el árbol que ya
#: estaba, conservado para poder volver— y por eso no encaja aquí a propósito.
_RELEASE_CON_FW = re.compile(r"^\d{8}T\d{6}Z-(?P<fw>.+)$")


class RolloutCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: Annotated[str, Field(min_length=1, max_length=128)]
    #: Los sitios que entran. El canary sale de aquí: o el declarado, o el
    #: primero. Vacío = todos los del tenant con gabinete comandable.
    site_ids: list[UUID] = Field(default_factory=list)
    canary_site_id: UUID | None = None


class RolloutAbortIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Annotated[str, Field(min_length=3, max_length=280)]


class RolloutSiteOut(BaseModel):
    site_id: UUID
    site_name: str
    phase: str
    activated: bool
    #: Estado del COMANDO: `pending`/`acked`/`rejected`/`expired`, o `null` si al
    #: sitio todavía no se le ordenó nada.
    command_status: str | None = None
    #: SHA que el PROCESO de ese gabinete declara estar ejecutando. `null` = el
    #: gabinete no lo ha dicho todavía (o no hay gabinete). JAMÁS se rellena con
    #: el SHA del disco: sería exactamente la mentira que T-2.69 cerró.
    fw_running: str | None = None
    #: `fw_running == target_fw`. Es lo ÚNICO que autoriza a seguir.
    confirmed: bool = False


class RolloutOut(BaseModel):
    rollout_id: UUID
    release_id: str
    target_fw: str
    state: str
    created_at: datetime
    finished_at: datetime | None = None
    abort_reason: str | None = None
    sites: list[RolloutSiteOut] = Field(default_factory=list)


async def _vista(rollout_id: UUID, conn: AsyncConnection) -> RolloutOut:
    cab = (await conn.execute(q.SELECT_ROLLOUT, {"rollout": str(rollout_id)})).mappings().first()
    if cab is None:
        raise http_error(404, "rollout no encontrado")
    filas = (
        (await conn.execute(q.SELECT_ROLLOUT_SITES, {"rollout": str(rollout_id)})).mappings().all()
    )
    sitios = [
        RolloutSiteOut(
            site_id=f["site_id"],
            site_name=f["site_name"],
            phase=f["phase"],
            activated=f["command_id"] is not None,
            command_status=f["command_status"],
            fw_running=f["fw_running"],
            confirmed=bool(f["fw_running"]) and f["fw_running"] == cab["target_fw"],
        )
        for f in filas
    ]
    return RolloutOut(
        rollout_id=cab["rollout_id"],
        release_id=cab["release_id"],
        target_fw=cab["target_fw"],
        state=cab["state"],
        created_at=cab["created_at"],
        finished_at=cab["finished_at"],
        abort_reason=cab["abort_reason"],
        sites=sitios,
    )


async def _activar(
    *,
    conn: AsyncConnection,
    claims: Claims,
    publisher: CommandPublisher,
    keys: CommandKeyProvider,
    rollout_id: UUID,
    site_id: UUID,
    tenant_id: str,
    release_id: str,
) -> None:
    """Emite la orden firmada a UN sitio y anota su comando en el rollout."""
    fila = await issue_signed_command(
        conn,
        settings=Settings(),
        publisher=publisher,
        keys=keys,
        claims=claims,
        site_id=site_id,
        tenant_id=tenant_id,
        channel="system",
        action="update_activate",
        event_id=f"ROLLOUT-{rollout_id}",
        payload_extra={"release_id": release_id, "ventana_de_mantenimiento": False},
        audit_meta={"rollout_id": str(rollout_id), "release_id": release_id},
    )
    await conn.execute(
        q.MARK_ACTIVATED,
        {
            "rollout": str(rollout_id),
            "site": str(site_id),
            "command": str(fila["command_id"]),
            "now": datetime.now(tz=UTC),
        },
    )


@router.post("/fleet/rollouts", response_model=RolloutOut, status_code=202)
async def create_rollout(
    body: RolloutCreateIn,
    claims: Claims = Depends(_require_deploy),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> RolloutOut:
    """Abre el rollout y activa **UN SOLO** gabinete: el canary.

    No hay un parámetro para «actívalos todos». Esa ausencia es la ficha entera:
    un despliegue a toda la flota a la vez es un incidente a toda la flota a la
    vez, y la forma de impedirlo no es un aviso en un runbook.
    """
    if not _RELEASE_ID.fullmatch(body.release_id):
        raise http_error(422, "release_id inválido")
    m = _RELEASE_CON_FW.match(body.release_id)
    if m is None:
        raise http_error(
            422,
            "release_id sin SHA reconocible: un rollout necesita saber qué debe "
            "declarar fw_running para dar el canary por bueno",
        )
    target_fw = m.group("fw")

    comandables = (await conn.execute(q.COMMANDABLE_SITES)).mappings().all()
    por_id = {str(f["site_id"]): str(f["tenant_id"]) for f in comandables}
    scope = scope_filter(claims)

    if body.site_ids:
        pedidos = [str(s) for s in body.site_ids]
        faltan = [s for s in pedidos if s not in por_id]
        if faltan:
            raise http_error(409, f"sitios sin gateway comandable: {', '.join(sorted(faltan))}")
    else:
        pedidos = sorted(por_id)
    if scope is not None:
        pedidos = [s for s in pedidos if s in scope]
    if not pedidos:
        raise http_error(409, "no hay sitios con gateway comandable en el alcance")

    # UN ROLLOUT, UN TENANT. Ver el docstring del módulo: no es una limitación
    # del modelo, es la política. Y se comprueba aquí y no en la base porque el
    # mensaje importa: «mezclaste dos clientes» es accionable, un error de FK no.
    tenants = {por_id[s] for s in pedidos}
    if len(tenants) > 1:
        raise http_error(
            422,
            "un rollout es de UN tenant: actualizar varios clientes a la vez es "
            "exactamente lo que el canary existe para impedir",
        )
    tenant_id = tenants.pop()

    canario = str(body.canary_site_id) if body.canary_site_id else pedidos[0]
    if canario not in pedidos:
        raise http_error(422, "el canary tiene que ser uno de los sitios del rollout")

    cab = (
        (
            await conn.execute(
                q.INSERT_ROLLOUT,
                {
                    "tenant": tenant_id,
                    "release": body.release_id,
                    "target_fw": target_fw,
                    "user_id": claims.sub,
                },
            )
        )
        .mappings()
        .one()
    )
    rollout_id = cab["rollout_id"]
    for site in pedidos:
        await conn.execute(
            q.INSERT_ROLLOUT_SITE,
            {
                "rollout": str(rollout_id),
                "site": site,
                "tenant": tenant_id,
                "phase": "canary" if site == canario else "resto",
            },
        )

    await _activar(
        conn=conn,
        claims=claims,
        publisher=publisher,
        keys=keys,
        rollout_id=rollout_id,
        site_id=UUID(canario),
        tenant_id=tenant_id,
        release_id=body.release_id,
    )
    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="fleet_rollout_start",
        obj=f"fleet_rollout:{rollout_id}",
        meta={"release_id": body.release_id, "canary": canario, "sitios": len(pedidos)},
    )
    return await _vista(rollout_id, conn)


@router.get("/fleet/rollouts/{rollout_id}", response_model=RolloutOut)
async def read_rollout(
    rollout_id: UUID,
    claims: Claims = Depends(_require_lectura),
    conn: AsyncConnection = Depends(get_session),
) -> RolloutOut:
    """Qué SHA declara cada gabinete. Sin MFA: mirar no mueve nada."""
    return await _vista(rollout_id, conn)


@router.post("/fleet/rollouts/{rollout_id}/advance", response_model=RolloutOut, status_code=202)
async def advance_rollout(
    rollout_id: UUID,
    claims: Claims = Depends(_require_deploy),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> RolloutOut:
    """Suelta el resto de la cohorte — y sólo si el canary lo ganó.

    **El 409 es el corazón de la ficha.** Se niega mientras el canary no declare
    el SHA esperado, y «declare» significa `fw_running`, no un ack: el ack dice
    que la orden llegó, y entre «llegó» y «el gabinete arrancó ese código» caben
    todos los fallos que importan.
    """
    vista = await _vista(rollout_id, conn)
    if vista.state == "abortado":
        raise http_error(409, "el rollout está abortado")
    if vista.state == "desplegado":
        raise http_error(409, "el rollout ya soltó su cohorte")
    canario = next((s for s in vista.sites if s.phase == "canary"), None)
    if canario is None or not canario.confirmed:
        declara = canario.fw_running if canario else None
        raise http_error(
            409,
            "el canary todavía no confirma la versión: se esperaba "
            f"fw_running={vista.target_fw!r} y declara {declara!r}. "
            "Un ack no basta: dice que la orden llegó, no que el gabinete arrancó "
            "ese código.",
        )

    resto = [s for s in vista.sites if s.phase == "resto" and not s.activated]
    tenant_id = (
        (await conn.execute(q.SELECT_ROLLOUT, {"rollout": str(rollout_id)})).mappings().one()
    )["tenant_id"]
    for sitio in resto:
        await _activar(
            conn=conn,
            claims=claims,
            publisher=publisher,
            keys=keys,
            rollout_id=rollout_id,
            site_id=sitio.site_id,
            tenant_id=str(tenant_id),
            release_id=vista.release_id,
        )
    await conn.execute(
        q.SET_STATE,
        {
            "rollout": str(rollout_id),
            "state": "desplegado",
            "now": datetime.now(tz=UTC),
            "reason": None,
        },
    )
    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="fleet_rollout_advance",
        obj=f"fleet_rollout:{rollout_id}",
        meta={"sitios": len(resto)},
    )
    return await _vista(rollout_id, conn)


@router.post("/fleet/rollouts/{rollout_id}/abort", response_model=RolloutOut, status_code=202)
async def abort_rollout(
    rollout_id: UUID,
    body: RolloutAbortIn,
    claims: Claims = Depends(_require_deploy),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> RolloutOut:
    """Manda revertir a TODO lo que ya se activó, y cierra el rollout.

    Se ordena a los sitios ACTIVADOS y no a todos: pedirle volver atrás a un
    gabinete que nunca estrenó nada le costaría un reinicio —y, si su dueño de
    pines sigue dentro de `takab-edge`, un ciclo de gas y retenedores— por una
    versión que jamás corrió.
    """
    vista = await _vista(rollout_id, conn)
    if vista.state == "abortado":
        raise http_error(409, "el rollout ya está abortado")
    tenant_id = (
        (await conn.execute(q.SELECT_ROLLOUT, {"rollout": str(rollout_id)})).mappings().one()
    )["tenant_id"]
    for sitio in [s for s in vista.sites if s.activated]:
        await issue_signed_command(
            conn,
            settings=Settings(),
            publisher=publisher,
            keys=keys,
            claims=claims,
            site_id=sitio.site_id,
            tenant_id=str(tenant_id),
            channel="system",
            action="update_rollback",
            event_id=f"ROLLOUT-{rollout_id}",
            payload_extra={"motivo": body.motivo},
            audit_meta={"rollout_id": str(rollout_id), "motivo": body.motivo},
        )
    await conn.execute(
        q.SET_STATE,
        {
            "rollout": str(rollout_id),
            "state": "abortado",
            "now": datetime.now(tz=UTC),
            "reason": body.motivo,
        },
    )
    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="fleet_rollout_abort",
        obj=f"fleet_rollout:{rollout_id}",
        meta={"motivo": body.motivo},
    )
    return await _vista(rollout_id, conn)
