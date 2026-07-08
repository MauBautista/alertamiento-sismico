import { Navigate, Outlet, useLocation } from "react-router";

import { useSessionStore } from "../auth/session.store";
import MobileOnlyScreen from "../pages/MobileOnlyScreen";
import { ErrorScreen, SplashScreen } from "../pages/StatusScreens";

/** Muro de sesión de todas las rutas protegidas. Estados explícitos siempre
 * (regla de oro #7): splash, error con retry, redirect a login con returnTo. */
export default function RequireSession() {
  const status = useSessionStore((s) => s.status);
  const me = useSessionStore((s) => s.me);
  const location = useLocation();

  if (status === "booting" || status === "authenticating") {
    return <SplashScreen />;
  }
  if (status === "error") {
    return <ErrorScreen />;
  }
  if (status !== "authenticated" || !me) {
    return <Navigate to="/" replace state={{ returnTo: location.pathname + location.search }} />;
  }
  if (me.allowed_routes.length === 0) {
    return <MobileOnlyScreen />;
  }
  return <Outlet />;
}
