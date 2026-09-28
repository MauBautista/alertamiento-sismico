// [T-9.33 · D-43] La lógica de CONFIRMAR / ESCALAR del lado del cliente: la
// cabeza vigente sale de la cadena (la más reciente primero), confirmar manda
// SU dictamen_id, un 409 recarga la cadena y un 403 se dice.
import {
  confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost,
  listDictamensIncidentsIncidentIdDictamensGet,
  requestDictamenIncidentsIncidentIdDictamenRequestPost,
} from "@takab/sdk";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { useConfirmarDictamen } from "./useConfirmarDictamen";

jest.mock("@takab/sdk", () => ({
  listDictamensIncidentsIncidentIdDictamensGet: jest.fn(),
  confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost: jest.fn(),
  requestDictamenIncidentsIncidentIdDictamenRequestPost: jest.fn(),
}));

const list = listDictamensIncidentsIncidentIdDictamensGet as jest.Mock;
const confirm = confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost as jest.Mock;
const request = requestDictamenIncidentsIncidentIdDictamenRequestPost as jest.Mock;

function fila(id: string, over: Record<string, unknown> = {}) {
  return {
    dictamen_id: id,
    incident_id: "i-1",
    tenant_id: "t-1",
    status: "inhabit_monitor",
    band: "amarillo",
    signed_by: null,
    signature_kind: null,
    supersedes_dictamen_id: null,
    created_at: "2026-09-27T10:00:00Z",
    basis: { motivos: ["pga_banda_amarilla"] },
    ...over,
  };
}

function ok<T>(data: T, status = 200) {
  return { data, error: undefined, response: { status } };
}

function falla(status: number, detail = "x") {
  return { data: undefined, error: { detail }, response: { status } };
}

// Sin `gcTime: 0` y sin vaciar los clientes, los temporizadores de react-query
// mantienen vivo el proceso de jest después de la última prueba.
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

async function montar(incidentId: string | null = "i-1") {
  const r = await renderHook(() => useConfirmarDictamen(incidentId), { wrapper: envoltorio() });
  return r;
}

beforeEach(() => {
  list.mockReset();
  confirm.mockReset();
  request.mockReset();
  // La cadena llega más reciente primero: la cabeza es la PRIMERA.
  list.mockResolvedValue(ok({ items: [fila("d-2"), fila("d-1")] }));
});

it("sin incidente no pregunta nada", async () => {
  const { result } = await montar(null);
  expect(list).not.toHaveBeenCalled();
  expect(result.current.cabeza).toBeUndefined();
});

it("la cabeza es la primera de la cadena", async () => {
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza?.dictamen_id).toBe("d-2"));
});

it("confirmar manda el dictamen_id de la CABEZA y queda confirmado", async () => {
  confirm.mockResolvedValue(ok(fila("d-3", { signed_by: "u-1" }), 201));
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza).toBeDefined());
  await act(async () => {
    await result.current.confirmar();
  });
  expect(confirm).toHaveBeenCalledWith({ path: { incident_id: "i-1", dictamen_id: "d-2" } });
  expect(result.current.confirmacion.estado).toBe("hecho");
  // Recarga la cadena para enseñar la fila nueva firmada.
  expect(list.mock.calls.length).toBeGreaterThanOrEqual(2);
});

it("409 ⇒ la cabeza cambió: se DICE y se recarga la cadena", async () => {
  confirm.mockResolvedValue(falla(409));
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza).toBeDefined());
  const antes = list.mock.calls.length;
  await act(async () => {
    await result.current.confirmar();
  });
  expect(result.current.confirmacion.estado).toBe("error");
  expect(result.current.confirmacion.mensaje).toMatch(/cambió/);
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(antes));
});

// [F3·r3] El 409 «requiere inspector» (hay un daño ROJO reportado) NO es «la
// cabeza cambió»: se explica y se manda a ESCALAR, no a revisar el vigente.
it("409 «requiere inspector» ⇒ se explica el daño y se ofrece escalar", async () => {
  confirm.mockResolvedValue(
    falla(
      409,
      "hay daños reportados que exigen inspección (muros): requiere inspector, no se confirma",
    ),
  );
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza).toBeDefined());
  await act(async () => {
    await result.current.confirmar();
  });
  expect(result.current.confirmacion.estado).toBe("error");
  expect(result.current.confirmacion.requiereInspector).toBe(true);
  expect(result.current.confirmacion.mensaje).toMatch(/daño/);
  expect(result.current.confirmacion.mensaje).toMatch(/inspector/);
  expect(result.current.confirmacion.mensaje).not.toMatch(/cambió/);
});

