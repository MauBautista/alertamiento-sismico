// Línea de tiempo del bloqueo de reingreso (1.5) — derivación PURA de los
// datos del servidor (mobile-state: incidente + dictamen + check-in propio).
// El paso "Reingreso autorizado" JAMÁS se marca done aquí: cuando el backend
// emite reentry_approved esta pantalla deja de existir (la fase manda).
export type TimelineStep = {
  key: string;
  label: string;
  detail: string | null;
  state: "done" | "current" | "pending";
};

export function reentryTimeline(args: {
  openedAt: string;
  hasOwnCheckin: boolean;
  /** true si el check-in propio ya está en el servidor (no solo encolado). */
  checkinSynced: boolean;
  dictamenStatus: string | null;
  dictamenSigned: boolean;
}): TimelineStep[] {
  const checkin: TimelineStep = args.hasOwnCheckin
    ? args.checkinSynced
      ? { key: "checkin", label: "Su check-in", detail: "Recibido por el servidor.", state: "done" }
      : {
          key: "checkin",
          label: "Su check-in",
          detail: "Guardado en este dispositivo · pendiente de envío.",
          state: "current",
        }
    : { key: "checkin", label: "Su check-in", detail: "Sin registrar.", state: "pending" };

  const dictamen: TimelineStep = args.dictamenSigned
    ? {
        key: "dictamen",
        label: "Dictamen técnico · inspector",
        detail: `Firmado (${args.dictamenStatus ?? "sin estado"}).`,
        state: "done",
      }
    : args.dictamenStatus !== null
      ? {
          key: "dictamen",
          label: "Dictamen técnico · inspector",
          detail: `Evaluación en curso (${args.dictamenStatus}).`,
          state: "current",
        }
      : {
          key: "dictamen",
          label: "Evaluación estructural",
          detail: "En espera del inspector.",
          state: "current",
        };

  return [
    {
      key: "evento",
      label: "Evento registrado",
      detail: new Date(args.openedAt).toLocaleString("es-MX", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }),
      state: "done",
    },
    { key: "sacudida", label: "Sacudida concluida", detail: null, state: "done" },
    checkin,
    dictamen,
    {
      key: "reingreso",
      label: "Reingreso autorizado",
      detail: "Lo emite el centro de mando al firmarse un dictamen habitable.",
      state: "pending",
    },
  ];
}
