import type { GatewayConfigStateOut, RuleSetOut, SiteOut, TenantOut } from "@takab/sdk";

/**
 * Defaults REALES de `ThresholdBand` del edge (`edge/takab_edge/config/settings.py`).
 * Cuando una clave falta en `config.edge.thresholds`, el gabinete aplica ESTE valor
 * (Pydantic lo rellena). Mostrarlo rotulado como default es la única lectura honesta:
 * ni inventamos un 0 ni fingimos que el umbral está "sin configurar".
 */
export const EDGE_THRESHOLD_DEFAULTS = {
  pga_watch_g: 0.04,
  pga_trip_g: 0.06,
  pgv_watch_cms: 2.0,
  pgv_trip_cms: 4.0,
} as const;

export type ThresholdKey = keyof typeof EDGE_THRESHOLD_DEFAULTS;

export const THRESHOLD_KEYS: readonly ThresholdKey[] = [
  "pga_watch_g",
  "pga_trip_g",
  "pgv_watch_cms",
  "pgv_trip_cms",
];

export interface ThresholdValue {
  value: number;
  /** false ⇒ el valor mostrado es el default del edge, no algo que el tenant fijó. */
  fromConfig: boolean;
}

export type ThresholdBand = Record<ThresholdKey, ThresholdValue>;

/** Canales de la cascada, en el ORDEN FIJO del backend (`notify/plan.py`). */
export const CASCADE_ORDER = ["webhook", "whatsapp", "sms", "email"] as const;
export type ChannelKey = (typeof CASCADE_ORDER)[number];

