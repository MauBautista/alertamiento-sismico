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
  sirenEvidence,
  type CommandOut,
  type FeatureRow,
  type IncidentActionOut,
  type SiteStateFrame,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Modal, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { ControlSheet } from "@/features/control/ControlSheet";
import { preconditionsFor } from "@/features/control/preconditions";
import { executeTacticalCommand, type TacticalAction } from "@/features/control/service";
import { useCommandAck } from "@/features/control/useCommandAck";
import { mergeAction } from "@/features/panel/actions";
import { applyHealthFrame } from "@/features/panel/health";
import { PanelView, type LivePill } from "@/features/panel/PanelView";
import { getLiveSocket } from "@/live/socket";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { space } from "@/ui/theme";

export default function Panel() {
  const router = useRouter();
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

  // La traza del incidente abierto: REST + live, deduplicada por action_id.
  const acciones = useMemo(() => {
    if (incidentId === null) {
      return [];
    }
    const base = restActions.data ?? [];
    const seen = new Set(base.map((a) => a.action_id));
    return [
      ...base,
      ...liveActions.filter((a) => a.incident_id === incidentId && !seen.has(a.action_id)),
    ];
  }, [incidentId, restActions.data, liveActions]);

  const groups = useMemo(() => groupActions(acciones), [acciones]);

  const health = useMemo(
    () => (data ? applyHealthFrame(data.site_health, healthFrame) : null),
    [data, healthFrame],
  );

  // [T-2.09] Control táctico 2.2 server-driven por allowed_actions.
  const actions = useSessionStore((s) => s.me?.allowed_actions);
  const canActivate = actions?.manual_activate === true;
  const canSilence = actions?.siren_silence === true;
  const [control, setControl] = useState<TacticalAction | null>(null);
  const [busy, setBusy] = useState(false);
  // [T-2.107] La 201 es sólo el PUNTO DE PARTIDA (siempre nace `pending`): el
  // acuse real se sigue con `useCommandAck` hasta un estado terminal o hasta
  // el techo derivado del TTL del propio comando.
  const [issued, setIssued] = useState<CommandOut | null>(null);
  const ack = useCommandAck({ siteId, issued });
  const [controlError, setControlError] = useState<string | null>(null);

  // [T-2.110] La sirena "activa" del preflight sale del ÚLTIMO DATO REAL del
  // canal, no de que exista un `siren_on` en la traza.
  //
  // EL DEFECTO: los grupos son POR KIND, así que `siren_off` —que el ingest sí
  // escribe (`ACK_KIND[('siren','deactivate')]`)— caía en otro grupo y no
  // cancelaba nada. Una activación histórica dejaba la precondición satisfecha
  // el resto del incidente, y su detalle afirmaba que el gabinete reportaba la
  // sirena activa sin que nadie lo hubiera reportado. T-2.75.a tapó la mitad
  // (una acción SIMULADA ya no la satisface); esto suelta el enclavamiento.
  //
  // `sirenEvidence` (@takab/sdk, compartida) prefiere el `channel_state` que el
  // gabinete recalcula tras arbitrar sus demandas (T-2.116) y sólo cae al verbo
  // de la traza cuando ese censo no viaja. Devuelve `null` —«no consta»— en vez
  // de un `false` que se leería como «está apagada».
  const siren = useMemo(() => sirenEvidence(acciones), [acciones]);

  const openControl = (action: TacticalAction) => {
    setControl(action);
    setIssued(null);
    setControlError(null);
  };

  // Cerrar la hoja suelta el seguimiento: el sondeo del acuse existe para la
  // persona que lo está mirando, no como tráfico de fondo.
  const closeControl = () => {
    setControl(null);
    setIssued(null);
  };

  const confirmControl = () => {
    if (control === null || siteId === null) {
      return;
    }
    setBusy(true);
    setControlError(null);
    void (async () => {
      const out = await executeTacticalCommand({ siteId, action: control });
      setBusy(false);
      if (out.ok) {
        setIssued(out.command);
      } else {
        setControlError(out.reason);
      }
    })();
  };

  return (
    <StateFrame
      empty={siteId === null}
      emptyText="Sin sitio vigilado. Vincúlese o revise su alcance con el administrador."
      error={data === null ? error : null}
      loading={loading}
      staleSinceMs={stale && data !== null ? dataUpdatedAt : null}
    >
      {data !== null && health !== null ? (
        <>
          <PanelView
            canActivate={canActivate}
            canSilence={canSilence}
            dictamenSigned={data.reentry?.dictamen_signed === true}
            featuresAtMs={featuresAtMs}
            groups={groups}
            health={health}
            incidentOpen={incidentId !== null}
            latestByChannel={[...latestByChannel.values()].sort((a, b) =>
              a.channel.localeCompare(b.channel),
            )}
            live={live}
            nowMs={nowMs}
            onActivate={() => openControl("activate")}
            onOpenDictamen={() => router.push("/dictamen")}
            onSilence={() => openControl("deactivate")}
            siteName={data.site_name}
            tier={data.latest_tier}
          />
          <Modal
            animationType="slide"
            onRequestClose={closeControl}
            transparent
            visible={control !== null}
          >
            <View style={modalStyles.backdrop}>
              {control !== null ? (
                <ControlSheet
                  ackContext={{
                    unconfirmed: ack?.unconfirmed === true,
                    waitCeilingS: ack?.waitCeilingS,
                    // "Alerta vigente" en el sentido de la spec §2.2: el sitio
                    // tiene un incidente sísmico ABIERTO, cuya demanda de
                    // sirena es independiente del canal manual que se retira.
                    alertActive: data.phase === "alert_active",
                  }}
                  action={control}
                  busy={busy}
                  error={controlError}
                  onClose={closeControl}
                  onConfirm={confirmControl}
                  preconditions={preconditionsFor(control, data, {
                    siren,
                    // [T-2.106] El quórum de pánico enciende la sirena SIN abrir
                    // incidente: sin esto, la traza está vacía por diseño y el
                    // táctico no podría silenciar la alarma que tiene delante.
                    buildingAlarm: data.building_alarm != null,
                  })}
                  result={ack?.command ?? null}
                />
              ) : null}
            </View>
          </Modal>
        </>
      ) : null}
    </StateFrame>
  );
}

const modalStyles = {
  backdrop: {
    flex: 1,
    justifyContent: "flex-end" as const,
    backgroundColor: "rgba(0,0,0,0.6)",
    padding: space[3],
  },
};
