// Puerta de entrada: enruta por estado de sesión + grupo server-driven
// (gateFor sobre /me). Default-deny: sin sesión → login; gate negado → denied.
import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { palette } from "@/ui/theme";

export default function Index() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);

  if (status === "booting") {
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
  if (status === "anonymous") {
    return <Redirect href="/login" />;
  }
  if (status === "denied") {
    return <Redirect href="/denied" />;
  }
  return (
    <Redirect href={profile === "occupant" ? "/(occupant)/inicio" : "/(brigadista)/panel"} />
  );
}
