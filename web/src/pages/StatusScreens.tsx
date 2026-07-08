import logoTakab from "../assets/LogoTakab2.png";
import { useSessionStore } from "../auth/session.store";

export function SplashScreen() {
  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <img src={logoTakab} alt="TAKAB TECHNOLOGY" className="soc-screen__logo" />
        <p className="soc-screen__sub">INICIANDO CONSOLA SOC…</p>
      </div>
    </div>
  );
}

/** /me falló por algo ≠ 401 (red, 5xx): estado explícito con reintento. */
export function ErrorScreen() {
  const error = useSessionStore((s) => s.error);
  const refreshMe = useSessionStore((s) => s.refreshMe);
  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <h1 className="soc-screen__title">ERROR DE SESIÓN</h1>
        <p className="soc-screen__error">{error ?? "No se pudo cargar la identidad (/me)."}</p>
        <button type="button" className="soc-btn soc-btn--primary" onClick={() => void refreshMe()}>
          REINTENTAR
        </button>
      </div>
    </div>
  );
}
