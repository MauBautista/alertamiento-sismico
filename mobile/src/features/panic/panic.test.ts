// 1.9 — la copy del pánico SIEMPRE deja claro que NO es la alerta sísmica; el
// quórum lo decide el servidor (contado/activado/descartado).
import type { PanicVoteOut } from "@takab/sdk";

import { PANIC_DISCLAIMER, panicStatusFromVote, windowRemaining } from "./panicView";

function vote(over: Partial<PanicVoteOut>): PanicVoteOut {
  return { status: "counted", distinct_voters: 1, remaining: 1, window_s: 30, ...over };
}

describe("PANIC_DISCLAIMER", () => {
  it("declara que NO es la alerta sísmica", () => {
    expect(PANIC_DISCLAIMER).toMatch(/NO es la alerta sísmica/);
    expect(PANIC_DISCLAIMER).toMatch(/segunda persona/);
  });
});

describe("panicStatusFromVote", () => {
  it("1 voto ⇒ '1 DE 2' con la ventana", () => {
    const s = panicStatusFromVote(vote({ distinct_voters: 1, remaining: 1 }));
    expect(s.phase).toBe("counted");
    expect(s.title).toBe("1 DE 2 CONFIRMACIONES");
    expect(s.detail).toMatch(/ventana de 30 s/);
  });

  it("quórum ⇒ ALARMA ACTIVADA (crit)", () => {
    const s = panicStatusFromVote(vote({ status: "activated", distinct_voters: 2, remaining: 0 }));
    expect(s.phase).toBe("activated");
    expect(s.title).toBe("ALARMA ACTIVADA");
    expect(s.tone).toBe("crit");
  });

  it("geofence ⇒ descartado, explica que está fuera del inmueble", () => {
    const s = panicStatusFromVote(vote({ status: "discarded", distinct_voters: 0, remaining: 2 }));
    expect(s.phase).toBe("discarded");
    expect(s.detail).toMatch(/fuera del inmueble/);
  });
});

describe("windowRemaining", () => {
  it("cuenta atrás, nunca negativo", () => {
    expect(windowRemaining(1000, 30, 1000)).toBe(30);
    expect(windowRemaining(1000, 30, 11_000)).toBe(20);
    expect(windowRemaining(1000, 30, 40_000)).toBe(0);
    expect(windowRemaining(1000, 30, 999_999)).toBe(0);
  });
});
