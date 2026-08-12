import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";

import DegradedSessionScreen from "./app/DegradedSessionScreen";
import { routes } from "./app/routes";
import { configureApiClient } from "./auth/apiClient";
import { useSessionStore } from "./auth/session.store";
import { createQueryClient } from "./lib/queryClient";

configureApiClient();

const router = createBrowserRouter(routes);
const queryClient = createQueryClient();

export default function App() {
  const bootstrap = useSessionStore((s) => s.bootstrap);
  const status = useSessionStore((s) => s.status);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // [T-2.123] Sin `/me` no hay alcance, y sin alcance el router NO SE MONTA: no
  // es que las rutas denieguen, es que no llegan a existir, así que ninguna
  // pantalla puede pedir un dato de tenant. La consola arranca igual y declara
  // qué no sabe — la decisión y su porqué, en `DegradedSessionScreen.tsx`.
  if (status === "degraded") {
    return <DegradedSessionScreen />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
