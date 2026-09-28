"""[T-9.80 · D-48] ``/me/emergency-contacts`` · los contactos de emergencia del PORTADOR.

Hasta tres personas a quienes TAKAB avisa por correo si el titular marca
«NECESITO AYUDA» tras un sismo (el aviso lo encola ``notify/orchestrator.py`` a
partir de la acción ``need_help_contacts`` que deja ``submit_checkin``).

Son datos de TERCEROS, así que la superficie es la mínima y la acota la BASE:

* la política ``ec_self`` filtra por ``user_sub = app_user_id()``, no sólo por
  tenant: ningún rol —ni el administrador del cliente ni el de TAKAB— lee la lista
  de otro por aquí. Las sentencias repiten el filtro y escriben ``app_tenant_id()``
  / ``app_user_id()`` en vez de un parámetro: no hay por dónde nombrar a otro;
* ``PUT`` REEMPLAZA la lista entera en la transacción del request y exige la
  versión VIGENTE del aviso (``privacy/texts/contactos_es_mx.json``);
* la auditoría cuenta cuántos y con qué aviso, **sin un solo dato personal**:
  ``audit_log`` no se poda nunca (regla de oro 11), y un correo ahí sobreviviría
  al ARCO del titular.

Todo exige superficie móvil, como el resto de ``/me/*`` de la app.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_mobile_surface
from takab_api.privacy.artifacts import NoticeSpec, get_catalog
from takab_api.routers._common import http_error
from takab_api.schemas.contactos_emergencia import (
    AvisoContactos,
    ContactoOut,
    ContactosIn,
    ContactosOut,
)

router = APIRouter(dependencies=[Depends(require_mobile_surface)])

#: Propósito y locale del aviso en el catálogo del repo.
PURPOSE = "emergency_contacts"
LOCALE = "es-MX"

_COLUMNAS = "posicion, display_name, email, phone, consent_version, consented_at"

_LISTA = text(
    f"SELECT {_COLUMNAS} FROM emergency_contacts "
    "WHERE tenant_id = app_tenant_id() AND user_sub = app_user_id() "
    "ORDER BY posicion"
)

_BORRA = text(
    "DELETE FROM emergency_contacts WHERE tenant_id = app_tenant_id() AND user_sub = app_user_id()"
)

# `consented_at = now()`: el instante de la TRANSACCIÓN, el mismo para toda la lista
# que se aceptó de una vez.
_INSERTA = text(
    "INSERT INTO emergency_contacts (tenant_id, user_sub, posicion, display_name, email, "
    "  phone, consent_version, consented_at) "
    "VALUES (app_tenant_id(), app_user_id(), :posicion, :display_name, :email, :phone, "
    "  :version, now()) "
    f"RETURNING {_COLUMNAS}"
)


def _aviso() -> NoticeSpec:
    spec = get_catalog().get(PURPOSE, LOCALE)
    if spec is None:
        # Sin texto que aceptar no se registra a nadie: un consentimiento sin aviso
        # no es un consentimiento. El catálogo ya gritó en el log por qué falta.
        raise http_error(503, "aviso_de_contactos_no_disponible")
    return spec


def _aviso_out(spec: NoticeSpec) -> AvisoContactos:
    return AvisoContactos(version=spec.version, texto=spec.body, provisional=spec.provisional)


@router.get("/me/emergency-contacts", response_model=ContactosOut)
async def get_emergency_contacts(
    conn: AsyncConnection = Depends(get_session),
) -> ContactosOut:
    """La lista PROPIA, en orden, y el aviso vigente que hay que aceptar para
    cambiarla. Sin contactos, ``contactos`` es ``[]`` (no un 404)."""
    spec = _aviso()
    filas = (await conn.execute(_LISTA)).all()
    return ContactosOut(
        contactos=[ContactoOut(**dict(f._mapping)) for f in filas],
        aviso=_aviso_out(spec),
    )


@router.put("/me/emergency-contacts", response_model=ContactosOut)
async def put_emergency_contacts(
    body: ContactosIn,
    claims: Claims = Depends(require_mobile_surface),
    conn: AsyncConnection = Depends(get_session),
) -> ContactosOut:
    """REEMPLAZA la lista entera: ``posicion`` = el orden en que llegan.

    Borrar y volver a insertar, en la transacción del request: una lista a medias
    no es un estado alcanzable, y el ``UNIQUE (tenant, user, posicion)`` no puede
    chocar con la lista vieja.
    """
    spec = _aviso()
    if body.consentimiento_version != spec.version:
        raise http_error(409, "consentimiento_desactualizado")

    await conn.execute(_BORRA)
    filas = []
    for posicion, contacto in enumerate(body.contactos, start=1):
        fila = (
            await conn.execute(
                _INSERTA,
                {
                    "posicion": posicion,
                    "display_name": contacto.display_name,
                    "email": contacto.email,
                    "phone": contacto.phone,
                    "version": spec.version,
                },
            )
        ).one()
        filas.append(ContactoOut(**dict(fila._mapping)))

    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="emergency_contacts_updated",
        obj=f"emergency_contacts:user:{claims.sub}",
        # Cuántos y sobre qué texto. NI UN nombre, correo o teléfono: esta fila no
        # se poda nunca y el ARCO del titular no la reescribe.
        meta={"n": len(filas), "consent_version": spec.version},
    )
    return ContactosOut(contactos=filas, aviso=_aviso_out(spec))


@router.delete("/me/emergency-contacts", status_code=204)
async def delete_emergency_contacts(
    claims: Claims = Depends(require_mobile_surface),
    conn: AsyncConnection = Depends(get_session),
) -> Response:
    """Borra la lista PROPIA. Idempotente: sin contactos también es 204."""
    borrados = (await conn.execute(_BORRA)).rowcount
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="emergency_contacts_deleted",
        obj=f"emergency_contacts:user:{claims.sub}",
        meta={"n": borrados},
    )
    return Response(status_code=204)
