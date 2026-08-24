"""La matriz de código debe ser idéntica a RBAC-TAKAB.md §2 (copia a mano).

Si el código y el documento divergen, este test FALLA. La tabla de abajo se
transcribió celda por celda de §2: True = la celda NO es "—".
"""

from __future__ import annotations

import ast
from pathlib import Path

from takab_api.auth.matrix import (
    ACTIONS,
    AUDIT,
    BUILDING,
    CONSOLE,
    FLEET,
    ROLE_ROUTE_MATRIX,
    TENANTS,
    TRIAGE,
    allowed_actions,
    allowed_routes,
    roles_with_action,
)
from takab_api.routers import privacy as privacy_router

# Columnas §2 → (MONITOREO, Flota Edge, EVALUACIÓN, Multi-Tenant, Auditoría,
# Dash Edificio).
COLS = (CONSOLE, FLEET, TRIAGE, TENANTS, AUDIT, BUILDING)

# Copiado A MANO de RBAC-TAKAB.md §2 (matriz web), celda por celda.
RBAC_SECTION_2 = {
    #                    console fleet triage tenants audit building
    "takab_superadmin": (True, True, True, True, True, True),
    "takab_support": (True, True, True, True, True, True),
    "tenant_admin": (True, True, True, True, True, True),
    "soc_operator": (True, True, True, False, False, True),
    "gov_operator": (True, True, True, False, True, True),
    "inspector": (True, False, True, False, False, True),
    "building_admin": (True, False, True, False, False, True),
    "brigadista": (False, False, False, False, False, False),
    "security_guard": (False, False, False, False, False, False),
    "occupant": (False, False, False, False, False, False),
}

MOBILE_ONLY = ("brigadista", "security_guard", "occupant")


def _expected_routes(role: str) -> list[str]:
    return [col for col, granted in zip(COLS, RBAC_SECTION_2[role], strict=True) if granted]


def test_route_matrix_matches_rbac_section_2() -> None:
    assert set(ROLE_ROUTE_MATRIX) == set(RBAC_SECTION_2)
    for role in RBAC_SECTION_2:
        expected = _expected_routes(role)
        assert allowed_routes(role) == expected, role
        assert ROLE_ROUTE_MATRIX[role] == frozenset(expected), role


def test_mobile_only_roles_have_no_web_routes() -> None:
    for role in MOBILE_ONLY:
        assert allowed_routes(role) == []


def test_allowed_routes_are_ordered() -> None:
    # Superadmin cubre todas: el orden debe ser el de COLS.
    assert allowed_routes("takab_superadmin") == list(COLS)


DENY_ALL = {
    "ack_incident": False,
    "sign_dictamen": False,
    "export": False,
    "generate_report": False,
    "edit_thresholds": False,
    "siren_test": False,
    "manage_fleet": False,
    "relocate_epicenter": False,
    "request_dictamen": False,
    "read_audit": False,
    "self_test": False,
    "drill_start": False,
    "manage_tenants": False,
    "manage_visibility": False,
    "manage_retire_code": False,
    "manage_users": False,
    "checkin_submit": False,
    "roster_read": False,
    "damage_report_submit": False,
    "evidence_upload": False,
    "siren_silence": False,
    "manual_activate": False,
    "enrollment_manage": False,
    "panic_vote": False,
    "dictamen_read": False,
    "panel_read": False,
    "maintenance_window": False,
    "platform_maintenance_window": False,
    # [T-2.79.e] Publicar el aviso de privacidad del cliente y registrar el
    # consentimiento de un tercero sin sesión (mismo círculo: el DUEÑO del cliente).
    "manage_privacy_notice": False,
    # [T-2.80.b] Registrar una solicitud ARCO recibida por escrito y ejecutarla por
    # cuenta del titular (mismo círculo, acción aparte: esta no se deshace).
    "manage_privacy_erasure": False,
    # [T-2.70] Activar una release en un gabinete, o devolverlo a la anterior. Un
    # rol desconocido no puede tocar el código desde el que arranca el camino de
    # vida de un edificio.
    "deploy_firmware": False,
}

