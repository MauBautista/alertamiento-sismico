// @takab/design-tokens — única fuente de verdad del design system TAKAB
// (spec móvil §9 · T-2.01). Dos vistas del MISMO dato:
//   · cssVariables → mapa plano exacto (de aquí se genera css/tokens.css)
//   · tokens       → vista estructurada para React Native / TS
// más los CONTRATOS SEMÁNTICOS etiqueta→tono que web y móvil deben resolver
// idéntico (SevTag / pill de derived_state — regla: desconocido ⇒ ámbar,
// jamás degradar a ok).

import cssVariables from "../tokens.json";

export { cssVariables };
export type TkCssVariable = keyof typeof cssVariables;

const v = (name: TkCssVariable): string => cssVariables[name];

/** Convierte un token dimensional ("14px", "120ms", "1.25") a número. */
export const toNumber = (value: string): number => {
  const n = Number.parseFloat(value);
  if (Number.isNaN(n)) {
    throw new Error(`token no numérico: ${JSON.stringify(value)}`);
  }
  return n;
};

/** Vista estructurada (mismos valores que cssVariables, byte a byte). */
export const tokens = {
  color: {
    navy: {
      900: v("--tk-navy-900"),
      800: v("--tk-navy-800"),
      700: v("--tk-navy-700"),
      600: v("--tk-navy-600"),
      500: v("--tk-navy-500"),
      400: v("--tk-navy-400"),
    },
    light: {
      100: v("--tk-light-100"),
      200: v("--tk-light-200"),
      300: v("--tk-light-300"),
      400: v("--tk-light-400"),
    },
    cyan: {
      base: v("--tk-cyan"),
      hover: v("--tk-cyan-hover"),
      press: v("--tk-cyan-press"),
      a15: v("--tk-cyan-15"),
      a08: v("--tk-cyan-08"),
    },
    status: {
      normal: v("--tk-status-normal"),
      warning: v("--tk-status-warning"),
      critical: v("--tk-status-critical"),
      normal15: v("--tk-status-normal-15"),
      normal08: v("--tk-status-normal-08"),
      warning15: v("--tk-status-warning-15"),
      warning08: v("--tk-status-warning-08"),
      critical15: v("--tk-status-critical-15"),
      critical08: v("--tk-status-critical-08"),
    },
    fg: {
      primary: v("--tk-fg-1"),
      secondary: v("--tk-fg-2"),
      tertiary: v("--tk-fg-3"),
      disabled: v("--tk-fg-disabled"),
      onLight1: v("--tk-fg-on-light-1"),
      onLight2: v("--tk-fg-on-light-2"),
      onLight3: v("--tk-fg-on-light-3"),
    },
    border: {
      base: v("--tk-border"),
      strong: v("--tk-border-strong"),
      cyan: v("--tk-border-cyan"),
      onLight: v("--tk-border-on-light"),
    },
    surface: {
      0: v("--tk-surface-0"),
      1: v("--tk-surface-1"),
      2: v("--tk-surface-2"),
      3: v("--tk-surface-3"),
      overlay: v("--tk-surface-overlay"),
    },
  },
  font: {
    brand: v("--tk-font-brand"),
    ui: v("--tk-font-ui"),
    mono: v("--tk-font-mono"),
  },
  fontSize: {
    xs: v("--tk-text-xs"),
    sm: v("--tk-text-sm"),
    base: v("--tk-text-base"),
    md: v("--tk-text-md"),
    lg: v("--tk-text-lg"),
    xl: v("--tk-text-xl"),
    "2xl": v("--tk-text-2xl"),
    "3xl": v("--tk-text-3xl"),
    "4xl": v("--tk-text-4xl"),
    "5xl": v("--tk-text-5xl"),
  },
  tracking: {
    tight: v("--tk-tracking-tight"),
    normal: v("--tk-tracking-normal"),
    wide: v("--tk-tracking-wide"),
    mono: v("--tk-tracking-mono"),
  },
  leading: {
    tight: v("--tk-leading-tight"),
    snug: v("--tk-leading-snug"),
    normal: v("--tk-leading-normal"),
    data: v("--tk-leading-data"),
  },
  space: {
    0: v("--tk-space-0"),
    1: v("--tk-space-1"),
    2: v("--tk-space-2"),
    3: v("--tk-space-3"),
    4: v("--tk-space-4"),
    5: v("--tk-space-5"),
    6: v("--tk-space-6"),
    7: v("--tk-space-7"),
    8: v("--tk-space-8"),
  },
  radius: {
    none: v("--tk-radius-none"),
    sm: v("--tk-radius-sm"),
    md: v("--tk-radius-md"),
    lg: v("--tk-radius-lg"),
    pill: v("--tk-radius-pill"),
  },
  shadow: {
    none: v("--tk-shadow-none"),
    card: v("--tk-shadow-card"),
    active: v("--tk-shadow-active"),
    critical: v("--tk-shadow-critical"),
    warning: v("--tk-shadow-warning"),
    modal: v("--tk-shadow-modal"),
  },
  focusRing: v("--tk-focus-ring"),
  motion: {
    ease: v("--tk-ease"),
    easeData: v("--tk-ease-data"),
    durFast: v("--tk-dur-fast"),
    durBase: v("--tk-dur-base"),
    durSlow: v("--tk-dur-slow"),
  },
  layout: {
    gridCols: v("--tk-grid-cols"),
    gridGutter: v("--tk-grid-gutter"),
    sidebarW: v("--tk-sidebar-w"),
    detailW: v("--tk-detail-w"),
  },
  z: {
    nav: v("--tk-z-nav"),
    sticky: v("--tk-z-sticky"),
    modal: v("--tk-z-modal"),
    toast: v("--tk-z-toast"),
    alert: v("--tk-z-alert"),
  },
} as const;

/* =========================================================================
   CONTRATOS SEMÁNTICOS (spec móvil §9.3/§9.4)
   El mapeo etiqueta→tono es DATO del design system, no lógica de cada app.
   ========================================================================= */

/** Tono de estado: ok=verde, warn=ámbar, crit=rojo. */
export type StatusKind = "ok" | "warn" | "crit";

/** Tono → color del semáforo (mismos tokens en web y móvil). */
export const KIND_COLOR: Record<StatusKind, string> = {
  ok: v("--tk-status-normal"),
  warn: v("--tk-status-warning"),
  crit: v("--tk-status-critical"),
};

/** Severidades del CHECK de ``incidents.severity`` (db/schema.sql), menor→mayor. */
export type IncidentSeverity = "info" | "watch" | "warning" | "critical";

/** Severidad de incidente → tono + etiqueta ES (contrato de SevTag). */
export const INCIDENT_SEVERITY: Record<IncidentSeverity, { kind: StatusKind; label: string }> = {
  critical: { kind: "crit", label: "CRÍTICO" },
  warning: { kind: "warn", label: "ADVERTENCIA" },
  watch: { kind: "warn", label: "VIGILANCIA" },
  info: { kind: "ok", label: "NORMAL" },
};

/** Severidad desconocida ⇒ ámbar y texto crudo — jamás degradar a NORMAL. */
export const UNKNOWN_SEVERITY_KIND: StatusKind = "warn";

/** ``gateways.derived_state`` (server) → tono del pill (contrato de SiteCard). */
export const DERIVED_STATE_PILL: Record<string, StatusKind> = {
  OPERATIVO: "ok",
  DEGRADADO: "warn",
  "SIN ENLACE": "crit",
};

/** Estado derivado desconocido ⇒ ámbar, nunca ok. */
export const UNKNOWN_DERIVED_STATE_KIND: StatusKind = "warn";
