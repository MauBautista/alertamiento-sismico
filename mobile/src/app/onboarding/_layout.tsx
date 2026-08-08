// Stack del onboarding CON GUARDA DE SESIÓN [T-2.79.b].
//
// Antes esto era un `Stack` pelado. `app/index.tsx:34` era el único punto de la
// app que reaccionaba a quedarse anónimo, y durante el onboarding esa ruta no
// está montada: cualquier `signOut()` disparado aquí —hoy un 401, mañana otro—
// dejaba a la persona EN LA PANTALLA, sin token y en silencio. Nadie la llevaba
// al login. Para un occupant eso es una trampa cerrada: canjear el código de
// sitio exige sesión viva, así que nunca completa el enrolamiento, nunca se
// marca el onboarding como hecho y nunca llega al check-in de vida ni al botón
// de pánico (reglas de oro 1 y 2).
//
// La guarda vive en el LAYOUT a propósito: expo-router lo monta alrededor de
// TODA ruta de esta carpeta, así que una pantalla nueva queda cubierta sin que
// nadie tenga que acordarse de nada. Eso es lo que verifica `guard.test.tsx`,
// que deriva la lista de pantallas del propio directorio.
//
// `booting` NO expulsa: sesión desconocida no es sesión muerta, y redirigir
// mientras el bootstrap lee el almacén seguro echaría en cada arranque en frío
// a gente con sesión válida.
//
// Esto NO sustituye a la exención de `services/sdk.ts`
// (`RUTAS_QUE_NO_CIERRAN_SESION`): son dos defensas distintas. Aquélla impide
// que una vía de CUMPLIMIENTO expulse a la flota; ésta garantiza que, cuando la
// sesión sí muere, la persona acabe en el login y no en un limbo.
import { Redirect, Stack } from "expo-router";
import type { ReactNode } from "react";

import { useSessionStore } from "@/auth/session.store";
import { palette } from "@/ui/theme";

/** Guarda de sesión del stack de onboarding (exportada para poder probarla
 * pantalla por pantalla, no solo sobre el layout entero). */
export function OnboardingSessionGuard({ children }: { children: ReactNode }) {
  const status = useSessionStore((s) => s.status);

  if (status === "anonymous") {
    return <Redirect href="/login" />;
  }
  if (status === "denied") {
    return <Redirect href="/denied" />;
  }
  return <>{children}</>;
}

export default function OnboardingLayout() {
  return (
    <OnboardingSessionGuard>
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.bg },
        }}
      />
    </OnboardingSessionGuard>
  );
}
