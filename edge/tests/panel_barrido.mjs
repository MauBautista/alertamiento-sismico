/**
 * [T-7.05] Barrido de solapes del panel del gabinete, con un navegador de
 * verdad. Existe porque las cifras de los censos de T-7.04 y T-7.05 («75
 * parejas → 0», «304 px²», «48 px² × 4 carriles») se escribieron desde un
 * scratchpad que no quedó en el árbol: eran afirmaciones que nadie podía
 * reproducir, ni el integrador ni CI. Esto las vuelve a medir.
 *
 *   node edge/tests/panel_barrido.mjs                 # las 14 escenas × 3 modos
 *   node edge/tests/panel_barrido.mjs alerta muro     # una sola combinación
 *
 * NO corre dentro de `make test`: el gate de `edge` es pytest + ruff y no tiene
 * navegador; Playwright vive en `web/node_modules`. Las guardas que SÍ corren en
 * cada `make test` están en `test_local_api_panel.py` y leen la HOJA, que es
 * mecánica y no píxeles. Este guion es la medida; aquéllas son el candado.
 *
 * Qué mide, exactamente:
 *  · Solape de TINTA entre textos. No compara cajas de elemento (dos cajas que
 *    se tocan sin que sus glifos se toquen no es un defecto, y contarlo llena el
 *    informe de ruido): compara los rectángulos de `Range.getClientRects()`,
 *    que es la caja del texto renderizado. Descuenta parejas antepasado↔hijo.
 *  · Desbordamiento horizontal del documento (`scrollWidth > viewport`).
 *  · Alto del documento, que en MURO tiene que caber en 1080 SIN scroll.
 *  · Texto RECORTADO ENTERO por un antepasado con `overflow:hidden`. No es un
 *    solape, es peor: el rótulo está en el DOM, el lector de pantalla lo canta
 *    y el operador no lo ve.
 * CUÁNDO mide: cuando la ESCENA ESTÁ COMPLETA, no a los N milisegundos. La
 * versión anterior esperaba 2 000 ms fijos y `alerta` no empuja sus marcadores
 * hasta los ~3 s de escena, así que la línea base que dejó escrita estaba
 * medida en un instante en el que parte de lo que hay que mirar todavía no
 * existía — y los picos del carril aún eran los de antes del sismo, que son más
 * cortos y solapan menos. Ahora se espera a `S.status` + los carriles en el DOM
 * y, en las escenas que emiten marcadores (derivadas del panel, no listadas
 * aquí), a que los marcadores EXISTAN; después, dos `requestAnimationFrame`.
 *
 * Lo que NO puede ver, y hay que decirlo: la traza del canvas no está en el
 * DOM. Que el lienzo no pinte dentro de la banda de rótulos —ni la onda, ni la
 * reja, ni los marcadores SASMEX/TIER— lo sostienen `--lane-band` +
 * `laneBand()` y lo comprueba, orden de dibujo a orden de dibujo,
 * `test_en_CAMPO_ninguna_orden_de_dibujo_entra_en_la_banda_de_rotulos` en
 * `test_local_api_panel.py`.
 *
 * ESTADO MEDIDO el 2026-09-12 (Chromium 149 headless), 42 combinaciones, con la
 * versión de T-7.05 y con la ANTERIOR (`TAKAB_PANEL` apuntando a una copia de
 * `git show HEAD:…/index.html`) para poder atribuir cada hallazgo. La línea base
 * se volvió a levantar ENTERA después de cambiar la espera. Esto NO es un gate
 * —sale con código 1 si encuentra algo— sino la línea base de la próxima
 * corrida:
 *
 *                                     ANTES          AHORA
 *   muro 1920×1080 · 14/14 escenas    1 solape    →  0 solapes · 0 recortados
 *                                                    doc = 1080 EXACTO (P-1 cerrado)
 *   campo 412×915  · 14/14           16 solapes   →  4 parejas en 12 escenas,
 *                                                    5 en `arranque_frio`,
 *                                                    0 en `sin_senal`
 *                                                    · 0 recortados
 *   consola 1440×900 · 14/14         15–73 recortados → los mismos, sin cambio
 *
 * Totales de la corrida completa: 42 combinaciones · 53 parejas · 787 recortados.
 *
 * ESAS 53 NO SON CERO, y el criterio de verificación de T-7.05 pide «0 parejas
 * en MURO y CAMPO». En MURO se cumple; en CAMPO no, y lo que queda es UN solo
 * residuo repetido carril a carril (`.lane .peak` ∩ `.lane .scale`), ANTERIOR a
 * esta ficha: contra `git show HEAD:…/index.html` eran 16 por escena. O se
 * cierra —y es una decisión de producto, no de maquetación— o el criterio se
 * corrige diciendo eso.
 *
 * Los dos residuos están fichados con su reproducción y su medida en
 * `test_local_api_panel.py`, cada uno como un test que AVISA en cada corrida
 * (`FichaAbierta`) y que cae el día que su causa se arregle:
 * `test_FICHADO_en_CAMPO_el_pico_del_carril_se_pisa_con_la_escala` y
 * `test_FICHADO_en_CONSOLA_de_900px_el_tierline_se_aplasta_y_no_se_ve_nada`. El
 * segundo es el más grave y no lo vio nadie hasta este barrido: en un portátil
 * de 900 px de alto `#tierline` se aplasta a 2 px y el ESTADO DEL INMUEBLE —con
 * el estado de la sirena y de los cinco relés— no se pinta.
 */
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const aqui = path.dirname(fileURLToPath(import.meta.url));
const raiz = path.resolve(aqui, '..', '..');
const require = createRequire(path.join(raiz, 'web', 'package.json'));
const { chromium } = require('playwright');

