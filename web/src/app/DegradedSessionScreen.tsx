import { useState } from "react";

import logoTakab from "../assets/LogoTakab2.png";
import { useSessionStore } from "../auth/session.store";

/**
 * [T-2.123] Arranque en DEGRADADO cuando `GET /me` no contesta.
 *
 * ── LA DECISIÓN ──────────────────────────────────────────────────────────────
 * La consola ARRANCA, DECLARA que no puede establecer el alcance del operador y
 * NO muestra ni un dato de tenant.
 *
 * ── POR QUÉ, que es lo que impide relajarla en cualquiera de las dos direcciones
 *
 * `T-2.114` ató `GET /me` a la base a propósito: el inmueble del ocupante no
 * viaja en el claim de Cognito y tiene que salir de `user_zone_assignments`. Eso
 * es correcto y no se toca. Lo que cambió es el MODO DE FALLO del cliente, y
 * frente a él sólo había tres conductas posibles:
 *
 *  1. NO ARRANCAR — inaceptable. Una caída de base coincide a menudo con un
 *     incidente, y eso deja al SOC sin pantalla justo cuando hace falta.
 *  2. ARRANCAR Y MOSTRAR DATOS — inaceptable (regla de oro 5). Sin `/me` no hay
 *     `site_scope` ni `allowed_routes`: un `soc_operator` sin alcance resuelto no
 *     puede ver NADA, y adivinarlo —del claim, de un caché, de un default— es la
 *     brecha multi-tenant, no un atajo.
 *  3. ARRANCAR Y DECLARAR — la única que respeta las dos reglas, y la elegida.
 *     El operador ve que el sistema está vivo y que NO SE PUEDE ESTABLECER SU
 *     IDENTIDAD. Eso es información accionable y verdadera (regla de oro 7);
 *     una pantalla con datos de procedencia incierta no lo sería.
 *
 * De ahí que esta pantalla sustituya al router ENTERO en `App.tsx` en vez de
 * vivir dentro de una ruta: si ninguna ruta se monta, ninguna pantalla puede
 * pedir datos, y el degradado no puede degenerar en una puerta trasera. El muro
 * de `RequireSession` repite la denegación como segunda capa, por si algún día
 * alguien vuelve a montar el router en este estado.
 *
 * NO se copia aquí lo que hace la app móvil. Su `bootstrapSession` conserva la
 * sesión con `me = null` y resuelve el inmueble desde el caché sellado por `sub`
 * —correcto allí: es la regla de oro 2, el ocupante necesita su pantalla de
 * crisis SIN red, y el dato cacheado es UNO y suyo—. La consola no tiene ese
 * caso: su "alcance" es autorización sobre el tenant entero, y con la base caída
 * tampoco habría a quién pedirle los datos que ese alcance abriría. Cachearlo
 * sólo compraría el riesgo de pintar el tenant equivocado.
 */
export default function DegradedSessionScreen() {
  const error = useSessionStore((s) => s.error);
  const refreshMe = useSessionStore((s) => s.refreshMe);
  const logout = useSessionStore((s) => s.logout);
  const [retrying, setRetrying] = useState(false);

  function onRetry() {
    setRetrying(true);
    void refreshMe().finally(() => setRetrying(false));
  }

  return (
    <div className="soc-screen">
      <div className="soc-screen__panel" role="alert" aria-live="assertive">
        <img src={logoTakab} alt="TAKAB TECHNOLOGY" className="soc-screen__logo" />
        <h1 className="soc-screen__title">CONSOLA EN MODO DEGRADADO</h1>

        <p className="soc-screen__sub">
          La consola está en línea, pero{" "}
          <strong>no puede establecer el alcance de su operador</strong>: el servidor de identidad
          no respondió.
        </p>
        <p className="soc-screen__sub">
          Sin ese dato no se sabe a qué cliente ni a qué inmuebles tiene acceso su cuenta, así que
          esta pantalla <strong>no muestra ningún dato</strong>. No es que no haya información: es
          que no se puede acreditar quién puede verla.
        </p>
        <p className="soc-screen__sub">
          El alertamiento no depende de esta pantalla: cada gabinete sigue detectando y accionando
          sirena y actuadores sin nube.
        </p>

        {error ? <p className="soc-screen__error">{error}</p> : null}

        <button
          type="button"
          className="soc-btn soc-btn--primary"
          disabled={retrying}
          onClick={onRetry}
        >
          {retrying ? "REINTENTANDO…" : "REINTENTAR"}
        </button>
        <button type="button" className="soc-btn soc-btn--secondary" onClick={() => void logout()}>
          CERRAR SESIÓN
        </button>
      </div>
    </div>
  );
}
