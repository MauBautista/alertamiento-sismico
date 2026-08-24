"""Modelos de GET /me (identidad, T-1.26) y /me/profile (presentación, T-1.48)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


class MeActions(BaseModel):
    """Acciones sensibles (espejo de ``matrix.ACTIONS``, default-deny).

    Desde T-2.03 incluye la superficie MÓVIL: la app deriva su UI de estos
    booleanos (server-driven), igual que la consola.
    """

    ack_incident: bool
    sign_dictamen: bool
    export: bool
    generate_report: bool
    edit_thresholds: bool
    siren_test: bool
    manage_fleet: bool
    relocate_epicenter: bool
    request_dictamen: bool
    read_audit: bool
    self_test: bool
    drill_start: bool
    manage_tenants: bool
    manage_visibility: bool
    #: [T-2.36] Rotar el código de retiro del cliente (solo takab_superadmin).
    manage_retire_code: bool
    #: [T-2.54] Alta/edición/baja de identidades en Cognito (superadmin +
    #: tenant_admin acotado a su tenant). No la recibe ``takab_support``.
    manage_users: bool
    checkin_submit: bool
    roster_read: bool
    damage_report_submit: bool
    evidence_upload: bool
    siren_silence: bool
    manual_activate: bool
    enrollment_manage: bool
    panic_vote: bool
    dictamen_read: bool
    #: [T-2.08] Dashboard táctico 2.1 (RBAC §3): traza BMS + canal live móvil.
    panel_read: bool
    #: [T-2.71] Abrir una ventana de mantenimiento sobre UN gabinete: silencia sus
    #: alarmas de on-call mientras dure la intervención (superadmin/tenant_admin).
    maintenance_window: bool
    #: [T-2.71] Ventana de PLATAFORMA (alarmas ec2_* de la instancia de la nube):
    #: SOLO takab_superadmin — vigilan infra común de todos los clientes.
    platform_maintenance_window: bool
    #: [T-2.79.e] Publicar el aviso de privacidad del cliente y registrar el
    #: consentimiento de un tercero sin sesión (superadmin/tenant_admin: el
    #: *responsable* de los datos de los ocupantes es el dueño del inmueble).
    manage_privacy_notice: bool
    #: [T-2.80.b] Registrar una solicitud ARCO recibida POR ESCRITO y ejecutarla
    #: por cuenta del titular (superadmin/tenant_admin). Que la acción esté en
    #: `true` NO significa que se pueda anonimizar a cualquiera: hace falta una
    #: CONSTANCIA registrada, y eso lo exige la base (RLS), no esta bandera.
    manage_privacy_erasure: bool
    #: [T-2.70] Ordenar a un gabinete que ACTIVE una release ya verificada, o que
    #: vuelva a la anterior. SOLO takab_superadmin: el código es de TAKAB, el
    #: artefacto lo puso su operador y una release mala deja un edificio sin
    #: alertamiento — un tenant_admin no tiene con qué juzgarla.
    deploy_firmware: bool


class MeEnrolledSite(BaseModel):
    """[T-2.114] Inmueble en el que el portador está ENROLADO (R2).

    El enrolamiento vive en ``user_zone_assignments`` y NO viaja en el claim de
    Cognito: el alcance móvil se resuelve server-side desde que existe T-2.03.
    Publicarlo aquí es lo que permite al teléfono dejar de ser la única memoria
    de a qué edificio pertenece un ocupante — y, por tanto, soltar ese dato al
    cerrar sesión sin dejar tirado a nadie.
    """

    site_id: UUID
    site_name: str
    zone_id: UUID | None
    zone_name: str | None
    #: Política de evacuación de la zona (``evacuate``/``shelter``/…), la misma
    #: que devuelve el alta; ``null`` si el enrolamiento no fijó zona.
    evac_policy: str | None
    #: Rol que concedió el código de alta (``occupant``/``brigadista``/…).
    role: str


class MeResponse(BaseModel):
    """Perfil del portador del token: qué ve y qué puede hacer (RBAC §2/§7).

    ``site_scope``: ``"*"`` = todo el tenant; lista ordenada de sitios en otro
    caso (vacía = default-deny). Rol móvil-only ⇒ ``allowed_routes`` vacías.

    ``enrolled_sites`` (T-2.114): los inmuebles del ENROLAMIENTO, que son cosa
    distinta de ``site_scope`` (ese sale del claim). Vacío = no enrolado, y se
    declara vacío en vez de adivinar.
    """

    sub: str
    tenant_id: str
    role: str
    site_scope: Literal["*"] | list[str]
    #: [T-2.45] Si el SERVIDOR está filtrando de verdad por ``site_scope`` en las
    #: pantallas de consola. Existe porque el cutover va en dos fases: durante la
    #: fase A un claim vacío no filtra, y una insignia que dijera "ALCANCE · 0
    #: ESTACIONES" mientras se ve todo el tenant sería exactamente el dato falso
    #: que la regla de oro 7 prohíbe. La UI declara lo que el servidor hace.
    console_scope_enforced: bool = False
    surface: str
    allowed_routes: list[str]
    allowed_actions: MeActions
    #: [T-2.114] Inmuebles del enrolamiento (R2), ordenados. Fuente de verdad
    #: del "sitio vigilado" del ocupante: sin esto el dato solo existía en el
    #: SecureStore del teléfono y se heredaba entre usuarios del mismo aparato.
    enrolled_sites: list[MeEnrolledSite] = []


class ProfileOut(BaseModel):
    """Perfil de presentación del operador (T-1.48). Sin fila ⇒ campos null
    (200, no 404): "sin nombre configurado" es un estado normal, no un error.

    [T-2.03·R4] ``phone``: PII con consentimiento — alimenta la llamada de un
    toque del roster (headcount 2.6)."""

    user_sub: UUID
    display_name: str | None
    phone: str | None
    updated_at: datetime | None


class ProfilePutIn(BaseModel):
    """Cuerpo de PUT /me/profile: el nombre se normaliza (trim + colapso de
    espacios internos) ANTES de validar longitud — "   " no es un nombre.

    [T-2.03·R4] ``phone`` opcional (E.164 laxo): proporcionarlo ES el
    consentimiento de aparecer en el roster; ``null`` lo retira."""

    display_name: str
    phone: str | None = None

    @field_validator("display_name")
    @classmethod
    def _normalize(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if not v:
            raise ValueError("display_name vacío")
        if len(v) > 80:
            raise ValueError("display_name supera 80 caracteres")
        return v

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = re.sub(r"[\s().-]+", "", v.strip())
        if not v:
            return None
        if not re.fullmatch(r"\+?[0-9]{7,15}", v):
            raise ValueError("phone inválido (7-15 dígitos, prefijo + opcional)")
        return v
