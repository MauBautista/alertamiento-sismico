// Categorías del formulario de daños (2.4) + severidad + PRIORIDAD. Lógica
// PURA: "personas atrapadas/heridas" es prioridad máxima y salta al frente de
// la cola (spec §2.4). Los keys/severidades espejan el schema del backend.
export const DAMAGE_CATEGORIES = [
  { key: "structural", label: "Daño estructural" },
  { key: "non_structural", label: "Daño no estructural" },
  { key: "water_leak", label: "Fuga de agua" },
  { key: "gas_leak", label: "Fuga de gas" },
  { key: "electrical", label: "Daño eléctrico" },
  { key: "people_trapped", label: "Personas atrapadas o heridas" },
] as const;

export type DamageKey = (typeof DAMAGE_CATEGORIES)[number]["key"];
export const SEVERITIES = ["low", "medium", "high", "critical"] as const;
export type Severity = (typeof SEVERITIES)[number];

export type SelectedCategory = { key: DamageKey; severity: Severity; note?: string };

/** Prioridad máxima: hay personas en riesgo (salta al frente de la cola). */
export function isUrgent(categories: { key: string }[]): boolean {
  return categories.some((c) => c.key === "people_trapped");
}

/** Prioridad de la cola: 0 = normal, 1 = frente (urgente). Se usa para ordenar
 *  el envío — un reporte con personas en riesgo se despacha ANTES. */
export function queuePriority(categories: { key: string }[]): number {
  return isUrgent(categories) ? 1 : 0;
}

/** Ordena items por prioridad DESC y luego por antigüedad (FIFO dentro del
 *  mismo nivel) — los urgentes salen primero sin reordenar el resto. */
export function orderByPriority<T extends { priority: number; created_at: number }>(
  items: T[],
): T[] {
  return [...items].sort((a, b) => b.priority - a.priority || a.created_at - b.created_at);
}
