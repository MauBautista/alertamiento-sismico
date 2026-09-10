/**
 * [T-6.25 · U-22] EL HOLD DE PÁNICO ERA EL ÚNICO ESTADO QUE VIVÍA SOLO EN EL
 * MOVIMIENTO.
 *
 * Mantener pulsado 1.5 s evita el disparo accidental, y hasta esta ficha lo
 * único que decía cuánto faltaba era una barra llenándose. Para quien tiene el
 * movimiento reducido puesto —o simplemente no mira la barra porque está
 * mirando el edificio— no había ninguna señal.
 *
 * Y había algo peor de fondo: **la confirmación colgaba del callback de la
 * animación**. Una animación no es un reloj —el sistema puede recortarla, y con
 * `reduceMotion` puesto lo correcto es NO animar—, así que atar a ella el voto
 * de pánico es atar una decisión a la decoración.
 */
import { act, fireEvent, render } from "@testing-library/react-native";

import { HOLD_MS, PanicButton } from "./PanicButton";

let mockReduce = false;
jest.mock("@/ui/useReduceMotion", () => ({ useReduceMotion: () => mockReduce }));

beforeEach(() => {
  mockReduce = false;
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

async function montar(onConfirm = jest.fn()) {
  const v = await render(
    <PanicButton disabled={false} label="MANTENGA PARA CONFIRMAR" onConfirm={onConfirm} />,
  );
  return { v, onConfirm };
}

/** RNTL 14: el `fireEvent` que provoca un `setState` necesita su `act` async, o
 *  el árbol que se mira después es el de ANTES del evento. */
async function tocar(el: Parameters<typeof fireEvent>[0], evento: string): Promise<void> {
  await act(async () => {
    fireEvent(el, evento);
  });
}

async function avanzar(ms: number): Promise<void> {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
}

describe("[T-6.25] el hold cuenta EN TEXTO, no solo en la barra", () => {
  it("al empezar dice que hay que mantener, y cuánto", async () => {
    const { v } = await montar();
    await tocar(v.getByTestId("panic-hold"), "pressIn");
    await avanzar(50);
    expect(v.getByTestId("panic-cuenta")).toHaveTextContent(/MANTENGA/);
  });

  it("la cuenta BAJA mientras se mantiene", async () => {
    const { v } = await montar();
    await tocar(v.getByTestId("panic-hold"), "pressIn");
    await avanzar(100);
    const alPrincipio = v.getByTestId("panic-cuenta").props.children;
    await avanzar(900);
    expect(v.getByTestId("panic-cuenta").props.children).not.toEqual(alPrincipio);
  });

  it("al completar el hold DICE confirmado y avisa una sola vez", async () => {
    const { v, onConfirm } = await montar();
    await tocar(v.getByTestId("panic-hold"), "pressIn");
    await avanzar(HOLD_MS + 50);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(v.getByTestId("panic-cuenta")).toHaveTextContent(/CONFIRMADO/);
    await avanzar(2_000);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("soltar antes de tiempo NO confirma y la cuenta se retira", async () => {
    const { v, onConfirm } = await montar();
    await tocar(v.getByTestId("panic-hold"), "pressIn");
    await avanzar(500);
    await tocar(v.getByTestId("panic-hold"), "pressOut");
    await avanzar(HOLD_MS);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(v.queryByTestId("panic-cuenta")).toBeNull();
  });

  it("CON MOVIMIENTO REDUCIDO el hold sigue tardando lo mismo y sigue contando", async () => {
    // Esto es el criterio: la barra puede no moverse, pero la protección
    // anti-accidente no se acorta y la persona sabe cuánto falta.
    mockReduce = true;
    const { v, onConfirm } = await montar();
    await tocar(v.getByTestId("panic-hold"), "pressIn");
    await avanzar(HOLD_MS - 200);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(v.getByTestId("panic-cuenta")).toHaveTextContent(/MANTENGA/);
    await avanzar(300);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("deshabilitado no arranca nada", async () => {
    const onConfirm = jest.fn();
    const v = await render(
      <PanicButton disabled label="MANTENGA PARA CONFIRMAR" onConfirm={onConfirm} />,
    );
    await tocar(v.getByTestId("panic-hold"), "pressIn");
    await avanzar(HOLD_MS + 500);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
