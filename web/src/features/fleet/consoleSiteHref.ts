// [T-7.05 · C-4] CÓMO SE ENTRA A MONITOREO CON UNA ESTACIÓN YA ABIERTA.
//
// El mecanismo lo estrenó `T-6.14`: `/console?sitio=<site_id>` hace que la consola
// nazca con ESE sitio seleccionado y su ficha lateral abierta (`ConsolePage.tsx`,
// estado INICIAL, no un efecto). Lo que faltaba era que el alta de hardware lo
// enlazara, para que la estación recién dada de alta no haya que buscarla a mano
// entre N pins con el cliente delante.
//
// El nombre del parámetro estaba TECLEADO A MANO en cada emisor. Un nombre repetido
// no es un contrato: si alguien lo renombra en la consola, cada emisor sigue verde y
// el enlace aterriza en `/console` pelado — el defecto original, en silencio. Aquí
// vive el único sitio de `features/fleet` donde ese nombre se escribe, y
// `consoleSiteHref.test.ts` lo ata al extremo que lo LEE.
//
// Vive en `features/fleet/` porque es lo que `T-7.05` podía tocar. El otro emisor del
// producto —`features/triage/TriageDetail.tsx:231`, el «volver» del dictamen— sigue
// con el literal escrito a mano; el censo de este módulo lo vigila igual (mide todo
// `src/`), pero cuando se toque esa pantalla este módulo debería subir a `src/lib/`
// para que también lo CONSTRUYA desde aquí.

/** El parámetro con el que `/console` entra con un sitio seleccionado (T-6.14). */
export const CONSOLE_SITE_PARAM = "sitio";

/** Enlace a Monitoreo en Vivo con la ficha de `siteId` abierta. */
export function consoleSiteHref(siteId: string): string {
  const q = new URLSearchParams({ [CONSOLE_SITE_PARAM]: siteId });
  return `/console?${q.toString()}`;
}
