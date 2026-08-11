// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context` y un `*.test.tsx` ahí dentro
// rompe el bundle. Misma nota que `sync-states.test.tsx`.
//
// [T-2.111] EL VOTO DE PÁNICO SE PERDÍA EN SILENCIO CON LA RED CAÍDA.
//
// `vote()` hacía `void (async () => { … const res = await panicVote(…);
// setBusy(false); … })()` SIN `try`. El cliente del SDK **lanza** cuando
// `fetch` muere (no devuelve `{data, error}`: eso es sólo para los HTTP de
// error), así que con la red caída la promesa se rechazaba antes de
// `setBusy(false)`: el botón se quedaba en «ENVIANDO…» para siempre, la
// pantalla no decía nada, y quien acababa de pedir la sirena por un incendio
// se quedaba mirando un botón muerto creyendo que su voto iba en camino.
//
// La rama `else` de `!res.data` YA existía y pintaba «NO SE PUDO ENVIAR»: el
// defecto es que el camino del LANZAMIENTO no llegaba nunca a ella.
import { act, fireEvent, render } from "@testing-library/react-native";

import Panic from "@/app/panic";

const SITE = "11111111-1111-1111-1111-111111111111";

// ------------------------------------------------------------------ mocks

jest.mock("expo-router", () => {
  const { Text } = require("react-native");
  return { Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text> };
});

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: null }) => unknown) =>
    sel({ status: "authenticated", me: null }),
}));

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => mockSitio }));

let mockConsienteGps = false;
jest.mock("@/services/onboarding", () => ({ getGpsConsent: async () => mockConsienteGps }));

const mockCapturarGps = jest.fn(async () => null);
jest.mock("@/features/checkin/location", () => ({ captureLocation: () => mockCapturarGps() }));

const mockVotar = jest.fn();
jest.mock("@takab/sdk", () => ({
  panicVoteSitesSiteIdManualActivationVotesPost: (...a: unknown[]) => mockVotar(...a),
}));

// El botón real es un MANTENER-PRESIONADO de 1.5 s sobre `Animated`; su gesto
// es asunto de `PanicButton` y ya no es lo que esta ficha mide. Aquí se
// sustituye por un pulsador simple que CONSERVA las dos props que sí importan
// —`label` y `disabled`—, que son las que delatan el botón colgado.
jest.mock("@/features/panic/PanicButton", () => {
  const { Pressable, Text } = require("react-native");
  return {
    PanicButton: (p: { disabled: boolean; label: string; onConfirm: () => void }) => (
      <Pressable disabled={p.disabled} onPress={p.onConfirm} testID="panic-hold">
        <Text>{p.label}</Text>
      </Pressable>
    ),
  };
});

beforeEach(() => {
  mockSitio = SITE;
  mockConsienteGps = false;
  mockVotar.mockReset();
  mockCapturarGps.mockReset();
  mockCapturarGps.mockResolvedValue(null);
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("1.9 · pánico · un fallo de red no cuelga el botón (regla de oro 7)", () => {
  it("el SDK LANZA: el botón vuelve y se dice que el voto NO se registró", async () => {
    mockVotar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Panic />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("panic-hold"));
    });
    await asentar();

    // 1) El botón NO se quedó en "ENVIANDO…".
    expect(v.getByText("MANTENGA PRESIONADO PARA CONFIRMAR")).toBeTruthy();
    expect(v.queryByText("ENVIANDO…")).toBeNull();
    // 2) El desenlace se PINTA, y dice que no se contó nada.
    expect(v.getByTestId("panic-status")).toHaveTextContent("NO SE PUDO ENVIAR");
    expect(v.getByText(/Su voto NO se registró/)).toBeTruthy();
  });

  it("si es la CAPTURA DE GPS la que lanza, tampoco se cuelga", async () => {
    // El GPS se toma antes del POST: una excepción aquí dejaba el botón
    // ocupado sin que ni siquiera se hubiera intentado el voto.
    mockConsienteGps = true;
    mockCapturarGps.mockRejectedValue(new Error("location unavailable"));
    mockVotar.mockResolvedValue({ data: undefined });

    const v = await render(<Panic />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("panic-hold"));
    });
    await asentar();

    expect(v.queryByText("ENVIANDO…")).toBeNull();
    expect(v.getByTestId("panic-status")).toHaveTextContent("NO SE PUDO ENVIAR");
  });

  it("un HTTP de error (sin lanzar) sigue pintando el mismo desenlace", async () => {
    mockVotar.mockResolvedValue({ data: undefined, error: { detail: "429" } });

    const v = await render(<Panic />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("panic-hold"));
    });
    await asentar();

    expect(v.getByTestId("panic-status")).toHaveTextContent("NO SE PUDO ENVIAR");
    expect(v.queryByText("ENVIANDO…")).toBeNull();
  });

  it("el voto que SÍ sale pinta las confirmaciones, no un error", async () => {
    mockVotar.mockResolvedValue({
      data: { status: "counted", distinct_voters: 1, remaining: 1, window_s: 30 },
    });

    const v = await render(<Panic />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("panic-hold"));
    });
    await asentar();

    expect(v.getByTestId("panic-status")).toHaveTextContent("1 DE 2 CONFIRMACIONES");
  });
});

describe("1.9 · pánico · sin sitio vigilado DECLARA su estado", () => {
  it("lo dice con el contrato de estados, no con un texto suelto", async () => {
    mockSitio = null;

    const v = await render(<Panic />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Vincúlese a su edificio/);
    expect(v.queryByTestId("panic-hold")).toBeNull();
  });
});
