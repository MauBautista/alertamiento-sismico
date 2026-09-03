// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context`, los `*.test.tsx` incluidos, y la
// app deja de compilar. Misma nota que `crisis-states.test.tsx`.
//
// [T-2.117] LA PANTALLA DE ALARMA DEL INMUEBLE GIRABA PARA SIEMPRE.
//
// Es el defecto GEMELO del que T-2.111 cerró en `crisis.tsx`, en la pantalla
// hermana: `alarma-inmueble.tsx` resolvía `if (!data?.building_alarm)` con un
// `ActivityIndicator` y el rótulo «VERIFICANDO LA ALARMA CON EL SERVIDOR…».
// Sin sitio vigilado la consulta de `mobile-state` ni se habilita
// (`enabled: siteId != null`), así que `data` es null PARA SIEMPRE: el ocupante
// se queda mirando girar la pantalla que existe para explicarle por qué está
// sonando la sirena de su edificio.
//
// Aquí se asserta el TEXTO que lee la persona, y se pasa el gate de los cuatro
// estados (`expectFourStates`).
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import AlarmaInmueble from "@/app/alarma-inmueble";

const SITE = "11111111-1111-1111-1111-111111111111";
// [T-5.21] El «ahora» del fixture es RELATIVO al reloj de verdad. Era un epoch
// clavado en 2027, y desde que la frescura sale del reloj —y no de que la
// consulta falle— un `dataUpdatedAt` en el futuro sale «fresco» y el estado
// `stale` no se materializaba. Contar hacia atrás desde `Date.now()` hace que
// «hace tres minutos» signifique de verdad hace tres minutos.
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

jest.mock("expo-router", () => {
  // [T-2.125] `requireActual` y no `require()`: dentro de una factoría de
  // `jest.mock` no se puede importar arriba (se hoistea), pero sí se puede pedir
  // el módulo REAL — que aquí es además la misma instancia, porque
  // `react-native` no está moqueado.
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
  };
});

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: null }) => unknown) =>
    sel({ status: "authenticated", me: null }),
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

// ------------------------------------------------------------------ datos

function estado(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "building_alarm",
    incident: null,
    building_alarm: { since: new Date(AHORA - 120_000).toISOString() },
    latest_tier: "normal",
    my_zone: { zone_id: "z-1", name: "Piso 12", evac_policy: null },
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
    ...over,
  } as unknown as MobileStateOut;
}

function instantanea(over: Record<string, unknown> = {}) {
  return {
    state: null as string | null,
    data: null as MobileStateOut | null,
    hasOwnCheckin: false,
    refetch: jest.fn(),
    dataUpdatedAt: 0,
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
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("2.6 · alarma del inmueble · sin sitio vigilado DECLARA, no gira", () => {
  it("dice que no hay edificio vinculado y qué hacer — jamás un spinner eterno", async () => {
    mockSitio = null;
    mockSnapshot = instantanea();

    const v = await render(<AlarmaInmueble />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/no está vinculado a ningún edificio/i);
    expect(v.queryByTestId("state-loading")).toBeNull();
    expect(v.queryByText(/VERIFICANDO LA ALARMA CON EL SERVIDOR/)).toBeNull();
  });

  it("si `mobile-state` falla y no hay dato, lo DICE con reintento", async () => {
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<AlarmaInmueble />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-error")).toHaveTextContent(
      /No se pudo consultar el estado del sitio/,
    );
    // Accionable: la pantalla NO afirma que no hay alarma — no pudo preguntar.
    expect(v.getByTestId("state-retry")).toBeTruthy();
    expect(v.queryByTestId("state-loading")).toBeNull();
    expect(v.queryByText(/ALARMA DEL INMUEBLE/)).toBeNull();
  });

  it("el servidor respondió y NO hay alarma: vacío honesto, distinto del error", async () => {
    mockSnapshot = instantanea({ data: estado({ building_alarm: null } as never) });

    const v = await render(<AlarmaInmueble />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/no reporta ninguna alarma/i);
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("con dato VIEJO se pinta la alarma PERO bajo el banner de retenidos", async () => {
    mockSnapshot = instantanea({
      state: "building_alarm",
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 5 * 60_000,
      dataUpdatedAt: AHORA - 5 * 60_000,
    });

    const v = await render(<AlarmaInmueble />);
    await asentar();

    expect(v.getByTestId("state-stale")).toBeTruthy();
    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    // "Retenido" no es "no hay nada": la instrucción sigue a la vista.
    expect(v.getByText("ATIENDA A SU BRIGADA")).toBeTruthy();
    expect(v.getByText("NO ES UNA ALERTA SÍSMICA")).toBeTruthy();
  });
});

describe("2.6 · alarma del inmueble · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          state: e === "stale" ? "building_alarm" : null,
          data: e === "stale" ? estado() : null,
          // [T-5.21] La frescura es un INSTANTE, y sale del mismo `dataUpdatedAt`
          // que el fixture declara: así no puede decir «viejo» y «fresco» a la vez.
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : 0,
        });
        return <AlarmaInmueble />;
      },
      { asentar },
    );
  });
});
