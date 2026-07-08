import { client } from "@takab/sdk";

import { getEnv } from "../app/env";
import { useSessionStore } from "./session.store";

let configured = false;

/** Configura el cliente del SDK una sola vez: baseUrl + Bearer + 401 ⇒ sesión fuera.
 *
 * Solo el 401 cierra sesión: un 403 (p.ej. site_scope) es autorización fina del
 * backend y NO debe expulsar al operador.
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
  client.interceptors.response.use((response) => {
    if (response.status === 401) {
      useSessionStore.getState().handleUnauthorized();
    }
    return response;
  });
}
