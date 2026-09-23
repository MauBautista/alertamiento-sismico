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
//
// [T-8.11 · A-024] Y el arreglo de (1) se quedó a medias: capturar el fallo
// hacía que la pantalla DIJERA que no quedó registrado, pero sin red seguía sin
// registrarse. El check-in delegado es de la cola desde esta ficha —igual que
// el propio, la foto y el reporte—: sin red se GUARDA y se dice que se guardó.
import type { RosterOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import {
  configureQueuePersistence,
  resetQueueStoreForTests,
  useQueueStore,
} from "@/offline/queue.store";
import { MemoryQueuePersistence } from "@/offline/store";
import { drainQueue } from "@/offline/sync";
import { expectFourStates } from "@/test-utils/expectFourStates";

import Lista from "@/app/(brigadista)/lista";

const SITE = "11111111-1111-1111-1111-111111111111";
// [T-5.21] El «ahora» del fixture es RELATIVO al reloj de verdad. Era un epoch
// clavado en 2027, y desde que la frescura sale del reloj —y no de que la
// consulta falle— un `dataUpdatedAt` en el futuro sale «fresco» y el estado
// `stale` no se materializaba. Contar hacia atrás desde `Date.now()` hace que
// «hace tres minutos» signifique de verdad hace tres minutos.
const AHORA = Date.now();

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

// La cola es la de verdad (en memoria): lo que se afirma es que el check-in
// delegado ENTRA en ella, no que alguien llame a una función.
jest.mock("expo-crypto", () => {
  let n = 0;
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    digestStringAsync: jest.fn(async (_alg: string, data: string) => `sha256:${data.length}`),
    randomUUID: jest.fn(() => `uuid-${++n}`),
  };
});

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
    // [T-5.21] `stale: boolean` → `staleSinceMs`: la frescura es un INSTANTE.
    staleSinceMs: null,
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

