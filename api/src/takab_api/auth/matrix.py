"""Matriz de acceso web como DATO — espejo programático de RBAC-TAKAB.md §2/§7.

Fuente única de verdad para rutas y acciones por rol. Si el documento cambia,
cambia aquí; ``test_matrix`` compara esta tabla contra una copia a mano de §2 y
falla ante cualquier divergencia.

Rutas (columnas §2 → ruta §7): MONITOREO=/console, Flota Edge=/fleet,
Triage=/triage, Multi-Tenant=/tenants, Auditoría=/audit, Dash Edificio=/building.
Una ruta está concedida si la celda de §2 no es "—".

[T-2.52] ``/audit`` es la columna nueva: ``GET /audit`` existía desde T-1.57 sin
ninguna pantalla que lo consumiera. La celda es EXACTAMENTE la acción
``read_audit`` (superadmin, support, tenant_admin, gov_operator) — no se inventa
una frontera nueva, se hace visible la que ya decidía el endpoint.

Divergencia doc conocida: §7 lista ``building_admin`` en ``/fleet`` pero §2 le da
"—" en Flota Edge. Seguimos §2 (celda a celda, como el test) → building_admin
NO tiene /fleet. Pendiente de resolver en el documento.

Acciones (derivadas de §2 + notas §4):
- ``ack_incident``  ← MONITOREO ∈ {Total, "Lectura + ack"}.
- ``sign_dictamen`` ← Triage dice "firma dictamen" (acto profesional del inspector;
  no se deriva del "Total" de superadmin — decisión de seguridad, ver notas).
- ``export``        ← Triage ∈ {Total, "Lectura + export"}: DESCARGAR evidencia ya
  archivada (miniSEED/PDF existente).
- ``generate_report`` ← CREAR evidencia nueva (PDF de dictamen) en el tenant. Es un
  subconjunto estricto de ``export``: gov_operator descarga evidencia de tenants
  ``gov_shared`` pero no escribe filas en un tenant ajeno. Separarla de ``export``
  evita que la consola pinte a gov_operator un botón que siempre daría 403
  (regla de oro 7).
- ``edit_thresholds`` ← administra umbrales (§1/§2: tenant_admin) + dueño de plataforma.
- ``siren_test``    ← Dash Edificio == Total (dueño del sitio); §2 lo concede
  explícitamente a building_admin y lo niega a gov_operator.
- ``manage_fleet``  ← alta/edición/retiro de sitios, gabinetes y sensores (T-1.32).
  [DECISION 2026-07-09] §2 da "Total" en Flota Edge a ``takab_support``, pero aquí NO
  recibe la acción: soporte lee la flota, no mueve la geometría de un sitio ajeno.
  Gana el código sobre el documento; la divergencia queda anotada en RBAC-TAKAB.md §2.
  Escribir la ubicación de una estación reencuadra el quórum (la ventana de asociación
  depende de la distancia entre sitios): es una acción de dueño, no de soporte.

Esta tabla es la fuente ÚNICA: ``routers/dictamens`` deriva de ella ``SIGN_ROLES``,
``routers/exports`` deriva ``EXPORT_ROLES``, ``routers/reports`` deriva
``REPORT_ROLES`` y ``routers/privacy`` deriva ``NOTICE_ROLES`` (T-2.79.e cerró la
última excepción, que llevaba desde T-2.79 declarada como deuda en el propio
router) y ``ERASURE_ROLES`` (T-2.80.b). Ningún router vuelve a listar roles a mano.
"""

from __future__ import annotations

CONSOLE = "/console"
FLEET = "/fleet"
TRIAGE = "/triage"
TENANTS = "/tenants"
AUDIT = "/audit"
BUILDING = "/building"

# Orden estable de rutas para allowed_routes(). ``/building`` va al final porque no
# es un tab (se entra por deep-link) y ``landing.ts`` toma la PRIMERA ruta distinta
# de él como destino tras el login: meter /audit antes rompería el aterrizaje.
ROUTE_ORDER: tuple[str, ...] = (CONSOLE, FLEET, TRIAGE, TENANTS, AUDIT, BUILDING)

