// Cliente único del SDK — espejo de web/src/auth/apiClient.ts:
// baseUrl + Bearer del store + SOLO el 401 cierra sesión (un 403 es
// autorización fina del backend y no expulsa), y ni siquiera todos: los del
// aviso de privacidad no expulsan (ver `RUTAS_QUE_NO_CIERRAN_SESION`). La app
// móvil no duplica clientes HTTP fuera de @takab/sdk (spec §13.5).
import { client } from "@takab/sdk";

import { API_BASE_URL } from "../auth/config";
import { useSessionStore } from "../auth/session.store";

/** Rutas cuyo 401 NO cierra la sesión.
 *
 * El aviso de privacidad es CUMPLIMIENTO, no sesión. Si su 401 pudiera cerrar
 * la sesión, un defecto de permisos en ese endpoint expulsaría a toda la flota
 * durante el onboarding — y en silencio: `app/index.tsx:34` es el único sitio
 * que reacciona a quedarse anónimo, y el stack de `app/onboarding/` no lo tiene
 * montado, así que nadie va al login. Un occupant se quedaría además atascado
 * en enrolamiento (canjear el código exige sesión viva) y no llegaría nunca al
 * check-in de vida ni al botón de pánico (reglas de oro 1 y 2).
 *
 * Esto no resucita sesiones: un token de verdad caducado se declara muerto en
 * la siguiente ruta de la que la app SÍ depende (`/me`, estado del sitio,
 * check-in). Solo se le quita a la vía de cumplimiento el poder de expulsar.
 */
const RUTAS_QUE_NO_CIERRAN_SESION = ["/privacy/consent", "/privacy/notice"];

function cierraSesion(url: string): boolean {
  return !RUTAS_QUE_NO_CIERRAN_SESION.some((ruta) => url.includes(ruta));
}

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
  client.interceptors.response.use((response, request) => {
    if (response.status === 401 && cierraSesion(request.url)) {
      useSessionStore.getState().signOut();
    }
    return response;
  });
}
