// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context` y un `*.test.tsx` ahí dentro
// rompe el bundle. Misma nota que `sync-states.test.tsx`.
//
// [T-2.111] EL PASE DE LISTA SE TRAGABA LOS TRES DESENLACES.
//
//  1. `markVerified` (check-in DELEGADO: el táctico da por viva a una persona)
//     no capturaba. El SDK LANZA al morir `fetch`, así que `setMarkingId(null)`
//     no corría: la fila se quedaba con «…» para siempre y el táctico creía
//     haber contabilizado a alguien que sigue SIN REPORTE. En un pase de lista
//     eso es dar por viva a una persona por un fallo de red.
//  2. `notifyUnreported` y `closeHeadcount` usaban `.finally(() => setBusy(false))`
//     y nada más: el botón se liberaba, pero NO se pintaba ni éxito ni error.
//     El táctico no podía saber si la notificación salió.
//  3. El error de `mobile-state` no viajaba al marco: con la consulta caída,
//     `incidentId` es null y la pantalla afirmaba «Sin incidente activo en su
//     sitio» — la afirmación más tranquilizadora posible, y falsa.
import type { RosterOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Lista from "@/app/(brigadista)/lista";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = 1_800_000_000_000;

// ------------------------------------------------------------------ mocks

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => SITE_MOCK }));
const SITE_MOCK = SITE;

type Snapshot = ReturnType<typeof instantanea>;
let mockSnapshot: Snapshot;
jest.mock("@/features/alert/useAlertState", () => ({ useAlertState: () => mockSnapshot }));

jest.mock("@/live/socket", () => ({
  getLiveSocket: () => ({
    status: "ready",
    connect: jest.fn(),
    close: jest.fn(),
    onStatus: () => () => undefined,
    subscribe: () => () => undefined,
  }),
}));

// La consulta del roster se conduce a mano: así se puede poner la pantalla en
// cada uno de los cuatro estados sin pelearse con el reloj de react-query.
let mockRoster: Record<string, unknown>;
jest.mock("@tanstack/react-query", () => ({ useQuery: () => mockRoster }));

const mockVerificar = jest.fn();
const mockNotificar = jest.fn();
const mockCerrar = jest.fn();
jest.mock("@takab/sdk", () => ({
  TOPIC_INCIDENTS: "incidents",
  incidentRosterIncidentsIncidentIdRosterGet: jest.fn(),
  submitCheckinIncidentsIncidentIdCheckinsPost: (...a: unknown[]) => mockVerificar(...a),
  notifyUnreportedIncidentsIncidentIdHeadcountNotifyUnreportedPost: (...a: unknown[]) =>
    mockNotificar(...a),
  closeHeadcountIncidentsIncidentIdHeadcountClosePost: (...a: unknown[]) => mockCerrar(...a),
}));

// ------------------------------------------------------------------ datos

function instantanea(over: Record<string, unknown> = {}) {
  return {
    state: "checkin_pending" as string | null,
    data: { incident: { incident_id: "inc-1" } } as unknown,
    hasOwnCheckin: false,
    refetch: jest.fn(),
    dataUpdatedAt: AHORA,
    loading: false,
    error: null as string | null,
    stale: false,
    ...over,
  };
}

function roster(over: Partial<RosterOut> = {}): RosterOut {
  return {
    incident_id: "inc-1",
    site_id: SITE,
    total: 2,
    safe: 1,
    need_help: 0,
    unreported: 1,
    entries: [
      {
        user_id: "u-1",
        display_name: "Ana Ruiz",
        zone_name: "Piso 12",
        phone: null,
        checkin: null,
      },
      {
        user_id: "u-2",
        display_name: "Beto Lara",
        zone_name: "Piso 3",
        phone: null,
        checkin: { status: "safe", via: "self" },
      },
    ],
    ...over,
  } as unknown as RosterOut;
}