/* `TAKAB_PANEL` apunta a otra copia del panel: es lo que permite medir una
   versión ANTERIOR (`git show HEAD:…/index.html > …/local_api/_previo.html`) con
   la misma vara y saber si un hallazgo lo trajo el cambio o ya estaba. Tiene que
   vivir en `local_api/` para que las `@font-face` relativas resuelvan. */
const HTML = process.env.TAKAB_PANEL || path.join(aqui, '..', 'takab_edge', 'local_api', 'index.html');
const PANEL = 'file://' + HTML;

/* Las escenas se leen del propio panel: una lista a mano aquí se quedaría
   atrás en cuanto alguien añada la decimoquinta. */
const { readFileSync } = await import('node:fs');
const html = readFileSync(HTML, 'utf8');
const bloque = html.slice(html.indexOf('const SCENES = {'));
const ESCENAS = [...new Set([...bloque.slice(0, bloque.indexOf('\n};')).matchAll(/^ {2}([a-z_]+):/gm)].map((m) => m[1]))];

/* Y QUÉ ESCENAS llegan a emitir marcadores (SASMEX / transición de tier) también
   lo dice el panel, no una lista aquí: `demoFillWave()` los empuja dentro de una
   rama `if (DEMO === '<escena>'){ … S.markers.push(…) }`. Importa porque los
   marcadores no aparecen hasta ~3 s de escena y el barrido esperaba 2 000 ms:
   la línea base anterior estaba medida en un instante en el que la escena
   todavía no estaba completa. */
const CON_MARCADORES = new Set(
  [...html.matchAll(/DEMO === '([a-z_]+)'\)\s*\{[\s\S]{0,600}?S\.markers\.push/g)].map((m) => m[1]),
);
if (!CON_MARCADORES.size) {
  throw new Error('ninguna escena emite marcadores: el panel cambió de forma y la espera de abajo ya no espera a nada');
}

/* CAMPO va a 412×915, que es el Pixel 8 Pro con el que se midió U-10 —no a
   800×1280, donde `body.mode-campo #grid{max-width:560px}` acota la columna y
   el carril sale 148 px más ancho de lo que sale en el teléfono—. CONSOLA va a
   1440×900, el portátil, no a 1080: el alto es justamente lo que aplasta la
   línea del tier. */
const MODOS = { muro: [1920, 1080], consola: [1440, 900], campo: [412, 915] };

const [soloEscena, soloModo] = process.argv.slice(2);
const navegador = await chromium.launch();
let parejas = 0;
let recortados = 0;
let combinaciones = 0;
const informe = [];