# Rutas concedidas por rol (espejo de §2, celda ≠ "—").
ROLE_ROUTE_MATRIX: dict[str, frozenset[str]] = {
    "takab_superadmin": frozenset({CONSOLE, FLEET, TRIAGE, TENANTS, AUDIT, BUILDING}),
    "takab_support": frozenset({CONSOLE, FLEET, TRIAGE, TENANTS, AUDIT, BUILDING}),
    "tenant_admin": frozenset({CONSOLE, FLEET, TRIAGE, TENANTS, AUDIT, BUILDING}),
    "soc_operator": frozenset({CONSOLE, FLEET, TRIAGE, BUILDING}),
    # [T-2.52] gov_operator SÍ ve /audit: RBAC §2 le da `read_audit` como evidencia
    # de protección civil, y la RLS `audit_read` ya acota las filas a lo que puede ver.
    "gov_operator": frozenset({CONSOLE, FLEET, TRIAGE, AUDIT, BUILDING}),
    "inspector": frozenset({CONSOLE, TRIAGE, BUILDING}),
    "building_admin": frozenset({CONSOLE, TRIAGE, BUILDING}),
    "brigadista": frozenset(),
    "security_guard": frozenset(),
    "occupant": frozenset(),
}

# Acciones sensibles del SOC web.
# [T-1.48] ``relocate_epicenter``/``request_dictamen`` — extensiones de la
# MONITOREO (§2 no las lista; anotadas en RBAC-TAKAB.md §2 como divergencia
# documentada): reubicar el epicentro reescribe un dato de RED compartido
# (acto de operador del tenant, jamás de gov/inspector) y solicitar dictamen
# inserta en el timeline (la RLS ``actions_insert`` excluye a gov_operator, así
# que concedérsela pintaría un botón que siempre da 403 — regla de oro 7).
# [T-1.57] ``read_audit`` — lectura de ``audit_log`` (GET /audit). Lectura PURA:
# la RLS ``audit_read`` ya acota (tenant propio o interno; filas con tenant NULL
# solo internos), la matriz decide QUIÉN ve el botón/endpoint. Se concede a
# superadmin/support (operación de plataforma), tenant_admin (su propio tenant)
# y gov_operator (evidencia de protección civil, solo lectura). Divergencia
# anotada en RBAC-TAKAB.md §2 (la tabla original no listaba esta columna).
ACTIONS: tuple[str, ...] = (
    "ack_incident",
    "sign_dictamen",
    "export",
    "generate_report",
    "edit_thresholds",
    "siren_test",
    "manage_fleet",
    "relocate_epicenter",
    "request_dictamen",
    "read_audit",
    # [T-1.59] Autodiagnóstico del gabinete (canal system): pulsa relés de gas/
    # puertas (NO audibles) con readback — espejo de siren_test (acción de dueño
    # del sitio), NO de lectura. soc_operator queda DENEGADO por default: opera
    # incidentes, no mantenimiento del gabinete (divergencia anotada en RBAC §2).
    "self_test",
    # [T-1.60] Simulacro institucional (POST /drills): acto ADMINISTRATIVO del
    # tenant (banner NO-real + voceo en N sitios) — superadmin/tenant_admin.
    # El voceo local del inmueble ya lo cubre el panel LAN con PIN.
    "drill_start",
    # [T-1.72] Alta de clientes (POST /tenants): crear un tenant es un acto del DUEÑO
    # de la plataforma — SOLO takab_superadmin. No lo recibe tenant_admin (no da de alta
    # OTROS clientes) ni support (lee la plataforma, no la provisiona). La RLS
    # ``tenants_admin`` ya exige app_role='takab_superadmin'; la matriz decide quién ve
    # el botón (regla de oro 7: sin botón que siempre daría 403).
    "manage_tenants",
    # [T-1.73] Visibilidad configurable entre clientes (conceder/revocar grants de
    # lectura cruzada): acto del DUEÑO de la plataforma — SOLO takab_superadmin. Toca
    # la frontera de aislamiento multi-tenant; ni tenant_admin ni support amplían la
    # visibilidad de un cliente sobre otro. La RLS ``vg_admin`` ya exige superadmin.
    "manage_visibility",
    # [T-2.36] Rotar el CÓDIGO DE RETIRO del tenant: el segundo factor que exige
    # retirar una estación. Es una credencial que TAKAB entrega fuera de banda —
    # SOLO takab_superadmin. Deliberadamente NO la recibe tenant_admin: si el
    # cliente pudiera rotar su propio código, el segundo factor sería el mismo
    # factor (su sesión) y la fricción desaparecería. La RLS ``trc_admin`` ya
    # exige app_role='takab_superadmin'; la matriz decide quién ve el control.
    "manage_retire_code",
    # [T-2.54] Alta/edición/baja de USUARIOS (proxy del Admin API de Cognito).
    # ``takab_superadmin`` (dueño de la plataforma) y ``tenant_admin`` (dueño del
    # cliente, acotado a SU tenant por el router). Deliberadamente NO la recibe
    # ``takab_support``: soporte lee la plataforma, no reparte identidades — y
    # ``custom:tenant_id``/``custom:role`` son justo los dos claims donde se ancla
    # la RLS (regla de oro 5), así que otorgarlos es otorgar datos. Los roles de
    # tenant solo pueden asignar roles NO internos (``schemas/users.PLATFORM_ROLES``),
    # o un tenant_admin se fabricaría un superadmin.
    "manage_users",
    # [T-2.03] SUPERFICIE MÓVIL (spec móvil §5/§8 + RBAC §3/§4). Los roles móviles
    # dejan de ser placeholders vacíos: estas son acciones de CAMPO (persona presente
    # en el inmueble con identidad de roster), por eso los roles de plataforma/SOC
    # NO las reciben — un superadmin sin asignación de zona no "pasa lista".
    # ``checkin_submit`` — check-in de vida (propio; delegado para tácticos).
    "checkin_submit",
    # ``roster_read`` — roster + estado de check-in por persona (PII: auditada).
    "roster_read",
    # ``damage_report_submit`` — formulario de daños → Triage (evidencia).
    "damage_report_submit",
    # ``evidence_upload`` — subir evidencia forense (fotos) al incidente (T-2.10).
    "evidence_upload",
    # ``siren_silence`` — retirar la demanda manual de sirena (RBAC §4: brigadista/
    # security_guard/building_admin; inspector NO silencia). Pipeline HMAC intacto.
    "siren_silence",
    # ``manual_activate`` — disparo manual deslizar-para-activar (RBAC §4: tácticos
    # individuales; el occupant SOLO por quórum-de-2 → panic_vote).
    "manual_activate",
    # ``enrollment_manage`` — administrar códigos de alta de ocupantes por sitio.
    "enrollment_manage",
    # ``panic_vote`` — voto de activación NO sísmica del occupant (quórum 2/30 s;
    # un voto JAMÁS activa). SOLO occupant: los tácticos ya tienen manual_activate.
    "panic_vote",
    # ``dictamen_read`` (R7) — leer/descargar el PDF de dictamen EXISTENTE en móvil
    # (no lo genera: generate_report sigue siendo inspector/superadmin).
    "dictamen_read",
    # [T-2.08] ``panel_read`` — dashboard táctico 2.1 (RBAC §3: "Dashboard táctico
    # (salud gabinete + actuadores)"): traza BMS del incidente + canal live en móvil.
    # El occupant NO lo recibe (§3 da "—"): su superficie es crisis/check-in, no la
    # operación del gabinete. Gatea GET /incidents/{id}/actions en superficie móvil.
    "panel_read",
    # [T-2.71] Abrir una VENTANA DE MANTENIMIENTO sobre un gabinete: silencia las
    # alarmas de on-call de ESE aparato mientras dure la intervención. Es un acto
    # administrativo del tenant (superadmin/tenant_admin), el mismo círculo que
    # ``drill_start`` — y NO el de ``self_test``, pese a ser mantenimiento.
    #
    # La diferencia con ``self_test`` es deliberada: ``building_admin`` sí prueba
    # los relés de SU inmueble, pero su superficie es MÓVIL y §2 le da "—" en
    # Flota Edge. Concederle esta acción pintaría un control en una ruta que no
    # tiene (regla de oro 7). Y lo que se apaga no es un dispositivo del edificio:
    # es el correo que despierta al on-call de TAKAB.
    #
    # ``soc_operator`` DENEGADO por el mismo criterio que ``self_test``: opera
    # incidentes, no mantenimiento del gabinete. ``gov_operator`` tampoco — lee
    # evidencia, no apaga vigilancia ajena.
    "maintenance_window",
    # [T-2.71] Ventana de PLATAFORMA (alarmas ``ec2_*`` de la instancia de la
    # nube): SOLO ``takab_superadmin``, mismo criterio que ``manage_tenants`` /
    # ``manage_visibility`` / ``manage_retire_code``. Esas alarmas no tienen dueño
    # de cliente: vigilan la infraestructura común de TODOS los tenants, así que
    # ningún tenant puede callarlas — ni siquiera "solo un rato".
    "platform_maintenance_window",
    # [T-2.70] ``deploy_firmware`` — ordenar a un gabinete que ACTIVE una release
    # ya verificada, o que VUELVA a la anterior. SOLO ``takab_superadmin``, y el
    # criterio no es el de ``maintenance_window`` sino el de
    # ``platform_maintenance_window``: el código que se activa es de TAKAB, el
    # artefacto lo puso el operador de TAKAB y una release mala deja un edificio
    # sin alertamiento. Un ``tenant_admin`` no tiene el artefacto ni puede juzgar
    # una versión, así que concedérsela sería darle un botón cuya consecuencia no
    # puede evaluar.
    #
    # ACTIVAR y REVERTIR van bajo la MISMA acción a propósito: la vuelta atrás es
    # la válvula de seguridad de la ida, y un permiso que dejara empujar sin
    # dejar volver sería peor que ninguno.
    "deploy_firmware",
    # [T-2.79.e] Publicar el AVISO DE PRIVACIDAD del tenant (POST /privacy/notices) y
    # dejar constancia del consentimiento de un TERCERO sin sesión (un teléfono: el
    # opt-in de WhatsApp de T-2.77). Van juntas porque son el mismo círculo de
    # confianza — el DUEÑO del cliente. Bajo la LFPDPPP el *responsable* de los datos
    # de los ocupantes de un inmueble es la organización dueña del inmueble, así que
    # publicar su aviso es un acto SUYO: superadmin/tenant_admin, el mismo círculo
    # que ``edit_thresholds`` / ``drill_start``.
    #
    # ``takab_support`` queda fuera a propósito, pese a su "Total" en §2: soporte lee
    # la plataforma, no firma el aviso de privacidad de un cliente en su nombre.
    # Misma disciplina que ``manage_fleet`` y ``manage_users``.
    #
    # La frontera de seguridad REAL es la RLS ``pn_publish`` (``tenant_id =
    # app_tenant_id() AND app_role() IN ('tenant_admin','takab_superadmin')``), que
    # además exige que la fila sea del PROPIO tenant — algo que ninguna matriz de
    # roles puede expresar. Esta acción solo hace que el 403 llegue limpio y que la
    # consola no pinte un botón que siempre fallaría (regla de oro 7).
    "manage_privacy_notice",
    # [T-2.80.b] Registrar una solicitud ARCO recibida POR ESCRITO y ejecutarla por
    # cuenta del titular (``POST /privacy/erasure-requests`` y su ``/erasure``).
    # Mismo círculo y misma razón que la anterior: bajo la LFPDPPP una solicitud
    # ARCO se le manda AL RESPONSABLE del tratamiento —la organización dueña del
    # inmueble—, no a TAKAB. ``takab_support`` fuera por el mismo criterio: soporte
    # lee la plataforma, no anonimiza al ocupante de un cliente en su nombre.
    #
    # Va SEPARADA de ``manage_privacy_notice`` aunque compartan roles, y no por
    # simetría: publicar un aviso es reversible publicando otra versión; anonimizar
    # a una persona no se deshace. Fundirlas obligaría a conceder la irreversible
    # para dar la reversible el día que los círculos dejen de coincidir.
    #
    # Lo que esta acción NO es —y aquí importa más que en ninguna otra— es la
    # frontera. Ejercer ARCO por cuenta de otro exige CONSTANCIA registrada, y eso
    # lo impone la base: ``app_can_erase_subject`` gatea cinco políticas RLS. El
    # confinamiento por tenant tampoco vive aquí: la constancia lleva un FK
    # compuesto contra el padrón del propio cliente, así que nombrar a un titular
    # ajeno viola integridad referencial. Esta acción solo hace que el 403 llegue
    # limpio (regla de oro 7).
    "manage_privacy_erasure",
)


