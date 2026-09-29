// [T-9.80 · D-48] El hook de los contactos de emergencia: qué le pide a la nube,
// qué manda al GUARDAR y cómo reporta el 409 (aviso cambiado) y el 422.
import {
  deleteEmergencyContactsMeEmergencyContactsDelete,
  getEmergencyContactsMeEmergencyContactsGet,
  putEmergencyContactsMeEmergencyContactsPut,
} from "@takab/sdk";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { useConteoContactos, useEmergencyContacts } from "./useEmergencyContacts";

jest.mock("@takab/sdk", () => ({
  getEmergencyContactsMeEmergencyContactsGet: jest.fn(),
  putEmergencyContactsMeEmergencyContactsPut: jest.fn(),
  deleteEmergencyContactsMeEmergencyContactsDelete: jest.fn(),
}));

const get = getEmergencyContactsMeEmergencyContactsGet as jest.Mock;
const put = putEmergencyContactsMeEmergencyContactsPut as jest.Mock;
const del = deleteEmergencyContactsMeEmergencyContactsDelete as jest.Mock;

const AVISO_V1 = { version: "2026-09-v1", texto: "Aviso uno", provisional: true };
const AVISO_V2 = { version: "2026-09-v2", texto: "Aviso dos", provisional: false };
const CONTACTO = {
  consent_version: AVISO_V1.version,
  consented_at: "2026-09-27T10:00:00Z",
  display_name: "Ana",
  email: "ana@example.com",
  phone: null,
  posicion: 1,
};

const clientes: QueryClient[] = [];
afterEach(() => {
  for (const c of clientes.splice(0)) {
    c.clear();
  }
});

function envoltorio() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clientes.push(qc);
  function Envoltorio({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return Envoltorio;
}

beforeEach(() => {
  get.mockReset();
  put.mockReset();
  del.mockReset();
  get.mockResolvedValue({ data: { contactos: [CONTACTO], aviso: AVISO_V1 }, response: { status: 200 } });
});

describe("useEmergencyContacts · lectura", () => {
  it("trae los contactos y el aviso, fresco y sin error", async () => {
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    expect(r.result.current.data?.contactos).toHaveLength(1);
    expect(r.result.current.data?.aviso.version).toBe(AVISO_V1.version);
    expect(r.result.current.loading).toBe(false);
    expect(r.result.current.error).toBeNull();
    expect(r.result.current.staleSinceMs).toBeNull();
  });

  it("si el SDK lanza, error con texto y sin dato inventado", async () => {
    get.mockRejectedValue(new TypeError("Network request failed"));
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.error).not.toBeNull());
    expect(r.result.current.data).toBeNull();
    expect(r.result.current.loading).toBe(false);
  });

  it("el conteo para la fila de CUENTA sale de la misma consulta", async () => {
    const r = await renderHook(() => useConteoContactos(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current).toBe(1));
  });
});

describe("useEmergencyContacts · GUARDAR", () => {
  it("manda la lista ENTERA con la versión del aviso y deja el dato del servidor", async () => {
    const guardado = { contactos: [CONTACTO, { ...CONTACTO, posicion: 2, email: "b@x.mx" }], aviso: AVISO_V1 };
    put.mockResolvedValue({ data: guardado, response: { status: 200 } });
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());

    const cuerpo = {
      consentimiento_version: AVISO_V1.version,
      contactos: [
        { display_name: "Ana", email: "ana@example.com", phone: null },
        { display_name: "Beto", email: "b@x.mx", phone: "+525512345678" },
      ],
    };
    let desenlace: unknown;
    await act(async () => {
      desenlace = await r.result.current.guardar(cuerpo);
    });
    expect(put).toHaveBeenCalledWith({ body: cuerpo });
    expect(desenlace).toEqual({ tipo: "ok" });
    await waitFor(() => expect(r.result.current.data?.contactos).toHaveLength(2));
  });

  it("un 409 recarga el aviso y lo reporta como consentimiento desactualizado", async () => {
    put.mockResolvedValue({
      data: undefined,
      error: { detail: "consentimiento_desactualizado" },
      response: { status: 409 },
    });
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    get.mockResolvedValue({ data: { contactos: [CONTACTO], aviso: AVISO_V2 }, response: { status: 200 } });

    let desenlace: unknown;
    await act(async () => {
      desenlace = await r.result.current.guardar({ consentimiento_version: AVISO_V1.version, contactos: [] });
    });
    expect(desenlace).toEqual({ tipo: "consentimiento" });
    await waitFor(() => expect(r.result.current.data?.aviso.version).toBe(AVISO_V2.version));
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("un 422 viaja por campo", async () => {
    put.mockResolvedValue({
      data: undefined,
      error: { detail: [{ loc: ["body", "contactos", 0, "email"], msg: "Value error, correo inválido" }] },
      response: { status: 422 },
    });
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    let desenlace: unknown;
    await act(async () => {
      desenlace = await r.result.current.guardar({ consentimiento_version: AVISO_V1.version, contactos: [] });
    });
    expect(desenlace).toEqual({ tipo: "validacion", campos: { "0.email": "correo inválido" }, general: null });
  });

  it("si el SDK lanza al guardar, el desenlace es un fallo con texto (no una excepción)", async () => {
    put.mockRejectedValue(new TypeError("Network request failed"));
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    let desenlace: { tipo: string } | undefined;
    await act(async () => {
      desenlace = await r.result.current.guardar({ consentimiento_version: AVISO_V1.version, contactos: [] });
    });
    expect(desenlace?.tipo).toBe("fallo");
  });
});

describe("useEmergencyContacts · BORRAR TODOS", () => {
  it("un 204 deja la lista vacía y conserva el aviso", async () => {
    del.mockResolvedValue({ data: undefined, response: { status: 204 } });
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    let desenlace: unknown;
    await act(async () => {
      desenlace = await r.result.current.borrarTodos();
    });
    expect(del).toHaveBeenCalledTimes(1);
    expect(desenlace).toEqual({ tipo: "ok" });
    await waitFor(() => expect(r.result.current.data?.contactos).toEqual([]));
    expect(r.result.current.data?.aviso.version).toBe(AVISO_V1.version);
  });

  it("un borrado que no llega es un fallo, no un «listo»", async () => {
    del.mockResolvedValue({ data: undefined, error: { detail: "x" }, response: { status: 503 } });
    const r = await renderHook(() => useEmergencyContacts(), { wrapper: envoltorio() });
    await waitFor(() => expect(r.result.current.data).not.toBeNull());
    let desenlace: { tipo: string } | undefined;
    await act(async () => {
      desenlace = await r.result.current.borrarTodos();
    });
    expect(desenlace?.tipo).toBe("fallo");
    expect(r.result.current.data?.contactos).toHaveLength(1);
  });
});