# [T-2.03] Acciones de la superficie MÓVIL (spec §5/§8 + RBAC §3/§4).
MOBILE_ACTIONS = (
    "checkin_submit",
    "roster_read",
    "damage_report_submit",
    "evidence_upload",
    "siren_silence",
    "manual_activate",
    "enrollment_manage",
    "panic_vote",
    "dictamen_read",
    # [T-2.08] Dashboard táctico 2.1 (RBAC §3: salud gabinete + actuadores).
    "panel_read",
)


def test_unknown_role_denied() -> None:
    assert allowed_routes("ghost") == []
    assert allowed_actions("ghost") == DENY_ALL


def test_action_anchors_from_rbac() -> None:
    assert allowed_actions("inspector")["sign_dictamen"] is True
    gov = allowed_actions("gov_operator")
    assert gov["export"] is True
    assert gov["ack_incident"] is True
    assert gov["edit_thresholds"] is False
    assert gov["siren_test"] is False
    assert allowed_actions("building_admin")["siren_test"] is True


def test_sign_dictamen_is_inspector_only() -> None:
    """Acto profesional del inspector: el "Total" de §2 NO lo concede (decisión
    de seguridad documentada en matrix.py). ``routers/dictamens`` deriva de aquí."""
    can_sign = {r for r in RBAC_SECTION_2 if allowed_actions(r)["sign_dictamen"]}
    assert can_sign == {"inspector"}


def test_generate_report_is_distinct_from_export() -> None:
    """``export`` = descargar evidencia ya archivada (miniSEED). ``generate_report``
    = CREAR evidencia nueva (PDF) en el tenant. gov_operator lee y descarga
    evidencia ajena (gov_shared) pero no escribe filas en un tenant que no es suyo,
    así que tiene export sin generate_report. Un solo flag para ambos haría que la
    consola le pintara un botón que siempre da 403 (regla de oro 7)."""
    can_export = {r for r in RBAC_SECTION_2 if allowed_actions(r)["export"]}
    can_report = {r for r in RBAC_SECTION_2 if allowed_actions(r)["generate_report"]}
    assert can_export == {"takab_superadmin", "gov_operator", "inspector"}
    assert can_report == {"takab_superadmin", "inspector"}
    assert can_report < can_export


def test_manage_fleet_excludes_takab_support() -> None:
    """§2 da "Total" a ``takab_support`` en Flota Edge, pero el código NO le concede
    ``manage_fleet`` ([DECISION 2026-07-09], documentada en matrix.py y RBAC-TAKAB.md).

    Mover la ubicación de una estación reencuadra la ventana de asociación del quórum
    (``|Δt| ≤ dist/v_P + margen``): es un acto de dueño del tenant, no de soporte.
    """
    can_manage = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_fleet"]}
    assert can_manage == {"takab_superadmin", "tenant_admin"}
    assert allowed_actions("takab_support")["manage_fleet"] is False
    # Y sigue viendo /fleet: la divergencia es de escritura, no de lectura.
    assert FLEET in ROLE_ROUTE_MATRIX["takab_support"]


def test_ack_incident_roles() -> None:
    can_ack = {r for r in RBAC_SECTION_2 if allowed_actions(r)["ack_incident"]}
    assert can_ack == {"takab_superadmin", "tenant_admin", "soc_operator", "gov_operator"}


def test_relocate_epicenter_is_tenant_operator_action() -> None:
    """[T-1.48] Reubicar el epicentro reescribe un dato de RED compartido
    (seismic_events): acto de operador del tenant + dueño de plataforma. Ni gov
    (solo lectura+acuse) ni inspector (juzga, no edita la física del evento)."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["relocate_epicenter"]}
    assert can == {"takab_superadmin", "tenant_admin", "soc_operator"}


def test_request_dictamen_excludes_gov() -> None:
    """[T-1.48] ``ack_incident`` menos gov: la RLS ``actions_insert`` impide a
    gov_operator insertar en incident_actions — concederle la acción pintaría
    un botón que siempre da 403 (regla de oro 7). Divergencia anotada en
    RBAC-TAKAB.md §2."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["request_dictamen"]}
    assert can == {"takab_superadmin", "tenant_admin", "soc_operator"}


