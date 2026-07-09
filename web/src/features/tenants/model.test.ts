import { describe, expect, it } from "vitest";

import type { GatewayConfigStateOut, RuleSetOut, TenantOut } from "@takab/sdk";

import {
  EDGE_THRESHOLD_DEFAULTS,
  activeTenantRuleSet,
  channelErrors,
  draftsFrom,
  isDedicated,
  patchChannels,
  patchThresholds,
  readChannels,
  readThresholds,
  siteCountOf,
  syncStatusOf,
  syncedFingerprintOf,
  thresholdErrors,
  verticalOf,
} from "./model";

function ruleSet(over: Partial<RuleSetOut> = {}): RuleSetOut {
  return {
    rule_set_id: "rs-1",
    tenant_id: "t-1",
    scope_type: "tenant",
    scope_id: "t-1",
    version: 1,
    is_active: true,
    config: {},
    created_by: null,
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function tenant(over: Partial<TenantOut> = {}): TenantOut {
  return {
    tenant_id: "t-1",
    code: "TKB-001",
    name: "Industrias del Valle",
    isolation_mode: "logical",
    vertical: "Industrial",
    visibility: "private",
    status: "active",
    plan_code: "mvp",
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function cfgState(over: Partial<GatewayConfigStateOut> = {}): GatewayConfigStateOut {
  return {
    gateway_id: "g-1",
    version: 3,
    published_at: "2026-07-08T10:00:00Z",
    sig_fingerprint: "abc123",
    in_sync: true,
    has_edge_config: true,
    is_syncable: true,
    ...over,
  };
}

describe("activeTenantRuleSet", () => {
  it("toma el activo de scope tenant con la versión más alta", () => {
    const rs = activeTenantRuleSet(
      [ruleSet({ version: 1 }), ruleSet({ rule_set_id: "rs-9", version: 9 })],
      "t-1",
    );
    expect(rs?.rule_set_id).toBe("rs-9");
  });

  it("ignora inactivos, otros scopes y otros tenants", () => {
    expect(activeTenantRuleSet([ruleSet({ is_active: false })], "t-1")).toBeNull();
    expect(activeTenantRuleSet([ruleSet({ scope_type: "site" })], "t-1")).toBeNull();
    expect(activeTenantRuleSet([ruleSet({ tenant_id: "otro" })], "t-1")).toBeNull();
    expect(activeTenantRuleSet(undefined, "t-1")).toBeNull();
  });
});

describe("readThresholds · nunca inventa un umbral", () => {
  it("lee config.edge.thresholds (la rama que el worker publica al edge)", () => {
    const band = readThresholds({ edge: { thresholds: { pga_trip_g: 0.12 } } });
    expect(band.pga_trip_g).toEqual({ value: 0.12, fromConfig: true });
  });

  it("una clave ausente cae al DEFAULT DEL EDGE, rotulado como tal", () => {
    const band = readThresholds({ edge: { thresholds: {} } });
    expect(band.pga_trip_g).toEqual({
      value: EDGE_THRESHOLD_DEFAULTS.pga_trip_g,
      fromConfig: false,
    });
    expect(band.pgv_watch_cms.fromConfig).toBe(false);
  });

  it("config vacío o sin bloque edge ⇒ todos default (el edge los aplicaría)", () => {
    for (const cfg of [undefined, {}, { edge: {} }, { edge: { thresholds: null } }]) {
      const band = readThresholds(cfg as Record<string, unknown> | undefined);
      expect(band.pga_watch_g.fromConfig).toBe(false);
      expect(band.pga_watch_g.value).toBe(EDGE_THRESHOLD_DEFAULTS.pga_watch_g);
    }
  });

  it("un valor no numérico (o NaN) NO se cuela como umbral", () => {
    const band = readThresholds({ edge: { thresholds: { pga_trip_g: "0.12" } } });
    expect(band.pga_trip_g.fromConfig).toBe(false);
  });
});

describe("patchThresholds · el config es jsonb opaco: nada se pierde", () => {
  const values = { pga_watch_g: 0.05, pga_trip_g: 0.09, pgv_watch_cms: 3, pgv_trip_cms: 7 };

  it("preserva las claves que esta pantalla no conoce", () => {
    const out = patchThresholds(
      { quorum: { min_nodes: 3 }, relays: { siren: "NO" }, notifications: { email: {} } },
      values,
    );
    expect(out["quorum"]).toEqual({ min_nodes: 3 });
    expect(out["relays"]).toEqual({ siren: "NO" });
    expect(out["notifications"]).toEqual({ email: {} });
  });

  it("preserva las OTRAS claves de config.edge (sample_rate, etc.)", () => {
    const out = patchThresholds({ edge: { sample_rate: 100, station: "TAKAB" } }, values);
    const edge = out["edge"] as Record<string, unknown>;
    expect(edge["sample_rate"]).toBe(100);
    expect(edge["station"]).toBe("TAKAB");
    expect(edge["thresholds"]).toEqual(values);
  });

  it("no muta el config original", () => {
    const original = { edge: { thresholds: { pga_trip_g: 0.06 } } };
    patchThresholds(original, values);
    expect(original.edge.thresholds.pga_trip_g).toBe(0.06);
  });

  it("crea el bloque edge si no existía", () => {
    expect(patchThresholds({}, values)["edge"]).toEqual({ thresholds: values });
  });
});

describe("thresholdErrors", () => {
  const ok = { pga_watch_g: 0.04, pga_trip_g: 0.06, pgv_watch_cms: 2, pgv_trip_cms: 4 };

  it("una banda válida no tiene errores", () => {
    expect(thresholdErrors(ok)).toEqual([]);
  });

  it("cautela por encima de disparo es inválido (PGA y PGV)", () => {
    expect(thresholdErrors({ ...ok, pga_watch_g: 0.09 })[0]).toMatch(/PGA/);
    expect(thresholdErrors({ ...ok, pgv_watch_cms: 9 })[0]).toMatch(/PGV/);
  });

  it("cero o negativo es inválido", () => {
    expect(thresholdErrors({ ...ok, pga_trip_g: 0 }).join()).toMatch(/mayor que cero/);
  });
});

describe("readChannels · espeja resolve_destinations del backend", () => {
  it("orden FIJO de la cascada, siempre los 4 canales", () => {
    expect(readChannels({}).map((c) => c.key)).toEqual(["webhook", "whatsapp", "sms", "email"]);
  });

  it("canal ausente ⇒ deshabilitado", () => {
    expect(readChannels({ notifications: {} })[0].enabled).toBe(false);
  });

  it("webhook con url ⇒ completo; el secret NUNCA se expone", () => {
    const [webhook] = readChannels({
      notifications: { webhook: { url: "https://x/y", secret: "s3cr3t" } },
    });
    expect(webhook.complete).toBe(true);
    expect(webhook.destination).toBe("https://x/y");
    expect(JSON.stringify(webhook)).not.toContain("s3cr3t");
  });

  it("webhook sin url ⇒ habilitado pero INCOMPLETO (el backend lo omitiría)", () => {
    const [webhook] = readChannels({ notifications: { webhook: { secret: "s" } } });
    expect(webhook.enabled).toBe(true);
    expect(webhook.complete).toBe(false);
  });

  it("sms/whatsapp exigen `to` no vacío", () => {
    const ch = readChannels({ notifications: { sms: { to: "" }, whatsapp: { to: "+52" } } });
    expect(ch.find((c) => c.key === "sms")?.complete).toBe(false);
    expect(ch.find((c) => c.key === "whatsapp")?.complete).toBe(true);
  });

  it("email acepta string o lista, y rechaza lista vacía", () => {
    const one = readChannels({ notifications: { email: { to: "a@b.c" } } });
    expect(one[3].complete).toBe(true);
    const many = readChannels({ notifications: { email: { to: ["a@b.c", "d@e.f"] } } });
    expect(many[3].destination).toBe("a@b.c, d@e.f");
    const none = readChannels({ notifications: { email: { to: [] } } });
    expect(none[3].complete).toBe(false);
  });
});

describe("syncStatusOf · el sync firmado sólo se afirma con evidencia", () => {
  it("sin datos aún ⇒ unknown (no se dice ni sincronizado ni pendiente)", () => {
    expect(syncStatusOf(undefined)).toBe("unknown");
  });

  it("todos in_sync ⇒ synced", () => {
    expect(syncStatusOf([cfgState(), cfgState({ gateway_id: "g-2" })])).toBe("synced");
  });

  it("ninguno in_sync ⇒ pending", () => {
    expect(syncStatusOf([cfgState({ in_sync: false })])).toBe("pending");
  });

  it("algunos sí y otros no ⇒ partial (jamás 'sincronizado')", () => {
    expect(syncStatusOf([cfgState(), cfgState({ gateway_id: "g-2", in_sync: false })])).toBe(
      "partial",
    );
  });

  it("un gateway retirado no deja el tenant en PENDIENTE para siempre", () => {
    expect(syncStatusOf([cfgState({ in_sync: false, is_syncable: false })])).toBe("no-gateways");
  });

  it("un gateway sin bloque edge tampoco: el worker nunca le publicará", () => {
    expect(syncStatusOf([cfgState({ in_sync: false, has_edge_config: false })])).toBe(
      "no-gateways",
    );
  });
});

describe("syncedFingerprintOf · huella, NO la versión del gateway", () => {
  it("todos in_sync con la misma firma ⇒ esa huella", () => {
    expect(
      syncedFingerprintOf([
        cfgState({ sig_fingerprint: "abc" }),
        cfgState({ gateway_id: "g2", sig_fingerprint: "abc" }),
      ]),
    ).toBe("abc");
  });

  it("firmas distintas ⇒ null (no se elige una al azar)", () => {
    expect(
      syncedFingerprintOf([
        cfgState({ sig_fingerprint: "abc" }),
        cfgState({ gateway_id: "g2", sig_fingerprint: "xyz" }),
      ]),
    ).toBeNull();
  });

  it("los gabinetes NO sincronizados no aportan huella", () => {
    expect(syncedFingerprintOf([cfgState({ in_sync: false, sig_fingerprint: "abc" })])).toBeNull();
  });

  it("sin publicaciones ⇒ null", () => {
    expect(syncedFingerprintOf([cfgState({ sig_fingerprint: null })])).toBeNull();
    expect(syncedFingerprintOf(undefined)).toBeNull();
  });

  it("`version` es un contador de ENTREGAS por gateway: dos al día pueden traer 5 y 1", () => {
    // Cualquier min/max de esos contadores sería engañoso junto a rule_sets.version.
    const states = [
      cfgState({ version: 5, sig_fingerprint: "s" }),
      cfgState({ gateway_id: "g2", version: 1, sig_fingerprint: "s" }),
    ];
    expect(syncedFingerprintOf(states)).toBe("s");
    expect(syncStatusOf(states)).toBe("synced");
  });
});

describe("ficha del tenant", () => {
  it("isolation_mode se pinta tal cual del CHECK", () => {
    expect(isDedicated(tenant({ isolation_mode: "dedicated" }))).toBe(true);
    expect(isDedicated(tenant({ isolation_mode: "logical" }))).toBe(false);
  });

  it("vertical nulo o vacío ⇒ SIN CLASIFICAR (texto libre, nullable)", () => {
    expect(verticalOf(tenant({ vertical: null }))).toBe("SIN CLASIFICAR");
    expect(verticalOf(tenant({ vertical: "  " }))).toBe("SIN CLASIFICAR");
    expect(verticalOf(tenant({ vertical: "Hospitalario" }))).toBe("Hospitalario");
  });

  it("sitios se cuentan de /sites; sin datos ⇒ null (nunca 0)", () => {
    expect(siteCountOf(undefined, "t-1")).toBeNull();
    expect(siteCountOf([], "t-1")).toBe(0);
  });
});

describe("patchChannels · escribe notifications sin filtrar el secret", () => {
  const drafts = (over: Partial<Record<string, string | boolean>> = {}) =>
    [
      { key: "webhook" as const, enabled: true, destination: "https://x/y" },
      { key: "whatsapp" as const, enabled: false, destination: "" },
      { key: "sms" as const, enabled: true, destination: "+521234567890" },
      { key: "email" as const, enabled: true, destination: "a@b.c, d@e.f" },
      ...[],
    ].map((d) => ({ ...d, ...over }));

  it("NO reenvía ningún secret: el servidor redacta al leer y reinyecta al escribir", () => {
    // El cliente jamás recibe `secret` (redact_config), así que tampoco lo emite.
    const out = patchChannels({ notifications: { webhook: { url: "https://viejo" } } }, drafts());
    const notif = out["notifications"] as Record<string, Record<string, unknown>>;
    expect(notif["webhook"]).toEqual({ url: "https://x/y" });
    expect(JSON.stringify(out)).not.toContain("secret");
  });

  it("aunque llegara un secret (config vieja en caché), no se propaga", () => {
    const out = patchChannels(
      { notifications: { webhook: { url: "https://viejo", secret: "s3cr3t" } } },
      drafts(),
    );
    expect(JSON.stringify(out)).not.toContain("s3cr3t");
  });

  it("un canal deshabilitado se ELIMINA (así lo entiende resolve_destinations)", () => {
    const out = patchChannels({ notifications: { whatsapp: { to: "+52" } } }, drafts());
    const notif = out["notifications"] as Record<string, unknown>;
    expect(notif["whatsapp"]).toBeUndefined();
    expect("enabled" in (notif as object)).toBe(false);
  });

  it("email se guarda como lista, partiendo por comas", () => {
    const out = patchChannels({}, drafts());
    const notif = out["notifications"] as Record<string, Record<string, unknown>>;
    expect(notif["email"]).toEqual({ to: ["a@b.c", "d@e.f"] });
  });

  it("preserva las demás claves del config (edge, quorum, relays)", () => {
    const out = patchChannels({ edge: { sample_rate: 100 }, quorum: { min_nodes: 3 } }, drafts());
    expect(out["edge"]).toEqual({ sample_rate: 100 });
    expect(out["quorum"]).toEqual({ min_nodes: 3 });
  });

  it("deshabilitar y re-habilitar el webhook no puede perder el secret: el cliente no lo maneja", () => {
    const off = patchChannels({ notifications: { webhook: { url: "https://x" } } }, [
      { key: "webhook", enabled: false, destination: "" },
    ]);
    expect((off["notifications"] as Record<string, unknown>)["webhook"]).toBeUndefined();
    const on = patchChannels(off, [{ key: "webhook", enabled: true, destination: "https://x" }]);
    expect((on["notifications"] as Record<string, Record<string, unknown>>)["webhook"]).toEqual({
      url: "https://x",
    });
  });

  it("round-trip: lo escrito se vuelve a leer igual", () => {
    const out = patchChannels({}, drafts());
    const back = readChannels(out);
    expect(back.find((c) => c.key === "sms")).toMatchObject({
      enabled: true,
      complete: true,
      destination: "+521234567890",
    });
    expect(back.find((c) => c.key === "whatsapp")?.enabled).toBe(false);
  });
});

describe("channelErrors / draftsFrom", () => {
  it("un canal habilitado sin destino se denuncia (el backend lo omitiría)", () => {
    const errs = channelErrors([{ key: "sms", enabled: true, destination: "  " }]);
    expect(errs[0]).toMatch(/sms.*omitiría/);
  });

  it("deshabilitado sin destino no es error", () => {
    expect(channelErrors([{ key: "sms", enabled: false, destination: "" }])).toEqual([]);
  });

  it("draftsFrom convierte el estado leído en borrador editable", () => {
    const drafts = draftsFrom(readChannels({ notifications: { sms: { to: "+52" } } }));
    expect(drafts.find((d) => d.key === "sms")).toEqual({
      key: "sms",
      enabled: true,
      destination: "+52",
    });
    expect(drafts.find((d) => d.key === "email")).toEqual({
      key: "email",
      enabled: false,
      destination: "",
    });
  });
});
