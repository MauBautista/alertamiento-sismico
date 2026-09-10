/**
 * [T-6.25] EL PILL DEL PANEL AFIRMABA «LIVE» SOBRE UN CANAL MUDO.
 *
 * Salía del estado del socket y nada más: `ready` ⇒ LIVE en verde, para
 * siempre. La misma pantalla ya imprimía «Frame recibido hace X» dos tarjetas
 * más abajo — dos afirmaciones sobre el mismo hecho, y la grande era la
 * optimista.
 */
import { estadoPill, FRAME_FRESCO_MS } from "./livePill";

const AHORA = 1_800_000_000_000;

describe("[T-6.25] el pill del panel dice si el dato está LLEGANDO", () => {
  it("con frames frescos late y dice LIVE", () => {
    const e = estadoPill("ready", AHORA - 1_000, AHORA);
    expect(e).toEqual({ label: "LIVE", tone: "ok", late: true });
  });

  it("con el canal abierto y el último frame VIEJO deja de latir y lo dice", () => {
    const e = estadoPill("ready", AHORA - FRAME_FRESCO_MS - 1, AHORA);
    expect(e.late).toBe(false);
    expect(e.label).toMatch(/SIN FRAMES RECIENTES/);
    // Y no miente en la otra dirección: el canal SÍ sigue abierto.
    expect(e.label).toMatch(/LIVE/);
    expect(e.tone).toBe("warn");
  });

  it("«jamás llegó un frame» no se pinta como «llegó y envejeció»", () => {
    const e = estadoPill("ready", null, AHORA);
    expect(e.label).toBe("CANAL ABIERTO · SIN FRAMES");
    expect(e.late).toBe(false);
  });

  it("el socket manda cuando está cerrado o reconectando: la frescura solo QUITA", () => {
    expect(estadoPill("closed", AHORA, AHORA).late).toBe(false);
    expect(estadoPill("closed", AHORA, AHORA).label).toBe("SIN CANAL LIVE");
    expect(estadoPill("connecting", AHORA, AHORA).label).toBe("RECONECTANDO…");
  });

  it("justo en el umbral todavía late: el corte es estrictamente mayor", () => {
    expect(estadoPill("ready", AHORA - FRAME_FRESCO_MS, AHORA).late).toBe(true);
  });

  it("el umbral son cinco frames de 1 s: ni parpadea ni miente", () => {
    expect(FRAME_FRESCO_MS).toBeGreaterThanOrEqual(3_000);
    expect(FRAME_FRESCO_MS).toBeLessThanOrEqual(15_000);
  });
});
