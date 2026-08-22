// [T-2.147.b · D-05] El acuse de la brigada, del lado del cliente.
//
// Best-effort DECLARADO, no silencioso: un fallo se muestra y se puede reintentar.
// La razón es la cadena entera — si el acuse se perdiera sin decirlo, quien lo pulsó
// creería haber avisado y el SOC escalaría igual a los ~2 min. Un error visible es
// peor experiencia y mejor información, que es el orden correcto aquí.
//
// El endpoint es **idempotente por persona** y devuelve `already: true` en la segunda
// pulsación, así que reintentar es seguro: lo que se mide aguas arriba es cuántas
// PERSONAS respondieron, no cuántas veces pulsaron.
import { tacticalAckIncidentsIncidentIdTacticalAckPost } from "@takab/sdk";
import { useCallback, useState } from "react";

import { type AckEstado } from "./TacticalAckButton";

export type TacticalAck = {
  estado: AckEstado;
  /** ISO del instante en que ESTE teléfono registró el acuse. */
  acusadoEn: string | null;
  acusar: () => Promise<void>;
};

export function useTacticalAck(incidentId: string | null): TacticalAck {
  const [estado, setEstado] = useState<AckEstado>("idle");
  const [acusadoEn, setAcusadoEn] = useState<string | null>(null);

  const acusar = useCallback(async () => {
    if (incidentId === null || estado === "enviando" || estado === "acusado") {
      return;
    }
    setEstado("enviando");
    try {
      const res = await tacticalAckIncidentsIncidentIdTacticalAckPost({
        path: { incident_id: incidentId },
      });
      if (res.error) {
        setEstado("error");
        return;
      }
      setAcusadoEn(new Date().toISOString());
      setEstado("acusado");
    } catch {
      setEstado("error");
    }
  }, [incidentId, estado]);

  return { estado, acusadoEn, acusar };
}
