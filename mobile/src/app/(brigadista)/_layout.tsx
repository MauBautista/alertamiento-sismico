// Perfil 2 · TÁCTICO (brigadista/security_guard + inspector/building_admin
// por D4d) — la barra se DERIVA de `allowed_actions`, no de una lista por rol.
// Guard de grupo server-driven: si el gate no dio "tactical", fuera.
//
// [T-6.22] Aquí vivían cinco pantallas escritas a mano, iguales para los
// cuatro roles: `inspector` veía LISTA sin `roster_read` y `building_admin`
// veía TRIAGE sin `damage_report_submit`. El reparto vive ahora en
// `auth/pestanasTacticas.ts`, y `href: null` saca la pestaña de la barra.
//
// Lo que esto NO es: un control de acceso. Que la pantalla siga alcanzable por
// otro camino no filtra nada —el servidor revalida cada acción y devolvería 403
// igual—; lo que se corrige es la PROMESA: una pestaña a la vista dice «esto lo
// puedes usar», y para dos de los cuatro roles eso era falso.
import { Feather } from "@expo/vector-icons";
import { Redirect, Tabs } from "expo-router";
import { StyleSheet, View } from "react-native";

import { PESTANAS_TACTICAS, pestanasVisibles } from "@/auth/pestanasTacticas";
import { useSessionStore } from "@/auth/session.store";
import { SiteNotices } from "@/features/notices/SiteNotices";
import { fontSize, palette } from "@/ui/theme";

export default function BrigadistaLayout() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  const actions = useSessionStore((s) => s.me?.allowed_actions);
  if (status !== "authenticated" || profile !== "tactical") {
    return <Redirect href="/" />;
  }

  // `expo-router` exige declarar TODAS las rutas del grupo: una que no aparezca
  // aquí sigue existiendo y se alcanza igual. Se declaran las siete y se apagan
  // las que no correspondan.
  const visibles = new Set(pestanasVisibles(actions).map((p) => p.name));

  // [T-6.19] La franja de avisos (simulacro · modo demostración) va en el
  // navegador, no en una pestaña: se ve igual en todas.
  return (
    <View style={styles.root}>
      <SiteNotices />
      <Tabs
        screenOptions={{
          headerShown: false,
          sceneStyle: { backgroundColor: palette.bg },
          tabBarStyle: { backgroundColor: palette.card, borderTopColor: palette.border },
          tabBarActiveTintColor: palette.cyan,
          tabBarInactiveTintColor: palette.fg3,
          // [T-6.22] Rótulo más pequeño y apretado que en la barra del ocupante,
          // y es una MEDICIÓN, no un gusto: con siete pestañas cada hueco mide
          // 64 dp en el Pixel 8 Pro (448 dp de ancho) y «DIRECTORIO» a 11 px se
          // pinta como «DIRECTO…». Bajar sólo el tracking a 0.4 NO bastó —
          // comprobado en el teléfono—, así que baja también el cuerpo al 2xs
          // que ya existía en el paquete. La barra del ocupante tiene cuatro
          // pestañas y ahí no hay nada que apretar.
          //
          // Se recorta el RÓTULO y nunca el objetivo táctil: cada pestaña sigue
          // midiendo 64 × 48.7 dp, por encima del mínimo de 48 de T-6.20.
          tabBarLabelStyle: { fontSize: fontSize.xxs, letterSpacing: 0.4 },
        }}
      >
        {PESTANAS_TACTICAS.map((p) => (
          <Tabs.Screen
            key={p.name}
            name={p.name}
            options={{
              title: p.title,
              href: visibles.has(p.name) ? undefined : null,
              tabBarIcon: ({ color, size }) => (
                <Feather color={color} name={p.icon} size={size} />
              ),
            }}
          />
        ))}
      </Tabs>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: palette.bg },
});
