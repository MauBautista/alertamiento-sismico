// Ruta de crisis (1.2/1.3) — TOMA TOTAL: sin gesto de regreso ni descarte
// mientras el SERVIDOR reporte alerta activa (spec §7). La salida la decide
// la fase del backend, jamás un botón local.
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { CrisisView } from "@/features/alert/CrisisView";
import { elapsedSeconds } from "@/features/alert/machine";
import { sourceLabel } from "@/features/alert/source";
import { startAlertLoop, stopAlertLoop } from "@/features/alert/sound";
import { useAlertState } from "@/features/alert/useAlertState";
import { useWatchedSiteId } from "@/services/mySite";
import { fontSize, palette, space } from "@/ui/theme";

export default function Crisis() {
  const status = useSessionStore((s) => s.status);
  const siteId = useWatchedSiteId();
  const { state, data } = useAlertState(siteId);
  const [nowMs, setNowMs] = useState(() => Date.now());

  // T+ ascendente: tick de 1 s mientras la pantalla vive.
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1_000);
    return () => clearInterval(timer);
  }, []);

  // Sonido en loop SOLO durante alert_active (la push CRISIS ya sonó al llegar).
  useEffect(() => {
    if (state === "alert_active") {
      void startAlertLoop();
      return () => stopAlertLoop();
    }
    return undefined;
  }, [state]);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  // La fase del SERVIDOR dejó de ser alerta: la sacudida concluida pasa al
  // check-in de vida (1.4); lo demás regresa al inicio.
  if (state === "checkin_pending" || state === "reentry_blocked") {
    return <Redirect href="/checkin" />;
  }
  if (state !== null && state !== "alert_active") {
    return <Redirect href="/" />;
  }
  if (!data?.incident) {
    // La push despertó a la app; la VERDAD es mobile-state — se declara la
    // verificación en curso, no se finge una alerta.
    return (
      <View style={{ flex: 1, backgroundColor: palette.bg, alignItems: "center", justifyContent: "center", gap: space[3] }}>
        <ActivityIndicator color={palette.crit} size="large" />
        <Text style={{ color: palette.fg2, fontSize: fontSize.sm, letterSpacing: 1 }}>
          VERIFICANDO ALERTA CON EL SERVIDOR…
        </Text>
      </View>
    );
  }

  return (
    <CrisisView
      elapsedS={elapsedSeconds(data.incident.opened_at, nowMs)}
      policy={(data.my_zone?.evac_policy as "evacuate" | "shelter" | null) ?? null}
      source={sourceLabel(data.incident)}
      zoneName={data.my_zone?.name ?? null}
    />
  );
}
