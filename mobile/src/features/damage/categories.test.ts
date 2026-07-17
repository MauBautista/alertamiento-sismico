// 2.4 — personas atrapadas = prioridad máxima (frente de la cola).
import { isUrgent, orderByPriority, queuePriority } from "./categories";

describe("prioridad de daños", () => {
  it("people_trapped ⇒ urgente, prioridad 1 (frente de cola)", () => {
    const urgent = [{ key: "people_trapped" }, { key: "structural" }];
    expect(isUrgent(urgent)).toBe(true);
    expect(queuePriority(urgent)).toBe(1);
  });

  it("sin personas en riesgo ⇒ prioridad normal", () => {
    const normal = [{ key: "structural" }, { key: "gas_leak" }];
    expect(isUrgent(normal)).toBe(false);
    expect(queuePriority(normal)).toBe(0);
  });

  it("orderByPriority: urgentes primero, FIFO dentro del nivel", () => {
    const items = [
      { id: "a", priority: 0, created_at: 1 },
      { id: "b", priority: 1, created_at: 3 },
      { id: "c", priority: 0, created_at: 2 },
      { id: "d", priority: 1, created_at: 2 },
    ];
    expect(orderByPriority(items).map((i) => i.id)).toEqual(["d", "b", "a", "c"]);
  });
});
