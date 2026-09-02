import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render as rtlRender, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GatewayOut } from "@takab/sdk";

// T-1.59: SiteCard monta useSelfTest (react-query + SDK) — se mockean SOLO las
// dos funciones de comandos; el resto del módulo no se usa en esta card.
const sdk = vi.hoisted(() => ({
  issueCommandSitesSiteIdCommandsPost: vi.fn(),
  listCommandsSitesSiteIdCommandsGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import SiteCard from "./SiteCard";
import type { FleetCabinet } from "./useFleet";

/** Render con QueryClient limpio (useSelfTest lo exige); sesión opcional aparte. */
function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
  sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
    data: { items: [] },
    response: { status: 200 },
  });
});

const GW: GatewayOut = {
  gateway_id: "g-1",
  site_id: "s-1",
  site_name: "Planta Cholula",
  site_code: "CHL-A",
  site_status: "active",
  serial: "TKB-0001",
  // [T-2.69] SHA de 7 hex: el ÚNICO formato que produce `deploy/edge/deploy.sh`
  // (`git describe --always --dirty --abbrev=7` sobre un repo SIN TAGS). El
  // `edge-1.4.0` que vivía aquí no lo puede generar producción jamás, y cualquier
  // lógica de deriva escrita contra él se habría validado contra un semver
  // ordenable para luego comportarse distinto con SHAs reales.
  fw_version: "62f3f1e",
  version_state: "AL DÍA",
  releases_behind: 0,
  release_age_s: 7200,
  version_age_s: 42,
  iot_thing: "gw-dev-0001",
  status: "active",
  has_wr1: true,
  installed_at: null,
  row_version: "1",
  derived_state: "OPERATIVO",
  last_heartbeat_ts: "2026-07-08T10:41:00Z",
  power_status: "line",
  battery_pct: 100,
  cert_days_remaining: 200,
  mqtt_rtt_ms: 42.5,
  seedlink_lag_s: 0.4,
  ntp_offset_ms: 3.2,
};

function cabinet(over: Partial<FleetCabinet> = {}, gw: Partial<GatewayOut> = {}): FleetCabinet {
  return {
    gateway: { ...GW, ...gw },
    siteName: "Planta Cholula",
    siteCode: "CHL-A",
    siteStatus: "active",
    relays: [
      { key: "siren", label: "SIRENA", wiring: "NO", armed: true },
      { key: "gas_valve", label: "GAS", wiring: "fail_close", armed: true },
    ],
    ...over,
  };
}

