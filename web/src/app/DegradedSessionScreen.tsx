import { useCallback, useEffect, useRef, useState } from "react";

import logoTakab from "../assets/logotipo-takab-ailert.png";
import { useSessionStore } from "../auth/session.store";
import { retryDelayMs } from "./degradedRetry";

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
 *
 * ── [T-2.134] Y SE RECUPERA SOLA ─────────────────────────────────────────────
 *
 * El botón exige que alguien esté mirando. Esto ocurre DURANTE un incidente, que
 * es justo cuando nadie mira una pantalla que ya declaró que no sirve: la consola
 * podía quedarse degradada media hora con la base de vuelta.
 *
 * El reintento automático vive AQUÍ y no en el store, y es deliberado: su ciclo
 * de vida es EXACTAMENTE el de esta pantalla. Mientras está montada hay
 * degradado (`App` la monta sólo en ese estado), y al dejar de estarlo el
 * `useEffect` cancela su temporizador solo — no queda un bucle huérfano
 * preguntando por `/me` desde un store que ya nadie mira, ni hace falta
 * acordarse de apagarlo en `logout`, en `handleUnauthorized` ni en los tests.
 *
 * Las dos cosas que este reintento NO puede hacer, que son la ficha entera:
 *
 *  1. **No puede martillear.** El retardo es exponencial con techo y con jitter
 *     (`degradedRetry.ts`, con su porqué). Una base que arranca es a la que
 *     menos se le puede añadir carga, y el fallo es SIMULTÁNEO en todas las
 *     consolas de todos los tenants: sin jitter reintentarían al mismo compás.
 *  2. **No puede desmontar esta pantalla.** `refreshMe` desde `degraded` no pasa
 *     por `booting` (T-2.123), así que `App` no cambia de rama y el operador no
 *     ve un parpadeo por intento. Fijado con la identidad del nodo en
 *     `degraded-session.test.tsx`.
 */
export default function DegradedSessionScreen() {
  const error = useSessionStore((s) => s.error);
  const refreshMe = useSessionStore((s) => s.refreshMe);
  const logout = useSessionStore((s) => s.logout);
  const [retrying, setRetrying] = useState(false);
  /** Intentos ya fallados en ESTE episodio degradado: mueve el backoff. */
  const [intentos, setIntentos] = useState(0);
  /** Evita que el temporizador y el clic humano se solapen en dos peticiones. */
  const enCurso = useRef(false);

  const reintentar = useCallback(async () => {
    if (enCurso.current) {
      return;
    }
    enCurso.current = true;
    setRetrying(true);
    try {
      await refreshMe();
    } finally {
      enCurso.current = false;
      setRetrying(false);
      // Sube SIEMPRE, venga del temporizador o del botón: un operador
      // impaciente no puede reiniciar el backoff a fuerza de clics, y cada
      // intento reprograma el siguiente desde el nuevo escalón. Si el reintento
      // funcionó, este `set` cae en un componente ya desmontado por `App` y
      // React lo ignora (no hay bucle que cancelar).
      setIntentos((n) => n + 1);
    }
  }, [refreshMe]);

  useEffect(() => {
    const timer = setTimeout(() => void reintentar(), retryDelayMs(intentos));
    return () => clearTimeout(timer);
  }, [intentos, reintentar]);

  return (
    <div className="soc-screen">
      <div className="soc-screen__panel" role="alert" aria-live="assertive">
        <img src={logoTakab} alt="TAKAB Ailert" className="soc-screen__logo" />
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

        <p className="soc-screen__sub">
          La consola <strong>reintenta sola</strong>, espaciando los intentos para no cargar el
          servidor mientras se recupera. En cuanto responda, entra sin que nadie toque nada.
        </p>

        {error ? <p className="soc-screen__error">{error}</p> : null}

        <button
          type="button"
          className="soc-btn soc-btn--primary"
          disabled={retrying}
          onClick={() => void reintentar()}
        >
          {retrying ? "REINTENTANDO…" : "REINTENTAR AHORA"}
        </button>
        <button type="button" className="soc-btn soc-btn--secondary" onClick={() => void logout()}>
          CERRAR SESIÓN
        </button>
      </div>
    </div>
  );
}
