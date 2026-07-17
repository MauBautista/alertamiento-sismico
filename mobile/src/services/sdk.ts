// Cliente único del SDK — espejo de web/src/auth/apiClient.ts:
// baseUrl + Bearer del store + SOLO el 401 cierra sesión (un 403 es
// autorización fina del backend y no expulsa). La app móvil no duplica
// clientes HTTP fuera de @takab/sdk (spec §13.5).
import { client } from "@takab/sdk";

import { API_BASE_URL } from "../auth/config";
import { useSessionStore } from "../auth/session.store";

let configured = false;

export function configureApiClient(): void {
  if (configured) {
    return;
  }
  configured = true;
  client.setConfig({ baseUrl: API_BASE_URL });
  client.interceptors.request.use((request) => {
    const { idToken } = useSessionStore.getState();
    if (idToken) {
      request.headers.set("Authorization", `Bearer ${idToken}`);
    }
    return request;
  });
  client.interceptors.response.use((response) => {
    if (response.status === 401) {
      useSessionStore.getState().signOut();
    }
    return response;
  });
}