describe("SiteCard", () => {
  it("pinta el estado server-derived tal cual (OPERATIVO ⇒ pill ok)", () => {
    const { container } = render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText("OPERATIVO")).toBeInTheDocument();
    expect(container.querySelector(".soc-pill--ok")).not.toBeNull();
    expect(container.querySelector(".fleet-card--ok")).not.toBeNull();
  });

  it("muestra lags crudos: MQTT ↔ ms y SeedLink lag s", () => {
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText("↔ 42.5 ms")).toBeInTheDocument();
    expect(screen.getByText("lag 0.40 s")).toBeInTheDocument();
  });

  it("SIN ENLACE ⇒ pill crit, pills de enlace en crit con — sin enlace — y relays S/D", () => {
    const { container } = render(
      <SiteCard
        cabinet={cabinet(
          {
            relays: [{ key: "siren", label: "SIRENA", wiring: "NO", armed: null }],
          },
          {
            derived_state: "SIN ENLACE",
            mqtt_rtt_ms: null,
            seedlink_lag_s: null,
            power_status: null,
            battery_pct: null,
            last_heartbeat_ts: null,
          },
        )}
      />,
    );
    expect(screen.getByText("SIN ENLACE")).toBeInTheDocument();
    expect(container.querySelector(".soc-pill--crit")).not.toBeNull();
    expect(screen.getAllByText("— sin enlace —")).toHaveLength(2);
    expect(screen.getByText("S/D")).toBeInTheDocument();
    expect(screen.queryByText("ARMADO")).toBeNull();
    expect(screen.getByText(/HB —/)).toBeInTheDocument();
  });

  it("DEGRADADO ⇒ pill warn; el detalle de la métrica NO se recalcula en UI", () => {
    const { container } = render(
      <SiteCard
        cabinet={cabinet(
          {},
          { derived_state: "DEGRADADO", power_status: "battery", battery_pct: 72 },
        )}
      />,
    );
    expect(screen.getByText("DEGRADADO")).toBeInTheDocument();
    expect(container.querySelector(".soc-pill--warn")).not.toBeNull();
    expect(screen.getByText("EN BATERÍA")).toBeInTheDocument();
  });

  it("DEGRADADO con degrade_reasons ⇒ pills server-derived con QUÉ degrada (T-1.40)", () => {
    render(
      <SiteCard
        cabinet={cabinet(
          {},
          {
            derived_state: "DEGRADADO",
            ntp_offset_ms: 180,
            cert_days_remaining: 12,
            degrade_reasons: ["CERT 12d", "NTP +180ms"],
          },
        )}
      />,
    );
    expect(screen.getByText("CERT 12d")).toBeInTheDocument();
    expect(screen.getByText("NTP +180ms")).toBeInTheDocument();
  });

  it("OPERATIVO jamás pinta razones aunque el campo venga (defensa en la UI)", () => {
    const { container } = render(
      <SiteCard cabinet={cabinet({}, { degrade_reasons: ["CERT 12d"] })} />,
    );
    expect(container.querySelector(".fleet-card__reasons")).toBeNull();
  });

  it("un derived_state desconocido JAMÁS pinta ok", () => {
    const { container } = render(<SiteCard cabinet={cabinet({}, { derived_state: "???" })} />);
    expect(container.querySelector(".soc-pill--ok")).toBeNull();
    expect(container.querySelector(".soc-pill--warn")).not.toBeNull();
  });

  it("relays de la config: etiqueta, numeración y cableado en title + caption honesto", () => {
    const { container } = render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByText("SIRENA")).toBeInTheDocument();
    expect(screen.getByText("GAS")).toBeInTheDocument();
    expect(screen.getAllByText("ARMADO")).toHaveLength(2);
    expect(screen.getByText("R1")).toBeInTheDocument();
    expect(container.querySelector('[title="cableado NO"]')).not.toBeNull();
    expect(screen.getByText("CONFIG ACTIVA · ESTADO DERIVADO DEL ENLACE")).toBeInTheDocument();
  });

  it("sin config visible degrada al badge agregado (enlace vivo)", () => {
    render(<SiteCard cabinet={cabinet({ relays: null })} />);
    expect(screen.getByText("ARMADOS · CONFIG DE RELAYS NO VISIBLE")).toBeInTheDocument();
  });

  it("autodiagnóstico: sin la acción self_test queda deshabilitado con la razón", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    render(<SiteCard cabinet={cabinet()} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringContaining("self_test"));
  });

  it("autodiagnóstico (T-1.59): tenant_admin lo dispara y llega el POST system/self_test", async () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({
      data: { command_id: "c-st-1", status: "pending" },
      response: { status: 201 },
    });
    render(<SiteCard cabinet={cabinet()} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    await waitFor(() =>
      expect(sdk.issueCommandSitesSiteIdCommandsPost).toHaveBeenCalledWith({
        path: { site_id: "s-1" },
        body: { channel: "system", action: "self_test" },
      }),
    );
  });

  it("autodiagnóstico: SIN ENLACE queda deshabilitado (el comando expiraría por TTL)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    render(<SiteCard cabinet={cabinet({}, { derived_state: "SIN ENLACE" })} />);
    const btn = screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringContaining("TTL"));
  });

  it("autodiagnóstico: el ack del edge pinta chips por relé (jamás inventados)", async () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    sdk.issueCommandSitesSiteIdCommandsPost.mockResolvedValue({
      data: { command_id: "c-st-2", status: "pending" },
      response: { status: 201 },
    });
    sdk.listCommandsSitesSiteIdCommandsGet.mockResolvedValue({
      data: {
        items: [
          {
            command_id: "c-st-2",
            status: "acked",
            ack: {
              detail: "self-test completado",
              results: {
                relays: {
                  gas_valve: { pulsed: true, readback_ok: true },
                  elevator: { pulsed: true, readback_ok: false },
                  siren: { pulsed: false, readback_ok: true },
                },
              },
            },
            error: null,
          },
        ],
      },
      response: { status: 200 },
    });
    render(<SiteCard cabinet={cabinet()} />);
    fireEvent.click(screen.getByRole("button", { name: /AUTODIAGNÓSTICO SILENCIOSO/ }));
    const result = await screen.findByTestId("selftest-result");
    expect(result).toHaveTextContent("GAS_VALVE ✓");
    expect(result).toHaveTextContent("ELEVATOR ✗");
    expect(result).toHaveTextContent("SIREN LECTURA"); // la sirena solo se lee
  });

  it("footer con fw y último heartbeat en UTC", () => {
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.getByTestId("version-badge")).toHaveTextContent(/62f3f1e/);
    expect(screen.getByText(/HB 10:41:00 UTC/)).toBeInTheDocument();
  });

  // [T-2.69] El chip antiguo pintaba `gw.fw_version` a secas: un gabinete callado
  // tres semanas mostraba su versión EXACTAMENTE igual que uno que acababa de
  // confirmarla. Es el defecto del 14-jul en su forma de versiones.
  it("un gabinete SIN ENLACE no pinta su versión como si fuera la que corre", () => {
    render(
      <SiteCard
        cabinet={cabinet(
          {},
          {
            derived_state: "SIN ENLACE",
            version_state: "ÚLTIMA CONOCIDA",
            version_age_s: 21 * 86_400,
          },
        )}
      />,
    );
    const badge = screen.getByTestId("version-badge");
    expect(badge).toHaveTextContent(/ÚLTIMA CONOCIDA/);
    expect(badge).toHaveTextContent(/21 d/); // la edad del dato, en el rótulo
    expect(badge).not.toHaveTextContent(/AL DÍA/);
  });

  it("un gabinete que late y no declara versión dice S/D, no la versión vieja", () => {
    render(<SiteCard cabinet={cabinet({}, { version_state: "NO DECLARA" })} />);
    const badge = screen.getByTestId("version-badge");
    expect(badge).toHaveTextContent(/S\/D/);
    expect(badge).not.toHaveTextContent(/62f3f1e/);
  });
});