def test_read_audit_is_read_only_oversight() -> None:
    """[T-1.57] Lectura PURA del audit trail: plataforma (superadmin/support),
    dueño del tenant (tenant_admin) y protección civil (gov_operator; la RLS
    ``audit_read`` lo acota a tenants visibles). Los operadores/inspectores no
    supervisan la auditoría — la generan."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["read_audit"]}
    assert can == {"takab_superadmin", "takab_support", "tenant_admin", "gov_operator"}


def test_audit_route_matches_read_audit_action_exactly() -> None:
    """[T-2.52] La ruta /audit NO inventa una frontera nueva: es la acción
    ``read_audit`` hecha visible. Si alguien concediera la ruta sin la acción, la
    pestaña llevaría a un 403; si concediera la acción sin la ruta, el endpoint
    quedaría otra vez sin pantalla (que es el defecto que esta tarea cerró)."""
    with_route = {r for r in RBAC_SECTION_2 if AUDIT in ROLE_ROUTE_MATRIX[r]}
    with_action = {r for r in RBAC_SECTION_2 if allowed_actions(r)["read_audit"]}
    assert with_route == with_action


def test_self_test_is_owner_maintenance_action() -> None:
    """[T-1.59] Autodiagnóstico del gabinete = espejo de siren_test (acción de
    dueño del sitio): pulsa gas/puertas con readback. soc_operator DENEGADO —
    opera incidentes, no mantenimiento (divergencia anotada en RBAC §2)."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["self_test"]}
    assert can == {"takab_superadmin", "tenant_admin", "building_admin"}
    siren = {r for r in RBAC_SECTION_2 if allowed_actions(r)["siren_test"]}
    assert can == siren  # mismo círculo de confianza que la prueba de sirena


def test_drill_start_is_institutional_admin_action() -> None:
    """[T-1.60] Iniciar un simulacro es un acto ADMINISTRATIVO del tenant
    (banner NO-real + voceo en N sitios): superadmin/tenant_admin. Ni gov
    (lectura del registro por RLS) ni operadores/inspectores."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["drill_start"]}
    assert can == {"takab_superadmin", "tenant_admin"}


def test_manage_retire_code_is_superadmin_only() -> None:
    """[T-2.36] El segundo factor del retiro lo rota TAKAB, no el cliente.

    Si ``tenant_admin`` pudiera rotar su propio código, el segundo factor volvería a
    ser el primero (su sesión) y la fricción del retiro sería decorativa.
    """
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_retire_code"]}
    assert can == {"takab_superadmin"}


def test_manage_tenants_is_superadmin_only() -> None:
    """[T-1.72] Alta de clientes (POST /tenants) = acto del DUEÑO de la plataforma.
    Solo takab_superadmin: tenant_admin no da de alta OTROS clientes; support lee la
    plataforma, no la provisiona. La RLS ``tenants_admin`` ya exige superadmin."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_tenants"]}
    assert can == {"takab_superadmin"}