beforeEach(async () => {
  resetQueueStoreForTests();
  configureQueuePersistence(new MemoryQueuePersistence());
  await useQueueStore.getState().hydrate();
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

describe("2.6 · pase de lista · el check-in DELEGADO va por la COLA (T-8.11 · A-024)", () => {
  const delegados = () =>
    useQueueStore.getState().items.filter((i) => i.kind === "delegated_checkin");

  it("con red sale en el acto, con subject_user_id, y no pinta ningún aviso", async () => {
    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");

    expect(mockVerificar).toHaveBeenCalledTimes(1);
    const [item] = delegados();
    expect(item.state).toBe("synced");
    const call = mockVerificar.mock.calls[0][0] as { path: { incident_id: string }; body: unknown };
    expect(call.path.incident_id).toBe("inc-1");
    expect(call.body).toMatchObject({
      checkin_id: item.id,
      status: "safe",
      subject_user_id: "u-1",
    });
    expect(v.queryByTestId("headcount-outcome")).toBeNull();
    expect(mockRoster.refetch).toHaveBeenCalled();
  });

  it("SIN RED se ENCOLA —no se pierde— y lo dice: guardada en el teléfono, sigue SIN REPORTE", async () => {
    mockVerificar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");

    const items = delegados();
    expect(items).toHaveLength(1);
    expect(items[0].state).toBe("pending");
    expect(items[0].payload).toMatchObject({ incident_id: "inc-1", subject_user_id: "u-1" });

    const aviso = v.getByTestId("headcount-outcome");
    expect(aviso).toHaveTextContent(/GUARDADA EN ESTE TELÉFONO/);
    expect(aviso).toHaveTextContent(/sigue SIN REPORTE/);
    // La fila no se puede volver a marcar: un segundo toque sería OTRO check-in
    // con otro id, no un reintento del primero.
    expect(v.queryByTestId("verify-u-1")).toBeNull();
    expect(v.getByTestId("queued-u-1")).toHaveTextContent("EN COLA");
  });

  it("cuando la cola la entrega, el pase de lista se re-consulta solo y el aviso se va", async () => {
    mockVerificar.mockRejectedValue(new TypeError("Network request failed"));
    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");
    (mockRoster.refetch as jest.Mock).mockClear();

    // Vuelve la red: la cola drena (lo haría `OfflineSyncGate`).
    mockVerificar.mockResolvedValue({ data: {} });
    await act(async () => {
      await drainQueue(Date.now() + 10 * 60_000);
    });
    await asentar();

    expect(delegados()[0].state).toBe("synced");
    expect(mockRoster.refetch).toHaveBeenCalled();
    expect(v.queryByTestId("headcount-outcome")).toBeNull();
  });

  it("si el servidor la RECHAZA, se dice y NO se da por verificada", async () => {
    mockVerificar.mockResolvedValue({ data: undefined, response: { status: 404 } });

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");

    expect(delegados()[0].state).toBe("failed");
    const aviso = v.getByTestId("headcount-outcome");
    expect(aviso).toHaveTextContent(/rechazó/);
    expect(aviso).toHaveTextContent(/sigue SIN REPORTE/);
    // Fallida no retiene la fila: se puede volver a intentar.
    expect(v.getByTestId("verify-u-1")).toHaveTextContent("VERIFICAR");
  });

  it("si ni siquiera se puede GUARDAR en el teléfono, lo dice y la fila se libera", async () => {
    resetQueueStoreForTests();
    const rota = new MemoryQueuePersistence();
    rota.upsert = async () => {
      throw new Error("disco lleno");
    };
    configureQueuePersistence(rota);
    await useQueueStore.getState().hydrate();

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");

    expect(mockVerificar).not.toHaveBeenCalled();
    const aviso = v.getByTestId("headcount-outcome");
    expect(aviso).toHaveTextContent(/No se pudo guardar/);
    expect(aviso).toHaveTextContent(/sigue SIN REPORTE/);
    expect(v.getByTestId("verify-u-1")).toHaveTextContent("VERIFICAR");
  });
});

// [T-8.11 · verificador] El aviso de la cola tiene que seguir siendo CIERTO
// mientras se ve. Dos desenlaces lo desmentían:
//   · con red, la segunda verificación seguida encuentra la cola drenando (una
//     sola pasada a la vez) y quedaba «pending»: el aviso culpaba a una conexión
//     que no se había perdido;
//   · si el drenaje de FONDO la rechazaba después (404/403), el aviso se
//     retiraba en silencio y la fila volvía a VERIFICAR sin decir por qué.
describe("2.6 · pase de lista · el aviso de la cola sigue siendo cierto mientras se ve", () => {
  const delegados = () =>
    useQueueStore.getState().items.filter((i) => i.kind === "delegated_checkin");

  it("si el drenaje de fondo la RECHAZA después, el aviso pasa a crítico: no desaparece en silencio", async () => {
    mockVerificar.mockRejectedValue(new TypeError("Network request failed"));
    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");
    expect(v.getByTestId("headcount-outcome")).toHaveTextContent(/GUARDADA EN ESTE TELÉFONO/);

    // Vuelve la red, pero el servidor la rechaza (404: el incidente ya no está).
    mockVerificar.mockResolvedValue({ data: undefined, response: { status: 404 } });
    await act(async () => {
      await drainQueue(Date.now() + 10 * 60_000);
    });
    await asentar();

    expect(delegados()[0].state).toBe("failed");
    const aviso = v.getByTestId("headcount-outcome");
    expect(aviso).toHaveTextContent(/rechazó/);
    expect(aviso).toHaveTextContent(/sigue SIN REPORTE/);
    expect(v.getByTestId("verify-u-1")).toHaveTextContent("VERIFICAR");
  });

  it("CON RED, dos verificaciones seguidas: la segunda no culpa a una conexión que no se perdió", async () => {
    const pendientes = roster().entries.map((e) => ({ ...e, checkin: null }));
    mockRoster = consulta({
      data: roster({
        unreported: 2,
        entries: [pendientes[0], { ...pendientes[1], user_id: "u-3" }],
      }),
    });
    // La primera entrega se queda EN VUELO: la cola sigue drenando cuando llega
    // el segundo toque.
    let soltar: (r: unknown) => void = () => undefined;
    mockVerificar.mockImplementationOnce(
      () =>
        new Promise((r) => {
          soltar = r;
        }),
    );

    const v = await render(<Lista />);
    await asentar();
    await pulsar(v, "verify-u-1");
    await pulsar(v, "verify-u-3");

    const aviso = v.getByTestId("headcount-outcome");
    expect(aviso).toHaveTextContent(/GUARDADA EN ESTE TELÉFONO/);
    expect(aviso).toHaveTextContent(/todavía no ha llegado al servidor/);
    expect(aviso).not.toHaveTextContent(/conexión/);

    // El drenaje en curso entrega las dos, y el aviso se retira solo.
    await act(async () => {
      soltar({ data: {} });
    });
    await asentar();
    expect(delegados().map((i) => i.state)).toEqual(["synced", "synced"]);
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
