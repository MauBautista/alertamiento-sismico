// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] El modo reposo del ocupante es la pantalla que más tiempo está a la
// vista y la que afirma, en letra grande, que su edificio está vigilado. Es
// EXACTAMENTE el sitio donde un dato congelado pintado como «live» hace el daño
// que describe la regla de oro 7 — la lección del 14-jul, cuando la consola
// estuvo 15 h ciega diciendo OPERATIVO.
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { useSessionStore } from "@/auth/session.store";
import { expectFourStates } from "@/test-utils/expectFourStates";

import Inicio from "@/app/(occupant)/inicio";

const SITE = "11111111-1111-1111-1111-111111111111";
// [T-5.21] El «ahora» del fixture es RELATIVO al reloj de verdad. Era un epoch
// clavado en 2027, y desde que la frescura sale del reloj —y no de que la
// consulta falle— un `dataUpdatedAt` en el futuro sale «fresco» y el estado
// `stale` no se materializaba. Contar hacia atrás desde `Date.now()` hace que
// «hace tres minutos» signifique de verdad hace tres minutos.
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
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

// El directorio de esta pantalla es un ACCESORIO (tres brigadistas de la zona);
// los cuatro estados del marco los gobierna `mobile-state`, que es la verdad
// del edificio. Su propio contrato lo mide `directorio-states.test.tsx`.
jest.mock("@/offline/useCachedQuery", () => ({
  useCachedQuery: () => ({
    data: [],
    staleSinceMs: null,
    loading: false,
    error: null,
    refetch: jest.fn(),
  }),
}));

// [F3·r3 · D-43] El certificado (quién firmó) se lee con `useQuery`; se captura
// la consulta para medir CUÁNDO se pide y qué devuelve.
type Consulta = { data?: unknown };
let mockCertificado: Consulta = {};
const mockConsultas: { enabled?: boolean; queryKey?: unknown[]; refetchInterval?: unknown }[] = [];
jest.mock("@tanstack/react-query", () => ({
  useQuery: (opts: { enabled?: boolean; queryKey?: unknown[]; refetchInterval?: unknown }) => {
    mockConsultas.push(opts);
    return opts.enabled === false ? {} : mockCertificado;
  },
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
    my_zone: { zone_id: "z-1", name: "Piso 12", evac_policy: "evacuate", level_code: null },
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
  mockCertificado = {};
  mockConsultas.length = 0;
  useSessionStore.setState({ me: null });
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("1.1 · inicio · nunca afirma vigilancia que no puede comprobar", () => {
  it("sin sitio vigilado dice cómo vincularse, no un edificio en blanco", async () => {
    mockSitio = null;

    const v = await render(<Inicio />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin sitio vigilado/);
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Vincúlese/);
  });

  it("si `mobile-state` falla y no hay dato, NO se pinta ninguna cifra del edificio", async () => {
    // La trampa de T-2.58/59: una tira de KPI fuera del marco pinta ceros que
    // se leen como «todo en orden».
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Inicio />);
    await asentar();

    expect(v.getByTestId("state-error")).toHaveTextContent(
      /No se pudo consultar el estado del sitio/,
    );
    expect(v.queryByText("TORRE REFORMA")).toBeNull();
  });

  it("con dato VIEJO se pinta el edificio PERO con el banner de retenidos encima", async () => {
    mockSnapshot = instantanea({
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 7 * 60_000,
      dataUpdatedAt: AHORA - 7 * 60_000,
    });

    const v = await render(<Inicio />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByText("TORRE REFORMA")).toBeTruthy();
  });
});

describe("1.1 · inicio · contrato de 4 estados (regla de oro 7)", () => {
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
        return <Inicio />;
      },
      { asentar },
    );
  });
});

