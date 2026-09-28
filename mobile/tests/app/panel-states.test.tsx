// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] El panel táctico es la pantalla que T-2.58/59 pilló pintando
// features CONGELADAS como vivas en el gabinete, y la tira de KPI de la consola
// pintando ceros con la API caída. Aquí se mide que el marco de la RUTA no deje
// pasar nada de eso: sin dato del servidor no se pinta ni una métrica.
//
// El censo de T-2.111 dejó esta ruta en la deuda anotando «varios StateFrame
// hermanos»; medido hoy, la ruta materializa UNO solo (`PanelView` es
// presentacional puro y no monta marcos), así que `expectFourStates` aplica
// directo y la nota queda corregida por medición.
import type { MobileStateOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Panel from "@/app/(brigadista)/panel";

const SITE = "11111111-1111-1111-1111-111111111111";
// [T-5.21] El «ahora» del fixture es RELATIVO al reloj de verdad. Era un epoch
// clavado en 2027, y desde que la frescura sale del reloj —y no de que la
// consulta falle— un `dataUpdatedAt` en el futuro sale «fresco» y el estado
// `stale` no se materializaba. Contar hacia atrás desde `Date.now()` hace que
// «hace tres minutos» signifique de verdad hace tres minutos.
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

const mockPush = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn() }),
}));

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => mockSitio,
}));

type Snapshot = ReturnType<typeof instantanea>;
let mockSnapshot: Snapshot;
jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => mockSnapshot,
}));

let mockAcciones: Record<string, boolean> = { manual_activate: true, siren_silence: true };
jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: unknown }) => unknown) =>
    sel({
      status: "authenticated",
      me: { sub: "u-1", allowed_actions: mockAcciones },
    }),
}));

// Socket mudo: el marco de la ruta lo gobierna `mobile-state`, no el live.
jest.mock("@/live/socket", () => ({
  getLiveSocket: () => ({
    status: "ready",
    connect: jest.fn(),
    close: jest.fn(),
    onStatus: () => () => undefined,
    subscribe: () => () => undefined,
  }),
}));

// La traza REST del incidente es accesoria al marco (sólo alimenta el detalle);
// su desenlace lo posee react-query. Aquí se deja muda.
jest.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
    failureCount: 0,
    dataUpdatedAt: 0,
    refetch: jest.fn(),
  }),
}));

// ------------------------------------------------------------------ datos

function estado(): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "idle",
    incident: null,
    latest_tier: "normal",
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
    site_health: {
      status: "OPERATIVO",
      heartbeat_at: new Date(AHORA - 60_000).toISOString(),
      age_s: 60,
      has_wr1: true,
      mqtt_rtt_ms: 77,
      seedlink_lag_s: 1.2,
      ntp_offset_ms: -0.2,
      cpu_temp_c: 51.3,
      power_status: null,
      battery_pct: null,
      cert_days_remaining: 120,
    },
  } as unknown as MobileStateOut;
}

function instantanea(over: Record<string, unknown> = {}) {
  return {
    state: null as string | null,
    data: null as MobileStateOut | null,
    hasOwnCheckin: false,
    refetch: jest.fn(),
    dataUpdatedAt: AHORA,
    loading: false,
    error: null as string | null,
    // [T-5.21] `stale: boolean` → `staleSinceMs`: la frescura es un INSTANTE.
    staleSinceMs: null,
    ...over,
  };
}

beforeEach(() => {
  mockSitio = SITE;
  mockSnapshot = instantanea();
  mockAcciones = { manual_activate: true, siren_silence: true };
  mockPush.mockClear();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("2.1 · panel · sin dato del servidor NO se pinta ni una métrica", () => {
  it("sin sitio vigilado dice qué hacer y con quién, no un panel en ceros", async () => {
    mockSitio = null;

    const v = await render(<Panel />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin sitio vigilado/);
    expect(v.getByTestId("state-empty")).toHaveTextContent(/administrador/);
    expect(v.queryByText(/OPERATIVO/)).toBeNull();
  });

  it("si `mobile-state` falla, la salud del gabinete NO aparece", async () => {
    // La trampa de T-2.58/59 en una línea: un KPI fuera del marco se lee como
    // «todo en orden» justo cuando nadie puede saberlo.
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Panel />);
    await asentar();

    expect(v.getByTestId("state-error")).toHaveTextContent(
      /No se pudo consultar el estado del sitio/,
    );
    expect(v.queryByText(/OPERATIVO/)).toBeNull();
    expect(v.queryByText(/TORRE REFORMA/)).toBeNull();
  });

  it("con dato VIEJO el panel se pinta bajo el banner de retenidos", async () => {
    mockSnapshot = instantanea({
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 9 * 60_000,
      dataUpdatedAt: AHORA - 9 * 60_000,
    });

    const v = await render(<Panel />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByText(/TORRE REFORMA/)).toBeTruthy();
  });
});

describe("2.1 · panel · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          data: e === "stale" ? estado() : null,
          // [T-5.21] La frescura es un INSTANTE, del mismo `dataUpdatedAt`
          // que el fixture declara: no puede decir «viejo» y «fresco» a la vez.
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : AHORA,
        });
        return <Panel />;
      },
      { asentar },
    );
  });
});