def test_manage_visibility_is_superadmin_only() -> None:
    """[T-1.73] Conceder/revocar visibilidad entre clientes toca la frontera de
    aislamiento multi-tenant: SOLO takab_superadmin. La RLS ``vg_admin`` lo exige igual."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_visibility"]}
    assert can == {"takab_superadmin"}


def test_manage_users_excludes_support() -> None:
    """[T-2.54] Repartir identidades = repartir ACCESO A DATOS: ``custom:tenant_id``
    y ``custom:role`` son los dos claims donde se ancla la RLS (regla de oro 5).

    Es del dueño de la plataforma y del dueño del cliente, nunca de soporte — que en
    §2 tiene "Total" en Flota Edge y aun así no puebla el directorio, misma
    disciplina que ``manage_fleet``.
    """
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_users"]}
    assert can == {"takab_superadmin", "tenant_admin"}
    assert allowed_actions("takab_support")["manage_users"] is False


def test_mobile_roles_have_only_mobile_actions() -> None:
    """[T-2.03] Los roles móviles dejaron de ser placeholders, pero sus acciones
    son EXCLUSIVAMENTE de campo: ninguna acción del SOC web se les concede."""
    for role in MOBILE_ONLY:
        granted = {a for a, ok in allowed_actions(role).items() if ok}
        assert granted, role  # ya no están vacíos
        assert granted <= set(MOBILE_ACTIONS), (role, granted - set(MOBILE_ACTIONS))


def test_occupant_field_actions_are_minimal() -> None:
    """[T-2.03] occupant = SOLO su check-in y su voto de pánico (quórum 2/30 s;
    RBAC §4: jamás deslizar-para-activar individual)."""
    granted = {a for a, ok in allowed_actions("occupant").items() if ok}
    assert granted == {"checkin_submit", "panic_vote"}


# Copiado A MANO de RBAC-TAKAB.md §3 (matriz móvil), fila por fila, para las
# funciones que YA tienen acción ejecutable. (Las filas de solo lectura —
# estado del edificio, crisis — no gatean por acción; el DASHBOARD TÁCTICO sí
# desde T-2.08: ``panel_read`` espeja la fila "Dashboard táctico (salud
# gabinete + actuadores)" — occupant "—", inspector "Lectura".)
RBAC_SECTION_3 = {
    #                 checkin roster  damage  evid.  silence activate dict_read panel
    "occupant": (True, False, False, False, False, False, False, False),
    "brigadista": (True, True, True, True, True, True, True, True),
    "security_guard": (True, True, True, True, True, True, True, True),
    "inspector": (True, False, True, True, False, True, True, True),
    "building_admin": (True, True, False, False, True, True, True, True),
}
_S3_COLS = (
    "checkin_submit",
    "roster_read",
    "damage_report_submit",
    "evidence_upload",
    "siren_silence",
    "manual_activate",
    "dictamen_read",
    "panel_read",
)


def test_mobile_actions_match_rbac_section_3() -> None:
    """[T-2.03] La matriz móvil del código es idéntica a RBAC-TAKAB.md §3,
    celda a celda (misma disciplina que §2 para la web)."""
    for role, cells in RBAC_SECTION_3.items():
        acts = allowed_actions(role)
        for col, expected in zip(_S3_COLS, cells, strict=True):
            assert acts[col] is expected, (role, col)


def test_panic_vote_is_occupant_only() -> None:
    """[T-2.03] El voto de pánico es del occupant (quórum de 2); los tácticos ya
    tienen ``manual_activate`` individual — dárselo duplicaría el camino."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["panic_vote"]}
    assert can == {"occupant"}


def test_siren_silence_excludes_inspector() -> None:
    """[T-2.03] RBAC §4: silenciar = brigadista/security_guard/building_admin.
    El inspector evalúa la estructura; no opera la sirena."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["siren_silence"]}
    assert can == {"brigadista", "security_guard", "building_admin"}


def test_enrollment_manage_is_admin_circle() -> None:
    """[T-2.03] Administrar códigos de alta = dueño del sitio/tenant/plataforma;
    jamás un rol de campo ni gov."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["enrollment_manage"]}
    assert can == {"takab_superadmin", "tenant_admin", "building_admin"}


def test_platform_roles_have_no_field_actions() -> None:
    """[T-2.03] Las acciones de CAMPO exigen presencia con identidad de roster:
    superadmin/support/soc/gov NO las reciben (un "Total" de plataforma no pasa
    lista ni silencia sirenas desde un escritorio)."""
    field_only = set(MOBILE_ACTIONS) - {"enrollment_manage"}
    for role in ("takab_superadmin", "takab_support", "soc_operator", "gov_operator"):
        granted = {a for a, ok in allowed_actions(role).items() if ok}
        assert granted.isdisjoint(field_only), (role, granted & field_only)


