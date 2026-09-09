/**
 * Apertura de las URLs presignadas de evidencia (dictamen PDF, reporte de
 * simulacro, miniSEED). Módulo aparte para poder mockearlo: jsdom no implementa
 * `window.open` de forma útil y los tests no deben abrir nada.
 *
 * EL PROBLEMA que resuelve `openPendingDownload`: la URL presignada no existe
 * hasta que el servidor responde (genera el PDF, lo sube a S3 y lo firma). Abrir
 * la pestaña DESPUÉS, en el `onSuccess`, es tarde: la activación transitoria del
 * usuario dura ~5 s en Chrome, y pasado ese plazo el navegador bloquea el popup
 * EN SILENCIO — el operador pulsa DICTAMEN PDF, la petición va bien, no aparece
 * ningún error… y no pasa nada. En una consola de emergencia eso es inaceptable.
 *
 * La pestaña se RESERVA dentro del gesto (sincrónicamente, en el onClick) y se
 * navega cuando la URL llega.
 *
 * [T-6.16] Y MIENTRAS TANTO DICE QUÉ ESTÁ PASANDO. La pestaña reservada era un
 * `about:blank` durante toda la generación —10 s medidos en el stack local con
 * el reporte de simulacro—: una pestaña en blanco que aparece sola no se
 * distingue de un fallo, y quien la ve la cierra. Ahora se escribe una espera
 * legible en cuanto se reserva, y si la petición falla esa misma pestaña pasa a
 * declarar el error en vez de cerrarse de golpe delante del operador.
 *
 * Qué hace el navegador con el PDF —mostrarlo o descargarlo— lo decide ÉL según
 * su configuración: se sirve con su Content-Type real y sin forzar
 * `Content-Disposition: attachment`.
 */

export interface PendingDownload {
  /** Navega la pestaña reservada a la URL final. */
  resolve(url: string): void;
  /** La petición falló: la pestaña reservada lo DICE, no se cierra en silencio. */
  fail(motivo: string): void;
  /** false = el navegador bloqueó incluso la reserva ⇒ hay que ofrecer un enlace. */
  readonly opened: boolean;
}

/** Página de espera/error de la pestaña reservada. Sin CSS externo: es
 *  `about:blank`, no tiene la hoja de la consola ni debe pedirla. */
function pagina(titulo: string, cuerpo: string, color: string): string {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>TAKAB · ${titulo}</title></head>
<body style="margin:0;display:flex;align-items:center;justify-content:center;
min-height:100vh;background:#0B1A2A;color:#F0F2F5;
font:400 14px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif">
<div style="max-width:34rem;padding:2rem;text-align:center">
<p style="margin:0 0 .75rem;font:700 13px/1.2 system-ui;letter-spacing:.14em;
text-transform:uppercase;color:${color}">${titulo}</p>
<p style="margin:0;color:#8A9CB1">${cuerpo}</p>
</div></body></html>`;
}

/** Escribe en la pestaña reservada. Nunca lanza: si el navegador no deja
 *  escribirla, lo que NO puede pasar es que se caiga la exportación entera. */
function escribir(tab: Window | null, html: string): void {
  if (tab === null || tab.closed) {
    return;
  }
  try {
    tab.document.open();
    tab.document.write(html);
    tab.document.close();
  } catch {
    /* pestaña ya navegada o bloqueada: la descarga sigue su curso */
  }
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
  escribir(
    tab,
    pagina(
      "Generando el documento",
      "El servidor lo está construyendo, sellando y firmando. Esta pestaña se " +
        "abrirá sola con el archivo en cuanto esté listo; no hace falta recargarla.",
      "#00BFFF",
    ),
  );
  return {
    opened: tab !== null,
    resolve(url: string) {
      if (tab !== null && !tab.closed) {
        tab.location.href = url;
      }
    },
    fail(motivo: string) {
      escribir(
        tab,
        pagina(
          "No se pudo generar el documento",
          `${motivo}. Puede cerrar esta pestaña y volver a intentarlo desde la consola.`,
          "#FFC107",
        ),
      );
    },
  };
}