def _actions(
    *,
    ack_incident: bool = False,
    sign_dictamen: bool = False,
    export: bool = False,
    generate_report: bool = False,
    edit_thresholds: bool = False,
    siren_test: bool = False,
    manage_fleet: bool = False,
    relocate_epicenter: bool = False,
    request_dictamen: bool = False,
    read_audit: bool = False,
    self_test: bool = False,
    drill_start: bool = False,
    manage_tenants: bool = False,
    manage_visibility: bool = False,
    manage_retire_code: bool = False,
    manage_users: bool = False,
    checkin_submit: bool = False,
    roster_read: bool = False,
    damage_report_submit: bool = False,
    evidence_upload: bool = False,
    siren_silence: bool = False,
    manual_activate: bool = False,
    enrollment_manage: bool = False,
    panic_vote: bool = False,
    dictamen_read: bool = False,
    panel_read: bool = False,
    maintenance_window: bool = False,
    platform_maintenance_window: bool = False,
    deploy_firmware: bool = False,
    manage_privacy_notice: bool = False,
    manage_privacy_erasure: bool = False,
) -> dict[str, bool]:
    return {
        "ack_incident": ack_incident,
        "sign_dictamen": sign_dictamen,
        "export": export,
        "generate_report": generate_report,
        "edit_thresholds": edit_thresholds,
        "siren_test": siren_test,
        "manage_fleet": manage_fleet,
        "relocate_epicenter": relocate_epicenter,
        "request_dictamen": request_dictamen,
        "read_audit": read_audit,
        "self_test": self_test,
        "drill_start": drill_start,
        "manage_tenants": manage_tenants,
        "manage_visibility": manage_visibility,
        "manage_retire_code": manage_retire_code,
        "manage_users": manage_users,
        "checkin_submit": checkin_submit,
        "roster_read": roster_read,
        "damage_report_submit": damage_report_submit,
        "evidence_upload": evidence_upload,
        "siren_silence": siren_silence,
        "manual_activate": manual_activate,
        "enrollment_manage": enrollment_manage,
        "panic_vote": panic_vote,
        "dictamen_read": dictamen_read,
        "panel_read": panel_read,
        "maintenance_window": maintenance_window,
        "platform_maintenance_window": platform_maintenance_window,
        "deploy_firmware": deploy_firmware,
        "manage_privacy_notice": manage_privacy_notice,
        "manage_privacy_erasure": manage_privacy_erasure,
    }


