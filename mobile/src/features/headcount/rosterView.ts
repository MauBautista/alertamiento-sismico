// Vista PURA del headcount (2.6): clasifica cada entrada del roster y filtra
// "no reportados". Los contadores vienen del servidor (RosterOut); aquí solo se
// deriva el estado por persona y el orden (no reportados primero).
import type { RosterEntry, RosterOut } from "@takab/sdk";

export type PersonState = "safe" | "need_help" | "unreported";

export function personState(entry: RosterEntry): PersonState {
  if (entry.checkin == null) {
    return "unreported";
  }
  return entry.checkin.status === "need_help" ? "need_help" : "safe";
}

/** ¿El check-in fue marcado "verificado en persona" por un táctico? */
export function isDelegated(entry: RosterEntry): boolean {
  return entry.checkin?.via === "delegated";
}

export type RosterRow = {
  userId: string;
  name: string;
  zone: string | null;
  phone: string | null;
  state: PersonState;
  delegated: boolean;
};

export function rosterRow(entry: RosterEntry): RosterRow {
  return {
    userId: entry.user_id,
    name: entry.display_name ?? "Sin nombre",
    zone: entry.zone_name ?? null,
    phone: entry.phone ?? null,
    state: personState(entry),
    delegated: isDelegated(entry),
  };
}

const STATE_RANK: Record<PersonState, number> = { need_help: 0, unreported: 1, safe: 2 };

/** Filtra (opcionalmente solo no reportados) y ordena: ayuda → no reportado →
 *  a salvo; dentro del nivel, por nombre. */
export function rosterRows(roster: RosterOut, onlyUnreported: boolean): RosterRow[] {
  const rows = roster.entries.map(rosterRow);
  const filtered = onlyUnreported ? rows.filter((r) => r.state === "unreported") : rows;
  return filtered.sort(
    (a, b) => STATE_RANK[a.state] - STATE_RANK[b.state] || a.name.localeCompare(b.name),
  );
}

/** ¿Todos contabilizados? (precondición para cerrar el headcount). */
export function allAccounted(roster: RosterOut): boolean {
  return roster.total > 0 && roster.unreported === 0;
}
