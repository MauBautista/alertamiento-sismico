// 2.1 · Dashboard táctico (ruta). Snapshot por mobile-state; live por el
// MISMO LiveSocket de la consola (@takab/sdk): site_state actualiza métricas,
// features:<site> alimenta el strip 1 s y el topic incidents alimenta la
// traza BMS junto con el REST /incidents/{id}/actions (panel_read, RBAC §3).
import {
  featuresTopic,
  listIncidentActionsIncidentsIncidentIdActionsGet,
  TOPIC_INCIDENTS,
  TOPIC_SITE_STATE,
  groupActions,
  type FeatureRow,
  type IncidentActionOut,
  type SiteStateFrame,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useAlertState } from "@/features/alert/useAlertState";
import { mergeAction } from "@/features/panel/actions";
import { applyHealthFrame } from "@/features/panel/health";
import { PanelView, type LivePill } from "@/features/panel/PanelView";
import { getLiveSocket } from "@/live/socket";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

export default function Panel() {
  const siteId = useWatchedSiteId();
  const { data, loading, error, stale, dataUpdatedAt } = useAlertState(siteId);
  const incidentId = data?.incident?.incident_id ?? null;

  const [live, setLive] = useState<LivePill>("closed");
  const [healthFrame, setHealthFrame] = useState<SiteStateFrame | null>(null);
  const [latestByChannel, setLatest] = useState<Map<string, FeatureRow>>(new Map());
  const [featuresAtMs, setFeaturesAtMs] = useState<number | null>(null);
  const [liveActions, setLiveActions] = useState<IncidentActionOut[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 5_000);
    return () => clearInterval(t);
  }, []);

  // Canal live: conectar + suscribir; el estado inicial del pill llega por
  // continuación (lint v6: sin setState síncrono en el cuerpo del effect).
  useEffect(() => {
    if (siteId === null) {
      return;
    }
    const sock = getLiveSocket();
    sock.connect();
    let alive = true;
    Promise.resolve().then(() => {
      if (alive) {
        setLive(sock.status);
      }
    });
    const offStatus = sock.onStatus((s) => setLive(s));
    const offSite = sock.subscribe(TOPIC_SITE_STATE, (f) => {
      if (f.type === "site_state" && f.kind === "device_health" && String(f.site_id) === siteId) {
        setHealthFrame(f);
      }
    });
    const offFeatures = sock.subscribe(featuresTopic(siteId), (f) => {
      if (f.type !== "features") {
        return;
      }
      setLatest((prev) => {
        const next = new Map(prev);
        for (const row of f.rows) {
          next.set(row.channel, row);
        }
        return next;
      });
      setFeaturesAtMs(Date.now());
    });
    const offIncidents = sock.subscribe(TOPIC_INCIDENTS, (f) => {
      if (f.type === "incident_action") {
        // Acumula deduplicado por action_id; al PINTAR se filtra por el
        // incidente abierto (frames de otros incidentes no contaminan).
        setLiveActions((prev) => mergeAction(prev, f, String(f.incident_id)));
      }
    });
    return () => {
      alive = false;
      offStatus();
      offSite();
      offFeatures();
      offIncidents();
    };
  }, [siteId]);

  const restActions = useQuery({
    queryKey: ["incident-actions", incidentId],
    enabled: incidentId != null,
    queryFn: async () => {
      const res = await listIncidentActionsIncidentsIncidentIdActionsGet({
        path: { incident_id: incidentId as string },
      });
      if (!res.data) {
        throw new Error("traza no disponible");
      }
      return res.data;
    },
    refetchInterval: 30_000,
  });

  const groups = useMemo(() => {
    if (incidentId === null) {
      return [];
    }
    const base = restActions.data ?? [];
    const seen = new Set(base.map((a) => a.action_id));
    const combined = [
      ...base,
      ...liveActions.filter((a) => a.incident_id === incidentId && !seen.has(a.action_id)),
    ];
    return groupActions(combined);
  }, [incidentId, restActions.data, liveActions]);

  const health = useMemo(
    () => (data ? applyHealthFrame(data.site_health, healthFrame) : null),
    [data, healthFrame],
  );

  return (
    <StateFrame
      empty={siteId === null}
      emptyText="Sin sitio vigilado. Vincúlese o revise su alcance con el administrador."
      error={data === null ? error : null}
      loading={loading}
      staleSinceMs={stale && data !== null ? dataUpdatedAt : null}
    >
      {data !== null && health !== null ? (
        <PanelView
          featuresAtMs={featuresAtMs}
          groups={groups}
          health={health}
          incidentOpen={incidentId !== null}
          latestByChannel={[...latestByChannel.values()].sort((a, b) =>
            a.channel.localeCompare(b.channel),
          )}
          live={live}
          nowMs={nowMs}
          siteName={data.site_name}
          tier={data.latest_tier}
        />
      ) : null}
    </StateFrame>
  );
}
