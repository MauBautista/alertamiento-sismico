// Ruta 1.4 · Check-in de vida — toma de pantalla tras la sacudida. El toque
// SELLA ts_device, captura GPS solo si (need_help ∧ consentimiento), ENCOLA
// (funciona sin red) e intenta drenar de inmediato. La salida de esta pantalla
// la decide la fase del servidor + el propio check-in (máquina §4.1).
//
// [T-2.111] Dos defectos del mismo género, en la pantalla con la que una
// persona dice que está viva:
//   · sin sitio vigilado la consulta de `mobile-state` no se habilita, así que
//     el `ActivityIndicator` de «VERIFICANDO ESTADO CON EL SERVIDOR…» no se
//     resolvía JAMÁS. Ahora los cuatro estados los declara `StateFrame`.
//   · `submit()` no capturaba: encolar escribe en la base local cifrada y
//     puede fallar (disco lleno, base bloqueada). Al fallar, `setBusy(null)` no
//     corría —el botón se quedaba con el spinner— y la persona creía haber
//     avisado sin que existiera nada guardado en ninguna parte. Misma costura
//     que `triage.tsx` (T-2.108): try/catch/finally y desenlace pintado.
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { CheckinView } from "@/features/checkin/CheckinView";
import { captureLocation } from "@/features/checkin/location";
import { buildCheckinPayload } from "@/features/checkin/payload";
import { ReentryBlockedView } from "@/features/reentry/ReentryBlockedView";
import { reentryTimeline } from "@/features/reentry/timeline";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import { getGpsConsent } from "@/services/onboarding";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { fontSize, palette, radius, space } from "@/ui/theme";

const SIN_SITIO =
  "Este teléfono no está vinculado a ningún edificio, así que no hay check-in que enviar. Vincúlese con el código de su inmueble.";

const SIN_INCIDENTE = "El servidor no reporta ninguna sacudida por la que haya que reportarse.";

/** Encolar es una escritura LOCAL: si falla, el check-in no existe en NINGUNA
 *  parte. Callarlo sería lo peor que puede hacer esta pantalla. */
const NO_SE_GUARDO =
  "No se pudo guardar su check-in en este teléfono. NO se ha enviado nada: vuelva a pulsar el botón.";

export default function Checkin() {
  const status = useSessionStore((s) => s.status);
  const siteId = useWatchedSiteId();
  const { state, data, hasOwnCheckin, loading, error, stale, dataUpdatedAt, refetch } =
    useAlertState(siteId);
  const queueItems = useQueueStore((s) => s.items);
  const [busy, setBusy] = useState<"safe" | "need_help" | null>(null);
  const [gpsConsent, setGpsConsent] = useState(false);
  // El desenlace vive en estado del componente, no en una variable local del
  // manejador: `CheckinView` se reconstruye en cada frame y un mensaje guardado
  // fuera del estado se perdería en el primer re-render.
  const [fallo, setFallo] = useState<string | null>(null);

  // Consentimiento LFPDPPP desde el almacén seguro (null = NO consentido).
  useEffect(() => {
    let alive = true;
    getGpsConsent().then((granted) => {
      if (alive) {
        setGpsConsent(granted === true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  if (state === "alert_active") {
    return <Redirect href="/crisis" />;
  }
  if (state === "idle" || state === "reentry_approved") {
    return <Redirect href="/" />;
  }

  const sinSitio = siteId === null;
  const incident = data?.incident ?? null;
  const localItem =
    incident === null
      ? null
      : (queueItems.filter((i) => i.payload.incident_id === incident.incident_id).at(-1) ?? null);

  const submit = (checkinStatus: "safe" | "need_help") => {
    if (incident === null) {
      return;
    }
    setBusy(checkinStatus);
    setFallo(null);
    void (async () => {
      try {
        const tsDevice = new Date().toISOString(); // sellado AL TOQUE
        const fix = checkinStatus === "need_help" && gpsConsent ? await captureLocation() : null;
        await useQueueStore.getState().enqueueCheckin(
          buildCheckinPayload({
            incidentId: incident.incident_id,
            status: checkinStatus,
            zoneId: data?.my_zone?.zone_id ?? null,
            gpsConsent,
            fix,
            tsDevice,
          }),
        );
        void drainQueue(); // intento inmediato; sin red queda pending con backoff
      } catch {
        setFallo(NO_SE_GUARDO);
      } finally {
        // En `finally` a propósito: pase lo que pase, el botón se libera. Un
        // botón de vida bloqueado en "enviando" es peor que uno que falla.
        setBusy(null);
      }
    })();
  };

  return (
    <StateFrame
      empty={sinSitio || (data !== null && incident === null)}
      emptyText={sinSitio ? SIN_SITIO : SIN_INCIDENTE}
      error={data === null ? error : null}
      loading={loading}
      onRetry={refetch}
      staleSinceMs={stale && data !== null ? dataUpdatedAt : null}
    >
      {incident !== null && hasOwnCheckin ? (
        // 1.5 · Bloqueo de reingreso: timeline derivada de los datos del
        // servidor; se libera SOLO cuando la fase cambia a reentry_approved
        // (redirect arriba).
        <ReentryBlockedView
          assemblyPoint={data?.assembly_point ?? null}
          complianceLabels={data?.compliance_labels ?? {}}
          timeline={reentryTimeline({
            openedAt: incident.opened_at,
            hasOwnCheckin,
            checkinSynced: localItem === null || localItem.state === "synced",
            dictamenStatus: data?.reentry.dictamen_status ?? null,
            dictamenSigned: data?.reentry.dictamen_signed ?? false,
          })}
        />
      ) : null}

      {incident !== null && !hasOwnCheckin ? (
        <View style={styles.pila}>
          {fallo !== null ? (
            <View style={styles.fallo} testID="checkin-outcome">
              <Text style={styles.falloText}>{fallo}</Text>
            </View>
          ) : null}
          <CheckinView
            busy={busy}
            gpsConsent={gpsConsent}
            onCheckin={submit}
            zoneName={data?.my_zone?.name ?? null}
          />
        </View>
      ) : null}
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  pila: { flex: 1, backgroundColor: palette.bg },
  fallo: {
    backgroundColor: palette.card,
    borderColor: palette.crit,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
    margin: space[4],
    marginBottom: 0,
  },
  falloText: { color: palette.crit, fontSize: fontSize.sm, lineHeight: 20 },
});