// --- [T-2.71] Ventana de mantenimiento: ADITIVA, jamás sustitutiva ------------

const MW = {
  window_id: "w-1",
  tenant_id: "t-1",
  gateway_id: "g-1",
  gateway_serial: "TKB-0001",
  site_name: "Planta Cholula",
  scope: "gateway",
  opened_by: "u-1",
  reason: "cambio del cable de red del Shake",
  duration_s: 1800,
  opened_at: "2026-08-06T03:30:12Z",
  starts_at: "2026-08-06T03:31:00Z",
  ends_at: "2026-08-06T04:01:00Z",
  closed_at: null,
  active: true,
  alarm_names: ["a", "b"],
  requested: 2,
  silenced: 2,
  missing_names: [],
  missing: 0,
  mute_rule: "takab-dev-mw-w-1",
};

describe("ventana de mantenimiento en la tarjeta", () => {
  it("añade el rótulo con la hora UTC de cierre", () => {
    render(<SiteCard cabinet={cabinet()} maintenance={MW as never} />);
    expect(screen.getByText(/EN MANTENIMIENTO HASTA 04:01 UTC/)).toBeTruthy();
  });

  it("NO toca el derived_state: el gabinete sigue diciendo SIN ENLACE", () => {
    // Este es el test que importa. Sustituir el estado por uno neutro/verde
    // reproduciría exactamente el bug que cerró T-2.59: un cero tranquilizador
    // que nadie comprobó (regla de oro 7). Un gabinete en mantenimiento SIGUE
    // sin enlace — lo que cambia es que ahora se sabe por qué.
    render(
      <SiteCard cabinet={cabinet({}, { derived_state: "SIN ENLACE" })} maintenance={MW as never} />,
    );
    expect(screen.getByText("SIN ENLACE")).toBeTruthy();
    expect(screen.getByText(/EN MANTENIMIENTO HASTA/)).toBeTruthy();
  });

  it("sin ventana no inventa ningún rótulo", () => {
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.queryByText(/EN MANTENIMIENTO/)).toBeNull();
  });

  // --- [B8] El tooltip afirmaba el silencio pasara lo que pasara -------------

  it("con TODAS mudas el tooltip lo afirma, y el DOM lo declara", () => {
    render(<SiteCard cabinet={cabinet()} maintenance={MW as never} />);
    const badge = screen.getByTestId("maintenance-badge");
    expect(badge.getAttribute("title")).toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    expect(badge.getAttribute("title")).toContain("2/2 ALARMAS SILENCIADAS");
    expect(badge.getAttribute("data-mute")).toBe("all");
  });

  it("con el silenciador APAGADO la tarjeta NO afirma que las alarmas están mudas", () => {
    // `ops_muting_enabled=False` (el default de producción) ⇒ `mute_rule` NULL y
    // 0 silenciadas. La tarjeta decía «Alarmas de operación silenciadas» en el
    // tooltip pasara lo que pasara, y el rótulo visible «EN MANTENIMIENTO» se
    // lee exactamente igual. Quien está de guardia deduciría que ese gabinete
    // está callado cuando sus alarmas siguen sonando.
    const apagado = {
      ...MW,
      requested: 2,
      silenced: 0,
      missing: 2,
      missing_names: ["a", "b"],
      mute_rule: null,
    };
    render(<SiteCard cabinet={cabinet()} maintenance={apagado as never} />);
    const badge = screen.getByTestId("maintenance-badge");
    expect(badge.textContent).toContain("ALARMAS SIN SILENCIAR");
    expect(badge.getAttribute("title")).toContain("LAS ALARMAS DE OPERACIÓN SIGUEN SONANDO");
    expect(badge.getAttribute("title")).not.toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    // La causa tampoco se disfraza de "esa alarma no existe" (B9).
    expect(badge.getAttribute("title")).toContain("SILENCIADOR APAGADO O CON FALLO");
    expect(badge.getAttribute("title")).not.toContain("SIN ALARMA EXISTENTE");
    expect(badge.getAttribute("data-mute")).toBe("none");
  });

  it("con ALGUNAS mudas la tarjeta no lo redondea a silencio", () => {
    const parcial = { ...MW, requested: 2, silenced: 1, missing: 1, missing_names: ["a"] };
    render(<SiteCard cabinet={cabinet()} maintenance={parcial as never} />);
    const badge = screen.getByTestId("maintenance-badge");
    expect(badge.textContent).toContain("SILENCIADAS EN PARTE");
    expect(badge.getAttribute("title")).not.toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    expect(badge.getAttribute("data-mute")).toBe("partial");
  });

  // --- [C2] La tarjeta tampoco puede pintar la suposición como medida --------

  it("con el acuse SIN COMPROBAR el rótulo declara la duda, no el silencio", () => {
    // `mute_verified=false` llega con la misma forma que un éxito (`2/2`,
    // `missing 0`, regla con nombre) porque el servidor asume lo peor a
    // propósito. Sin leer el flag, la tarjeta pintaba el rótulo CORTO —el que se
    // reserva para la afirmación cierta— y quien barre la flota daba por hecho
    // que ese edificio está callado y comprobado.
    render(<SiteCard cabinet={cabinet()} maintenance={{ ...MW, mute_verified: false } as never} />);
    const badge = screen.getByTestId("maintenance-badge");
    expect(badge.textContent).toContain("SILENCIO SIN COMPROBAR");
    expect(badge.getAttribute("data-mute")).toBe("assumed");
    expect(badge.getAttribute("title")).toContain("SILENCIO SUPUESTO");
    expect(badge.getAttribute("title")).not.toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    expect(badge.getAttribute("title")).not.toContain("2/2 ALARMAS SILENCIADAS");
  });

  it("el motivo sigue en el tooltip: una ventana sin dueño visible no existe", () => {
    render(<SiteCard cabinet={cabinet()} maintenance={MW as never} />);
    expect(screen.getByTestId("maintenance-badge").getAttribute("title")).toContain(
      "cambio del cable de red del Shake",
    );
  });
});

