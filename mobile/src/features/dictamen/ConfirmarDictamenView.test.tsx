// [T-9.33 · D-43] La vista de CONFIRMAR DICTAMEN: explica la banda y su porqué,
// la lista de revisión, y DOS botones grandes. Qué botón existe lo dicen la
// cabeza (un ROJO no se confirma) y el servidor (`confirm_dictamen`,
// `request_dictamen`).
import { fireEvent, render } from "@testing-library/react-native";

import { ConfirmarDictamenView, type ConfirmarDictamenViewProps } from "./ConfirmarDictamenView";

const IDLE: ConfirmarDictamenViewProps["confirmacion"] = { estado: "idle", mensaje: null };

const AMARILLO: ConfirmarDictamenViewProps["vista"] = {
  tipo: "confirmable",
  dictamenId: "d-1",
  banda: "amarillo",
  titulo: "DICTAMEN AMARILLO · HABITAR CON MONITOREO",
  porque: ["La aceleración máxima medida (0.055 g) está entre 0.04 g y 0.1 g."],
  revision: ["Recorra el inmueble."],
};

function montar(over: Partial<ConfirmarDictamenViewProps> = {}) {
  const props: ConfirmarDictamenViewProps & { onConfirmar: jest.Mock } = {
    vista: AMARILLO,
    confirmacion: IDLE,
    escalado: IDLE,
    onConfirmar: jest.fn(),
    onEscalar: jest.fn(),
    ...over,
  } as ConfirmarDictamenViewProps & { onConfirmar: jest.Mock };
  return { props, v: render(<ConfirmarDictamenView {...props} />) };
}

it("AMARILLO: banda, porqué, revisión y los dos botones", async () => {
  const { props, v } = montar();
  const r = await v;
  expect(r.getByTestId("confirmar-banda")).toHaveTextContent(/AMARILLO/);
  expect(r.getByTestId("confirmar-porque")).toHaveTextContent(/0.055 g/);
  expect(r.getByTestId("confirmar-revision")).toHaveTextContent(/Recorra el inmueble/);
  await fireEvent.press(r.getByTestId("confirmar-dictamen"));
  expect(props.onConfirmar).toHaveBeenCalled();
  await fireEvent.press(r.getByTestId("escalar-inspector"));
  expect(props.onEscalar).toHaveBeenCalled();
});

it("ROJO: no hay botón de confirmar; sí el de escalar", async () => {
  const r = await montar({
    vista: { tipo: "solo_inspector", banda: "rojo", titulo: "DICTAMEN ROJO", porque: ["x"] },
  }).v;
  expect(r.queryByTestId("confirmar-dictamen")).toBeNull();
  expect(r.getByTestId("escalar-inspector")).toBeTruthy();
  expect(r.getByText(/lo firma el inspector/)).toBeTruthy();
});

it("ya firmado: dice por quién y no ofrece nada", async () => {
  const r = await montar({
    vista: {
      tipo: "ya_firmado",
      banda: "amarillo",
      titulo: "DICTAMEN AMARILLO",
      firmante: "CONFIRMADO POR PERSONAL AUTORIZADO",
    },
  }).v;
  expect(r.getByTestId("confirmar-firmado")).toHaveTextContent(/CONFIRMADO POR PERSONAL/);
  expect(r.queryByTestId("confirmar-dictamen")).toBeNull();
  expect(r.queryByTestId("escalar-inspector")).toBeNull();
});

it("sin permiso de escalar, no se pinta el botón y se dice a quién avisar", async () => {
  const r = await montar({ onEscalar: null }).v;
  expect(r.queryByTestId("escalar-inspector")).toBeNull();
  expect(r.getByTestId("escalar-sin-permiso")).toHaveTextContent(/administración/);
});

it("enviando / hecho / error se ven en cada botón", async () => {
  const r = await montar({
    confirmacion: { estado: "error", mensaje: "El dictamen cambió." },
    escalado: { estado: "hecho", mensaje: "Solicitud enviada al inspector." },
  }).v;
  expect(r.getByTestId("confirmar-mensaje")).toHaveTextContent(/cambió/);
  expect(r.getByTestId("escalar-mensaje")).toHaveTextContent(/Solicitud enviada/);
  expect(r.getByTestId("escalar-inspector")).toHaveTextContent(/ESCALADO/);
});

it("confirmado ⇒ el botón queda en estado terminal", async () => {
  const { props, v } = montar({ confirmacion: { estado: "hecho", mensaje: "Dictamen confirmado." } });
  const r = await v;
  expect(r.getByTestId("confirmar-dictamen")).toHaveTextContent(/CONFIRMADO/);
  await fireEvent.press(r.getByTestId("confirmar-dictamen"));
  expect(props.onConfirmar).not.toHaveBeenCalled();
});

