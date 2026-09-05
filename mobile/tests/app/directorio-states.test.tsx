// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] El directorio es la pantalla a la que la alarma del inmueble MANDA
// al ocupante («ATIENDA A SU BRIGADA»), así que su copia offline y sus cuatro
// estados no son cosmética: es el teléfono al que va a llamar.
//
// Aquí importa una distinción que el marcado ya declara y nadie había medido:
// «su edificio no publica contactos» (vacío) NO es «no hay copia local»
// (error). La primera es una verdad del edificio; la segunda, una del teléfono.
import type { DirectoryEntryOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Directorio from "@/app/(occupant)/directorio";

const SITE = "11111111-1111-1111-1111-111111111111";
// [T-5.21] El «ahora» del fixture es RELATIVO al reloj de verdad. Era un epoch
// clavado en 2027, y desde que la frescura sale del reloj —y no de que la
// consulta falle— un `dataUpdatedAt` en el futuro sale «fresco» y el estado
// `stale` no se materializaba. Contar hacia atrás desde `Date.now()` hace que
// «hace tres minutos» signifique de verdad hace tres minutos.
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => mockSitio,
}));

type Resultado = ReturnType<typeof resultado>;
let mockDirectorio: Resultado;
jest.mock("@/offline/useCachedQuery", () => ({
  useCachedQuery: () => mockDirectorio,
}));

// ------------------------------------------------------------------ datos

const ENTRADAS: DirectoryEntryOut[] = [
  {
    user_id: "u-1",
    role: "brigadista",
    display_name: "Ana Ruiz",
    phone: "+525555550001",
    zone_id: "z-1",
    zone_name: "Piso 12",
  },
];

function resultado(over: Record<string, unknown> = {}) {
  return {
    data: null as DirectoryEntryOut[] | null,
    staleSinceMs: null as number | null,
    loading: false,
    error: null as string | null,
    refetch: jest.fn(),
    ...over,
  };
}

beforeEach(() => {
  mockSitio = SITE;
  mockDirectorio = resultado();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("1.7 · directorio · qué lee el ocupante cuando algo falta", () => {
  it("sin sitio vigilado dice cómo vincularse, no un roster vacío", async () => {
    mockSitio = null;

    const v = await render(<Directorio />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin sitio vigilado/);
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Vincúlese/);
  });

  it("el edificio SIN contactos publicados es un vacío distinto del fallo", async () => {
    mockDirectorio = resultado({ data: [] });

    const v = await render(<Directorio />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/aún no publica contactos/);
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("sin copia local lo DICE — jamás una lista vacía que se lea como «no hay brigada»", async () => {
    mockDirectorio = resultado({ error: "No hay copia local de esta información." });

    const v = await render(<Directorio />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-error")).toHaveTextContent(/No hay copia local/);
    expect(v.queryByText(/aún no publica contactos/)).toBeNull();
  });

  it("la copia offline se pinta CON su edad, no como si fuera de ahora", async () => {
    mockDirectorio = resultado({ data: ENTRADAS, staleSinceMs: AHORA - 3 * 60_000 });

    const v = await render(<Directorio />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByText("Ana Ruiz")).toBeTruthy();
  });
});

describe("1.7 · directorio · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockDirectorio = resultado({
          loading: e === "loading",
          error: e === "error" ? "No hay copia local de esta información." : null,
          data: e === "stale" ? ENTRADAS : null,
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
        });
        return <Directorio />;
      },
      { asentar },
    );
  });
});
