#!/usr/bin/env node
// Regenera los shots PNG del design canvas móvil de forma reproducible.
//
//   node tools/regen-shots.mjs            → regenera los 21 PNG y corre el check
//   node tools/regen-shots.mjs --check    → solo verifica (cero escrituras)
//
// Requisitos: web/node_modules con Playwright (el chromium del e2e de la consola).
// Red: el código (react/babel/lucide) se sirve SIEMPRE desde vendor/ — cero red;
// las fuentes de Google se intentan por red y, si no hay, aplica el fallback del
// font stack (se reporta como aviso, no como fallo).

import http from 'node:http';
import { promises as fs } from 'node:fs';
import { createReadStream, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const TOOLS = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(TOOLS, '..');
const REPO = path.resolve(APP, '..', '..', '..');
const SHOTS = path.join(APP, 'shots');
const CHECK_ONLY = process.argv.includes('--check');

// artboard id (index.html) → archivo en shots/ → componente global del harness
const SHOT_MAP = [
  ['a-login', 'a1-login.png', 'AccesoLogin'],
  ['a-permisos', 'a2-permisos.png', 'AccesoPermisos'],
  ['a-privacidad', 'a3-privacidad.png', 'AccesoPrivacidad'],
  ['a-enrolamiento', 'a4-enrolamiento.png', 'AccesoEnrolamiento'],
  ['o-reposo', 'o1-reposo.png', 'OcupanteReposo'],
  ['o-simulacro', 'o1b-simulacro.png', 'OcupanteReposoSimulacro'],
  ['o-evac', 'o2-crisis-evacue.png', 'OcupanteCrisisEvac'],
  ['o-replie', 'o3-crisis-repliegue.png', 'OcupanteCrisisReplie'],
  ['o-checkin', 'o4-checkin.png', 'OcupanteCheckin'],
  ['o-bloqueo', 'o5-bloqueo.png', 'OcupanteBloqueo'],
  ['o-rutas', 'o6-rutas.png', 'OcupanteRutas'],
  ['o-directorio', 'o7-directorio.png', 'OcupanteDirectorio'],
  ['o-cuenta', 'o8-cuenta.png', 'OcupanteCuenta'],
  ['o-panico', 'o9-panico.png', 'OcupantePanico'],
  ['b-panel', 'b1-panel.png', 'BrigadistaPanel'],
  ['b-control', 'b2-control-remoto.png', 'BrigadistaControlRemoto'],
  ['b-camara', 'b3-camara.png', 'BrigadistaCamara'],
  ['b-form', 'b4-formulario.png', 'BrigadistaFormulario'],
  ['b-sync', 'b5-sync.png', 'BrigadistaSync'],
  ['b-headcount', 'b6-headcount.png', 'BrigadistaHeadcount'],
  ['b-dictamen', 'b7-dictamen.png', 'BrigadistaDictamen'],
];
const EXPECTED_ARTBOARDS = SHOT_MAP.length; // 21 — index.html debe declararlos todos

// Los <script> de index.html apuntan a unpkg PINEADO; el check los sirve desde
// vendor/ (bytes idénticos ⇒ los atributos integrity siguen siendo válidos).
const VENDOR = new Map([
  ['react@18.3.1/umd/react.development.js', 'react.development.js'],
  ['react-dom@18.3.1/umd/react-dom.development.js', 'react-dom.development.js'],
  ['@babel/standalone@7.29.0/babel.min.js', 'babel.min.js'],
  ['lucide@1.24.0/dist/umd/lucide.min.js', 'lucide.min.js'],
]);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.jsx': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.ttf': 'font/ttf',
  '.json': 'application/json; charset=utf-8',
};

function loadChromium() {
  const req = createRequire(path.join(REPO, 'web', 'package.json'));
  for (const pkg of ['playwright', '@playwright/test', 'playwright-core']) {
    try {
      const mod = req(pkg);
      if (mod && mod.chromium) return mod.chromium;
    } catch {
      /* siguiente candidato */
    }
  }
  throw new Error('Playwright no encontrado en web/node_modules (corre `npm ci` en web/)');
}

function serveApp() {
  const srv = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const safe = path.normalize(urlPath).replace(/^([/\\])+/, '');
    const file = path.join(APP, safe || 'index.html');
    if (!file.startsWith(APP) || !existsSync(file)) {
      res.writeHead(404).end('404');
      return;
    }
    res.writeHead(200, { 'content-type': MIME[path.extname(file)] ?? 'application/octet-stream' });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => srv.listen(0, '127.0.0.1', () => resolve(srv)));
}

// Errores de fuentes remotas = aviso (el fallback del stack aplica), no fallo.
const isFontNoise = (text) => /googleapis|gstatic|fonts/i.test(text);
// El canvas intenta restaurar su estado pan/zoom persistido; que no exista
// es el arranque normal (primer uso) — benigno, ni siquiera es aviso.
const isBenign = (url) => /\.design-canvas\.state\.json/.test(url);