export interface ChannelState {
  key: ChannelKey;
  /** El canal existe en `config.notifications`. */
  enabled: boolean;
  /**
   * El destino está completo según `notify/config.resolve_destinations`. Un canal
   * habilitado sin destino lo OMITE el backend con un warning: pintarlo como activo
   * sería mentir.
   */
  complete: boolean;
  /** Destino legible (url del webhook, teléfono, correos). Nunca el `secret`. */
  destination: string | null;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

/**
 * rule_set ACTIVO de alcance `tenant` del tenant dado (la versión más alta).
 * Los umbrales del edge viven en el scope tenant; el de sitio es una extensión
 * futura de esta pantalla.
 */
export function activeTenantRuleSet(
  ruleSets: RuleSetOut[] | undefined,
  tenantId: string | null,
): RuleSetOut | null {
  const candidates = (ruleSets ?? []).filter(
    (r) => r.is_active && r.scope_type === "tenant" && r.tenant_id === tenantId,
  );
  if (candidates.length === 0) {
    return null;
  }
  return candidates.reduce((a, b) => (b.version > a.version ? b : a));
}

/** `config.edge.thresholds` — la ÚNICA rama que el worker de sync publica al edge. */
export function readThresholds(config: Record<string, unknown> | undefined): ThresholdBand {
  const edge = asRecord(config?.["edge"]);
  const raw = asRecord(edge?.["thresholds"]) ?? {};
  const out = {} as ThresholdBand;
  for (const key of THRESHOLD_KEYS) {
    const v = raw[key];
    out[key] =
      typeof v === "number" && Number.isFinite(v)
        ? { value: v, fromConfig: true }
        : { value: EDGE_THRESHOLD_DEFAULTS[key], fromConfig: false };
  }
  return out;
}

/**
 * Aplica los umbrales dentro de `config.edge.thresholds` PRESERVANDO todo lo demás.
 * `config` es jsonb opaco sin validación server-side: reescribir el blob entero a
 * ciegas borraría `quorum`, `relays`, `notifications` o cualquier clave que esta
 * pantalla no conozca.
 */
export function patchThresholds(
  config: Record<string, unknown> | undefined,
  values: Record<ThresholdKey, number>,
): Record<string, unknown> {
  const base = { ...(config ?? {}) };
  const edge = { ...(asRecord(base["edge"]) ?? {}) };
  const thresholds = { ...(asRecord(edge["thresholds"]) ?? {}) };
  for (const key of THRESHOLD_KEYS) {
    thresholds[key] = values[key];
  }
  edge["thresholds"] = thresholds;
  base["edge"] = edge;
  return base;
}

/** La banda de cautela nunca puede exceder la de disparo (blueprint §4.5). */
export function thresholdErrors(values: Record<ThresholdKey, number>): string[] {
  const errs: string[] = [];
  if (values.pga_watch_g > values.pga_trip_g) {
    errs.push("PGA: la banda de cautela no puede superar la de disparo");
  }
  if (values.pgv_watch_cms > values.pgv_trip_cms) {
    errs.push("PGV: la banda de cautela no puede superar la de disparo");
  }
  for (const key of THRESHOLD_KEYS) {
    if (!(values[key] > 0)) {
      errs.push(`${key}: debe ser mayor que cero`);
    }
  }
  return errs;
}

function destinationOf(key: ChannelKey, raw: Record<string, unknown>): ChannelState {
  if (key === "webhook") {
    const url = raw["url"];
    const ok = typeof url === "string" && url.length > 0;
    return { key, enabled: true, complete: ok, destination: ok ? (url as string) : null };
  }
  if (key === "email") {
    const to = raw["to"];
    const list = typeof to === "string" && to ? [to] : Array.isArray(to) ? to : [];
    const ok = list.length > 0 && list.every((x) => typeof x === "string" && x);
    return { key, enabled: true, complete: ok, destination: ok ? list.join(", ") : null };
  }
  const to = raw["to"];
  const ok = typeof to === "string" && to.length > 0;
  return { key, enabled: true, complete: ok, destination: ok ? (to as string) : null };
}

/**
 * Estado de los 4 canales, en el orden fijo de la cascada. Espeja exactamente la
 * validación de `notify/config.resolve_destinations`: lo que el backend omitiría,
 * aquí se marca INCOMPLETO en vez de pintarse como activo.
 */
export function readChannels(config: Record<string, unknown> | undefined): ChannelState[] {
  const raw = asRecord(config?.["notifications"]) ?? {};
  return CASCADE_ORDER.map((key) => {
    const entry = asRecord(raw[key]);
    if (entry === null) {
      return { key, enabled: false, complete: false, destination: null };
    }
    return destinationOf(key, entry);
  });
}

/**
 * Escribe los canales en `config.notifications`.
 *
 * El `secret` del webhook NO viaja al cliente (el servidor lo redacta en
 * `GET /rule-sets`) y por tanto tampoco se re-envía: al guardar, el backend
 * reinyecta el vigente (`schemas/rule_sets.merge_secrets`). Intentar conservarlo
 * aquí sería, en el mejor caso, propagar un secreto por la caché del navegador; y
 * en el peor, borrarlo al deshabilitar y re-habilitar el canal.
 *
 * Un canal deshabilitado se ELIMINA de `notifications` (así es como
 * `resolve_destinations` entiende "no configurado") y el servidor descarta su
 * secret con él: es la intención explícita del operador.
 *
 * [T-1.62] Esta pantalla escribe SOLO los cuatro canales de la cascada. Arrancar
 * con `next = {}` reescribía `notifications` entero y BORRABA lo que no conoce
 * — `inspector_emails` (T-1.61) desaparecía al guardar cualquier canal, y el
 * correo del inspector se apagaba sin dejar rastro en la BD. Se parte de lo
 * vigente y solo se reescriben las claves propias, igual que `patchThresholds`.
 */
export function patchChannels(
  config: Record<string, unknown> | undefined,
  drafts: ChannelDraft[],
): Record<string, unknown> {
  const base = { ...(config ?? {}) };
  const next: Record<string, unknown> = { ...(asRecord(base["notifications"]) ?? {}) };
  for (const key of CASCADE_ORDER) {
    delete next[key]; // los canales se reconstruyen desde los drafts (sin secret)
  }

  for (const draft of drafts) {
    if (!draft.enabled) {
      continue;
    }
    if (draft.key === "webhook") {
      next[draft.key] = { url: draft.destination.trim() };
    } else if (draft.key === "email") {
      next[draft.key] = {
        to: draft.destination
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s !== ""),
      };
    } else {
      next[draft.key] = { to: draft.destination.trim() };
    }
  }

