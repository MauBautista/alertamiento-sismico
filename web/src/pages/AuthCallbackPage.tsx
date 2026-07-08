import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router";

import { landingPath } from "../app/landing";
import { useSessionStore } from "../auth/session.store";
import { SplashScreen } from "./StatusScreens";

/** Aterrizaje del code+PKCE de Cognito. El intercambio es one-shot: el store lo
 * latchea contra el doble montaje de StrictMode. */
export default function AuthCallbackPage() {
  const completeCognitoCallback = useSessionStore((s) => s.completeCognitoCallback);
  const status = useSessionStore((s) => s.status);
  const me = useSessionStore((s) => s.me);
  const [result, setResult] = useState<{ returnTo?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    completeCognitoCallback()
      .then(setResult)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      });
  }, [completeCognitoCallback]);

  if (error) {
    return (
      <div className="soc-screen">
        <div className="soc-screen__panel">
          <h1 className="soc-screen__title">ERROR DE LOGIN</h1>
          <p className="soc-screen__error">{error}</p>
          <Link className="soc-btn soc-btn--secondary" to="/">
            VOLVER AL INICIO
          </Link>
        </div>
      </div>
    );
  }

  if (result && status === "authenticated" && me) {
    return <Navigate to={result.returnTo ?? landingPath(me) ?? "/"} replace />;
  }

  return <SplashScreen />;
}