def test_maintenance_window_is_tenant_admin_action_not_a_field_role() -> None:
    """[T-2.71] Abrir una ventana de mantenimiento silencia las alarmas de on-call
    de un gabinete. Es un acto ADMINISTRATIVO del tenant — mismo círculo que
    ``drill_start``, NO el de ``self_test``.

    La diferencia con ``self_test`` es deliberada y hay que poder leerla aquí:
    ``building_admin`` sí prueba los relés de SU inmueble, pero §2 le da "—" en
    Flota Edge, así que concederle esta acción pintaría un control en una ruta que
    no tiene (regla de oro 7). Y lo que se apaga no es un dispositivo del
    edificio: es el correo que despierta al on-call de TAKAB.
    """
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["maintenance_window"]}
    assert can == {"takab_superadmin", "tenant_admin"}
    assert can == {r for r in RBAC_SECTION_2 if allowed_actions(r)["drill_start"]}
    # …y NO es el círculo de self_test: building_admin queda fuera a propósito.
    assert can != {r for r in RBAC_SECTION_2 if allowed_actions(r)["self_test"]}


def test_toda_ventana_de_mantenimiento_se_abre_desde_una_ruta_que_el_rol_tiene() -> None:
    """Regla de oro 7 medida: el control vive en ``/fleet``. Un rol con la acción
    y sin la ruta sería un botón invisible o un 403 garantizado."""
    for role in RBAC_SECTION_2:
        if allowed_actions(role)["maintenance_window"]:
            assert FLEET in ROLE_ROUTE_MATRIX[role], role


