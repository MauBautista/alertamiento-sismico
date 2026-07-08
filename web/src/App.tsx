import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";

import { routes } from "./app/routes";
import { configureApiClient } from "./auth/apiClient";
import { useSessionStore } from "./auth/session.store";
import { createQueryClient } from "./lib/queryClient";

configureApiClient();

const router = createBrowserRouter(routes);
const queryClient = createQueryClient();

export default function App() {
  const bootstrap = useSessionStore((s) => s.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