// [F3·r3] El 409 de un VERDE: no es «la cabeza cambió» ni «reintente».
it("409 del VERDE ⇒ explica que lo firma el sistema y no se reintenta", async () => {
  confirm.mockResolvedValue(
    falla(409, "el VERDE lo firma el sistema tras la gracia (o el inspector); no se confirma"),
  );
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza).toBeDefined());
  await act(async () => {
    await result.current.confirmar();
  });
  expect(result.current.confirmacion.estado).toBe("error");
  expect(result.current.confirmacion.loFirmaElSistema).toBe(true);
  expect(result.current.confirmacion.mensaje).toMatch(/sistema/);
  expect(result.current.confirmacion.mensaje).not.toMatch(/cambió/);
});

// [F3·r3] Antes de mandar, se relee la cabeza: si otra firma o una subida de
// banda la cambió bajo la brigada, NO se envía la confirmación de la vieja.
it("confirmar relee la cabeza ANTES de enviar: si cambió, no envía y lo dice", async () => {
  list.mockReset();
  list
    .mockResolvedValueOnce(ok({ items: [fila("d-2"), fila("d-1")] }))
    .mockResolvedValue(ok({ items: [fila("d-5"), fila("d-2"), fila("d-1")] }));
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza?.dictamen_id).toBe("d-2"));
  await act(async () => {
    await result.current.confirmar();
  });
  expect(confirm).not.toHaveBeenCalled();
  expect(result.current.confirmacion.estado).toBe("error");
  expect(result.current.confirmacion.mensaje).toMatch(/cambió/);
  expect(result.current.cabeza?.dictamen_id).toBe("d-5");
});

// [F3·r3] «Confirmado» vale para ESE dictamen_id. Si luego aparece otra cabeza
// sin firmar (la regla subió la banda por un daño tardío), se vuelve a ofrecer.
it("«hecho» se liga al dictamen confirmado: otra cabeza sin firmar vuelve a ofrecer", async () => {
  list.mockReset();
  list
    .mockResolvedValueOnce(ok({ items: [fila("d-2")] }))
    .mockResolvedValueOnce(ok({ items: [fila("d-2")] }))
    .mockResolvedValue(ok({ items: [fila("d-4"), fila("d-3", { signed_by: "u-1" })] }));
  confirm.mockResolvedValue(ok(fila("d-3", { signed_by: "u-1" }), 201));
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza?.dictamen_id).toBe("d-2"));
  await act(async () => {
    await result.current.confirmar();
  });
  expect(confirm).toHaveBeenCalledWith({ path: { incident_id: "i-1", dictamen_id: "d-2" } });
  await waitFor(() => expect(result.current.cabeza?.dictamen_id).toBe("d-4"));
  expect(result.current.confirmacion.estado).toBe("idle");
});

it("403 ⇒ no le corresponde: se dice y se ofrece escalar", async () => {
  confirm.mockResolvedValue(falla(403));
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza).toBeDefined());
  await act(async () => {
    await result.current.confirmar();
  });
  expect(result.current.confirmacion.estado).toBe("error");
  expect(result.current.confirmacion.mensaje).toMatch(/inspector/);
});

it("sin red ⇒ error declarado y se puede reintentar", async () => {
  confirm.mockRejectedValueOnce(new Error("offline"));
  const { result } = await montar();
  await waitFor(() => expect(result.current.cabeza).toBeDefined());
  await act(async () => {
    await result.current.confirmar();
  });
  expect(result.current.confirmacion.estado).toBe("error");
  confirm.mockResolvedValueOnce(ok(fila("d-3", { signed_by: "u-1" }), 201));
  await act(async () => {
    await result.current.confirmar();
  });
  expect(result.current.confirmacion.estado).toBe("hecho");
});

it("escalar al inspector usa la solicitud de dictamen que ya existe", async () => {
  request.mockResolvedValue(ok({ action_id: "a-1" }, 201));
  const { result } = await montar();
  await act(async () => {
    await result.current.escalar();
  });
  expect(request).toHaveBeenCalledWith({
    path: { incident_id: "i-1" },
    body: { note: "Escalado desde la app al confirmar el dictamen." },
  });
  expect(result.current.escalado.estado).toBe("hecho");
});

