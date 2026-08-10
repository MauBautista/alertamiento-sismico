// Layout raíz: SDK configurado una sola vez + bootstrap de sesión desde el
// almacén seguro + providers (TanStack Query). El tema visual sale de
// @takab/design-tokens (misma fuente que la consola, T-2.01).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";

import { useSessionStore } from "@/auth/session.store";
import { bootstrapSession } from "@/auth/useAuth";
import { CrisisWatcher } from "@/features/alert/CrisisWatcher";
import { OfflineSyncGate } from "@/offline/OfflineSyncGate";
import { useWatchedSiteId } from "@/services/mySite";
import { registerDeviceForPush } from "@/services/push";
import { configureApiClient } from "@/services/sdk";
import { palette } from "@/ui/theme";

configureApiClient();

const queryClient = new QueryClient();

export default function RootLayout() {
  const status = useSessionStore((s) => s.status);
  // [T-2.109] La fuente del inmueble del token es la MISMA que la del sitio
  // vigilado: un solo sitio por dispositivo, y observable (T-2.103).
  const watchedSiteId = useWatchedSiteId();

  useEffect(() => {
    void bootstrapSession();
  }, []);

  // [T-2.04] Registro del token push al quedar autenticado (best-effort:
  // sin permiso devuelve 'no-permission' y el onboarding 0.2 lo hace visible;
  // el upsert del backend hace la re-llamada idempotente).
  //
  // [T-2.109] ...y CON el inmueble. Esta llamada iba sin argumento —era el único
  // punto de registro de la app—, así que mandaba `site_id: null` y la nube, que
  // elige destinatarios con `WHERE site_id = <uuid>`, no encontraba nunca a
  // nadie. Además el efecto dependía SOLO de `status`: un teléfono que entraba
  // sin sitio y luego canjeaba su código de enrolamiento no se re-registraba
  // hasta reinstalar. Ahora depende también del sitio vigilado, así que
  // enrolarse o cambiar de edificio RE-APUNTA el token solo (el upsert del
  // backend es por `token`: mueve la fila, no crea una segunda), y volver a
  // entrar tras cerrar sesión lo re-registra en vez de presumir que la fila del
  // servidor sigue bien apuntada.
  useEffect(() => {
    if (status === "authenticated") {
      void registerDeviceForPush(watchedSiteId);
    }
  }, [status, watchedSiteId]);

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="light" />
      <CrisisWatcher />
      <OfflineSyncGate />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.bg },
        }}
      >
        {/* Tomas totales: sin gesto de regreso — la salida de crisis y de
            check-in la decide la fase del servidor (spec §7 · 1.2/1.4). */}
        <Stack.Screen name="crisis" options={{ gestureEnabled: false }} />
        <Stack.Screen name="checkin" options={{ gestureEnabled: false }} />
      </Stack>
    </QueryClientProvider>
  );
}