def test_platform_maintenance_window_is_superadmin_only() -> None:
    """[T-2.71] Las alarmas ``ec2_*`` vigilan la instancia donde corren la API, la
    DB y los workers de TODOS los clientes. Ningún tenant puede callarlas, ni
    siquiera un rato: mismo criterio que ``manage_tenants``/``manage_visibility``/
    ``manage_retire_code``."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["platform_maintenance_window"]}
    assert can == {"takab_superadmin"}
    assert can == {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_tenants"]}


def test_la_ventana_de_plataforma_es_un_subconjunto_estricto_de_la_de_gabinete() -> None:
    """Quien puede callar la plataforma puede callar un gabinete, nunca al revés.
    Si algún día se invirtiera, un tenant_admin apagaría la vigilancia de la infra
    común desde el mismo botón."""
    plataforma = {r for r in RBAC_SECTION_2 if allowed_actions(r)["platform_maintenance_window"]}
    gabinete = {r for r in RBAC_SECTION_2 if allowed_actions(r)["maintenance_window"]}
    assert plataforma < gabinete


# ---------------------------------------------------------------------------
# [T-2.79.e] Superficie de PRIVACIDAD: publicar el aviso del tenant.
# ---------------------------------------------------------------------------

#: Copia A MANO del conjunto que gobernaba ``routers/privacy`` **antes** de que la
#: acción existiera, cuando ``NOTICE_ROLES`` era una tupla literal en el router.
#:
#: Es un test CARACTERIZADOR y por eso no se deriva de nada: no dice lo que la
#: frontera *debería* ser, dice lo que **era** el día que se movió a la matriz. Si
#: derivarla de ``ROLE_ACTION_MATRIX`` hubiera cambiado quién publica el aviso de un
#: cliente, esto lo habría gritado — que es justo lo que una "mera refactorización"
#: no puede permitirse callar.
PRIVACY_NOTICE_ROLES_ANTES = {"takab_superadmin", "tenant_admin"}


def test_publicar_aviso_conserva_exactamente_los_roles_que_tenia_el_router() -> None:
    """La frontera de ``POST /privacy/notices`` no se movió al salir del router."""
    assert set(privacy_router.NOTICE_ROLES) == PRIVACY_NOTICE_ROLES_ANTES


def test_manage_privacy_notice_is_the_tenant_owner_circle() -> None:
    """[T-2.79.e] Bajo la LFPDPPP el *responsable* de los datos de los ocupantes de
    un inmueble es la organización dueña del inmueble: publicar su aviso —y dejar
    constancia del consentimiento de un tercero sin sesión— es un acto SUYO.

    ``takab_support`` queda fuera a propósito, pese a su "Total" en §2: soporte lee
    la plataforma, no firma el aviso de privacidad de un cliente en su nombre. Misma
    disciplina que ``manage_fleet`` y ``manage_users``.
    """
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_privacy_notice"]}
    assert can == {"takab_superadmin", "tenant_admin"}
    assert allowed_actions("takab_support")["manage_privacy_notice"] is False
    # Mismo círculo que los otros actos administrativos del dueño del cliente.
    assert can == {r for r in RBAC_SECTION_2 if allowed_actions(r)["drill_start"]}


def test_el_router_de_privacidad_consulta_la_matriz_y_no_su_propia_lista() -> None:
    """[T-2.79.e] ``NOTICE_ROLES`` es DERIVADO, no declarado.

    El test caracterizador de arriba fija el VALOR; este fija el ORIGEN. Sin los dos,
    alguien podría "arreglar" la coherencia copiando el mismo par de roles otra vez a
    mano y los dos tests seguirían en verde.
    """
    assert privacy_router.NOTICE_ROLES == roles_with_action("manage_privacy_notice")


def test_manage_privacy_erasure_is_the_responsible_circle() -> None:
    """[T-2.80.b] Una solicitud ARCO por escrito se le manda AL RESPONSABLE del
    tratamiento —la organización dueña del inmueble—, no a TAKAB. Mismo círculo
    que publicar su aviso, y ``takab_support`` fuera por el mismo criterio:
    soporte lee la plataforma, no anonimiza al ocupante de un cliente en su
    nombre.
    """
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_privacy_erasure"]}
    assert can == {"takab_superadmin", "tenant_admin"}
    assert allowed_actions("takab_support")["manage_privacy_erasure"] is False
    assert can == {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_privacy_notice"]}


def test_ejercer_arco_por_otro_es_una_accion_APARTE_de_publicar_el_aviso() -> None:
    """[T-2.80.b] Comparten roles HOY y siguen siendo dos acciones, a propósito.

    Publicar un aviso se deshace publicando otra versión; anonimizar a una persona
    no se deshace. Fundirlas obligaría a conceder la irreversible para dar la
    reversible el día que los círculos dejen de coincidir — y ese día nadie se
    acordaría de que el fusionado era una casualidad de 2026.
    """
    assert "manage_privacy_erasure" in ACTIONS
    assert "manage_privacy_notice" in ACTIONS
    assert privacy_router.ERASURE_ROLES == roles_with_action("manage_privacy_erasure")


def test_el_derecho_del_titular_sigue_sin_llevar_rol() -> None:
    """[T-2.80.b] La acción nueva NO gatea ``POST /privacy/erasure``.

    Ejercer ARCO sobre uno mismo es un derecho, no un permiso: si la puerta del
    responsable hubiera acabado gateando también la del titular, la tarea habría
    convertido un derecho en un privilegio — exactamente lo que ``RBAC-TAKAB.md``
    dice que no puede pasar.
    """

    def _guardas(path: str, metodo: str) -> set[str]:
        ruta = next(
            r
            for r in privacy_router.router.routes
            if getattr(r, "path", "") == path and metodo in getattr(r, "methods", set())
        )
        return {
            d.call.__name__
            for d in ruta.dependant.dependencies  # type: ignore[attr-defined]
            if getattr(d, "call", None) is not None
        }

    # `require_roles` devuelve una closure llamada `_dep`: su presencia ES la guarda.
    assert "_dep" not in _guardas("/privacy/erasure", "POST"), (
        "`POST /privacy/erasure` ganó una guarda de rol: el ARCO del titular sobre "
        "sí mismo es un derecho, no un permiso que se concede"
    )
    # Y el contraste, que es lo que hace útil al assert de arriba: la puerta del
    # RESPONSABLE sí la lleva, en los dos actos.
    assert "_dep" in _guardas("/privacy/erasure-requests", "POST")
    assert "_dep" in _guardas("/privacy/erasure-requests/{request_id}/erasure", "POST")


# ---------------------------------------------------------------------------
# [T-2.79.e · criterio 3] Barrido: ninguna superficie de privacidad lista roles.
# ---------------------------------------------------------------------------

_SRC = Path(privacy_router.__file__).resolve().parents[1]

#: Excepción NOMBRADA y única. ``privacy/retention.py`` declara el ``app.role`` con
#: el que se degrada la sesión del JOB de retención: es una identidad **máquina**
#: (RBAC-TAKAB.md — las identidades máquina no son roles RBAC), no una respuesta a
#: "quién puede pulsar esto". No hay portador de token ni acción de matriz que
#: derivar, así que no tiene sitio en ``ROLE_ACTION_MATRIX``.
LITERALES_DE_ROL_PERMITIDOS: frozenset[tuple[str, str]] = frozenset(
    {("privacy/retention.py", "takab_support")}
)


def _superficies_de_privacidad() -> list[Path]:
    """Se calcula, no se lista: un fichero nuevo en ``privacy/`` entra solo."""
    rutas = [
        *sorted((_SRC / "privacy").glob("*.py")),
        _SRC / "routers" / "privacy.py",
        _SRC / "routers" / "compliance.py",
        _SRC / "schemas" / "privacy.py",
        _SRC / "schemas" / "compliance.py",
        _SRC / "queries" / "compliance.py",
        _SRC / "compliance.py",
    ]
    return [r for r in rutas if r.exists()]


def test_ninguna_superficie_de_privacidad_enumera_roles_a_mano() -> None:
    """[T-2.79.e] La deuda cerrada no puede volver por otra puerta.

    Se mira el AST y se compara por IGUALDAD, así que la PROSA sigue libre: un
    comentario que explique por qué ``takab_support`` queda fuera no es una lista de
    roles, es la razón de una. Lo que se prohíbe es que un nombre de rol sea un
    VALOR del código en estos ficheros — ahí es donde deja de haber una sola verdad.
    """
    encontrados: set[tuple[str, str]] = set()
    for ruta in _superficies_de_privacidad():
        rel = ruta.relative_to(_SRC).as_posix()
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
                continue
            if nodo.value in RBAC_SECTION_2:
                encontrados.add((rel, nodo.value))
    assert encontrados <= LITERALES_DE_ROL_PERMITIDOS, (
        "una superficie de privacidad volvió a enumerar roles a mano: "
        f"{sorted(encontrados - LITERALES_DE_ROL_PERMITIDOS)}. "
        "Deriva de `auth/matrix.roles_with_action(...)`."
    )


def test_deploy_firmware_is_platform_not_tenant() -> None:
    """[T-2.70] Activar una release es una acción de PLATAFORMA, no de cliente.

    El código que se activa es de TAKAB, el artefacto lo puso su operador y una
    versión mala deja un edificio sin sirena, sin cierre de gas y sin
    retenedores. `tenant_admin` tiene `maintenance_window` —puede callar las
    alarmas de SU gabinete— y aun así NO puede empujarle una versión: no tiene
    el artefacto ni con qué juzgarlo.
    """
    assert set(roles_with_action("deploy_firmware")) == {"takab_superadmin"}
    # Y el contraste que da sentido a la frontera: la ventana de gabinete sí es
    # del círculo del cliente. Si algún día coincidieran, alguien movió una de
    # las dos sin decidirlo.
    assert "tenant_admin" in roles_with_action("maintenance_window")
    assert "tenant_admin" not in roles_with_action("deploy_firmware")
