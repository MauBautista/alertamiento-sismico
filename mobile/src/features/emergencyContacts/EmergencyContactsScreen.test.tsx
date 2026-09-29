// [T-9.80 · D-48] CUENTA → CONTACTOS DE EMERGENCIA. Lo que la persona ve y lo que
// sale hacia la nube cuando pulsa GUARDAR o BORRAR TODOS.
import type { ContactosOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { EmergencyContactsScreen } from "./EmergencyContactsScreen";
import type { Desenlace } from "./useEmergencyContacts";

const AVISO = { version: "2026-09-v1", texto: "Texto completo del aviso del servidor.", provisional: true };

function contacto(i: number, over: Partial<ContactosOut["contactos"][number]> = {}) {
  return {
    consent_version: AVISO.version,
    consented_at: "2026-09-27T10:00:00Z",
    display_name: `Contacto ${i}`,
    email: `c${i}@example.com`,
    phone: null,
    posicion: i,
    ...over,
  };
}

function datos(n: number, aviso = AVISO): ContactosOut {
  return { aviso, contactos: Array.from({ length: n }, (_, k) => contacto(k + 1)) };
}

async function montar(over: {
  data?: ContactosOut;
  guardar?: jest.Mock;
  borrarTodos?: jest.Mock;
} = {}) {
  const guardar = over.guardar ?? jest.fn(async (): Promise<Desenlace> => ({ tipo: "ok" }));
  const borrarTodos = over.borrarTodos ?? jest.fn(async (): Promise<Desenlace> => ({ tipo: "ok" }));
  const v = await render(
    <EmergencyContactsScreen borrarTodos={borrarTodos} data={over.data ?? datos(1)} guardar={guardar} />,
  );
  return { v, guardar, borrarTodos };
}

async function pulsar(v: Awaited<ReturnType<typeof montar>>["v"], testID: string) {
  await act(async () => {
    fireEvent.press(v.getByTestId(testID));
  });
}

async function teclear(v: Awaited<ReturnType<typeof montar>>["v"], testID: string, texto: string) {
  await act(async () => {
    fireEvent.changeText(v.getByTestId(testID), texto);
  });
}

describe("CONTACTOS DE EMERGENCIA · lo que se lee", () => {
  it("renderiza los contactos guardados, la explicación y el conteo", async () => {
    const { v } = await montar({ data: datos(2) });
    expect(v.getByTestId("contacto-nombre-0").props.value).toBe("Contacto 1");
    expect(v.getByTestId("contacto-email-1").props.value).toBe("c2@example.com");
    expect(v.getByTestId("contactos-conteo")).toHaveTextContent("2 de 3");
    expect(
      v.getByText(
        "Si marca NECESITO AYUDA tras un sismo, les llega un correo con su nombre, el inmueble y la zona. La ubicación, solo si la compartió.",
      ),
    ).toBeTruthy();
  });

  it("enseña el aviso del servidor COMPLETO y el rótulo PROVISIONAL si lo es", async () => {
    const { v } = await montar();
    expect(v.getByTestId("aviso-texto")).toHaveTextContent(AVISO.texto);
    expect(v.getByTestId("aviso-provisional")).toHaveTextContent("PROVISIONAL");
    const def = await montar({ data: datos(1, { ...AVISO, provisional: false }) });
    expect(def.v.queryByTestId("aviso-provisional")).toBeNull();
  });

  it("sin contactos: el vacío dice qué significa, y AGREGAR sigue a mano", async () => {
    const { v } = await montar({ data: datos(0) });
    expect(v.getByTestId("state-empty")).toHaveTextContent(
      "Sin contactos. Si marca NECESITO AYUDA, nadie fuera del inmueble recibe aviso.",
    );
    expect(v.getByTestId("contactos-agregar")).toBeTruthy();
  });
});

describe("CONTACTOS DE EMERGENCIA · AGREGAR y QUITAR", () => {
  it("AGREGAR añade un contacto con +52 sugerido y se deshabilita al tercero", async () => {
    const { v } = await montar({ data: datos(1) });
    await pulsar(v, "contactos-agregar");
    expect(v.getByTestId("contacto-telefono-1").props.value).toBe("+52");
    expect(v.getByTestId("contactos-agregar")).not.toBeDisabled();
    await pulsar(v, "contactos-agregar");
    expect(v.getByTestId("contactos-conteo")).toHaveTextContent("3 de 3");
    expect(v.getByTestId("contactos-agregar")).toBeDisabled();
  });

  it("con 3 guardados, AGREGAR ya nace deshabilitado", async () => {
    const { v } = await montar({ data: datos(3) });
    expect(v.getByTestId("contactos-agregar")).toBeDisabled();
  });

  it("QUITAR saca ESE contacto de la lista", async () => {
    const { v } = await montar({ data: datos(2) });
    await pulsar(v, "contacto-quitar-0");
    expect(v.queryByTestId("contacto-nombre-1")).toBeNull();
    expect(v.getByTestId("contacto-nombre-0").props.value).toBe("Contacto 2");
  });
});

describe("CONTACTOS DE EMERGENCIA · GUARDAR", () => {
  it("GUARDAR exige la casilla de consentimiento", async () => {
    const { v, guardar } = await montar();
    expect(v.getByTestId("contactos-guardar")).toBeDisabled();
    await pulsar(v, "contactos-guardar");
    expect(guardar).not.toHaveBeenCalled();
    await pulsar(v, "contactos-acepto");
    expect(v.getByTestId("contactos-acepto").props.accessibilityState).toMatchObject({ checked: true });
    expect(v.getByTestId("contactos-guardar")).not.toBeDisabled();
  });

  it("manda la lista ENTERA con la versión del aviso; el +52 a solas no es teléfono", async () => {
    const { v, guardar } = await montar({ data: datos(1) });
    await pulsar(v, "contactos-agregar");
    await teclear(v, "contacto-nombre-1", "  Beto  ");
    await teclear(v, "contacto-email-1", "beto@example.mx");
    await pulsar(v, "contactos-acepto");
    await pulsar(v, "contactos-guardar");
    expect(guardar).toHaveBeenCalledWith({
      consentimiento_version: AVISO.version,
      contactos: [
        { display_name: "Contacto 1", email: "c1@example.com", phone: null },
        { display_name: "Beto", email: "beto@example.mx", phone: null },
      ],
    });
    expect(v.getByTestId("contactos-guardado")).toBeTruthy();
  });

  it("valida POR CAMPO antes de salir, y no manda nada si hay errores", async () => {
    const { v, guardar } = await montar({ data: datos(1) });
    await teclear(v, "contacto-email-0", "no-es-correo");
    await teclear(v, "contacto-telefono-0", "5512345678");
    await pulsar(v, "contactos-acepto");
    await pulsar(v, "contactos-guardar");
    expect(guardar).not.toHaveBeenCalled();
    expect(v.getByTestId("contacto-error-email-0")).toHaveTextContent(/Correo inválido/);
    expect(v.getByTestId("contacto-error-telefono-0")).toHaveTextContent(/\+52/);
    expect(v.queryByTestId("contacto-error-nombre-0")).toBeNull();
  });

  it("un 422 del servidor se pinta junto al campo que lo tiene", async () => {
    const guardar = jest.fn(
      async (): Promise<Desenlace> => ({
        tipo: "validacion",
        campos: { "0.email": "correo inválido" },
        general: null,
      }),
    );
    const { v } = await montar({ guardar });
    await pulsar(v, "contactos-acepto");
    await pulsar(v, "contactos-guardar");
    expect(v.getByTestId("contacto-error-email-0")).toHaveTextContent("correo inválido");
  });

  it("un 409 (aviso nuevo) desmarca la casilla y pide volver a aceptar el texto nuevo", async () => {
    const guardar = jest.fn(async (): Promise<Desenlace> => ({ tipo: "consentimiento" }));
    const { v } = await montar({ guardar });
    await pulsar(v, "contactos-acepto");
    await pulsar(v, "contactos-guardar");
    expect(v.getByTestId("contactos-aviso-cambio")).toHaveTextContent(/aviso cambió/i);
    // La recarga del aviso (versión nueva) la trae el hook; aquí llega por props.
    await act(async () => {
      v.rerender(
        <EmergencyContactsScreen
          borrarTodos={jest.fn()}
          data={datos(1, { ...AVISO, version: "2026-10-v2", texto: "Aviso NUEVO." })}
          guardar={guardar}
        />,
      );
    });
    expect(v.getByTestId("aviso-texto")).toHaveTextContent("Aviso NUEVO.");
    expect(v.getByTestId("contactos-acepto").props.accessibilityState).toMatchObject({ checked: false });
    expect(v.getByTestId("contactos-guardar")).toBeDisabled();
  });

  it("un fallo de red se dice, y la lista tecleada no se pierde", async () => {
    const guardar = jest.fn(async (): Promise<Desenlace> => ({ tipo: "fallo", mensaje: "No se pudo guardar." }));
    const { v } = await montar({ guardar });
    await teclear(v, "contacto-nombre-0", "Ana Editada");
    await pulsar(v, "contactos-acepto");
    await pulsar(v, "contactos-guardar");
    expect(v.getByTestId("contactos-fallo")).toHaveTextContent("No se pudo guardar.");
    expect(v.getByTestId("contacto-nombre-0").props.value).toBe("Ana Editada");
  });
});

describe("CONTACTOS DE EMERGENCIA · BORRAR TODOS", () => {
  it("pide confirmación antes de borrar, y CANCELAR no borra", async () => {
    const { v, borrarTodos } = await montar({ data: datos(2) });
    await pulsar(v, "contactos-borrar");
    expect(borrarTodos).not.toHaveBeenCalled();
    expect(v.getByTestId("contactos-borrar-confirmacion")).toHaveTextContent(/nadie fuera del inmueble/i);
    await pulsar(v, "contactos-borrar-cancelar");
    expect(v.queryByTestId("contactos-borrar-confirmacion")).toBeNull();
    expect(borrarTodos).not.toHaveBeenCalled();
  });

  it("CONFIRMAR borra", async () => {
    const { v, borrarTodos } = await montar({ data: datos(2) });
    await pulsar(v, "contactos-borrar");
    await pulsar(v, "contactos-borrar-confirmar");
    expect(borrarTodos).toHaveBeenCalledTimes(1);
  });

  it("sin nada guardado no hay BORRAR TODOS", async () => {
    const { v } = await montar({ data: datos(0) });
    expect(v.queryByTestId("contactos-borrar")).toBeNull();
  });
});
