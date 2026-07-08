import { ShieldOff } from "lucide-react";
import { useLocation } from "react-router";

import { useSessionStore } from "../auth/session.store";

/** Se renderiza IN-PLACE: la URL del deep-link denegado NO cambia, para que el
 * operador vea exactamente qué ruta le fue bloqueada y con qué rol. */
export default function NoAccessPage() {
  const me = useSessionStore((s) => s.me);
  const location = useLocation();
  return (
    <section className="soc-placeholder">
      <ShieldOff size={32} aria-hidden="true" />
      <h1>SIN ACCESO</h1>
      <p className="soc-screen__sub">
        El rol <span className="soc-mono">{me?.role}</span> no tiene acceso a{" "}
        <span className="soc-mono">{location.pathname}</span>.
      </p>
    </section>
  );
}