// [F3·r3] La entrada a CONFIRMAR DICTAMEN desde el INICIO táctico: el servidor
// dice «pendiente de confirmación» y el perfil confirma ⇒ un botón que abre la
// pantalla con ESE incidente. Sin el permiso, no hay botón.
describe("F3 · panel · entrada a CONFIRMAR DICTAMEN", () => {
  function pendiente(): MobileStateOut {
    const e = estado();
    return {
      ...e,
      phase: "reentry_blocked",
      reentry: {
        blocked: true,
        dictamen_status: "inhabit_monitor",
        dictamen_signed: false,
        incident_id: "i-7",
        reason: "pendiente_confirmacion",
      },
    } as unknown as MobileStateOut;
  }

  it("con confirm_dictamen ⇒ el botón abre /confirmar-dictamen con el incidente", async () => {
    mockAcciones = { confirm_dictamen: true };
    mockSnapshot = instantanea({ data: pendiente() });
    const v = await render(<Panel />);
    await asentar();
    fireEvent.press(v.getByTestId("open-confirmar-dictamen"));
    expect(mockPush).toHaveBeenCalledWith({
      pathname: "/confirmar-dictamen",
      params: { incident: "i-7" },
    });
  });

  // [F3·r3] Con el incidente AÚN ABIERTO (fase `shaking_concluded`), la nube ya
  // manda `reason = pendiente_confirmacion` con `blocked = true` y SIN tocar la
  // fase: la entrada debe existir igual y llevar el incidente ABIERTO.
  it.each([
    ["sin incident_id en el reingreso", null],
    ["con incident_id en el reingreso", "i-8"],
  ])("incidente ABIERTO (%s) ⇒ el botón abre el incidente abierto", async (_n, delReingreso) => {
    mockAcciones = { confirm_dictamen: true };
    const e = estado();
    mockSnapshot = instantanea({
      data: {
        ...e,
        phase: "shaking_concluded",
        incident: {
          incident_id: "i-8",
          opened_at: new Date().toISOString(),
          trigger: "sasmex",
          max_pga_g: 0.06,
          node_count: null,
          severity: "moderate",
          state: "open",
        },
        reentry: {
          blocked: true,
          dictamen_status: "inhabit_monitor",
          dictamen_signed: false,
          incident_id: delReingreso,
          reason: "pendiente_confirmacion",
        },
      } as unknown as MobileStateOut,
    });
    const v = await render(<Panel />);
    await asentar();
    fireEvent.press(v.getByTestId("open-confirmar-dictamen"));
    expect(mockPush).toHaveBeenCalledWith({
      pathname: "/confirmar-dictamen",
      params: { incident: "i-8" },
    });
  });

  // [D-49 · R1] Con el edificio en movimiento la nube responde 409 «vuelva a
  // calma»: no se ofrece el botón, pero se DICE que hay un dictamen esperando.
  it("AMARILLO pendiente con el edificio en movimiento ⇒ sin botón, explica la calma", async () => {
    mockAcciones = { confirm_dictamen: true };
    mockSnapshot = instantanea({
      data: { ...pendiente(), phase: "alert_active", latest_tier: "evacuate_or_hold" },
    });
    const v = await render(<Panel />);
    await asentar();
    expect(v.queryByTestId("open-confirmar-dictamen")).toBeNull();
    expect(v.getByTestId("confirmar-espera-calma")).toHaveTextContent(
      /espere a que el edificio vuelva a calma/,
    );
  });

  it("con el tier fuera de normal (fase ya no de alerta) tampoco se ofrece", async () => {
    mockAcciones = { confirm_dictamen: true };
    mockSnapshot = instantanea({ data: { ...pendiente(), latest_tier: "watch" } });
    const v = await render(<Panel />);
    await asentar();
    expect(v.queryByTestId("open-confirmar-dictamen")).toBeNull();
    expect(v.getByTestId("confirmar-espera-calma")).toBeTruthy();
  });

  // [D-49 · R2] El AMARILLO sin confirmar de un incidente ANTERIOR bloquea aunque
  // haya otro abierto: la entrada lleva el incidente que CITA el reingreso.
  it("AMARILLO de un incidente ANTERIOR con otro abierto ⇒ abre el anterior", async () => {
    mockAcciones = { confirm_dictamen: true };
    mockSnapshot = instantanea({
      data: {
        ...pendiente(),
        phase: "reentry_blocked",
        latest_tier: "normal",
        incident: {
          incident_id: "i-replica",
          opened_at: new Date().toISOString(),
          trigger: "sasmex",
          max_pga_g: 0.01,
          node_count: null,
          severity: "minor",
          state: "open",
        },
      } as unknown as MobileStateOut,
    });
    const v = await render(<Panel />);
    await asentar();
    fireEvent.press(v.getByTestId("open-confirmar-dictamen"));
    expect(mockPush).toHaveBeenCalledWith({
      pathname: "/confirmar-dictamen",
      params: { incident: "i-7" },
    });
  });

  it("sin confirm_dictamen ⇒ no hay botón", async () => {
    mockSnapshot = instantanea({ data: pendiente() });
    const v = await render(<Panel />);
    await asentar();
    expect(v.queryByTestId("open-confirmar-dictamen")).toBeNull();
  });
});
