// Consola C4I · Live Wall (T-1.27, mockup 1 con desviaciones ratificadas).
//
// El LiveSocket lo posee AppShell desde T-1.49 (topbar viva en todas las
// páginas); la consola lo consume por contexto. El wall: mapa MMI real
// (MapLibre) + banner MVP + cola de incidentes en vivo + detalle del sitio
// enfocado. Los 4 estados obligatorios (regla de oro 7) los materializa
// StateFrame sobre el snapshot del mapa (la fuente que define si el wall
// puede pintar).

import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { ackIncidentIncidentsIncidentIdAckPost } from "@takab/sdk";
import { useQueryClient } from "@tanstack/react-query";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useProfile } from "../../auth/useProfile";
import { useNow } from "../../lib/useNow";
import AlertBanner from "./AlertBanner";
import DetailPanel from "./DetailPanel";
import EpicenterModal from "./EpicenterModal";
import IncidentTable from "./IncidentTable";
import MapPanel from "./MapPanel";
import { useAutoPopup } from "./useAutoPopup";
import { useDictamenRequest } from "./useDictamenRequest";
import { useIncidentActions } from "./useIncidentActions";
import { useLiveIncidents } from "./useLiveIncidents";
import { useMapState } from "./useMapState";
import { useSiteFeatures } from "./useSiteFeatures";
import { useSiteRelays } from "./useSiteRelays";
import { useSiteSoh } from "./useSiteSoh";

/** Sin snapshot fresco del mapa tras esto (poll 30 s) el wall es DATOS RETENIDOS. */
export const CONSOLE_STALE_MS = 90_000;

