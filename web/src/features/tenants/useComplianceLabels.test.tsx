// [T-2.82.b] Hueco de cobertura del lote T-2.82: `useComplianceLabels` y
// `useSaveComplianceLabels` NO se ejecutaban en ningún test. Su único consumidor
// —`ComplianceLabelsCard`— mockea el módulo entero, así que el mapeo de errores
// 403/404/409/422 y el umbral de DATOS RETENIDOS eran código de producción que
// nunca había corrido: dos cosas que solo se ven cuando algo va mal, probadas
// únicamente por el camino en que todo va bien.
//
// Lo que se prueba aquí es el hook DE VERDAD (`renderHook`), no un doble suyo.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ComplianceDoc } from "./useComplianceLabels";
import {
  COMPLIANCE_STALE_MS,
  complianceErrorMessage,
  useComplianceLabels,
  useSaveComplianceLabels,
} from "./useComplianceLabels";

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@takab/sdk", () => ({
  client: {
    get: (...a: unknown[]) => mocks.get(...a),
    put: (...a: unknown[]) => mocks.put(...a),
  },
}));

/** Tipado contra el CONTRATO: si el SDK gana un campo requerido, esto no compila. */
const DOC: ComplianceDoc = {
  tenant_id: "t-1",
  provenance: "declared_by_tenant",
  notice: "TAKAB no verifica ni certifica.",
  items: [],
  notes: ["SIN MARCO NORMATIVO DECLARADO · la ausencia no significa cumplimiento."],
  unreadable: null,
  updated_at: null,
  updated_by: null,
};

const T0 = Date.parse("2026-08-13T12:00:00Z");
let ahora = T0;

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ok = (doc: ComplianceDoc = DOC) => ({ data: doc, response: { status: 200 } });
/** El cliente del SDK NO lanza en error HTTP: devuelve `data: undefined`. */
const fallo = (status: number) => ({ data: undefined, response: { status } });

beforeEach(() => {
  ahora = T0;
  vi.spyOn(Date, "now").mockImplementation(() => ahora);
  vi.clearAllMocks();
  mocks.get.mockResolvedValue(ok());
  mocks.put.mockResolvedValue(ok());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("complianceErrorMessage · cada fallo dice QUÉ hacer", () => {
  it.each([
    [403, /SIN PERMISO/],
    [404, /NO ENCONTRADO/],
    [409, /CAMBIÓ EN EL SERVIDOR/],
    [422, /AFIRMACIÓN INVÁLIDA/],
  ])("%i tiene su propio texto", (status, patron) => {
    expect(complianceErrorMessage(status)).toMatch(patron);
  });

  it("un estado no previsto NO se disfraza de ninguno de los cuatro", () => {
    // Inventarle una causa a un 503 es peor que decir el número: el operador
    // saldría a pedir un permiso que ya tiene.
    const otro = complianceErrorMessage(503);
    expect(otro).toContain("503");
    for (const conocido of [403, 404, 409, 422]) {
      expect(otro).not.toBe(complianceErrorMessage(conocido));
    }
  });
});

describe("useComplianceLabels · el hook, no un doble suyo", () => {
  it("pide el documento del cliente y lo entrega", async () => {
    const { result } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await waitFor(() => expect(result.current.doc).not.toBeNull());
    expect(mocks.get).toHaveBeenCalledWith({ url: "/tenants/t-1/compliance-labels" });
    expect(result.current.doc).toEqual(DOC);
    expect(result.current.error).toBeNull();
  });

  it("sin cliente seleccionado no pregunta NADA y no se queda cargando", () => {
    // `loading` con `tenantId === null` dejaría un esqueleto eterno en la ficha.
    const { result } = renderHook(() => useComplianceLabels(null), { wrapper });
    expect(mocks.get).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.doc).toBeNull();
  });

  it.each([403, 404, 409, 422])("un %i llega a la pantalla con su texto", async (status) => {
    mocks.get.mockResolvedValue(fallo(status));
    const { result } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toBe(complianceErrorMessage(status));
    expect(result.current.doc).toBeNull();
  });

  it("`refetch` vuelve a preguntar", async () => {
    const { result } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await waitFor(() => expect(result.current.doc).not.toBeNull());
    result.current.refetch();
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
  });
});

describe("useComplianceLabels · el umbral de DATOS RETENIDOS (regla de oro 7)", () => {
  it("recién leído no está viejo", async () => {
    const { result } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await waitFor(() => expect(result.current.doc).not.toBeNull());
    expect(result.current.staleSince).toBeNull();
  });

  it("EN el umbral todavía no; PASADO el umbral delata la hora del último dato", async () => {
    const { result, rerender } = renderHook(() => useComplianceLabels("t-1"), { wrapper });
    await waitFor(() => expect(result.current.doc).not.toBeNull());

    // Justo en los 5 min: el corte es estricto (`>`), así que aún es fresco. Si
    // alguien lo cambia a `>=`, este caso lo dice.
    ahora = T0 + COMPLIANCE_STALE_MS;
    rerender();
    expect(result.current.staleSince).toBeNull();

    ahora = T0 + COMPLIANCE_STALE_MS + 1;
    rerender();
    // No basta con "es viejo": la pantalla tiene que poder decir DESDE CUÁNDO,
    // y ese sello es el del último dato bueno, no el de ahora.
    expect(result.current.staleSince).toBe(T0);
  });

  it("el umbral son 5 minutos, y se afirma en el sitio donde se lee", () => {
    expect(COMPLIANCE_STALE_MS).toBe(300_000);
  });
});

describe("useSaveComplianceLabels · el hook, no un doble suyo", () => {
  const BODY = {
    items: [{ key: "regulatory_framework", claim: "Título Sexto", reference: "Gaceta 2004" }],
    base_updated_at: null,
  };

  it("manda el reemplazo COMPLETO con su testigo de concurrencia", async () => {
    const { result } = renderHook(() => useSaveComplianceLabels("t-1"), { wrapper });
    result.current.save(BODY);
    await waitFor(() =>
      expect(mocks.put).toHaveBeenCalledWith({
        url: "/tenants/t-1/compliance-labels",
        body: BODY,
      }),
    );
  });

  it("el 409 del testigo llega al operador como 'recarga y reintenta'", async () => {
    // Es EL error de esta pantalla: dos personas editando el marco declarado del
    // mismo cliente. Perder ese texto dejaría al que guarda segundo creyendo que
    // falló la red.
    mocks.put.mockResolvedValue(fallo(409));
    const { result } = renderHook(() => useSaveComplianceLabels("t-1"), { wrapper });
    result.current.save(BODY);
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toBe(complianceErrorMessage(409));
  });

  it.each([403, 422])("un %i de guardado también dice qué pasó", async (status) => {
    mocks.put.mockResolvedValue(fallo(status));
    const { result } = renderHook(() => useSaveComplianceLabels("t-1"), { wrapper });
    result.current.save(BODY);
    await waitFor(() => expect(result.current.error).toBe(complianceErrorMessage(status)));
  });

  it("tras guardar, lo que se relee es lo GUARDADO y no la copia en caché", async () => {
    // Sin la invalidación, la ficha seguiría enseñando el documento anterior —
    // y de ahí sale un dictamen firmado con etiquetas que ya no son las suyas.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const wrap = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useSaveComplianceLabels("t-1"), { wrapper: wrap });
    result.current.save(BODY);
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["compliance-labels", "t-1"] }),
    );
  });
});