// [T-5.05] UN GABINETE SIMULADO SE VEÍA IGUAL QUE UNO REAL.
//
// La separación entre lo simulado y lo real vivía en el seed y en el despliegue,
// no en la pantalla — que es justo donde se hace la demo. En `make soc-local` un
// prospecto veía 21 sitios y 5 gabinetes con idéntico aspecto en el mapa y en la
// flota, de los cuales 20 y 4 no existen.
describe("SiteCard · lo de demostración se ve de demostración", () => {
  it("un gabinete simulado sale marcado", () => {
    render(<SiteCard cabinet={cabinet({ siteCode: "site-sim-003" }, { serial: "gw-sim-0002" })} />);
    expect(screen.getByTestId("demo-badge")).toHaveTextContent("DEMO");
  });

  it("basta con que lo sea el SITIO, aunque el serial no lo delate", () => {
    render(<SiteCard cabinet={cabinet({ siteCode: "site-sim-007" }, { serial: "gw-loquesea" })} />);
    expect(screen.getByTestId("demo-badge")).toBeInTheDocument();
  });

  it("un gabinete REAL no se marca — y esta es la mitad que importa", () => {
    // Rotular de demostración un edificio con gente dentro es peor que no
    // rotular nada: el operador dejaría de creerse lo que ve en esa tarjeta.
    render(<SiteCard cabinet={cabinet()} />);
    expect(screen.queryByTestId("demo-badge")).toBeNull();
  });

  it("con cero sitios simulados la tarjeta es idéntica: el rótulo no reserva sitio", () => {
    const { container } = render(<SiteCard cabinet={cabinet()} />);
    expect(container.querySelectorAll(".fleet-card__demo")).toHaveLength(0);
  });
});