for (const modo of Object.keys(MODOS)) {
  if (soloModo && modo !== soloModo) continue;
  const [w, h] = MODOS[modo];
  for (const escena of ESCENAS) {
    if (soloEscena && escena !== soloEscena) continue;
    const ctx = await navegador.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const pagina = await ctx.newPage();
    await pagina.goto(`${PANEL}?demo=${escena}&mode=${modo}`);
    await pagina.waitForFunction(() => document.fonts.status === 'loaded');
    /* Se espera a que la ESCENA ESTÉ COMPLETA, no a un plazo. Dos condiciones,
       las dos observables:
        · el panel pintó un estado y sus carriles (`S.status` + `.lane`), y
        · si la escena emite marcadores, que los marcadores EXISTAN.
       El plazo fijo de 2 000 ms que había aquí medía `alerta` antes de que
       aparecieran sus marcadores —los empuja a los ~3 s de escena—, así que la
       línea base salía de un estado en el que lo que hay que mirar todavía no
       estaba pintado. `S` es una `const` de ámbito global del script clásico del
       panel: se resuelve desde `evaluate` sin colgarla de `window`. */
    await pagina.waitForFunction(
      (esperaMarcadores) =>
        typeof S !== 'undefined' &&
        S.status !== null &&
        document.querySelectorAll('.lane').length > 0 &&
        (!esperaMarcadores || S.markers.length > 0),
      CON_MARCADORES.has(escena),
      { timeout: 30000 },
    );
    /* Dos fotogramas para que lo último que cambió llegue al lienzo y al DOM.
       Dos, no «un rato»: `requestAnimationFrame` encadenado es determinista. */
    await pagina.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const r = await pagina.evaluate(() => {
      const visible = (el) => {
        const s = getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
        /* Un texto SOLO-LECTOR (`.sr-only`: 1×1 px recortado) no se pinta: su
           caja vive debajo de lo que sí se pinta y `Range.getClientRects()` la
           devuelve entera, así que sin esta línea el barrido delata como solape
           el texto que existe precisamente para no verse. */
        const caja = el.getBoundingClientRect();
        if (caja.width <= 1 || caja.height <= 1) return false;
        if (s.clip !== 'auto' && s.clip !== '') return false;
        return true;
      };
      /* Hojas de texto: elementos sin hijos de elemento y con texto no vacío. */
      const hojas = [...document.querySelectorAll('body *')].filter(
        (el) => el.children.length === 0 && (el.textContent || '').trim() !== '' && visible(el),
      );
      /* `Range.getClientRects()` devuelve la caja del texto AUNQUE un antepasado
         con `overflow:hidden` lo esté recortando: sin recortarla a mano, todo
         rótulo que se sale de su tarjeta se delata como solape con lo que hay
         debajo, y eso NO es lo que se ve en pantalla. Se recorta contra cada
         antepasado que recorte, y lo que queda en cero se apunta aparte —un
         texto recortado ENTERO es su propio defecto: está en el DOM, el lector
         de pantalla lo lee, y el operador no lo ve. */
      const recortes = (el) => {
        const cajas = [];
        for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
          const s = getComputedStyle(a);
          if (s.overflow !== 'visible' || s.overflowX !== 'visible' || s.overflowY !== 'visible') cajas.push(a.getBoundingClientRect());
        }
        return cajas;
      };
      const tinta = (el) => {
        const r = document.createRange();
        r.selectNodeContents(el);
        let rects = [...r.getClientRects()].filter((x) => x.width > 0 && x.height > 0);
        for (const c of recortes(el)) {
          rects = rects
            .map((x) => {
              const left = Math.max(x.left, c.left), right = Math.min(x.right, c.right);
              const top = Math.max(x.top, c.top), bottom = Math.min(x.bottom, c.bottom);
              return { left, right, top, bottom, width: right - left, height: bottom - top };
            })
            .filter((x) => x.width > 0.5 && x.height > 0.5);
        }
        return rects;
      };
      const sello = (el) => {
        const partes = [el.tagName.toLowerCase()];
        if (el.id) partes.push('#' + el.id);
        if (el.className && typeof el.className === 'string') partes.push('.' + el.className.trim().split(/\s+/).join('.'));
        return partes.join('') + ' «' + (el.textContent || '').trim().slice(0, 28) + '»';
      };
      const todas = hojas.map((el) => ({ el, rects: tinta(el) }));
      const cajas = todas.filter((x) => x.rects.length);
      /* Texto que existe y NO se ve: recortado entero por un antepasado. */
      const recortados = todas.filter((x) => !x.rects.length).map((x) => sello(x.el));
      const choques = [];
      for (let i = 0; i < cajas.length; i++) {
        for (let j = i + 1; j < cajas.length; j++) {
          const a = cajas[i], b = cajas[j];
          if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
          let area = 0;
          for (const ra of a.rects) {
            for (const rb of b.rects) {
              const dx = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
              const dy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
              if (dx > 0.5 && dy > 0.5) area += dx * dy;
            }
          }
          if (area > 0) choques.push({ a: sello(a.el), b: sello(b.el), px2: +area.toFixed(1) });
        }
      }
      return {
        choques: choques.sort((x, y) => y.px2 - x.px2),
        recortados,
        textos: cajas.length,
        doc: { w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight },
        vp: { w: innerWidth, h: innerHeight },
      };
    });
    await ctx.close();
    combinaciones += 1;
    parejas += r.choques.length;
    recortados += r.recortados.length;
    const desbordaX = r.doc.w > r.vp.w;
    const muroNoCabe = modo === 'muro' && r.doc.h > r.vp.h;
    const linea = `${modo.padEnd(8)} ${escena.padEnd(26)} textos=${String(r.textos).padStart(3)} parejas=${r.choques.length}` +
      ` recortados=${r.recortados.length} doc=${r.doc.w}×${r.doc.h}${desbordaX ? ' ¡DESBORDA EN X!' : ''}${muroNoCabe ? ' ¡MURO NO CABE EN 1080!' : ''}`;
    console.log(linea);
    for (const c of r.choques.slice(0, 6)) console.log(`         ${c.px2} px²  ${c.a}  ∩  ${c.b}`);
    for (const c of r.recortados.slice(0, 6)) console.log(`         RECORTADO ENTERO  ${c}`);
    if (r.choques.length || r.recortados.length || desbordaX || muroNoCabe) informe.push(linea);
  }
}

console.log(`\n${combinaciones} combinaciones · ${parejas} parejas de texto solapadas · ${recortados} textos recortados enteros`);
console.log(informe.length ? 'CON HALLAZGOS:\n' + informe.join('\n') : '== SIN SOLAPES NI DESBORDES ==');
await navegador.close();
process.exit(informe.length ? 1 : 0);
