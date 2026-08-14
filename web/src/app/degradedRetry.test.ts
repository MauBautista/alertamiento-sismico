/**
 * [T-2.134] El backoff del modo degradado.
 *
 * Un reintento apretado contra una base caída añade carga JUSTO cuando menos
 * puede soportarla: Postgres arrancando, recuperando WAL o reeligiendo primario
 * es cuando peor le viene un tropel de `GET /me`. Y no es un navegador: son
 * todas las consolas de todos los tenants, que perdieron `/me` en el MISMO
 * instante y por tanto reintentarían al mismo compás.
 *
 * Por eso el retardo es exponencial CON JITTER. Las dos mitades importan y se
 * fijan aquí por separado.
 */
import { describe, expect, it } from "vitest";

import { BASE_MS, retryDelayMs, TOPE_MS } from "./degradedRetry";

/** Peor caso del jitter: el retardo NOMINAL de ese intento. */
const nominal = (intento: number) => retryDelayMs(intento, () => 1);
/** Mejor caso: la mitad. Nunca menos, y ahí está el suelo de la carga. */
const minimo = (intento: number) => retryDelayMs(intento, () => 0);

describe("[T-2.134] el reintento del degradado no martillea la base caída", () => {
  it("el primer reintento NO es inmediato: hay un suelo medible", () => {
    // Un reintento inmediato convierte al cliente en un generador de carga
    // durante el arranque de la base, que es el peor momento posible.
    expect(minimo(0)).toBeGreaterThanOrEqual(BASE_MS / 2);
  });

  it("crece exponencialmente mientras la base siga caída", () => {
    expect(nominal(0)).toBe(BASE_MS);
    expect(nominal(1)).toBe(BASE_MS * 2);
    expect(nominal(2)).toBe(BASE_MS * 4);
    expect(nominal(3)).toBe(BASE_MS * 8);
  });

  it("y tiene TECHO: una caída larga no deja la consola reintentando cada hora", () => {
    // El techo es la otra mitad de la decisión: sin él, una caída de 40 min
    // dejaría el siguiente reintento a 20 min de distancia, y el operador
    // estaría mirando una pantalla degradada con la base ya de vuelta.
    expect(nominal(20)).toBe(TOPE_MS);
    expect(nominal(500)).toBe(TOPE_MS);
    expect(TOPE_MS).toBeLessThanOrEqual(120_000);
  });

  it("JITTER: dos consolas que cayeron a la vez NO reintentan a la vez", () => {
    // Sin esto, cada tenant tendría N consolas golpeando en el mismo
    // milisegundo: el backoff exponencial sincroniza el tropel en vez de
    // dispersarlo.
    const muestras = new Set([0, 0.25, 0.5, 0.75, 1].map((r) => retryDelayMs(3, () => r)));
    expect(muestras.size).toBe(5);
  });

  it("el jitter reparte entre la MITAD y el nominal, nunca por encima", () => {
    // Por encima del nominal el techo dejaría de ser el techo; por debajo de la
    // mitad se pierde el suelo de carga que da el punto uno.
    for (const intento of [0, 1, 2, 5, 30]) {
      for (const r of [0, 0.13, 0.5, 0.87, 1]) {
        const espera = retryDelayMs(intento, () => r);
        expect(espera).toBeGreaterThanOrEqual(nominal(intento) / 2);
        expect(espera).toBeLessThanOrEqual(nominal(intento));
      }
    }
  });

  it("un intento negativo o absurdo no produce un retardo negativo", () => {
    expect(retryDelayMs(-3, () => 0)).toBeGreaterThanOrEqual(BASE_MS / 2);
    expect(Number.isFinite(retryDelayMs(1e6, () => 0.5))).toBe(true);
  });
});
