import { describe, expect, it } from "vitest";

import type { GatewayOut, RuleSetOut } from "@takab/sdk";

import { buildCabinets } from "./useFleet";

/**
 * [T-2.70.a·B1] El grid de actuadores dejaba de decir la verdad.
 *
 * `armed` se derivaba SOLO de que el enlace estuviera vivo, con el argumento de
 * que el supervisor edge trata los actuadores como módulo crítico fail-fast:
 * proceso vivo ⇒ reglas armadas. D3 rompió esa implicación al sacar al dueño de
 * los pines a `takab-gpio`: con `gpio_owner=gpio` y ese proceso caído,
 * `takab-edge` late cada 60 s con todas sus métricas perfectas y **nadie**
 * gobierna la sirena, el gas, los ascensores ni los retenedores.
 *
 * El resultado medido era el peor posible: cinco tarjetas en verde diciendo
 * ARMADO sobre un edificio sin ninguna de sus cuatro protecciones.
 */

const GW: GatewayOut = {
  gateway_id: "g-70a",
  site_id: "s-70a",
  site_name: "Planta Cholula",
  site_code: "CHL-A",
  site_status: "active",
  serial: "TKB-070A",
  fw_version: "62f3f1e",
  iot_thing: "gw-dev-0001",
  status: "active",
  has_wr1: true,
  installed_at: null,
  row_version: "1",
  derived_state: "OPERATIVO",
  last_heartbeat_ts: "2026-08-08T10:41:00Z",
  power_status: "line",
  battery_pct: 100,
  cert_days_remaining: 200,
  mqtt_rtt_ms: 42.5,
  seedlink_lag_s: 0.4,
  ntp_offset_ms: 3.2,
};

const RS: RuleSetOut = {
  rule_set_id: "rs-70a",
  tenant_id: "t-70a",
  scope_type: "site",
  scope_id: "s-70a",
  version: 1,
  is_active: true,
  config: { relays: { siren: "NO", gas_valve: "fail_close" } },
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
};

function armados(gw: GatewayOut): (boolean | null)[] {
  const [cab] = buildCabinets([gw], [RS]);
  return (cab.relays ?? []).map((r) => r.armed);
}

describe("useFleet · el censo de relés manda sobre el enlace [T-2.70.a·B1]", () => {
  it("sin dueño de pines NO se pinta ARMADO, aunque el gabinete late perfecto", () => {
    const huerfano = { ...GW, relays_state: "unreadable" };
    expect(armados(huerfano)).toEqual([null, null]);
  });

  it("con el censo publicado sigue diciendo ARMADO (no-vacuidad)", () => {
    expect(armados({ ...GW, relays_state: "reported" })).toEqual([true, true]);
  });

  it("módulo detenido tampoco es ARMADO: nadie está tocando esos relés", () => {
    expect(armados({ ...GW, relays_state: "stopped" })).toEqual([null, null]);
  });

  it("un firmware que no opina conserva la conducta previa, no se tiñe de S/D", () => {
    // Compatibilidad hacia atrás: marcar S/D a toda la flota ≤1.9.0 por un campo
    // que su firmware no sabe emitir sería inventar una avería.
    expect(armados(GW)).toEqual([true, true]);
    expect(armados({ ...GW, relays_state: null })).toEqual([true, true]);
  });

  it("SIN ENLACE sigue mandando sobre cualquier censo", () => {
    const mudo = { ...GW, derived_state: "SIN ENLACE", relays_state: "reported" };
    expect(armados(mudo)).toEqual([null, null]);
  });
});
