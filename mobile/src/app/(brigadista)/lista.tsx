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
//
// [T-8.11 · A-024] …y el check-in delegado, aun capturando el fallo, hacía un
// POST DIRECTO: sin red decía «No se pudo verificar» y no guardaba nada. Es la
// pantalla del trío offline y la única captura del táctico que no pasaba por la
// cola. Ahora se ENCOLA (tipo `delegated_checkin`) y se intenta en el acto; sin
// red queda guardado en el teléfono y la fila lo dice («EN COLA»).
import {
  closeHeadcountIncidentsIncidentIdHeadcountClosePost,
  incidentRosterIncidentsIncidentIdRosterGet,
  notifyUnreportedIncidentsIncidentIdHeadcountNotifyUnreportedPost,
  TOPIC_INCIDENTS,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useAlertState } from "@/features/alert/useAlertState";
import { HeadcountView } from "@/features/headcount/HeadcountView";
import { getLiveSocket } from "@/live/socket";
import { delegadosEnCola } from "@/offline/queue";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { useStaleSince } from "@/ui/useStaleSince";
import { fontSize, palette, radius, space } from "@/ui/theme";

/** Piso de frescura del pase de lista (vida): también es su umbral de vejez. */
const ROSTER_POLL_MS = 15_000;

/** Desenlace de una acción del táctico. `crit` tiene que decir SIEMPRE qué NO
 *  pasó (nadie avisado, nadie contabilizado): el silencio de esta pantalla se
 *  lee como éxito. `warn` es lo que está a medio camino —guardado en el
 *  teléfono, sin llegar al servidor— y lleva `itemId`, el de SU item de la
 *  cola: el aviso sigue a ese item mientras se ve (ver `aviso`, abajo). */
type Desenlace = { tone: "ok" | "warn" | "crit"; text: string; itemId?: string };

/** El mismo texto para el rechazo en el acto y para el que llega después, en el
 *  drenaje de fondo: sin el código HTTP, que queda en su tarjeta de SYNC. */
const RECHAZADA =
  "El servidor rechazó la verificación: esa persona sigue SIN REPORTE en el pase de lista. Queda en SYNC, con el motivo, para reintentarla.";

/** Pendiente. Vale para los DOS caminos que la dejan así —sin red, o con red y
 *  la cola ya drenando otra (una sola pasada a la vez)—, así que no culpa a la
 *  conexión: [T-8.11 · verificador] decía «al recuperar la conexión» también
 *  cuando la conexión nunca se había perdido. */
const GUARDADA =
  "Verificación GUARDADA EN ESTE TELÉFONO: todavía no ha llegado al servidor y se enviará sola, sin repetirla. Hasta que llegue, esa persona sigue SIN REPORTE en el pase de lista.";

const TONO: Record<Desenlace["tone"], string> = {
  ok: palette.ok,
  warn: palette.warn,
  crit: palette.crit,
};

