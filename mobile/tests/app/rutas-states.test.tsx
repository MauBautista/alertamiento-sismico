// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] Las rutas de evacuación se consultan CON EL EDIFICIO SONANDO y, muy
// probablemente, sin red. Que la copia offline se distinga de la ausencia de
// copia no es un matiz de UI: es la diferencia entre bajar por donde toca y
// quedarse mirando una lista vacía.
import type { SiteAssetOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Rutas from "@/app/(occupant)/rutas";

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
let mockAssets: Resultado;
jest.mock("@/offline/useCachedQuery", () => ({
  useCachedQuery: () => mockAssets,
}));

// La caché de archivos toca `expo-file-system`; su lógica la prueba
// `assetsCache` por su cuenta. Aquí sólo hace falta que no pregunte al disco.
jest.mock("@/features/routes/assetsCache", () => ({
  assetRowKind: () => "downloadable",
  isCached: jest.fn(async () => false),
  downloadAsset: jest.fn(async () => undefined),
  openAsset: jest.fn(async () => undefined),
}));

// ------------------------------------------------------------------ datos

const ASSETS: SiteAssetOut[] = [
  {
    asset_id: "a-1",
    kind: "evac_route",
    title: "Ruta de evacuación · Piso 12",
    description: "Escalera norte",
    content_type: "application/pdf",
    updated_at: new Date(AHORA - 86_400_000).toISOString(),
    url: "https://s3/ruta.pdf?sig",
    zone_id: "z-1",
  },
];

function resultado(over: Record<string, unknown> = {}) {
  return {
    data: null as SiteAssetOut[] | null,
    staleSinceMs: null as number | null,
    loading: false,
    error: null as string | null,
    refetch: jest.fn(),
    ...over,
  };
}

beforeEach(() => {
  mockSitio = SITE;
  mockAssets = resultado();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("1.6 · rutas · el vacío del edificio no es el fallo del teléfono", () => {
  it("sin sitio vigilado dice cómo vincularse", async () => {
    mockSitio = null;

    const v = await render(<Rutas />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin sitio vigilado/);
  });

  it("el edificio SIN rutas publicadas lo dice tal cual", async () => {
    mockAssets = resultado({ data: [] });

    const v = await render(<Rutas />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/aún no publica rutas ni manuales/);
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("sin copia local lo DICE — no finge que el edificio no tiene rutas", async () => {
    mockAssets = resultado({ error: "No hay copia local de esta información." });

    const v = await render(<Rutas />);
    await asentar();

    expect(v.getByTestId("state-error")).toHaveTextContent(/No hay copia local/);
    expect(v.queryByText(/aún no publica rutas/)).toBeNull();
  });

  it("la copia offline se pinta CON su edad", async () => {
    mockAssets = resultado({ data: ASSETS, staleSinceMs: AHORA - 20 * 60_000 });

    const v = await render(<Rutas />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByTestId("asset-a-1")).toBeTruthy();
  });
});

describe("1.6 · rutas · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockAssets = resultado({
          loading: e === "loading",
          error: e === "error" ? "No hay copia local de esta información." : null,
          data: e === "stale" ? ASSETS : null,
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
        });
        return <Rutas />;
      },
      { asentar },
    );
  });
});