function watchPage(page, sink) {
  page.on('pageerror', (err) => sink.errors.push(`pageerror: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    // Los 404/fallos de red se reportan por el hook de 'response'/'requestfailed'
    // (que sí traen la URL); aquí solo interesan los errores de la página misma.
    if (/Failed to load resource/i.test(msg.text())) return;
    (isFontNoise(msg.text()) ? sink.warnings : sink.errors).push(`console: ${msg.text()}`);
  });
  page.on('response', (r) => {
    if (r.status() < 400 || isBenign(r.url())) return;
    const line = `HTTP ${r.status()}: ${r.url()}`;
    (isFontNoise(r.url()) ? sink.warnings : sink.errors).push(line);
  });
  page.on('requestfailed', (r) => {
    if (isBenign(r.url())) return;
    const line = `requestfailed: ${r.url()} (${r.failure()?.errorText})`;
    (isFontNoise(r.url()) ? sink.warnings : sink.errors).push(line);
  });
}

async function shootAll(context, base, sink) {
  for (const [, file, comp] of SHOT_MAP) {
    const page = await context.newPage();
    watchPage(page, sink);
    await page.goto(`${base}/tools/shot.html?screen=${comp}`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__shotReady === true, null, { timeout: 30_000 });
    const err = await page.evaluate(() => window.__shotError);
    if (err) {
      sink.errors.push(`${file}: ${err}`);
    } else {
      const pending = await page.evaluate(() => window.__shotPendingIcons);
      if (pending.length) sink.warnings.push(`${file}: íconos sin resolver → ${pending.join(', ')}`);
      await page.locator('#shot').screenshot({ path: path.join(SHOTS, file) });
      console.log(`  ✓ ${file} (${comp})`);
    }
    await page.close();
  }
}

async function checkCanvas(context, base, sink) {
  const page = await context.newPage();
  watchPage(page, sink);
  await page.route('**://unpkg.com/**', async (route) => {
    const url = route.request().url();
    const hit = [...VENDOR.entries()].find(([suffix]) => url.includes(suffix));
    if (!hit) return route.abort();
    await route.fulfill({
      contentType: 'text/javascript; charset=utf-8',
      body: await fs.readFile(path.join(APP, 'vendor', hit[1])),
    });
  });
  await page.goto(`${base}/index.html`, { waitUntil: 'load' });
  await page.waitForFunction(
    (n) => document.querySelectorAll('[data-artboard-id]').length >= n,
    EXPECTED_ARTBOARDS,
    { timeout: 60_000 },
  );
  await page.waitForTimeout(1500); // un ciclo del refresco de íconos del canvas
  const count = await page.evaluate(() => document.querySelectorAll('[data-artboard-id]').length);
  if (count !== EXPECTED_ARTBOARDS) {
    sink.errors.push(`index.html declara ${count} artboards; se esperaban ${EXPECTED_ARTBOARDS}`);
  } else {
    console.log(`  ✓ index.html renderiza ${count}/${EXPECTED_ARTBOARDS} artboards sin errores de página`);
  }
  const ids = await page.evaluate(() =>
    [...document.querySelectorAll('[data-artboard-id]')].map((el) => el.getAttribute('data-artboard-id')),
  );
  for (const [id] of SHOT_MAP) {
    if (!ids.includes(id)) sink.errors.push(`falta el artboard "${id}" en index.html`);
  }
  await page.close();
}

const main = async () => {
  const sink = { errors: [], warnings: [] };
  const chromium = loadChromium();
  const srv = await serveApp();
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 640, height: 1200 },
    deviceScaleFactor: 2,
  });

  try {
    if (!CHECK_ONLY) {
      console.log(`Regenerando ${SHOT_MAP.length} shots @2x en ${path.relative(APP, SHOTS)}/ …`);
      await shootAll(context, base, sink);
    }
    console.log('Verificando el canvas (index.html, vendor local, cero unpkg)…');
    await checkCanvas(context, base, sink);
    for (const [, file] of SHOT_MAP) {
      if (!existsSync(path.join(SHOTS, file))) sink.errors.push(`shot faltante: shots/${file}`);
    }
  } finally {
    await browser.close();
    srv.close();
  }

  for (const w of sink.warnings) console.warn(`  ⚠ ${w}`);
  if (sink.errors.length) {
    for (const e of sink.errors) console.error(`  ✗ ${e}`);
    console.error(`FALLÓ: ${sink.errors.length} error(es).`);
    process.exit(1);
  }
  console.log(CHECK_ONLY ? 'CHECK OK.' : 'Shots regenerados y verificados. OK.');
};

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