describe("1.1 · inicio · [F3·r3 · D-43] el cartel de reingreso dice QUIÉN lo aprobó", () => {
  const INC = "22222222-2222-2222-2222-222222222222";
  function aprobado(): MobileStateOut {
    return {
      ...estado(),
      phase: "reentry_approved",
      reentry: {
        blocked: false,
        dictamen_status: "normal_operation",
        dictamen_signed: true,
        incident_id: INC,
      },
    } as unknown as MobileStateOut;
  }
  function conPermiso(dictamenRead: boolean): void {
    useSessionStore.setState({
      me: { allowed_actions: { dictamen_read: dictamenRead } },
    } as never);
  }

  it("firma del SISTEMA ⇒ no se la atribuye al inspector", async () => {
    conPermiso(true);
    mockSnapshot = instantanea({ data: aprobado() });
    mockCertificado = {
      data: { signed: true, folio: "d-1", signature_kind: "system", band: "verde" },
    };

    const v = await render(<Inicio />);
    await asentar();

    const b = v.getByTestId("reentry-banner");
    expect(b).toHaveTextContent(/el sistema emitió el dictamen/);
    expect(b).not.toHaveTextContent(/inspector/);
    expect(mockConsultas.some((c) => c.enabled === true && c.queryKey?.includes(INC))).toBe(true);
  });

  it("CONFIRMACIÓN ⇒ dice el rol que confirmó", async () => {
    conPermiso(true);
    mockSnapshot = instantanea({ data: aprobado() });
    mockCertificado = {
      data: {
        signed: true,
        folio: "d-2",
        signature_kind: "confirmation",
        confirmed_by_role: "brigadista",
        band: "amarillo",
      },
    };

    const v = await render(<Inicio />);
    await asentar();

    expect(v.getByTestId("reentry-banner")).toHaveTextContent(/confirmado por BRIGADISTA/i);
  });

  // [F3·r4 · D-49] El certificado del cartel se INVALIDA cuando mobile-state
  // cambia: la clave lleva la huella del dictamen vigente, y un certificado que
  // no coincide con lo que dice mobile-state (el del firmante ANTERIOR, aún en
  // caché) no se atribuye a nadie.
  it("la clave cambia con el dictamen de mobile-state y se vuelve a pedir", async () => {
    conPermiso(true);
    mockSnapshot = instantanea({ data: aprobado() });
    await render(<Inicio />);
    await asentar();
    const antes = mockConsultas.filter((c) => c.enabled === true).at(-1);
    mockConsultas.length = 0;
    const otro = aprobado();
    otro.reentry = { ...otro.reentry, dictamen_status: "inhabit_monitor" };
    mockSnapshot = instantanea({ data: otro });
    await render(<Inicio />);
    await asentar();
    const despues = mockConsultas.filter((c) => c.enabled === true).at(-1);
    expect(JSON.stringify(despues?.queryKey)).not.toBe(JSON.stringify(antes?.queryKey));
    expect(JSON.stringify(despues?.queryKey)).toContain("inhabit_monitor");
    expect(despues?.refetchInterval).toEqual(expect.any(Number));
  });

  it("un certificado que ya no es el vigente (otro status) NO pone al firmante anterior", async () => {
    conPermiso(true);
    const e = aprobado();
    e.reentry = { ...e.reentry, dictamen_status: "inhabit_monitor" };
    mockSnapshot = instantanea({ data: e });
    mockCertificado = {
      data: {
        signed: true,
        folio: "d-1",
        incident_id: INC,
        status: "normal_operation",
        signature_kind: "system",
        band: "verde",
      },
    };
    const v = await render(<Inicio />);
    await asentar();
    const b = v.getByTestId("reentry-banner");
    expect(b).toHaveTextContent(/el dictamen vigente autorizó el reingreso/);
    expect(b).not.toHaveTextContent(/sistema/);
  });

  it("un certificado de OTRO incidente tampoco", async () => {
    conPermiso(true);
    mockSnapshot = instantanea({ data: aprobado() });
    mockCertificado = {
      data: {
        signed: true,
        folio: "d-1",
        incident_id: "otro-incidente",
        status: "normal_operation",
        signature_kind: "inspector",
      },
    };
    const v = await render(<Inicio />);
    await asentar();
    expect(v.getByTestId("reentry-banner")).not.toHaveTextContent(/inspector/);
  });

  it("sin `dictamen_read` (ocupante) NO se pide el certificado ni se le atribuye a nadie", async () => {
    conPermiso(false);
    mockSnapshot = instantanea({ data: aprobado() });
    mockCertificado = { data: { signed: true, folio: "d-3", signature_kind: "inspector" } };

    const v = await render(<Inicio />);
    await asentar();

    const b = v.getByTestId("reentry-banner");
    expect(b).toHaveTextContent(/el dictamen vigente autorizó el reingreso/);
    expect(b).not.toHaveTextContent(/inspector/);
    expect(mockConsultas.every((c) => c.enabled !== true)).toBe(true);
  });
});
