// 2.6 · Headcount del táctico. Roster (GET /incidents/{id}/roster) cruzado con
// check-ins EN VIVO: el WS emite una señal `roster` por cada check-in (T-2.11)
// y la lista se refresca en <2 s. Marcar "verificado en persona" = check-in
// DELEGADO; notificar/cerrar headcount llaman a los endpoints firmados.
//
// [T-2.111] Las tres acciones de esta pantalla se tragaban su desenlace:
//   · `markVerified` no capturaba y el SDK LANZA al morir `fetch`: la fila se
//     quedaba en «…» y el táctico daba por VIVA a una persona que sigue sin
//     reportar. En un pase de lista eso es lo peor que puede pasar.
//   · `notifyUnreported`/`closeHeadcount` liberaban el botón con `.finally` y
//     no pintaban nada: no había forma de saber si la notificación salió.
//   · el error de `mobile-state` no viajaba al marco, así que con la consulta
//     caída la pantalla afirmaba «Sin incidente activo en su sitio».
import {
  closeHeadcountIncidentsIncidentIdHeadcountClosePost,
  incidentRosterIncidentsIncidentIdRosterGet,
  notifyUnreportedIncidentsIncidentIdHeadcountNotifyUnreportedPost,
  submitCheckinIncidentsIncidentIdCheckinsPost,
  TOPIC_INCIDENTS,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useAlertState } from "@/features/alert/useAlertState";
import { HeadcountView } from "@/features/headcount/HeadcountView";
import { getLiveSocket } from "@/live/socket";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { fontSize, palette, radius, space } from "@/ui/theme";

/** Desenlace de una acción del táctico. `ok=false` tiene que decir SIEMPRE qué
 *  NO pasó (nadie avisado, nadie contabilizado): el silencio de esta pantalla
 *  se lee como éxito. */
type Desenlace = { ok: boolean; text: string };

export default function Lista() {
  const siteId = useWatchedSiteId();
  const {
    data: state,
    loading: stateLoading,
    error: stateError,
    refetch: refetchState,
  } = useAlertState(siteId);
  const incidentId = state?.incident?.incident_id ?? null;

  const [onlyUnreported, setOnlyUnreported] = useState(true);
  const [live, setLive] = useState(false);
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // El desenlace vive en el estado del componente: `HeadcountView` se
  // reconstruye en cada frame (y en cada señal del WS), así que un mensaje
  // guardado en una variable del manejador se perdería en el acto.
  const [desenlace, setDesenlace] = useState<Desenlace | null>(null);

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
    setDesenlace(null);
    void (async () => {
      try {
        // Check-in DELEGADO: subject_user_id ≠ portador ⇒ via='delegated',
        // verified_by=táctico (distinguible del propio del ocupante).
        const res = await submitCheckinIncidentsIncidentIdCheckinsPost({
          path: { incident_id: incidentId },
          body: { status: "safe", subject_user_id: userId, ts_device: new Date().toISOString() },
        });
        if (!res.data) {
          throw new Error("el servidor no aceptó el check-in delegado");
        }
        void roster.refetch();
      } catch {
        setDesenlace({
          ok: false,
          text: "No se pudo verificar a esa persona: sigue SIN REPORTE en el pase de lista. Nada quedó registrado — vuelva a intentarlo.",
        });
      } finally {
        setMarkingId(null);
      }
    })();
  };

  const notifyUnreported = () => {
    if (incidentId === null) {
      return;
    }
    setBusy(true);
    setDesenlace(null);
    void (async () => {
      try {
        const res = await notifyUnreportedIncidentsIncidentIdHeadcountNotifyUnreportedPost({
          path: { incident_id: incidentId },
        });
        if (!res.data) {
          throw new Error("el servidor no aceptó la notificación");
        }
        setDesenlace({
          ok: true,
          text: "Notificación enviada a quienes no han reportado.",
        });
      } catch {
        setDesenlace({
          ok: false,
          text: "No se pudo notificar: nadie ha sido avisado. Revise su conexión e intente de nuevo.",
        });
      } finally {
        setBusy(false);
      }
    })();
  };

  const closeHeadcount = () => {
    if (incidentId === null) {
      return;
    }
    setBusy(true);
    setDesenlace(null);
    void (async () => {
      try {
        // La firma con llave de hardware es opcional (§2.1-B); el cierre queda
        // registrado como acción del táctico aunque no se firme.
        const res = await closeHeadcountIncidentsIncidentIdHeadcountClosePost({
          path: { incident_id: incidentId },
          body: {},
        });
        if (!res.data) {
          throw new Error("el servidor no aceptó el cierre");
        }
        setDesenlace({ ok: true, text: "Headcount cerrado y registrado." });
      } catch {
        setDesenlace({
          ok: false,
          text: "No se pudo cerrar el headcount: sigue abierto y sin registrar. Revise su conexión e intente de nuevo.",
        });
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <StateFrame
      empty={stateError === null && incidentId === null}
      emptyText="Sin incidente activo en su sitio: no hay pase de lista que llevar."
      // Un `mobile-state` caído deja `incidentId` en null, y sin esto la
      // pantalla afirmaba «Sin incidente activo»: la frase más tranquilizadora
      // posible, dicha justo cuando no se sabe nada.
      error={
        stateError ?? (roster.isError && !roster.data ? "No se pudo cargar el roster." : null)
      }
      loading={(stateLoading && incidentId === null) || (roster.isLoading && incidentId !== null)}
      onRetry={() => {
        refetchState();
        void roster.refetch();
      }}
      staleSinceMs={roster.data != null && roster.failureCount > 0 ? roster.dataUpdatedAt : null}
    >
      {roster.data ? (
        <View style={styles.pila}>
          {desenlace !== null ? (
            <View
              style={[
                styles.desenlace,
                { borderColor: desenlace.ok ? palette.ok : palette.crit },
              ]}
              testID="headcount-outcome"
            >
              <Text style={[styles.desenlaceText, { color: desenlace.ok ? palette.ok : palette.crit }]}>
                {desenlace.text}
              </Text>
            </View>
          ) : null}
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
        </View>
      ) : null}
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  pila: { flex: 1, backgroundColor: palette.bg },
  desenlace: {
    backgroundColor: palette.card,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
    margin: space[4],
    marginBottom: 0,
  },
  desenlaceText: { fontSize: fontSize.sm, lineHeight: 20 },
});
