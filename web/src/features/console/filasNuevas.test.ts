/**
 * [T-6.10 · W13] UNA FILA QUE LLEGA SOLA NO SE ANUNCIA.
 *
 * La cola de incidentes se refresca por WebSocket. Un incidente nuevo aparecía
 * insertándose en la tabla sin nada que lo distinguiera: si el operador estaba
 * mirando el mapa, la fila ya llevaba ahí un rato cuando volvía la vista, y la
 * única forma de saber cuál era la nueva era leer la columna de edad entera.
 *
 * Lo que se anuncia es un RÓTULO —«NUEVO», que sobrevive sin movimiento— y no
 * un destello: quien tenga la reducción de movimiento puesta tiene que
 * enterarse igual. El movimiento solo confirma.
 */
import { describe, expect, it } from "vitest";

import { actualizarCenso, NUEVO_MS } from "./filasNuevas";

describe("[T-6.10] censo de filas: quién llegó DESPUÉS de que se estuviera mirando", () => {
  it("el primer censo no marca NADA: abrir la consola no es que lleguen 12 incidentes", () => {
    // El defecto más fácil de escribir: con un `Set` vacío como estado inicial,
    // la primera pintura enciende la cola entera y el rótulo deja de significar
    // «esto acaba de pasar».
    const { censo, nuevas } = actualizarCenso(null, ["a", "b", "c"], 1_000);
    expect([...nuevas]).toEqual([]);
    expect(censo.size).toBe(3);
  });

  it("lo que aparece después SÍ se marca, y solo eso", () => {
    const primero = actualizarCenso(null, ["a", "b"], 1_000);
    const segundo = actualizarCenso(primero.censo, ["c", "a", "b"], 2_000);
    expect([...segundo.nuevas]).toEqual(["c"]);
  });

  it("el rótulo caduca por RELOJ, no por haber vuelto a pintar", () => {
    // Si caducara al siguiente render, un refresco a los 200 ms lo borraría.
    const t0 = actualizarCenso(null, ["a"], 0);
    const llega = actualizarCenso(t0.censo, ["a", "b"], 1_000);
    expect([...llega.nuevas]).toEqual(["b"]);
    const casi = actualizarCenso(llega.censo, ["a", "b"], 1_000 + NUEVO_MS - 1);
    expect([...casi.nuevas]).toEqual(["b"]);
    const vencido = actualizarCenso(casi.censo, ["a", "b"], 1_000 + NUEVO_MS + 1);
    expect([...vencido.nuevas]).toEqual([]);
  });

  it("una fila que se va y VUELVE se vuelve a anunciar", () => {
    // Un incidente reabierto es una noticia igual que uno nuevo, y quien mira
    // no tiene por qué recordar que ya estuvo.
    const t0 = actualizarCenso(null, ["a", "b"], 0);
    const sinB = actualizarCenso(t0.censo, ["a"], 1_000);
    expect(sinB.censo.has("b")).toBe(false);
    const vuelveB = actualizarCenso(sinB.censo, ["a", "b"], 2_000);
    expect([...vuelveB.nuevas]).toEqual(["b"]);
  });

  it("el censo no crece con lo que ya no está en la cola", () => {
    // Sin la poda, una consola de guardia de 12 h acumula todos los incidentes
    // cerrados del turno en un mapa que nadie vacía.
    const t0 = actualizarCenso(null, ["a", "b", "c"], 0);
    const { censo } = actualizarCenso(t0.censo, ["b"], 1_000);
    expect([...censo.keys()]).toEqual(["b"]);
  });

  it("volver a censar con el MISMO reloj no reinicia la cuenta", () => {
    // React puede pintar dos veces con el mismo instante (modo estricto). Si el
    // sello se reescribiera, el rótulo se quedaría pegado para siempre.
    const t0 = actualizarCenso(null, ["a"], 0);
    const llega = actualizarCenso(t0.censo, ["a", "b"], 1_000);
    const otraVez = actualizarCenso(llega.censo, ["a", "b"], 1_000);
    expect(otraVez.censo.get("b")).toBe(1_000);
    const vencido = actualizarCenso(otraVez.censo, ["a", "b"], 1_000 + NUEVO_MS + 1);
    expect([...vencido.nuevas]).toEqual([]);
  });

  it("la ventana dura lo bastante para volver la vista, y no tanto como para mentir", () => {
    expect(NUEVO_MS).toBeGreaterThanOrEqual(5_000);
    expect(NUEVO_MS).toBeLessThanOrEqual(30_000);
  });
});
