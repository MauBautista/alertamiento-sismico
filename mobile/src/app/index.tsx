// Puerta de entrada: enruta por estado de sesión + grupo server-driven
// (gateFor sobre /me). Default-deny: sin sesión → login; gate negado → denied.
// [T-2.04] Autenticado SIN onboarding local → flujo 0.2-0.4 (permisos de
// alerta imposibles de ignorar, privacidad, enrolamiento del occupant).
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { isOnboardingDone } from "@/services/onboarding";
import { palette } from "@/ui/theme";

export default function Index() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  const [onboarded, setOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    let alive = true;
    void (async () => {
      const done = await isOnboardingDone();
      if (alive) {
        setOnboarded(done);
      }
    })();
    return () => {
      alive = false;
    };
  }, [status]);

  if (status === "anonymous") {
    return <Redirect href="/login" />;
  }
  if (status === "denied") {
    return <Redirect href="/denied" />;
  }
  if (status === "booting" || (status === "authenticated" && onboarded === null)) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: palette.bg,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <ActivityIndicator color={palette.cyan} size="large" />
      </View>
    );
  }
  if (!onboarded) {
    return <Redirect href="/onboarding/permisos" />;
  }
  return (
    <Redirect href={profile === "occupant" ? "/(occupant)/inicio" : "/(brigadista)/panel"} />
  );
}
