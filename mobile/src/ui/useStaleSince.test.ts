// [T-5.21] La edad sale del reloj, y sus tres respuestas.

import { FACTOR_DE_VEJEZ, staleSinceOf } from "./useStaleSince";

const AHORA = 1_800_000_000_000;
const POLL = 5_000;

describe("staleSinceOf", () => {
  it("un dato recién traído es fresco", () => {
    expect(staleSinceOf(AHORA - 1_000, AHORA, POLL)).toBeNull();
  });

  it("un dato de hace diez minutos es VIEJO aunque nada haya fallado", () => {
    // El defecto exacto que cierra la ficha: aquí no hay error, ni
    // `failureCount`, ni red caída. Solo tiempo.
    expect(staleSinceOf(AHORA - 600_000, AHORA, POLL)).toBe(AHORA - 600_000);
  });

  it("el umbral son TRES pollos perdidos, no un número fijo", () => {
    const justo = AHORA - POLL * FACTOR_DE_VEJEZ;
    expect(staleSinceOf(justo, AHORA, POLL)).toBeNull();
    expect(staleSinceOf(justo - 1, AHORA, POLL)).toBe(justo - 1);
  });

  it("una pantalla que consulta despacio envejece despacio", () => {
    // Con un umbral fijo, la de 30 s habría mentido en una de las dos
    // direcciones. El mismo dato, dos ritmos, dos veredictos correctos.
    const hace30s = AHORA - 30_000;
    expect(staleSinceOf(hace30s, AHORA, 5_000)).toBe(hace30s);
    expect(staleSinceOf(hace30s, AHORA, 30_000)).toBeNull();
  });

  it("sin consulta previa NO es fresquísimo: es que no hay dato", () => {
    // `loading`/`error` hablan de eso; la frescura no puede opinar sobre un
    // dato que no existe.
    expect(staleSinceOf(0, AHORA, POLL)).toBeNull();
  });
});
