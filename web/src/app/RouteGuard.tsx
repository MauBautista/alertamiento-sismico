import type { ReactNode } from "react";

import { useSessionStore } from "../auth/session.store";
import NoAccessPage from "../pages/NoAccessPage";

/** Guard por ruta contra `allowed_routes` del server (cero matriz local).
 * Deniega IN-PLACE: la URL no cambia, el deep-link bloqueado muestra el porqué.
 * `routeKey` es la clave de matrix.py (la paramétrica /building/:siteId ⇒ "/building"). */
export default function RouteGuard({
  routeKey,
  children,
}: {
  routeKey: string;
  children: ReactNode;
}) {
  const me = useSessionStore((s) => s.me);
  if (!me?.allowed_routes.includes(routeKey)) {
    return <NoAccessPage />;
  }
  return <>{children}</>;
}
