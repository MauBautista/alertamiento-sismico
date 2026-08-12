import { Navigate, Outlet, useLocation } from "react-router";

import { useSessionStore } from "../auth/session.store";
import MobileOnlyScreen from "../pages/MobileOnlyScreen";
import { ErrorScreen, SplashScreen } from "../pages/StatusScreens";
import DegradedSessionScreen from "./DegradedSessionScreen";

/** Muro de sesión de todas las rutas protegidas. Estados explícitos siempre
 * (regla de oro #7): splash, degradado con retry, redirect a login con returnTo. */
export default function RequireSession() {
  const status = useSessionStore((s) => s.status);
  const me = useSessionStore((s) => s.me);
  const location = useLocation();

  if (status === "booting" || status === "authenticating") {
    return <SplashScreen />;
  }
  // [T-2.123] SEGUNDA CAPA. `App` ni siquiera monta el router en degradado, así
  // que en la app real esto no se alcanza; existe para que el día que alguien
  // vuelva a montarlo —o monte el árbol de rutas en un test— el muro siga en
  // pie. Se deniega IN-PLACE y no se rebota al login: mandar al login diría "no
  // estás dentro" cuando la verdad es "no se sabe quién eres", y de paso
  // quemaría el `returnTo` de una sesión que sigue siendo válida.
  if (status === "degraded") {
    return <DegradedSessionScreen />;
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