function consulta(over: Record<string, unknown> = {}) {
  return {
    data: roster(),
    isLoading: false,
    isError: false,
    failureCount: 0,
    dataUpdatedAt: AHORA,
    refetch: jest.fn(async () => undefined),
    ...over,
  };
}

beforeEach(() => {
  mockSnapshot = instantanea();
  mockRoster = consulta();
  mockVerificar.mockReset();
  mockNotificar.mockReset();
  mockCerrar.mockReset();
  mockVerificar.mockResolvedValue({ data: {} });
  mockNotificar.mockResolvedValue({ data: { notified: 1 } });
  mockCerrar.mockResolvedValue({ data: {} });
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

async function pulsar(v: { getByTestId: (id: string) => unknown }, id: string): Promise<void> {
  await act(async () => {
    fireEvent.press(v.getByTestId(id) as Parameters<typeof fireEvent.press>[0]);
  });
  await asentar();
}

// ------------------------------------------------------------------ tests

describe("2.6 · pase de lista · el check-in DELEGADO no se traga su fallo", () => {
  it("si el SDK LANZA, la fila se libera y se dice que NO quedó contabilizada", async () => {
    mockVerificar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");

    // La fila vuelve: se puede reintentar (el botón dice VERIFICAR, no "…").
    expect(v.getByTestId("verify-u-1")).toHaveTextContent("VERIFICAR");
    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/No se pudo verificar/);
    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/sigue SIN REPORTE/);
  });

  it("si sale bien no se pinta ningún error", async () => {
    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");

    expect(mockVerificar).toHaveBeenCalledTimes(1);
    expect(v.queryByTestId("headcount-outcome")).toBeNull();
  });
});

describe("2.6 · pase de lista · notificar y cerrar DECLARAN su desenlace", () => {
  it("notificar con éxito lo dice", async () => {
    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "notify-unreported");

    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/Notificación enviada/);
  });

  it("notificar con la red caída lo dice, y dice que NADIE fue avisado", async () => {
    mockNotificar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "notify-unreported");

    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/No se pudo notificar/);
    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/nadie ha sido avisado/i);
    // Y el botón no queda muerto.
    expect(v.getByTestId("notify-unreported")).toHaveTextContent(/NOTIFICAR A NO REPORTADOS/);
  });

  it("cerrar el headcount con la red caída NO se da por hecho", async () => {
    mockRoster = consulta({ data: roster({ unreported: 0, safe: 2 }) });
    mockCerrar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "close-headcount");

    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/No se pudo cerrar el headcount/);
    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/sigue abierto/i);
  });

  it("cerrar el headcount con éxito lo dice", async () => {
    mockRoster = consulta({ data: roster({ unreported: 0, safe: 2 }) });

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "close-headcount");

    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/Headcount cerrado/);
  });
});

describe("2.6 · pase de lista · «sin incidente» no puede tapar un error", () => {
  it("si `mobile-state` falla se dice ESO, no «Sin incidente activo»", async () => {
    mockSnapshot = instantanea({
      state: null,
      data: null,
      error: "No se pudo consultar el estado del sitio.",
    });
    mockRoster = consulta({ data: undefined, isLoading: false });

    const v = await render(<Lista />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.queryByText(/Sin incidente activo/)).toBeNull();
  });
});

describe("2.6 · pase de lista · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSnapshot = instantanea({
          state: e === "empty" ? "idle" : "checkin_pending",
          data: e === "empty" ? { incident: null } : { incident: { incident_id: "inc-1" } },
          error: null,
        });
        mockRoster = consulta({
          data: e === "loading" || e === "error" ? undefined : roster(),
          isLoading: e === "loading",
          isError: e === "error" || e === "stale",
          failureCount: e === "stale" ? 1 : 0,
          dataUpdatedAt: AHORA - 3 * 60_000,
        });
        return <Lista />;
      },
      { asentar },
    );
  });
});
