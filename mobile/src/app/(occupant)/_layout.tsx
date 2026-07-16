// Perfil 1 · OCUPANTE — tabs del diseño (inicio · rutas · directorio · cuenta).
// Guard de grupo server-driven: si el gate no dio "occupant", fuera.
import { Feather } from "@expo/vector-icons";
import { Redirect, Tabs } from "expo-router";

import { useSessionStore } from "@/auth/session.store";
import { fontSize, palette } from "@/ui/theme";

export default function OccupantLayout() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  if (status !== "authenticated" || profile !== "occupant") {
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
        name="inicio"
        options={{
          title: "INICIO",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="home" size={size} />,
        }}
      />
      <Tabs.Screen
        name="rutas"
        options={{
          title: "RUTAS",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="map" size={size} />,
        }}
      />
      <Tabs.Screen
        name="directorio"
        options={{
          title: "DIRECTORIO",
          tabBarIcon: ({ color, size }) => <Feather color={color} name="phone" size={size} />,
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