  base["notifications"] = next;
  return base;
}

export interface ChannelDraft {
  key: ChannelKey;
  enabled: boolean;
  destination: string;
}

/** Borrador editable a partir del estado leído del config. */
export function draftsFrom(channels: ChannelState[]): ChannelDraft[] {
  return channels.map((c) => ({
    key: c.key,
    enabled: c.enabled,
    destination: c.destination ?? "",
  }));
}

/** Un canal habilitado sin destino sería omitido por el backend: se avisa. */
export function channelErrors(drafts: ChannelDraft[]): string[] {
  return drafts
    .filter((d) => d.enabled && d.destination.trim() === "")
    .map((d) => `${d.key}: habilitado sin destino — el backend lo omitiría`);
}

export type SyncStatus = "synced" | "pending" | "partial" | "no-gateways" | "unknown";

/**
 * Estado del sync firmado del tenant a partir del `config-state` REAL de cada
 * gabinete. `publish` sólo devuelve 202 `pending_sync`: sin este dato la consola
 * no puede afirmar que la config llegó.
 *
 * Sólo cuentan los gateways sincronizables (el worker excluye retirados y sin
 * `iot_thing`): incluirlos dejaría el tenant en PENDIENTE para siempre.
 */
export function syncStatusOf(states: GatewayConfigStateOut[] | undefined): SyncStatus {
  if (states === undefined) {
    return "unknown";
  }
  const relevant = states.filter((s) => s.is_syncable && s.has_edge_config);
  if (relevant.length === 0) {
    return "no-gateways";
  }
  const synced = relevant.filter((s) => s.in_sync).length;
  if (synced === relevant.length) {
    return "synced";
  }
  return synced === 0 ? "pending" : "partial";
}

/**
 * Huella de la config firmada que corre en los gabinetes, si TODOS traen la misma.
 *
 * Deliberadamente NO se muestra `GatewayConfigStateOut.version`: es un contador de
 * ENTREGAS por gateway (`commands/sync.py`: `(state_version or 0) + 1`), no la
 * `rule_sets.version`. Ponerlos juntos ("v3 en el edge · v8 publicada") sugería un
 * atraso de cinco versiones que no existe, y los dos contadores jamás convergen.
 * La huella sí identifica QUÉ config está aplicada.
 */
export function syncedFingerprintOf(states: GatewayConfigStateOut[] | undefined): string | null {
  const prints = (states ?? [])
    .filter((s) => s.is_syncable && s.in_sync)
    .map((s) => s.sig_fingerprint)
    .filter((p): p is string => typeof p === "string" && p !== "");
  if (prints.length === 0) {
    return null;
  }
  return prints.every((p) => p === prints[0]) ? prints[0] : null;
}

/** Sitios del tenant (para la ficha). `users` no tiene endpoint: no se muestra. */
export function siteCountOf(sites: SiteOut[] | undefined, tenantId: string): number | null {
  return sites === undefined ? null : sites.filter((s) => s.tenant_id === tenantId).length;
}

/** `tenants.vertical` es texto libre y nullable: es el "tipo de instalación". */
export function verticalOf(tenant: TenantOut): string {
  return tenant.vertical && tenant.vertical.trim() !== "" ? tenant.vertical : "SIN CLASIFICAR";
}

/** `isolation_mode` viene del CHECK ('logical','dedicated') — se pinta tal cual. */
export function isDedicated(tenant: TenantOut): boolean {
  return tenant.isolation_mode === "dedicated";
}

/** Bandas de referencia del blueprint §4.5. PISTA estática, no una agrupación real:
 * los umbrales se guardan por scope de rule_set, no por vertical. */
export const REFERENCE_BANDS =
  "Hospitales 0.040–0.060 g · Industriales 0.080–0.120 g · Corporativos 0.100–0.150 g";
