import { client } from "@takab/sdk";

import { getEnv } from "../app/env";
import { useSessionStore } from "./session.store";
import { isSessionExpiredResponse } from "./sessionLimit";

let configured = false;

/** El token con el que SALIÓ la petición (no el vigente ahora, que puede ser otro). */
function bearerOf(request: Request): string | null {
  const header = request.headers.get("Authorization");
  return header?.startsWith("Bearer ") ? header.slice("Bearer ".length) : null;
}

/** Configura el cliente del SDK una sola vez: baseUrl + Bearer + 401 ⇒ sesión fuera.
 *
 * Solo el 401 cierra sesión: un 403 (p.ej. site_scope) es autorización fina del
 * backend y NO debe expulsar al operador.
 *
 * [T-8.03 · D-38] Y no todo 401 es lo mismo:
 *   · el del TOPE de sesión (`sesion_expirada`: 24 h / 30 días desde el login)
 *     cierra con causa `max_age` SIN intentar renovar — Cognito seguiría
 *     refrescando y la API rechazaría en bucle;
 *   · cualquier otro (el token de 60 min venció) intenta UNA renovación antes
 *     de cerrar. La petición que falló NO se reintenta aquí: una consulta vuelve
 *     sola en su siguiente ciclo, y reenviar a ciegas un POST —un comando de
 *     actuador, un acuse— no es algo que un interceptor deba decidir.
 */
export function configureApiClient(): void {
  if (configured) {
    return;
  }
  configured = true;
  client.setConfig({ baseUrl: getEnv().apiBaseUrl });
  client.interceptors.request.use((request) => {
    const { idToken } = useSessionStore.getState();
    if (idToken) {
      request.headers.set("Authorization", `Bearer ${idToken}`);
    }
    return request;
  });
  client.interceptors.response.use(async (response, request) => {
    if (response.status !== 401) {
      return response;
    }
    const store = useSessionStore.getState();
    if (await isSessionExpiredResponse(response)) {
      store.handleUnauthorized("max_age");
    } else {
      void store.recoverFromUnauthorized(bearerOf(request));
    }
    return response;
  });
}
