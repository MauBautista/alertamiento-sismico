// Modal de reubicación de epicentro (T-1.51): REUTILIZA el MapPointPicker de
// la flota (marcador arrastrable + clic para colocar) sobre el modal nuevo.
// Con evento linkeado inicia en su epicentro actual; sin evento avisa que se
// creará un seismic_event source='manual' (EVT-MAN-…, determinista, sin
// magnitud — T-1.48) y arranca en las coordenadas del sitio.

import { MapPin } from "lucide-react";
import { useState } from "react";

import { getEventEventsEventIdGet } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import ConfirmButton from "../../components/ConfirmButton";
import Modal from "../../components/Modal";
import StateFrame from "../../components/StateFrame";
import MapPointPicker from "../fleet/MapPointPicker";
import { DEFAULT_PICK, parseLatLonPair, formatPoint, type LonLat } from "../fleet/geo";
import type { LiveIncident } from "./useLiveIncidents";
import { useEpicenter } from "./useEpicenter";

export interface EpicenterModalProps {
  incident: LiveIncident;
  /** Coordenadas del sitio del incidente (arranque sin evento), si se conocen. */
  site: { name: string; lat: number; lon: number } | null;
  onClose: () => void;
}

export default function EpicenterModal({ incident, site, onClose }: EpicenterModalProps) {
  const relocate = useEpicenter();
  const eventId = incident.event_id;

  const event = useQuery({
    queryKey: ["event", eventId],
    enabled: eventId !== null,
    queryFn: async () => {
      const res = await getEventEventsEventIdGet({
        path: { event_id: eventId as string },
        throwOnError: true,
      });
      return res.data;
    },
  });

  const fallback: LonLat = site ? { lon: site.lon, lat: site.lat } : DEFAULT_PICK;
  const eventPoint: LonLat | null =
    event.data?.epicenter_lon != null && event.data?.epicenter_lat != null
      ? { lon: event.data.epicenter_lon, lat: event.data.epicenter_lat }
      : null;

  const [point, setPoint] = useState<LonLat | null>(null);
  const [coordsDraft, setCoordsDraft] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const effective = point ?? eventPoint ?? fallback;

  const applyDraft = () => {
    if (coordsDraft === null) return;
    const parsed = parseLatLonPair(coordsDraft);
    if (parsed !== null) setPoint(parsed);
    setCoordsDraft(null);
  };

  return (
    <Modal title="REUBICAR EPICENTRO" onClose={onClose}>
      <div className="soc-epicenter">
        <p className="soc-epicenter__ctx">
          <MapPin size={12} aria-hidden /> Incidente{" "}
          <span className="soc-mono">{incident.incident_id.slice(0, 8)}</span>
          {site ? ` · ${site.name}` : ""}
        </p>

        {eventId === null ? (
          <p className="soc-epicenter__notice" role="note">
            INCIDENTE SIN EVENTO SÍSMICO ASOCIADO · SE CREARÁ UN EVENTO{" "}
            <span className="soc-mono">source=manual</span> (SIN MAGNITUD)
          </p>
        ) : (
          <p className="soc-epicenter__notice soc-epicenter__notice--event" role="note">
            EVENTO <span className="soc-mono">{eventId}</span> · EL PUNTO PREVIO QUEDA AUDITADO
          </p>
        )}

        <StateFrame
          label="EVENTO"
          loading={eventId !== null && event.isPending}
          error={eventId !== null && event.isError ? "GET /events falló" : null}
          onRetry={() => void event.refetch()}
        >
          <MapPointPicker value={effective} onChange={setPoint} />
        </StateFrame>

        <label className="soc-meta" htmlFor="epicenter-coords">
          LAT, LON MANUAL
        </label>
        <input
          id="epicenter-coords"
          className="soc-user__input soc-mono"
          value={coordsDraft ?? formatPoint(effective)}
          onChange={(e) => setCoordsDraft(e.target.value)}
          onBlur={applyDraft}
          onKeyDown={(e) => {
            if (e.key === "Enter") applyDraft();
          }}
        />

        <label className="soc-meta" htmlFor="epicenter-note">
          NOTA (OPCIONAL — P.EJ. FUENTE SSN)
        </label>
        <input
          id="epicenter-note"
          className="soc-user__input"
          value={note}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
        />

        {relocate.isError && (
          <p className="soc-user__error" role="alert">
            NO SE PUDO REUBICAR — {relocate.error instanceof Error ? relocate.error.message : ""}
          </p>
        )}

        <div className="soc-epicenter__actions">
          <ConfirmButton
            label="CONFIRMAR REUBICACIÓN"
            armedLabel="CLIC DE NUEVO PARA REUBICAR"
            variant="primary"
            disabled={relocate.isPending}
            onConfirm={() => {
              relocate.mutate(
                {
                  incidentId: incident.incident_id,
                  lon: effective.lon,
                  lat: effective.lat,
                  note: note.trim() === "" ? null : note.trim(),
                },
                { onSuccess: onClose },
              );
            }}
          />
        </div>
      </div>
    </Modal>
  );
}
