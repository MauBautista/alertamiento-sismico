/**
 * [T-6.21] LA PANTALLA ACREDITADA EN EL PIXEL NO CAMBIA DE COLOR.
 *
 * Mover 43 literales al paquete es una refactorización, y una refactorización
 * de las dos pantallas de VIDA tiene que demostrar que no movió un píxel. Dos
 * capturas «que se ven iguales» no lo demuestran: dependen de la luz, del
 * estado y del ojo. Los valores sí.
 *
 * Aquí están anclados BYTE A BYTE contra lo que había escrito a mano antes de
 * la ficha. Es el mismo trato que `designTokens.test.ts` de la consola hace con
 * las anclas de identidad: si alguien cambia uno, que sea un acto DELIBERADO y
 * no el efecto lateral de otra cosa.
 *
 * Los literales de este archivo son legítimos y por eso el censo de
 * `src/designTokens.test.ts` excluye los tests: aquí el literal ES el sujeto.
 */
import { emergency } from "./theme";

describe("[T-6.21] la piel roja de la crisis, byte a byte", () => {
  it.each([
    ["bg", emergency.red.bg, "#160808"],
    ["ink", emergency.red.ink, "#FFFFFF"],
    ["ink1", emergency.red.ink1, "rgba(255, 240, 240, 0.85)"],
    ["ink2", emergency.red.ink2, "rgba(255, 240, 240, 0.75)"],
    ["ink3", emergency.red.ink3, "rgba(255, 240, 240, 0.7)"],
    ["eyebrow", emergency.red.eyebrow, "rgba(255, 220, 220, 0.65)"],
    ["meta", emergency.red.meta, "rgba(255, 200, 200, 0.7)"],
  ])("red.%s", (_n, real, esperado) => {
    expect(real.replace(/\s+/g, "")).toBe(esperado.replace(/\s+/g, ""));
  });
});

describe("[T-6.21] la piel ámbar (repliegue y alarma del inmueble), byte a byte", () => {
  it.each([
    ["bg", emergency.amber.bg, "#1C1404"],
    ["strip", emergency.amber.strip, "#E8A700"],
    ["onStrip", emergency.amber.onStrip, "#2A1A00"],
    ["accent", emergency.amber.accent, "#FFCE3A"],
    ["accent50", emergency.amber.accent50, "rgba(255, 206, 58, 0.5)"],
    ["ink1", emergency.amber.ink1, "rgba(255, 246, 230, 0.85)"],
    ["ink2", emergency.amber.ink2, "rgba(255, 246, 230, 0.78)"],
    ["ink3", emergency.amber.ink3, "rgba(255, 246, 230, 0.7)"],
    ["eyebrow", emergency.amber.eyebrow, "rgba(255, 240, 210, 0.65)"],
    ["meta", emergency.amber.meta, "rgba(255, 235, 190, 0.7)"],
    ["error", emergency.amber.error, "#FF9B8A"],
  ])("amber.%s", (_n, real, esperado) => {
    expect(real.replace(/\s+/g, "")).toBe(esperado.replace(/\s+/g, ""));
  });
});

describe("[T-6.21] superficies sobre piel oscura y velos", () => {
  it.each([
    ["onDark.surface", emergency.onDark.surface, "rgba(255, 255, 255, 0.1)"],
    ["onDark.border", emergency.onDark.border, "rgba(255, 255, 255, 0.16)"],
    ["veil.soft", emergency.veil.soft, "rgba(0, 0, 0, 0.4)"],
    ["veil.base", emergency.veil.base, "rgba(0, 0, 0, 0.55)"],
    ["veil.strong", emergency.veil.strong, "rgba(0, 0, 0, 0.6)"],
    ["veil.ink", emergency.veil.ink, "#FFFFFF"],
  ])("%s", (_n, real, esperado) => {
    expect(real.replace(/\s+/g, "")).toBe(esperado.replace(/\s+/g, ""));
  });

  it("los tres velos son DISTINTOS: tres usos medidos, no un redondeo", () => {
    // 0.4 sobre la vista de cámara, 0.55 bajo la marca de agua y 0.6 en el
    // panel. Unificarlos habría cambiado píxeles de una pantalla acreditada.
    const pesos = new Set([emergency.veil.soft, emergency.veil.base, emergency.veil.strong]);
    expect(pesos.size).toBe(3);
  });
});