// [F3·r3] 409 «requiere inspector»: reintentar no sirve; el botón queda
// deshabilitado y la salida es ESCALAR.
it("409 «requiere inspector» ⇒ confirmar deshabilitado y escalar a la vista", async () => {
  const { props, v } = montar({
    confirmacion: {
      estado: "error",
      mensaje: "Hay un daño reportado que exige inspección.",
      requiereInspector: true,
      dictamenId: "d-1",
    },
  });
  const r = await v;
  expect(r.getByTestId("confirmar-dictamen")).not.toHaveTextContent(/REINTENTAR/);
  await fireEvent.press(r.getByTestId("confirmar-dictamen"));
  expect(props.onConfirmar).not.toHaveBeenCalled();
  expect(r.getByTestId("escalar-inspector")).toBeTruthy();
});

it("409 del VERDE ⇒ confirmar deshabilitado y se explica que lo firma el sistema", async () => {
  const { props, v } = montar({
    confirmacion: {
      estado: "error",
      mensaje: "Un dictamen verde lo emite el sistema.",
      loFirmaElSistema: true,
      dictamenId: "d-1",
    },
  });
  const r = await v;
  await fireEvent.press(r.getByTestId("confirmar-dictamen"));
  expect(props.onConfirmar).not.toHaveBeenCalled();
  expect(r.getByTestId("confirmar-mensaje")).toHaveTextContent(/sistema/);
});

it("VERDE sin firmar ⇒ no hay botón de confirmar; se explica que lo firma el sistema", async () => {
  const r = await montar({
    vista: {
      tipo: "lo_firma_el_sistema",
      banda: "verde",
      titulo: "DICTAMEN VERDE",
      porque: ["x"],
    },
  }).v;
  expect(r.queryByTestId("confirmar-dictamen")).toBeNull();
  expect(r.getByTestId("confirmar-lo-firma-el-sistema")).toHaveTextContent(/sistema/);
  expect(r.getByTestId("escalar-inspector")).toBeTruthy();
});

it("un «hecho» de OTRO dictamen no deja el botón terminal en la cabeza nueva", async () => {
  const { props, v } = montar({
    confirmacion: { estado: "hecho", mensaje: "Dictamen confirmado.", dictamenId: "d-viejo" },
  });
  const r = await v;
  expect(r.getByTestId("confirmar-dictamen")).toHaveTextContent(/CONFIRMAR DICTAMEN/);
  await fireEvent.press(r.getByTestId("confirmar-dictamen"));
  expect(props.onConfirmar).toHaveBeenCalled();
});

// [D-49 · R1] Con el edificio en movimiento NO hay botón de confirmar: se explica.
it("espere_calma: sin botón de confirmar, explica la calma y deja escalar", async () => {
  const r = await montar({
    vista: {
      tipo: "espere_calma",
      banda: "amarillo",
      titulo: "DICTAMEN AMARILLO",
      porque: ["x"],
      explicacion: "El edificio sigue en movimiento: espere a que el edificio vuelva a calma para confirmar.",
    },
  }).v;
  expect(r.queryByTestId("confirmar-dictamen")).toBeNull();
  expect(r.getByTestId("confirmar-espere-calma")).toHaveTextContent(
    /espere a que el edificio vuelva a calma/,
  );
  expect(r.getByTestId("escalar-inspector")).toBeTruthy();
});

// [D-49] Las causas TERMINALES de un 409/404 dejan el botón quieto con su texto;
// la de la calma se puede reintentar.
it.each([
  [{ loFirmaElInspector: true }, /ESCALE AL INSPECTOR/],
  [{ yaFirmado: true }, /YA ESTABA FIRMADO/],
  [{ fueraDeAlcance: true }, /FUERA DE SU ALCANCE/],
])("respuesta terminal %p ⇒ confirmar deshabilitado", async (flag, texto) => {
  const r = await montar({
    confirmacion: { estado: "error", mensaje: "m", dictamenId: "d-1", ...flag },
  }).v;
  const boton = r.getByTestId("confirmar-dictamen");
  expect(boton).toBeDisabled();
  expect(boton).toHaveTextContent(texto);
});

it("409 de la calma ⇒ se puede reintentar y el botón lo dice", async () => {
  const { props, v } = montar({
    confirmacion: { estado: "error", mensaje: "m", dictamenId: "d-1", esperaCalma: true },
  });
  const r = await v;
  const boton = r.getByTestId("confirmar-dictamen");
  expect(boton).not.toBeDisabled();
  expect(boton).toHaveTextContent(/EN CALMA/);
  await fireEvent.press(boton);
  expect(props.onConfirmar).toHaveBeenCalled();
});
