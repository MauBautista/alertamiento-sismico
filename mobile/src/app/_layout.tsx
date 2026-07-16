// Layout raíz: SDK configurado una sola vez + bootstrap de sesión desde el
// almacén seguro + providers (TanStack Query). El tema visual sale de
// @takab/design-tokens (misma fuente que la consola, T-2.01).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";

import { bootstrapSession } from "@/auth/useAuth";
import { configureApiClient } from "@/services/sdk";
import { palette } from "@/ui/theme";

configureApiClient();

const queryClient = new QueryClient();

export default function RootLayout() {
  useEffect(() => {
    void bootstrapSession();
  }, []);

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