it("escalar con una solicitud ya pendiente (409) cuenta como hecho, y lo dice", async () => {
  request.mockResolvedValue(falla(409));
  const { result } = await montar();
  await act(async () => {
    await result.current.escalar();
  });
  expect(result.current.escalado.estado).toBe("hecho");
  expect(result.current.escalado.mensaje).toMatch(/ya estaba/);
});

it("escalar sin permiso (403) se dice", async () => {
  request.mockResolvedValue(falla(403));
  const { result } = await montar();
  await act(async () => {
    await result.current.escalar();
  });
  expect(result.current.escalado.estado).toBe("error");
  expect(result.current.escalado.mensaje).toMatch(/administración/);
});

// [D-49 · F3·r4] Cada respuesta de confirmar se EXPLICA con su causa real (los
// `detail` literales de `routers/dictamens.confirm_dictamen`); ninguna cae en el
// genérico «compruebe la conexión» ni vuelve muda a `idle`.
describe("[D-49] cada respuesta de confirmar dice por qué", () => {
  async function confirmarCon(respuesta: unknown) {
    confirm.mockResolvedValue(respuesta);
    const { result } = await montar();
    await waitFor(() => expect(result.current.cabeza).toBeDefined());
    await act(async () => {
      await result.current.confirmar();
    });
    return result;
  }

  it("409 R1 (el edificio se mueve) ⇒ «espere a que el edificio vuelva a calma», reintentable", async () => {
    const r = await confirmarCon(
      falla(409, "el edificio sigue en movimiento: espere a que el edificio vuelva a calma"),
    );
    expect(r.current.confirmacion.estado).toBe("error");
    expect(r.current.confirmacion.esperaCalma).toBe(true);
    expect(r.current.confirmacion.mensaje).toMatch(/espere a que el edificio vuelva a calma/i);
    expect(r.current.confirmacion.requiereInspector).not.toBe(true);
  });

  it("409 de banda (no es AMARILLO de la regla) ⇒ «lo firma el inspector», terminal", async () => {
    const r = await confirmarCon(
      falla(409, "sólo se confirma un AMARILLO de la regla; este dictamen lo firma el inspector"),
    );
    expect(r.current.confirmacion.loFirmaElInspector).toBe(true);
    expect(r.current.confirmacion.mensaje).toMatch(/lo firma el inspector/i);
    expect(r.current.confirmacion.mensaje).not.toMatch(/cambió/);
  });

  it("409 VERDE ⇒ «el VERDE lo firma el sistema», terminal", async () => {
    const r = await confirmarCon(
      falla(409, "el VERDE lo firma el sistema tras la gracia (o el inspector); no se confirma"),
    );
    expect(r.current.confirmacion.loFirmaElSistema).toBe(true);
    expect(r.current.confirmacion.mensaje).toMatch(/lo emite el sistema/);
  });

  it("409 «ya está firmado» ⇒ lo dice, no «cambió o ya fue firmado» genérico", async () => {
    const r = await confirmarCon(falla(409, "el dictamen vigente ya está firmado"));
    expect(r.current.confirmacion.yaFirmado).toBe(true);
    expect(r.current.confirmacion.mensaje).toMatch(/ya estaba firmado/i);
  });

  it("404 ⇒ fuera de su alcance, NO «compruebe la conexión»", async () => {
    const r = await confirmarCon(falla(404, "incidente no encontrado"));
    expect(r.current.confirmacion.fueraDeAlcance).toBe(true);
    expect(r.current.confirmacion.mensaje).toMatch(/no pertenece a su inmueble/i);
    expect(r.current.confirmacion.mensaje).not.toMatch(/conexión/);
  });

  it("cabeza YA firmada al releerla ⇒ mensaje, no un idle mudo, y no se envía", async () => {
    const { result } = await montar();
    await waitFor(() => expect(result.current.cabeza).toBeDefined());
    list.mockResolvedValue(ok({ items: [fila("d-2", { signed_by: "u-9" }), fila("d-1")] }));
    await act(async () => {
      await result.current.confirmar();
    });
    expect(confirm).not.toHaveBeenCalled();
    expect(result.current.confirmacion.estado).not.toBe("idle");
    expect(result.current.confirmacion.yaFirmado).toBe(true);
    expect(result.current.confirmacion.mensaje).toMatch(/ya estaba firmado/i);
  });
});
