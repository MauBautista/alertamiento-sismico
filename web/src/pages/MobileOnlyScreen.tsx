import { useSessionStore } from "../auth/session.store";

/** Rol autenticado pero sin superficie web (allowed_routes = []): brigadista,
 * security_guard y occupant operan desde la app móvil (T-1.31, diferida). */
export default function MobileOnlyScreen() {
  const me = useSessionStore((s) => s.me);
  const logout = useSessionStore((s) => s.logout);
  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <h1 className="soc-screen__title">SIN SUPERFICIE WEB</h1>
        <p className="soc-screen__sub">
          El rol <span className="soc-mono">{me?.role}</span> opera desde la app móvil. Esta consola
          es solo para roles con acceso SOC.
        </p>
        <button type="button" className="soc-btn soc-btn--secondary" onClick={() => void logout()}>
          CERRAR SESIÓN
        </button>
      </div>
    </div>
  );
}
