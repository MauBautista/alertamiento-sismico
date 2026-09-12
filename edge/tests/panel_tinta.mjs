/**
 * [T-7.05] De dónde sale `_INK` en `test_local_api_panel.py`.
 *
 * `line-height` fija la caja de LÍNEA; los glifos se pintan en el ÁREA DE
 * CONTENIDO de la fuente, que es más alta. Las guardas de solape del panel
 * necesitan ese factor para saber cuánta tinta se sale de la caja por cada
 * lado, y un número tecleado a mano no es verificable: éste es el guion que lo
 * mide, contra las fuentes EMPAQUETADAS del panel (`local_api/fonts/`) y con un
 * navegador de verdad.
 *
 *   node edge/tests/panel_tinta.mjs
 *
 * NO corre dentro de `make test`: el gate de `edge` es pytest + ruff y no tiene
 * navegador; Playwright vive en `web/node_modules`. Lo que obliga a volver a
 * correrlo es
 * `test_el_factor_de_tinta_esta_atado_a_las_fuentes_que_se_midieron`, que ata
 * `_INK` a la huella de los dos ficheros de fuente: si alguien cambia la pila
 * tipográfica del panel, esa guarda cae y manda aquí.
 *
 * Medido el 2026-09-12 (Chromium 149 headless, x86_64). El máximo sobre todas
 * las caras y cuerpos que el panel usa fue 1.32 — y el factor NO es constante
 * con el cuerpo, porque Chromium redondea ascendente y descendente a píxeles
 * enteros por tamaño: Geist 700 a 72 px da 1.2917 y JetBrains Mono 400 a 100 px
 * da 1.32. `_INK` se queda con el MÁXIMO a propósito: una cota alta exige más
 * separación de la necesaria, que es el lado seguro de la guarda.
 */
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const aqui = path.dirname(fileURLToPath(import.meta.url));
const raiz = path.resolve(aqui, '..', '..');
const require = createRequire(path.join(raiz, 'web', 'package.json'));
const { chromium } = require('playwright');

const PANEL = 'file://' + path.join(aqui, '..', 'takab_edge', 'local_api', 'index.html');

/* Las caras y los cuerpos que el panel declara de verdad, más 100 px como
   referencia legible. Si una regla nueva estrena un cuerpo, va aquí. */
const CASOS = [
  ['Geist', 700, 72], // body.mode-muro #tier-label
  ['Geist', 700, 28], // #tier-label
  ['Geist', 600, 11], // .seclabel
  ['Geist', 400, 100],
  ['JetBrains Mono', 700, 13], // .lane .ch
  ['JetBrains Mono', 400, 10], // .lane .note
  ['JetBrains Mono', 400, 24], // body.mode-muro #tier-sub
  ['JetBrains Mono', 400, 100],
];

const navegador = await chromium.launch();
const ctx = await navegador.newContext({ viewport: { width: 1920, height: 1080 } });
const pagina = await ctx.newPage();
/* Se carga el PANEL, no una página en blanco: así las @font-face que se miden
   son exactamente las que el gabinete sirve. */
await pagina.goto(`${PANEL}?demo=reposo&mode=muro`);
await pagina.waitForFunction(() => document.fonts.status === 'loaded');

const medidas = await pagina.evaluate((casos) => {
  const cargadas = [...document.fonts].map((f) => `${f.family} ${f.status}`);
  const filas = casos.map(([fam, peso, px]) => {
    const s = document.createElement('span');
    s.style.cssText = `position:absolute;top:0;left:0;font:${peso} ${px}px/1 '${fam}',monospace`;
    s.textContent = 'ESTADO gjpqy';
    document.body.appendChild(s);
    const r = document.createRange();
    r.selectNodeContents(s);
    const rects = [...r.getClientRects()];
    const tinta = Math.max(...rects.map((x) => x.bottom)) - Math.min(...rects.map((x) => x.top));
    s.remove();
    return { fam, peso, px, tinta: +tinta.toFixed(2), factor: +(tinta / px).toFixed(4) };
  });
  return { cargadas, filas };
}, CASOS);

if (!medidas.cargadas.some((f) => f.startsWith('Geist loaded'))) {
  throw new Error('Geist no cargó: la medida sería de la fuente del sistema. ' + medidas.cargadas.join(' · '));
}
if (!medidas.cargadas.some((f) => f.startsWith('JetBrains Mono loaded'))) {
  throw new Error('JetBrains Mono no cargó: ' + medidas.cargadas.join(' · '));
}
console.table(medidas.filas);
console.log('_INK (máximo, el que va en test_local_api_panel.py) =', Math.max(...medidas.filas.map((f) => f.factor)));

/* [T-7.05 · P-2] …y de dónde salen `_NOTA_ANCHO_PX` y `_NOTA_AVANCE_PX`.
   La guarda de la nota del carril compara CARACTERES contra un ancho, y los dos
   números tenían que medirse en el teléfono de verdad y en CAMPO, que es el
   único modo donde la nota vive dentro de una banda reservada. Se miden los dos
   anchos que importan: el del Pixel 8 Pro (412 px, el aparato con el que se
   midió U-10 y el que fija el límite) y el del teléfono angosto de 360 px. */
for (const [w, h] of [
  [412, 915],
  [360, 800],
]) {
  const ctxN = await navegador.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const pag = await ctxN.newPage();
  await pag.goto(`${PANEL}?demo=reposo&mode=campo`);
  await pag.waitForFunction(() => document.fonts.status === 'loaded');
  await pag.waitForFunction(() => document.querySelectorAll('.lane .note').length > 0);
  const n = await pag.evaluate(() => {
    const nota = document.querySelector('.lane .note');
    const cs = getComputedStyle(nota);
    const s = document.createElement('span');
    s.style.cssText = `position:absolute;white-space:pre;font:${cs.fontWeight} ${cs.fontSize}/1 ${cs.fontFamily};letter-spacing:${cs.letterSpacing}`;
    s.textContent = 'M'.repeat(100);
    document.body.appendChild(s);
    const avance = s.getBoundingClientRect().width / 100;
    s.remove();
    const ancho = nota.getBoundingClientRect().width;
    return { ancho: +ancho.toFixed(2), avance: +avance.toFixed(4), caben: Math.floor(ancho / avance) };
  });
  console.log(`nota del carril · CAMPO ${w}×${h}: ancho útil ${n.ancho} px · avance ${n.avance} px/carácter · CABEN ${n.caben}`);
  await ctxN.close();
}

await navegador.close();