function coordsLabel(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}°${ns} · ${Math.abs(lon).toFixed(4)}°${ew}`;
}

function ConsoleWall() {
  const me = useSessionStore((s) => s.me);
  const profile = useProfile();
  const now = useNow(1000);
  const queryClient = useQueryClient();
  const incidents = useLiveIncidents();
  const map = useMapState();

  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Sitio enfocado: selección explícita, o el del incidente más severo.
  const focusSiteId = selectedSiteId ?? incidents.incidents[0]?.site_id ?? null;
  const features = useSiteFeatures(focusSiteId);
  const soh = useSiteSoh(focusSiteId);
  const relays = useSiteRelays(focusSiteId);
  const focusIncident = incidents.incidents.find((i) => i.site_id === focusSiteId) ?? null;
  const actions = useIncidentActions(focusIncident?.incident_id ?? null);

  // Pop-up automático por anomalía sostenida (criterio #4).
  const openDetail = useCallback((siteId: string) => {
    setSelectedSiteId(siteId);
    setDetailOpen(true);
  }, []);
  useAutoPopup(focusSiteId, features.points, openDetail);

  const siteById = useMemo(() => new Map(map.sites.map((s) => [s.site_id, s])), [map.sites]);
  const siteInfoOf = useCallback(
    (siteId: string) => {
      const site = siteById.get(siteId);
      return site ? { name: site.name, coords: coordsLabel(site.lat, site.lon) } : null;
    },
    [siteById],
  );

  const critical = incidents.incidents.find((i) => i.severity === "critical") ?? null;
  const focusSite = focusSiteId !== null ? (siteById.get(focusSiteId) ?? null) : null;

  const staleSince =
    !map.loading &&
    !map.error &&
    map.dataUpdatedAt > 0 &&
    now - map.dataUpdatedAt > CONSOLE_STALE_MS
      ? map.dataUpdatedAt
      : null;

  const canAck = me?.allowed_actions.ack_incident === true;
  const onAck = useCallback(
    (incidentId: string) => {
      void (async () => {
        await ackIncidentIncidentsIncidentIdAckPost({ path: { incident_id: incidentId } });
        await queryClient.invalidateQueries({ queryKey: ["incidents", "open"] });
        await queryClient.invalidateQueries({ queryKey: ["incident", incidentId, "actions"] });
      })();
    },
    [queryClient],
  );

  // T-1.51: botones del operador — gates de la matriz (allowed_actions).
  const navigate = useNavigate();
  const dictamenRequest = useDictamenRequest();
  const [epicenterFor, setEpicenterFor] = useState<string | null>(null);
  const canRelocate = me?.allowed_actions.relocate_epicenter === true;
  const canRequestDictamen = me?.allowed_actions.request_dictamen === true;
  const onRequestDictamen = useCallback(
    (incidentId: string) => {
      // La solicitud aterriza en el timeline; el flujo del dictamen vive en
      // Triage — se navega con el incidente preseleccionado.
      dictamenRequest.mutate(incidentId, {
        onSuccess: () => void navigate(`/triage?incident=${incidentId}`),
      });
    },
    [dictamenRequest, navigate],
  );
  const epicenterIncident =
    epicenterFor !== null
      ? (incidents.incidents.find((i) => i.incident_id === epicenterFor) ?? null)
      : null;
  const epicenterSite =
    epicenterIncident !== null ? (siteById.get(epicenterIncident.site_id) ?? null) : null;

  return (
    <div className="soc-shell" data-screen-label="01 Consola C4I · Live Wall">
      <h1 className="soc-vh">CONSOLA C4I</h1>
      <main className="soc-main">
        <StateFrame
          label="CONSOLA C4I"
          className="soc-wall"
          loading={map.loading || incidents.loading}
          error={map.error ?? incidents.error}
          onRetry={() => {
            map.refetch();
            incidents.refetch();
          }}
          empty={map.sites.length === 0}
          emptyText="SIN SITIOS VISIBLES EN EL TENANT"
          staleSince={staleSince}
        >
          <div className="soc-stage">
            <MapPanel sites={map.sites} onSelectSite={openDetail} />
            <AlertBanner
              incident={critical}
              siteName={critical ? (siteById.get(critical.site_id)?.name ?? null) : null}
            />
          </div>
          <IncidentTable
            incidents={incidents.incidents}
            siteInfoOf={siteInfoOf}
            nowMs={now}
            liveStatus={incidents.liveStatus}
            operatorLabel={
              me
                ? (profile.data?.display_name?.toUpperCase() ??
                  `${me.role.toUpperCase()} · ${me.sub.slice(0, 8)}`)
                : "—"
            }
            selectedId={focusIncident?.incident_id ?? null}
            onSelect={(incident) => openDetail(incident.site_id)}
            canAck={canAck}
            onAck={onAck}
            canRelocate={canRelocate}
            onRelocate={setEpicenterFor}
            canRequestDictamen={canRequestDictamen}
            onRequestDictamen={onRequestDictamen}
          />
        </StateFrame>
        {dictamenRequest.isError && (
          <p className="soc-user__error" role="alert">
            {dictamenRequest.error instanceof Error
              ? dictamenRequest.error.message.toUpperCase()
              : "NO SE PUDO SOLICITAR EL DICTAMEN"}
          </p>
        )}
      </main>
      {epicenterIncident !== null && (
        <EpicenterModal
          incident={epicenterIncident}
          site={
            epicenterSite
              ? { name: epicenterSite.name, lat: epicenterSite.lat, lon: epicenterSite.lon }
              : null
          }
          onClose={() => setEpicenterFor(null)}
        />
      )}
      {detailOpen && focusSiteId !== null && (
        <DetailPanel
          site={{
            site_id: focusSiteId,
            name: focusSite?.name ?? `SITIO ${focusSiteId.slice(0, 8)}`,
            coords: focusSite ? coordsLabel(focusSite.lat, focusSite.lon) : null,
          }}
          features={features}
          soh={soh}
          actions={actions}
          incident={focusIncident}
          relays={relays}
          nowMs={now}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </div>
  );
}

/** Página /console: consume el LiveSocket del shell (dueño: AppShell, T-1.49). */
export default function ConsolePage() {
  return <ConsoleWall />;
}
