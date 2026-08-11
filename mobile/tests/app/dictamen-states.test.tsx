// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] El certificado de reingreso es el papel con el que se deja entrar
// gente a un edificio después de un sismo. Sus cuatro estados son de
// compliance, no de UI: «no hay dictamen firmado» y «no pudimos consultarlo»
// autorizan cosas distintas, y un spinner eterno no autoriza ninguna.
import type { MobileDictamenOut, MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Dictamen from "@/app/dictamen";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = 1_800_000_000_000;

// ------------------------------------------------------------------ mocks

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => mockSitio,
}));

let mockSnapshot: { data: MobileStateOut | null };
jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => mockSnapshot,
}));

// La consulta del dictamen es la que gobierna el marco: se conduce directa.
type Consulta = ReturnType<typeof consulta>;
let mockDictamen: Consulta;
jest.mock("@tanstack/react-query", () => ({
  useQuery: () => mockDictamen,
}));

jest.mock("expo-sharing", () => ({ shareAsync: jest.fn(async () => undefined) }));
jest.mock("expo-file-system", () => ({
  Paths: { document: "file:///doc" },
  File: class {
    uri = "file:///doc/dictamen.pdf";
    exists = false;
    delete() {}
    static downloadFileAsync: () => Promise<void> = jest.fn(async () => undefined);
  },
}));

// ------------------------------------------------------------------ datos

function conIncidente(): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "shaking_concluded",
    incident: {
      incident_id: "inc-1",
      opened_at: new Date(AHORA - 900_000).toISOString(),
      trigger: "sasmex",
      max_pga_g: 0.152,
      node_count: null,
    },
    latest_tier: "evacuate_or_hold",
    my_zone: null,
    reentry: { blocked: true, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
    site_health: {} as never,
  } as unknown as MobileStateOut;
}

function firmado(over: Partial<MobileDictamenOut> = {}): MobileDictamenOut {
  return {
    incident_id: "inc-1",
    signed: true,
    folio: "abcdef12-3456-7890-abcd-ef1234567890",
    status: "inhabit_monitor",
    signed_by: "70000000-1111-2222-3333-444444444444",
    signed_at: "2026-07-16T18:30:00Z",
    habitable: true,
    pdf_url: "https://s3/report.pdf?sig",
    ...over,
  };
}

function consulta(over: Record<string, unknown> = {}) {
  return {
    data: undefined as MobileDictamenOut | undefined,
    isLoading: false,
    isError: false,
    failureCount: 0,
    dataUpdatedAt: 0,
    refetch: jest.fn(),
    ...over,
  };
}

beforeEach(() => {
  mockSitio = SITE;
  mockSnapshot = { data: conIncidente() };
  mockDictamen = consulta();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("2.7 · dictamen · sin incidente, sin firma y sin red dicen cosas distintas", () => {
  it("sin incidente activo: no hay dictamen que consultar", async () => {
    mockSnapshot = { data: null };

    const v = await render(<Dictamen />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin incidente activo/);
    expect(v.queryByTestId("state-loading")).toBeNull();
  });

  it("hay incidente pero el dictamen NO está firmado: se dice, no se insinúa", async () => {
    // `certificateView` devuelve null sin firma: la pantalla NO puede quedarse
    // en blanco ni sugerir que el reingreso está aprobado.
    mockDictamen = consulta({ data: firmado({ signed: false, folio: null }) });

    const v = await render(<Dictamen />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Aún no hay un dictamen firmado/);
    expect(v.queryByTestId("certificate")).toBeNull();
  });

  it("si no se pudo consultar, lo DICE — jamás se lee como «no está firmado»", async () => {
    mockDictamen = consulta({ isError: true });

    const v = await render(<Dictamen />);
    await asentar();

    expect(v.getByTestId("state-error")).toHaveTextContent(/No se pudo cargar el dictamen/);
    expect(v.queryByText(/Aún no hay un dictamen firmado/)).toBeNull();
  });

  it("el certificado retenido se pinta CON su edad, no como recién verificado", async () => {
    mockDictamen = consulta({
      data: firmado(),
      failureCount: 2,
      dataUpdatedAt: AHORA - 30 * 60_000,
    });

    const v = await render(<Dictamen />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByTestId("certificate")).toBeTruthy();
  });
});

describe("2.7 · dictamen · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = SITE;
        mockSnapshot = { data: e === "empty" ? null : conIncidente() };
        mockDictamen = consulta({
          isLoading: e === "loading",
          isError: e === "error",
          data: e === "stale" ? firmado() : undefined,
          failureCount: e === "stale" ? 1 : 0,
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : 0,
        });
        return <Dictamen />;
      },
      { asentar },
    );
  });
});
