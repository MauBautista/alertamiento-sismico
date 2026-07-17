// 2.6 · Headcount del táctico. Roster (GET /incidents/{id}/roster) cruzado con
// check-ins EN VIVO: el WS emite una señal `roster` por cada check-in (T-2.11)
// y la lista se refresca en <2 s. Marcar "verificado en persona" = check-in
// DELEGADO; notificar/cerrar headcount llaman a los endpoints firmados.
import {
  closeHeadcountIncidentsIncidentIdHeadcountClosePost,
  incidentRosterIncidentsIncidentIdRosterGet,
  notifyUnreportedIncidentsIncidentIdHeadcountNotifyUnreportedPost,
  submitCheckinIncidentsIncidentIdCheckinsPost,
  TOPIC_INCIDENTS,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useAlertState } from "@/features/alert/useAlertState";
import { HeadcountView } from "@/features/headcount/HeadcountView";
import { getLiveSocket } from "@/live/socket";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

export default function Lista() {
  const siteId = useWatchedSiteId();
  const { data: state, loading: stateLoading } = useAlertState(siteId);
  const incidentId = state?.incident?.incident_id ?? null;

  const [onlyUnreported, setOnlyUnreported] = useState(true);
  const [live, setLive] = useState(false);
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const roster = useQuery({
    queryKey: ["roster", incidentId],
    enabled: incidentId != null,
    // Piso de frescura (vida): aunque el WS calle o caiga, el pase de lista se
    // re-consulta solo; el WS sigue siendo el camino primario (<2 s).
    refetchInterval: 15_000,
    queryFn: async () => {
      const res = await incidentRosterIncidentsIncidentIdRosterGet({
        path: { incident_id: incidentId as string },
      });
      if (!res.data) {
        throw new Error("roster no disponible");
      }
      return res.data;
    },
  });

  // Live: la señal `roster` (o cualquier frame de incidente del sitio) refresca
  // el roster en <2 s. El pill del estado viene por continuación (lint v6).
  useEffect(() => {
    if (incidentId === null || siteId === null) {
      return;
    }
    const sock = getLiveSocket();
    sock.connect();
    let alive = true;
    Promise.resolve().then(() => {
      if (alive) {
        setLive(sock.status === "ready");
      }
    });
    const offStatus = sock.onStatus((s) => setLive(s === "ready"));
    const offIncidents = sock.subscribe(TOPIC_INCIDENTS, (f) => {
      if (
        (f.type === "roster" || f.type === "incident" || f.type === "incident_action") &&
        String((f as { site_id?: string }).site_id ?? siteId) === siteId
      ) {
        void roster.refetch();
      }
    });
    return () => {
      alive = false;
      offStatus();
      offIncidents();
    };
  }, [incidentId, siteId, roster]);

  const markVerified = (userId: string) => {
    if (incidentId === null) {
      return;
    }
    setMarkingId(userId);
    void (async () => {
      // Check-in DELEGADO: subject_user_id ≠ portador ⇒ via='delegated',
      // verified_by=táctico (distinguible del propio del ocupante).
      await submitCheckinIncidentsIncidentIdCheckinsPost({
        path: { incident_id: incidentId },
        body: { status: "safe", subject_user_id: userId, ts_device: new Date().toISOString() },
      });
      setMarkingId(null);
      void roster.refetch();
    })();
  };

  const notifyUnreported = () => {
    if (incidentId === null) {
      return;
    }
    setBusy(true);
    void notifyUnreportedIncidentsIncidentIdHeadcountNotifyUnreportedPost({
      path: { incident_id: incidentId },
    }).finally(() => setBusy(false));
  };

  const closeHeadcount = () => {
    if (incidentId === null) {
      return;
    }
    setBusy(true);
    // La firma con llave de hardware es opcional (§2.1-B); el cierre queda
    // registrado como acción del táctico aunque no se firme.
    void closeHeadcountIncidentsIncidentIdHeadcountClosePost({
      path: { incident_id: incidentId },
      body: {},
    }).finally(() => setBusy(false));
  };

  return (
    <StateFrame
      empty={incidentId === null}
      emptyText="Sin incidente activo en su sitio: no hay pase de lista que llevar."
      error={roster.isError && !roster.data ? "No se pudo cargar el roster." : null}
      loading={(stateLoading && incidentId === null) || (roster.isLoading && incidentId !== null)}
      staleSinceMs={roster.data != null && roster.failureCount > 0 ? roster.dataUpdatedAt : null}
    >
      {roster.data ? (
        <HeadcountView
          busy={busy}
          live={live}
          markingId={markingId}
          onCloseHeadcount={closeHeadcount}
          onMarkVerified={markVerified}
          onNotifyUnreported={notifyUnreported}
          onToggleFilter={setOnlyUnreported}
          onlyUnreported={onlyUnreported}
          roster={roster.data}
        />
      ) : null}
    </StateFrame>
  );
}