ROLE_ACTION_MATRIX: dict[str, dict[str, bool]] = {
    "takab_superadmin": _actions(
        ack_incident=True,
        export=True,
        generate_report=True,
        edit_thresholds=True,
        siren_test=True,
        manage_fleet=True,
        relocate_epicenter=True,
        request_dictamen=True,
        read_audit=True,
        self_test=True,
        drill_start=True,
        manage_tenants=True,
        manage_visibility=True,
        manage_retire_code=True,
        manage_users=True,
        # [T-2.03] Administra el alta de ocupantes; las acciones de CAMPO
        # (check-in/roster/daños/silenciar) NO — exigen presencia con identidad
        # de roster en el inmueble, no "Total" de plataforma.
        enrollment_manage=True,
        # [T-2.71] Ventanas de mantenimiento: la de gabinete y la de PLATAFORMA.
        # La segunda solo aquí — apaga la vigilancia de la infra común.
        maintenance_window=True,
        platform_maintenance_window=True,
        # [T-2.70] Ordena activar una release ya verificada, o volver a la
        # anterior. Sólo aquí: el código es de TAKAB y una release mala deja un
        # edificio sin alertamiento — ver la nota de la acción en ACTIONS.
        deploy_firmware=True,
        # [T-2.79.e] Publica el aviso de privacidad del cliente. La RLS ``pn_publish``
        # lo acota además a filas del PROPIO tenant del token.
        manage_privacy_notice=True,
        # [T-2.80.b] Ejecuta una solicitud ARCO recibida por escrito. A quién
        # alcanza no lo decide esta celda: lo decide la CONSTANCIA, y su FK contra
        # el padrón del cliente.
        manage_privacy_erasure=True,
    ),
    "takab_support": _actions(read_audit=True),
    "tenant_admin": _actions(
        ack_incident=True,
        edit_thresholds=True,
        siren_test=True,
        manage_fleet=True,
        relocate_epicenter=True,
        request_dictamen=True,
        read_audit=True,
        self_test=True,
        drill_start=True,
        manage_users=True,
        enrollment_manage=True,
        # [T-2.71] Su propio gabinete, jamás las alarmas ec2_* de la plataforma.
        maintenance_window=True,
        # [T-2.79.e] El *responsable* de los datos de sus ocupantes es él: su aviso
        # de privacidad lo publica él, no TAKAB en su nombre.
        manage_privacy_notice=True,
        # [T-2.80.b] Y por lo mismo, la solicitud ARCO por escrito se la mandan A
        # ÉL: es quien tiene la obligación de ejecutarla.
        manage_privacy_erasure=True,
    ),
    "soc_operator": _actions(ack_incident=True, relocate_epicenter=True, request_dictamen=True),
    # Descarga evidencia de tenants gov_shared, pero no la GENERA en tenant ajeno.
    "gov_operator": _actions(ack_incident=True, export=True, read_audit=True),
    # [T-2.03] inspector en móvil (RBAC §3, celda a celda): forense (cámara +
    # formulario, que además FIRMA) y disparo individual; SIN headcount (§3 da
    # "—" en pase de lista) y SIN silenciar (§3/§4).
    "inspector": _actions(
        sign_dictamen=True,
        export=True,
        generate_report=True,
        checkin_submit=True,
        damage_report_submit=True,
        evidence_upload=True,
        manual_activate=True,
        dictamen_read=True,
        panel_read=True,
    ),
    # [T-2.03] building_admin (RBAC §3): headcount y silenciar SÍ; forense NO
    # (§3 da "—" en cámara/formulario — administra el inmueble, no lo peritea).
    "building_admin": _actions(
        siren_test=True,
        self_test=True,
        checkin_submit=True,
        roster_read=True,
        siren_silence=True,
        manual_activate=True,
        enrollment_manage=True,
        dictamen_read=True,
        panel_read=True,
    ),
    # [T-2.03] Tácticos de campo (RBAC §4): deslizar-para-activar individual,
    # silenciar = retirada de demanda, forense y headcount.
    "brigadista": _actions(
        checkin_submit=True,
        roster_read=True,
        damage_report_submit=True,
        evidence_upload=True,
        siren_silence=True,
        manual_activate=True,
        dictamen_read=True,
        panel_read=True,
    ),
    "security_guard": _actions(
        checkin_submit=True,
        roster_read=True,
        damage_report_submit=True,
        evidence_upload=True,
        siren_silence=True,
        manual_activate=True,
        dictamen_read=True,
        panel_read=True,
    ),
    # [T-2.03] occupant: SOLO su check-in y su voto de pánico (quórum 2/30 s).
    "occupant": _actions(checkin_submit=True, panic_vote=True),
}


def roles_with_action(action: str) -> tuple[str, ...]:
    """Roles con ``action`` concedida, ordenados. Fuente única para los routers."""
    return tuple(sorted(r for r, acts in ROLE_ACTION_MATRIX.items() if acts.get(action)))


def allowed_routes(role: str) -> list[str]:
    """Rutas web del rol, en ``ROUTE_ORDER``. Rol desconocido/móvil-only ⇒ []."""
    granted = ROLE_ROUTE_MATRIX.get(role, frozenset())
    return [route for route in ROUTE_ORDER if route in granted]


def allowed_actions(role: str) -> dict[str, bool]:
    """Acciones booleanas del rol. Rol desconocido ⇒ todo False (default-deny)."""
    base = dict.fromkeys(ACTIONS, False)
    base.update(ROLE_ACTION_MATRIX.get(role, {}))
    return base
