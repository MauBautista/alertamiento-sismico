// Perfil 2 · TÁCTICO (brigadista/security_guard + inspector/building_admin
// por D4d) — tabs del diseño (panel · triage · lista · cuenta).
// Guard de grupo server-driven: si el gate no dio "tactical", fuera.
import { Feather } from "@expo/vector-icons";
import { Redirect, Tabs } from "expo-router";

import { useSessionStore } from "@/auth/session.store";
import { fontSize, palette } from "@/ui/theme";

export default function BrigadistaLayout() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  if (status !== "authenticated" || profile !== "tactical") {
    return <Redirect href="/" />;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: palette.bg },
        tabBarStyle: { backgroundColor: palette.card, borderTopColor: palette.border },
        tabBarActiveTintColor: palette.cyan,
        tabBarInactiveTintColor: palette.fg3,
        tabBarLabelStyle: { fontSize: fontSize.xs, letterSpacing: 1 },
      }}
    >
      <Tabs.Screen
        name="panel"
        options={{
          title: "PANEL",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="activity" size={size} />,
        }}
      />
      <Tabs.Screen
        name="triage"
        options={{
          title: "TRIAGE",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="clipboard" size={size} />,
        }}
      />
      <Tabs.Screen
        name="lista"
        options={{
          title: "LISTA",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="users" size={size} />,
        }}
      />
      <Tabs.Screen
        name="cuenta"
        options={{
          title: "CUENTA",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="user" size={size} />,
        }}
      />
    </Tabs>
  );
}
