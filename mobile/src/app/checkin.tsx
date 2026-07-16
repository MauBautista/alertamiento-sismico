// Ruta 1.4 · Check-in de vida — toma de pantalla tras la sacudida. El toque
// SELLA ts_device, captura GPS solo si (need_help ∧ consentimiento), ENCOLA
// (funciona sin red) e intenta drenar de inmediato. La salida de esta pantalla
// la decide la fase del servidor + el propio check-in (máquina §4.1).
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { CheckinStatusView, CheckinView } from "@/features/checkin/CheckinView";
import { captureLocation } from "@/features/checkin/location";
import { buildCheckinPayload } from "@/features/checkin/payload";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import { getGpsConsent } from "@/services/onboarding";
import { useWatchedSiteId } from "@/services/mySite";
import { fontSize, palette, space } from "@/ui/theme";

export default function Checkin() {
  const status = useSessionStore((s) => s.status);
  const siteId = useWatchedSiteId();
  const { state, data, hasOwnCheckin } = useAlertState(siteId);
  const queueItems = useQueueStore((s) => s.items);
  const [busy, setBusy] = useState<"safe" | "need_help" | null>(null);
  const [gpsConsent, setGpsConsent] = useState(false);

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

  const incident = data?.incident ?? null;
  if (state === null || incident === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={palette.warn} size="large" />
        <Text style={styles.verifying}>VERIFICANDO ESTADO CON EL SERVIDOR…</Text>
      </View>
    );
  }

  const localItem =
    queueItems.filter((i) => i.payload.incident_id === incident.incident_id).at(-1) ?? null;

  if (hasOwnCheckin) {
    return (
      <CheckinStatusView
        localState={localItem?.state ?? null}
        serverConfirmed={localItem === null || localItem.state === "synced"}
      />
    );
  }

  const submit = (checkinStatus: "safe" | "need_help") => {
    setBusy(checkinStatus);
    void (async () => {
      const tsDevice = new Date().toISOString(); // sellado AL TOQUE
      const fix =
        checkinStatus === "need_help" && gpsConsent ? await captureLocation() : null;
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
      setBusy(null);
      void drainQueue(); // intento inmediato; sin red queda pending con backoff
    })();
  };

  return (
    <CheckinView
      busy={busy}
      gpsConsent={gpsConsent}
      onCheckin={submit}
      zoneName={data?.my_zone?.name ?? null}
    />
  );
}

const styles = {
  center: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    gap: space[3],
  },
  verifying: { color: palette.fg2, fontSize: fontSize.sm, letterSpacing: 1 },
};
