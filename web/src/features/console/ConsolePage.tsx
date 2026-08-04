// MONITOREO EN VIVO (antes "Consola C4I") · Live Wall (T-1.27, mockup 1 con desviaciones ratificadas).
//
// El LiveSocket lo posee AppShell desde T-1.49 (topbar viva en todas las
// páginas); la consola lo consume por contexto. El wall: mapa MMI real
// (MapLibre) + banner MVP + cola de incidentes en vivo + detalle del sitio
// enfocado. Los 4 estados obligatorios (regla de oro 7) los materializa
// StateFrame sobre el snapshot del mapa (la fuente que define si el wall
// puede pintar).

import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { ackIncidentIncidentsIncidentIdAckPost } from "@takab/sdk";
import { useQueryClient } from "@tanstack/react-query";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useProfile } from "../../auth/useProfile";
import { useNow } from "../../lib/useNow";
import { useCatalog } from "../triage/useCatalog";
import AlertBanner from "./AlertBanner";
import ComparePanel from "./ComparePanel";
import DetailPanel from "./DetailPanel";
import EpicenterModal from "./EpicenterModal";
import DrillBanner from "./DrillBanner";
import IncidentTable from "./IncidentTable";
import KpiStrip from "./KpiStrip";
import MapPanel from "./MapPanel";
import { isLinkDown, siteLink } from "./link";
import { consoleKpis } from "./stats";
import { useAutoPopup } from "./useAutoPopup";
import { useDictamenRequest } from "./useDictamenRequest";
import { useIncidentActions } from "./useIncidentActions";
import { useLiveIncidents } from "./useLiveIncidents";
import { useQuorumCommands } from "./useQuorumCommands";
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

  // [T-2.28] comparativa histórica en dos pasos: sismo del catálogo → sitio.
  const catalog = useCatalog();
  const [catalogSel, setCatalogSel] = useState<string | null>(null);
  const [compareSiteId, setCompareSiteId] = useState<string | null>(null);
  const catalogSelRef = useRef<string | null>(null);
  catalogSelRef.current = catalogSel;

  // Sitio enfocado: selección explícita, o el del incidente más severo.
  const focusSiteId = selectedSiteId ?? incidents.incidents[0]?.site_id ?? null;
  const features = useSiteFeatures(focusSiteId);
  const soh = useSiteSoh(focusSiteId);
  const relays = useSiteRelays(focusSiteId);
  const focusIncident = incidents.incidents.find((i) => i.site_id === focusSiteId) ?? null;
  const actions = useIncidentActions(focusIncident?.incident_id ?? null);
  // [T-2.32] Burst de actuación del quórum de red para el incidente enfocado.
  const quorumCommanded = useQuorumCommands(focusSiteId, focusIncident?.event_id ?? null);

  // Pop-up automático por anomalía sostenida (criterio #4).
  const openDetail = useCallback((siteId: string) => {
    setSelectedSiteId(siteId);
    setDetailOpen(true);
  }, []);
  // Con un sismo del catálogo armado, el clic en un sitio es el PASO 2 de la
  // comparativa (no abre el detalle). El auto-popup usa openDetail directo, así
  // que una anomalía sostenida jamás cae en modo comparación.
  const onMapSiteClick = useCallback(
    (siteId: string) => {
      if (catalogSelRef.current !== null) {
        setCompareSiteId(siteId);
        return;
      }
      openDetail(siteId);
    },
    [openDetail],
  );
  useAutoPopup(focusSiteId, features.points, openDetail);

  // [T-2.50] Filtro explícito del wall. Las estaciones ocultas SIGUEN contando en
  // los KPIs: si el filtro las quitara también del semáforo, el operador podría
  // esconder sin darse cuenta justo el problema que tiene que atender.
  const [hideNoLink, setHideNoLink] = useState(false);
  const [viewportIds, setViewportIds] = useState<string[] | null>(null);
  const mapSites = useMemo(
    () => (hideNoLink ? map.sites.filter((s) => !isLinkDown(siteLink(s))) : map.sites),
    [map.sites, hideNoLink],
  );
  const kpis = useMemo(
    () => consoleKpis(map.sites, incidents.incidents),
    [map.sites, incidents.incidents],
  );
  // Antes de que el mapa reporte su viewport, "mostrando" son las que se dibujan:
  // no se inventa un recorte que el operador todavía no ha hecho.
  const shownCount = useMemo(() => {
    if (viewportIds === null) return mapSites.length;
    const visible = new Set(viewportIds);
    return mapSites.filter((s) => visible.has(s.site_id)).length;
  }, [mapSites, viewportIds]);

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
    <div className="soc-shell" data-screen-label="01 Monitoreo en Vivo">
      <h1 className="soc-vh">Monitoreo en Vivo</h1>
      <main className="soc-main">
        {/* T-1.60: banner NO-real del simulacro — FUERA del grid del wall; con
            incidente vivo se degrada a badge (lo real domina también visualmente). */}
        <DrillBanner hasLiveIncident={critical !== null} />
        <StateFrame
          label="MONITOREO"
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
          <KpiStrip
            kpis={kpis}
            shown={shownCount}
            hideNoLink={hideNoLink}
            onToggleHideNoLink={() => setHideNoLink((v) => !v)}
          />
          <div className="soc-stage">
            <MapPanel
              sites={mapSites}
              epicenters={map.epicenters}
              onSelectSite={onMapSiteClick}
              catalog={catalog.items}
              catalogError={catalog.error !== null}
              selectedCatalogId={catalogSel}
              onSelectCatalog={setCatalogSel}
              onViewportChange={setViewportIds}
            />
            {/* [T-2.55] Pila ÚNICA de sobrepuestos de la página, anclada
                arriba-derecha. Nada más se ancla a esa esquina, así que dos
                avisos no pueden taparse: se apilan. Vive aquí y NO dentro de
                MapPanel a propósito — la alerta sísmica no puede depender de
                que el mapa monte (regla de oro 1). */}
            <div className="soc-stage__overlays" data-testid="stage-overlays">
              <AlertBanner
                incident={critical}
                siteName={critical ? (siteById.get(critical.site_id)?.name ?? null) : null}
              />
            </div>
          </div>
          <IncidentTable
            incidents={incidents.incidents}
            siteInfoOf={siteInfoOf}
            sites={map.sites}
            epicenter={map.epicenters[0] ?? null}
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
      {catalogSel !== null &&
        compareSiteId !== null &&
        (() => {
          const quake = catalog.items.find((q) => q.ref_id === catalogSel) ?? null;
          return quake !== null ? (
            <ComparePanel
              quake={quake}
              sites={map.sites}
              initialSiteId={compareSiteId}
              onClose={() => {
                setCompareSiteId(null);
                setCatalogSel(null);
              }}
            />
          ) : null;
        })()}
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
          quorumCommanded={quorumCommanded}
          // [T-2.46] El enlace sale del MISMO snapshot que pinta el mapa: una
          // segunda consulta podría contar otra historia sobre el mismo gabinete.
          link={{
            // Sin el sitio en el snapshot NO se deriva nada: `null` es "no lo sé",
            // y la card lo pinta como empty en vez de afirmar un enlace.
            state: focusSite ? siteLink(focusSite) : null,
            reasons: focusSite?.link_reasons ?? [],
            lastHeartbeatTs: focusSite?.last_heartbeat_ts ?? null,
            mqttRttMs: focusSite?.mqtt_rtt_ms ?? null,
            seedlinkLagS: focusSite?.seedlink_lag_s ?? null,
            loading: map.loading,
            error: map.error,
            staleSince,
            refetch: map.refetch,
          }}
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
