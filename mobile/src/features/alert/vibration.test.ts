// [T-9.06] LA APP VIBRA EN CRISIS.
//
// Medido el 24-sep en el Pixel: con la alerta viva el teléfono SONÓ pero no
// vibró (buzz = 0). La vibración del canal de notificación sólo acompaña a la
// push; con la app en primer plano y la toma de pantalla puesta, nada movía el
// motor. Estos tests fijan el bucle y, sobre todo, su CANCELACIÓN: un teléfono
// que sigue vibrando cuando la alerta ya terminó es un dato congelado pintado
// como vivo, sólo que en la mano.
import { Vibration } from "react-native";

import { PATRON_ALERTA, startAlertVibration, stopAlertVibration } from "./vibration";

let vibrate: jest.SpyInstance;
let cancel: jest.SpyInstance;
let warn: jest.SpyInstance;

beforeEach(() => {
  vibrate = jest.spyOn(Vibration, "vibrate").mockImplementation(() => undefined);
  cancel = jest.spyOn(Vibration, "cancel").mockImplementation(() => undefined);
  warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
  stopAlertVibration(); // cada test arranca con el motor parado
  vibrate.mockClear();
  cancel.mockClear();
});

afterEach(() => {
  stopAlertVibration();
  vibrate.mockRestore();
  cancel.mockRestore();
  warn.mockRestore();
});

describe("el patrón", () => {
  it("es un patrón de Android [espera, vibra, espera…] con vibración de verdad", () => {
    expect(PATRON_ALERTA.length).toBeGreaterThanOrEqual(2);
    // Los índices IMPARES son los tramos que vibran: sumarlos a 0 sería el
    // buzz = 0 del Pixel, escrito en código.
    const vibrando = PATRON_ALERTA.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0);
    expect(vibrando).toBeGreaterThan(0);
    expect(PATRON_ALERTA.every((ms) => Number.isInteger(ms) && ms >= 0)).toBe(true);
  });
});

describe("startAlertVibration / stopAlertVibration", () => {
  it("arranca EN BUCLE (repeat = true) con el patrón de alerta", () => {
    startAlertVibration();
    expect(vibrate).toHaveBeenCalledTimes(1);
    expect(vibrate).toHaveBeenCalledWith([...PATRON_ALERTA], true);
  });

  it("arrancar dos veces no reinicia el ritmo", () => {
    startAlertVibration();
    startAlertVibration();
    expect(vibrate).toHaveBeenCalledTimes(1);
  });

  it("parar CANCELA el motor, y después se puede volver a arrancar", () => {
    startAlertVibration();
    stopAlertVibration();
    expect(cancel).toHaveBeenCalledTimes(1);
    startAlertVibration();
    expect(vibrate).toHaveBeenCalledTimes(2);
  });

  it("parar sin haber arrancado también cancela (no cuesta nada y no deja restos)", () => {
    stopAlertVibration();
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("best-effort: si el motor falla, la pantalla NO revienta y se registra", () => {
    vibrate.mockImplementation(() => {
      throw new Error("sin vibrador");
    });
    expect(() => startAlertVibration()).not.toThrow();
    expect(warn).toHaveBeenCalled();
    // Y no queda marcado como «vibrando»: el siguiente intento vuelve a probar.
    vibrate.mockImplementation(() => undefined);
    startAlertVibration();
    expect(vibrate).toHaveBeenCalledTimes(2);
  });

  it("best-effort: si cancelar falla, la transición de pantalla sigue", () => {
    startAlertVibration();
    cancel.mockImplementation(() => {
      throw new Error("puente caído");
    });
    expect(() => stopAlertVibration()).not.toThrow();
    // Tras el fallo se puede volver a arrancar: el estado se liberó igual.
    cancel.mockImplementation(() => undefined);
    startAlertVibration();
    expect(vibrate).toHaveBeenCalledTimes(2);
  });
});
