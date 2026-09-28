import { type FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router";

import Button from "../components/Button";
import { getEnv } from "../app/env";
import { landingPath } from "../app/landing";
import logoTakab from "../assets/imagotipo-takab-ailert.png";
import { useSessionStore } from "../auth/session.store";
import { MENSAJE_ROL_RETIRADO, maxAgeLabel } from "../auth/sessionLimit";
import { ETIQUETA_ROL } from "../auth/rolesHistoricos";
import { cognitoConfigured } from "../auth/userManager";
import MobileOnlyScreen from "./MobileOnlyScreen";
import { SplashScreen } from "./StatusScreens";

/** Solo para el panel dev local: la matriz de autorización REAL vive en el
 * backend (/me · matrix.py); esta lista únicamente llena el <select>.
 * [T-9.20 · D-42] Los 7 canónicos, de la tabla de rótulos (no otra lista a mano).
 * `/dev/token` todavía acepta los ids retirados para ensayar la ventana de alias,
 * pero el panel no los ofrece. */
const DEV_ROLES = Object.keys(ETIQUETA_ROL);

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
  const [role, setRole] = useState("tenant_admin");
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
      <Button variant="secondary" type="submit" disabled={status === "authenticating"}>
        ENTRAR COMO ROL
      </Button>
      {error ? <p className="soc-screen__error">{error}</p> : null}
    </form>
  );
}

interface LoginLocationState {
  returnTo?: string;
}

/**
 * [T-8.03 · D-38] El aviso del TOPE. La duración sale de lo que la API declaró
 * para el rol (`session_max_age_s`); si no llegó a decirlo, el aviso es el
 * genérico — «24 H» escrito a mano sería inventárselo para quien tiene 30 días.
 */
function avisoDeTope(maxAgeS: number | null): string {
  const duracion = maxAgeLabel(maxAgeS);
  const titular = duracion === null ? "SU SESIÓN TERMINÓ" : `SU SESIÓN DE ${duracion} TERMINÓ`;
  return (
    `${titular} · alcanzó la duración máxima para su rol, contada desde que entró. ` +
    "Por seguridad hay que volver a entrar con su contraseña y su código."
  );
}

export default function LoginPage() {
  const status = useSessionStore((s) => s.status);
  const me = useSessionStore((s) => s.me);
  const endedReason = useSessionStore((s) => s.endedReason);
  const sessionMaxAgeS = useSessionStore((s) => s.sessionMaxAgeS);
  const loginCognito = useSessionStore((s) => s.loginCognito);
  const location = useLocation();
  const [cognitoError, setCognitoError] = useState<string | null>(null);

  const returnTo = (location.state as LoginLocationState | null)?.returnTo;

  if (status === "booting") {
    return <SplashScreen />;
  }
  // [T-2.134] Había aquí una rama `status === "error"` ⇒ `ErrorScreen`, muerta
  // desde `T-2.123`: con `/me` sin contestar el estado es `degraded`, y en
  // degradado `App` ni siquiera monta el router, así que esta página no llega a
  // renderizarse. Se retiró con el estado.
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
        <img src={logoTakab} alt="TAKAB Ailert" className="soc-screen__logo" />
        <h1 className="soc-screen__title">CONSOLA SOC</h1>
        {/* [T-6.07] POR QUÉ está aquí, cuando no vino por su pie. La sesión se
            caía en silencio —`signinSilent` falla, `handleUnauthorized` limpia—
            y el operador reaparecía en un login idéntico al de un arranque en
            frío. Sin esta línea vuelve a entrar creyendo que se equivocó de
            pestaña, y no se entera de que el turno lleva un rato sin consola.

            Dice lo que se sabe y nada más: que el servidor dejó de reconocer la
            sesión. Un 401 puede ser expiración o revocación y desde aquí no se
            distinguen; llamarlo «inactividad» sería inventarse la causa. */}
        {endedReason === "expired" ? (
          <p className="soc-screen__aviso" role="status" data-testid="login-sesion-cerrada">
            SU SESIÓN SE CERRÓ · el servidor dejó de reconocerla (expiró o fue revocada). Vuelva a
            entrar.
          </p>
        ) : null}
        {/* [T-8.03] El tope (D-38) es OTRA causa y se dice distinto: aquí el
            operador no hizo nada mal, no hubo revocación, y renovar no sirve —
            la sesión cumplió la duración de su rol desde el login. */}
        {endedReason === "max_age" ? (
          <p className="soc-screen__aviso" role="status" data-testid="login-sesion-tope">
            {avisoDeTope(sessionMaxAgeS)}
          </p>
        ) : null}
        {/* [F2 · D-42] El rol retirado tampoco es una expiración: volver a entrar
            no lo arregla hasta que un administrador le asigne un rol vigente. */}
        {endedReason === "rol_retirado" ? (
          <p className="soc-screen__aviso" role="status" data-testid="login-rol-retirado">
            {MENSAJE_ROL_RETIRADO}
          </p>
        ) : null}
        {cognitoConfigured() ? (
          <Button
            variant="primary"
            disabled={status === "authenticating"}
            onClick={() => {
              setCognitoError(null);
              void loginCognito(returnTo).catch((err: unknown) => {
                setCognitoError(err instanceof Error ? err.message : String(err));
              });
            }}
          >
            ENTRAR CON COGNITO
          </Button>
        ) : (
          /* [T-6.07] Esto lo lee quien está de turno, no quien desplegó. Decía
             «Cognito no configurado (VITE_COGNITO_*)»: nombra un proveedor de
             identidad y dos variables de build a alguien que solo quiere entrar
             a la consola, y no dice ni qué hacer ni si el edificio sigue
             protegido —que es la pregunta de verdad. El detalle técnico no se
             pierde: viaja en el `title`, donde lo encuentra quien lo necesita. */
          <p
            className="soc-screen__sub"
            title="Faltan VITE_COGNITO_AUTHORITY y/o VITE_COGNITO_CLIENT_ID en el build de esta consola."
          >
            Esta consola no tiene identidad configurada: desde aquí no se puede entrar. Avise a
            quien la desplegó. El alertamiento de los edificios NO depende de esta pantalla.
          </p>
        )}
        {cognitoError ? <p className="soc-screen__error">{cognitoError}</p> : null}
        {getEnv().devTokenEnabled ? <DevLoginPanel /> : null}
      </div>
    </div>
  );
}
