/**
 * Apertura de las URLs presignadas de evidencia (dictamen PDF, miniSEED).
 * Módulo aparte para poder mockearlo: jsdom no implementa `window.open` de forma
 * útil y los tests no deben abrir nada.
 *
 * EL PROBLEMA que resuelve `openPendingDownload`: la URL presignada no existe
 * hasta que el servidor responde (genera el PDF, lo sube a S3 y lo firma). Abrir
 * la pestaña DESPUÉS, en el `onSuccess`, es tarde: la activación transitoria del
 * usuario dura ~5 s en Chrome, y pasado ese plazo el navegador bloquea el popup
 * EN SILENCIO — el operador pulsa DICTAMEN PDF, la petición va bien, no aparece
 * ningún error… y no pasa nada. En una consola de emergencia eso es inaceptable.
 *
 * La pestaña se RESERVA dentro del gesto (sincrónicamente, en el onClick) y se
 * navega cuando la URL llega. Si la petición falla, se cierra.
 *
 * Qué hace el navegador con el PDF —mostrarlo o descargarlo— lo decide ÉL según
 * su configuración: se sirve con su Content-Type real y sin forzar
 * `Content-Disposition: attachment`.
 */

export interface PendingDownload {
  /** Navega la pestaña reservada a la URL final. */
  resolve(url: string): void;
  /** Cierra la pestaña reservada (la petición falló: no dejar un about:blank). */
  cancel(): void;
  /** false = el navegador bloqueó incluso la reserva ⇒ hay que ofrecer un enlace. */
  readonly opened: boolean;
}

export function openPendingDownload(): PendingDownload {
  // Sin `noopener`: con esa flag `window.open` devuelve null y nos quedaríamos
  // sin la referencia que hace falta para navegar la pestaña luego. El acceso
  // del hijo a nuestra ventana se corta a mano justo después, que es la
  // mitigación equivalente.
  const tab = window.open("about:blank", "_blank");
  if (tab !== null) {
    tab.opener = null;
  }
  return {
    opened: tab !== null,
    resolve(url: string) {
      if (tab !== null && !tab.closed) {
        tab.location.href = url;
      }
    },
    cancel() {
      if (tab !== null && !tab.closed) {
        tab.close();
      }
    },
  };
}
