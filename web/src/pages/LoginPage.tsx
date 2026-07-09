import { type FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router";

import { getEnv } from "../app/env";
import { landingPath } from "../app/landing";
import logoTakab from "../assets/LogoTakab2.png";
import { useSessionStore } from "../auth/session.store";
import { cognitoConfigured } from "../auth/userManager";
import MobileOnlyScreen from "./MobileOnlyScreen";
import { ErrorScreen, SplashScreen } from "./StatusScreens";

/** Solo para el panel dev local: la matriz de autorización REAL vive en el
 * backend (/me · matrix.py); esta lista únicamente llena el <select>. */
const DEV_ROLES = [
  "takab_superadmin",
  "takab_support",
  "tenant_admin",
  "soc_operator",
  "gov_operator",
  "inspector",
  "building_admin",
  "brigadista",
  "security_guard",
  "occupant",
];

/** Tenant de la flota sembrada por `db/seeds/dev_fleet.sql` (21 sitios con `geom`).
 *
 * Tiene que ser ESTE y no otro: entrando con un tenant sin sitios, `/console` cae en
 * el estado `empty` de `StateFrame` ("SIN SITIOS VISIBLES EN EL TENANT") y el mapa no
 * se pinta. El mapa está bien; lo que faltaba eran los datos. El test importa esta
 * constante para que no vuelva a divergir del seed. */
export const DEV_TENANT_DEFAULT = "d0000000-0000-0000-0000-000000000001";

function DevLoginPanel() {
  const loginDev = useSessionStore((s) => s.loginDev);
  const status = useSessionStore((s) => s.status);
  const [role, setRole] = useState("soc_operator");
  const [tenantId, setTenantId] = useState(DEV_TENANT_DEFAULT);
  const [error, setError] = useState<string | null>(null);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    void loginDev({ role, tenant_id: tenantId }).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }

  return (
    <form className="soc-dev-panel" onSubmit={onSubmit}>
      <p className="soc-screen__sub">LOGIN DEV (POST /dev/token · solo local)</p>
      <label>
        ROL
        <select className="soc-select" value={role} onChange={(e) => setRole(e.target.value)}>
          {DEV_ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <label>
        TENANT ID
        <input
          className="soc-input"
          value={tenantId}
          onChange={(e) => setTenantId(e.target.value)}
        />
      </label>
      <button
        type="submit"
        className="soc-btn soc-btn--secondary"
        disabled={status === "authenticating"}
      >
        ENTRAR COMO ROL
      </button>
      {error ? <p className="soc-screen__error">{error}</p> : null}
    </form>
  );
}

interface LoginLocationState {
  returnTo?: string;
}

export default function LoginPage() {
  const status = useSessionStore((s) => s.status);
  const me = useSessionStore((s) => s.me);
  const loginCognito = useSessionStore((s) => s.loginCognito);
  const location = useLocation();
  const [cognitoError, setCognitoError] = useState<string | null>(null);

  const returnTo = (location.state as LoginLocationState | null)?.returnTo;

  if (status === "booting") {
    return <SplashScreen />;
  }
  if (status === "error") {
    return <ErrorScreen />;
  }
  if (status === "authenticated" && me) {
    const landing = landingPath(me);
    if (!landing) {
      return <MobileOnlyScreen />;
    }
    return <Navigate to={returnTo ?? landing} replace />;
  }

  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <img src={logoTakab} alt="TAKAB TECHNOLOGY" className="soc-screen__logo" />
        <h1 className="soc-screen__title">CONSOLA SOC</h1>
        {cognitoConfigured() ? (
          <button
            type="button"
            className="soc-btn soc-btn--primary"
            disabled={status === "authenticating"}
            onClick={() => {
              setCognitoError(null);
              void loginCognito(returnTo).catch((err: unknown) => {
                setCognitoError(err instanceof Error ? err.message : String(err));
              });
            }}
          >
            ENTRAR CON COGNITO
          </button>
        ) : (
          <p className="soc-screen__sub">Cognito no configurado (VITE_COGNITO_*).</p>
        )}
        {cognitoError ? <p className="soc-screen__error">{cognitoError}</p> : null}
        {getEnv().devTokenEnabled ? <DevLoginPanel /> : null}
      </div>
    </div>
  );
}
