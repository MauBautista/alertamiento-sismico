import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";

import { routes } from "./app/routes";
import { configureApiClient } from "./auth/apiClient";
import { useSessionStore } from "./auth/session.store";

configureApiClient();

const router = createBrowserRouter(routes);

export default function App() {
  const bootstrap = useSessionStore((s) => s.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return <RouterProvider router={router} />;
}
