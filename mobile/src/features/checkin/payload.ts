// Construcción del payload del check-in (1.4). REGLA DE HONESTIDAD (LFPDPPP,
// spec 0.3/1.4): el GPS viaja ÚNICAMENTE si (a) el usuario pide AYUDA y
// (b) dio consentimiento vigente. "Estoy bien" jamás manda ubicación — aunque
// exista un fix a la mano. Sin GPS viaja la zona asignada (y se declara).
import type { CheckinPayload } from "@/offline/queue";

export function buildCheckinPayload(args: {
  incidentId: string;
  status: "safe" | "need_help";
  zoneId: string | null;
  gpsConsent: boolean;
  fix: [number, number] | null;
  tsDevice: string;
}): CheckinPayload {
  const sendGps = args.status === "need_help" && args.gpsConsent;
  return {
    incident_id: args.incidentId,
    status: args.status,
    zone_id: args.zoneId,
    location: sendGps ? args.fix : null,
    ts_device: args.tsDevice,
  };
}

/** Texto de transparencia BAJO cada botón: qué se enviará exactamente. */
export function whatWillBeSent(args: {
  status: "safe" | "need_help";
  gpsConsent: boolean;
  zoneName: string | null;
}): string {
  const zone = args.zoneName ? `zona ${args.zoneName}` : "sin zona asignada";
  if (args.status === "need_help" && args.gpsConsent) {
    return `Enviará: su estado, ${zone}, hora del dispositivo y su ubicación GPS actual.`;
  }
  if (args.status === "need_help") {
    return `Enviará: su estado, ${zone} y hora del dispositivo. SIN GPS (no dio consentimiento).`;
  }
  return `Enviará: su estado, ${zone} y hora del dispositivo. Sin ubicación.`;
}
