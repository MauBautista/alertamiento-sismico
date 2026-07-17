import type { MeActions, MeResponse } from "../auth/me";

/** Espejo SOLO PARA TESTS de `api/src/takab_api/auth/matrix.py` (ROUTE_ORDER +
 * ROLE_ROUTE_MATRIX + ROLE_ACTION_MATRIX). La app real NUNCA consume esta tabla:
 * nav y guards leen `allowed_routes`/`allowed_actions` del servidor (/me).
 * Si la matriz cambia en el backend, este archivo debe cambiar con ella. */

export const ALL_ROUTES = ["/console", "/fleet", "/triage", "/tenants", "/building"] as const;

export const ACTIONS_NONE: MeActions = {
  ack_incident: false,
  sign_dictamen: false,
  export: false,
  generate_report: false,
  edit_thresholds: false,
  siren_test: false,
  manage_fleet: false,
  relocate_epicenter: false,
  request_dictamen: false,
  read_audit: false,
  self_test: false,
  drill_start: false,
  manage_tenants: false,
  manage_visibility: false,
  // [T-2.03] superficie móvil (la consola no las usa; el espejo debe estar completo)
  checkin_submit: false,
  roster_read: false,
  damage_report_submit: false,
  evidence_upload: false,
  siren_silence: false,
  manual_activate: false,
  enrollment_manage: false,
  panic_vote: false,
  dictamen_read: false,
  panel_read: false,
};

export const TENANT_ID = "11111111-1111-1111-1111-111111111111";

export const WEB_ROLES = [
  "takab_superadmin",
  "takab_support",
  "tenant_admin",
  "soc_operator",
  "gov_operator",
  "inspector",
  "building_admin",
] as const;

export const MOBILE_ONLY_ROLES = ["brigadista", "security_guard", "occupant"] as const;

export type RoleName = (typeof WEB_ROLES)[number] | (typeof MOBILE_ONLY_ROLES)[number];

function me(
  role: RoleName,
  routes: readonly string[],
  actions: Partial<MeActions> = {},
  surface = "web",
): MeResponse {
  return {
    sub: `sub-${role}`,
    tenant_id: TENANT_ID,
    role,
    site_scope: "*",
    surface,
    allowed_routes: [...routes],
    allowed_actions: { ...ACTIONS_NONE, ...actions },
  };
}

export const ME_FIXTURES: Record<RoleName, MeResponse> = {
  takab_superadmin: me("takab_superadmin", ALL_ROUTES, {
    ack_incident: true,
    export: true,
    generate_report: true,
    edit_thresholds: true,
    siren_test: true,
    manage_fleet: true,
    relocate_epicenter: true,
    request_dictamen: true,
    read_audit: true,
    self_test: true,
    drill_start: true,
    manage_tenants: true,
    manage_visibility: true,
    enrollment_manage: true,
  }),
  // Ve la Flota Edge pero no la administra: [DECISION 2026-07-09] en matrix.py.
  takab_support: me("takab_support", ALL_ROUTES, { read_audit: true }),
  tenant_admin: me("tenant_admin", ALL_ROUTES, {
    ack_incident: true,
    edit_thresholds: true,
    siren_test: true,
    manage_fleet: true,
    relocate_epicenter: true,
    request_dictamen: true,
    read_audit: true,
    self_test: true,
    drill_start: true,
    enrollment_manage: true,
  }),
  soc_operator: me("soc_operator", ["/console", "/fleet", "/triage", "/building"], {
    ack_incident: true,
    relocate_epicenter: true,
    request_dictamen: true,
  }),
  gov_operator: me("gov_operator", ["/console", "/fleet", "/triage", "/building"], {
    ack_incident: true,
    export: true,
    read_audit: true,
  }),
  inspector: me("inspector", ["/console", "/triage", "/building"], {
    sign_dictamen: true,
    export: true,
    generate_report: true,
    checkin_submit: true,
    damage_report_submit: true,
    evidence_upload: true,
    manual_activate: true,
    dictamen_read: true,
    panel_read: true,
  }),
  building_admin: me("building_admin", ["/console", "/triage", "/building"], {
    siren_test: true,
    self_test: true,
    checkin_submit: true,
    roster_read: true,
    siren_silence: true,
    manual_activate: true,
    enrollment_manage: true,
    dictamen_read: true,
    panel_read: true,
  }),
  // [T-2.03] Roles móviles: acciones de CAMPO (la web los sigue mandando a
  // MobileOnlyScreen; el espejo refleja matrix.py completo).
  brigadista: me(
    "brigadista",
    [],
    {
      checkin_submit: true,
      roster_read: true,
      damage_report_submit: true,
      evidence_upload: true,
      siren_silence: true,
      manual_activate: true,
      dictamen_read: true,
      panel_read: true,
    },
    "mobile",
  ),
  security_guard: me(
    "security_guard",
    [],
    {
      checkin_submit: true,
      roster_read: true,
      damage_report_submit: true,
      evidence_upload: true,
      siren_silence: true,
      manual_activate: true,
      dictamen_read: true,
      panel_read: true,
    },
    "mobile",
  ),
  occupant: me("occupant", [], { checkin_submit: true, panic_vote: true }, "mobile"),
};
