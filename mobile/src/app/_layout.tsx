// Layout raíz: SDK configurado una sola vez + bootstrap de sesión desde el
// almacén seguro + providers (TanStack Query). El tema visual sale de
// @takab/design-tokens (misma fuente que la consola, T-2.01).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";

import { useSessionStore } from "@/auth/session.store";
import { bootstrapSession } from "@/auth/useAuth";
import { registerDeviceForPush } from "@/services/push";
import { configureApiClient } from "@/services/sdk";
import { palette } from "@/ui/theme";

configureApiClient();

const queryClient = new QueryClient();

export default function RootLayout() {
  const status = useSessionStore((s) => s.status);

  useEffect(() => {
    void bootstrapSession();
  }, []);

  // [T-2.04] Registro del token push al quedar autenticado (best-effort:
  // sin permiso devuelve 'no-permission' y el onboarding 0.2 lo hace visible;
  // el upsert del backend hace la re-llamada idempotente).
  useEffect(() => {
    if (status === "authenticated") {
      void registerDeviceForPush();
    }
  }, [status]);

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.bg },
        }}
      />
    </QueryClientProvider>
  );
}