const SIN_PERSONAS: ReadonlySet<string> = new Set();

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
    refetchInterval: ROSTER_POLL_MS,
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
  // [T-5.21] La edad del pase de lista sale del RELOJ. Antes era
  // `failureCount > 0`: con red sana, un pase de lista de hace diez minutos
  // se pintaba como fresco — y esta es la pantalla que dice quién está dentro
  // del edificio y en qué estado.
  const rosterStaleSinceMs = useStaleSince(roster.dataUpdatedAt, ROSTER_POLL_MS);

  // [T-8.11] Lo que este teléfono ya verificó y aún no llegó al servidor. Sale
  // de la COLA, no de un estado de la pantalla: sobrevive a salir y volver, y a
  // cerrar la app.
  const queueItems = useQueueStore((s) => s.items);
  const enCola = incidentId === null ? SIN_PERSONAS : delegadosEnCola(queueItems, incidentId);
  // Cuántas entregó ya la cola. Cuando sube, el roster del servidor ya las
  // cuenta: se re-consulta en el acto, sin esperar al WS ni al sondeo de 15 s.
  const entregadas =
    incidentId === null
      ? 0
      : queueItems.filter(
          (i) =>
            i.kind === "delegated_checkin" &&
            i.payload.incident_id === incidentId &&
            i.state === "synced",
        ).length;
  // Solo cuando SUBE: al montar, la consulta del roster ya sale por su cuenta, y
  // las entregadas en otra visita (la cola las guarda 24 h) no son noticia.
  const entregadasAntes = useRef(entregadas);
  const refetchRoster = roster.refetch;
  useEffect(() => {
    if (entregadas > entregadasAntes.current) {
      void refetchRoster();
    }
    entregadasAntes.current = entregadas;
  }, [entregadas, refetchRoster]);

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
    if (incidentId === null || enCola.has(userId)) {
      return;
    }
    setMarkingId(userId);
    setDesenlace(null);
    void (async () => {
      try {
        // Check-in DELEGADO: subject_user_id ≠ portador ⇒ via='delegated',
        // verified_by=táctico (distinguible del propio del ocupante). Se sella
        // AL TOQUE y se guarda antes de intentar nada: la red no decide si la
        // verificación existe, solo cuándo llega.
        const item = await useQueueStore.getState().enqueueDelegatedCheckin({
          incident_id: incidentId,
          subject_user_id: userId,
          status: "safe",
          ts_device: new Date().toISOString(),
        });
        await drainQueue(); // intento inmediato; sin red queda pending con backoff
        const ahora = useQueueStore.getState().items.find((i) => i.id === item.id);
        if (ahora?.state === "synced") {
          void roster.refetch();
        } else if (ahora?.state === "failed") {
          setDesenlace({ tone: "crit", text: RECHAZADA });
        } else {
          // Pendiente: sin red, o la cola ya estaba drenando. Las dos cosas se
          // dicen igual, porque las dos son ciertas: está en el teléfono y
          // todavía no en el servidor.
          setDesenlace({ tone: "warn", itemId: item.id, text: GUARDADA });
        }
      } catch {
        setDesenlace({
          tone: "crit",
          text: "No se pudo guardar la verificación en este teléfono: esa persona sigue SIN REPORTE en el pase de lista y nada quedó registrado — vuelva a intentarlo.",
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
          tone: "ok",
          text: "Notificación enviada a quienes no han reportado.",
        });
      } catch {
        setDesenlace({
          tone: "crit",
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
        setDesenlace({ tone: "ok", text: "Headcount cerrado y registrado." });
      } catch {
        setDesenlace({
          tone: "crit",
          text: "No se pudo cerrar el headcount: sigue abierto y sin registrar. Revise su conexión e intente de nuevo.",
        });
      } finally {
        setBusy(false);
      }
    })();
  };

  // El aviso de «guardada en el teléfono» sigue a SU item de la cola, porque
  // deja de ser cierto sin que nadie toque nada:
  //   · entregado (o podado a las 24 h) ⇒ se retira solo;
  //   · RECHAZADO después, en el drenaje de fondo (404/403) ⇒ pasa a crítico
  //     con el mismo texto que el rechazo en el acto. Antes se retiraba EN
  //     SILENCIO y la fila volvía a VERIFICAR sin decir por qué: el motivo solo
  //     se veía en SYNC [T-8.11 · verificador].
  const vigilado =
    desenlace?.itemId === undefined
      ? null
      : (queueItems.find((i) => i.id === desenlace.itemId) ?? null);
  const aviso: Desenlace | null =
    desenlace?.itemId === undefined
      ? desenlace
      : vigilado === null || vigilado.state === "synced"
        ? null
        : vigilado.state === "failed"
          ? { tone: "crit", text: RECHAZADA }
          : desenlace;

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
      staleSinceMs={rosterStaleSinceMs}
    >
      {roster.data ? (
        <View style={styles.pila}>
          {aviso !== null ? (
            <View
              style={[styles.desenlace, { borderColor: TONO[aviso.tone] }]}
              testID="headcount-outcome"
            >
              <Text style={[styles.desenlaceText, { color: TONO[aviso.tone] }]}>{aviso.text}</Text>
            </View>
          ) : null}
          <HeadcountView
            busy={busy}
            enCola={enCola}
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
