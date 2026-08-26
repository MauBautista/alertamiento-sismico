// Gate determinista sobre dist/: cadenas obligatorias, cadenas prohibidas,
// orígenes externos, presupuestos de tamaño y saneos básicos de accesibilidad.
// Corre en CI (job `landing`) y en `make test`. Lighthouse/axe viven aparte
// (manuales): esto es lo que puede ser bloqueante sin flakear.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");

const gz = (buf) => gzipSync(buf, { level: 9 }).length;
const leer = (rel) => readFileSync(join(dist, rel), "utf8");

const paginas = ["index.html", "aviso-de-privacidad.html", "404.html"];

test("existen las páginas y los ficheros públicos", () => {
  for (const f of [
    ...paginas,
    "robots.txt",
    "sitemap.xml",
    "favicon.svg",
    "og-v2.png",
  ]) {
    assert.ok(existsSync(join(dist, f)), `falta dist/${f}`);
  }
});

test("cadenas obligatorias (deslinde SASMEX, dominio remitente, contacto, idioma)", () => {
  const index = leer("index.html");
  const obligatorias = [
    // fuente: envs/dev/site/index.html (T-2.156) — el deslinde y la declaración
    // del dominio remitente NO pueden perderse: el sitio es evidencia del caso SES.
    "no la genera ni la sustituye",
    "alertas@takabailert.com",
    "dominio remitente",
    "contacto@takabailert.com",
    "SASMEX",
    "Protéjase",
    'lang="es-MX"',
    'rel="canonical" href="https://takabailert.com/"',
  ];
  for (const s of obligatorias) {
    assert.ok(
      index.includes(s),
      `index.html no contiene la cadena obligatoria: ${s}`,
    );
  }
  const aviso = leer("aviso-de-privacidad.html");
  assert.ok(
    aviso.includes("contacto@takabailert.com"),
    "aviso sin correo de contacto",
  );
});

test("cadenas prohibidas (cifras, normas, clichés, terceros)", () => {
  // Decisión 2026-08-25: la landing NO publica cifras medidas. Y el deslinde
  // normativo (CONSULTA-LEGAL §3) prohíbe citar normas o certificaciones.
  const prohibidas = [
    "6.65",
    "4.16",
    "214 ms",
    "13/13",
    "NOM-",
    "fonts.googleapis",
    "fonts.gstatic",
    "App Store",
    "Google Play",
    "INAI",
  ];
  for (const p of paginas) {
    const html = leer(p);
    for (const s of prohibidas) {
      assert.ok(!html.includes(s), `${p} contiene la cadena prohibida: ${s}`);
    }
    assert.ok(!/family=(Inter|Roboto)/.test(html), `${p} carga Inter/Roboto`);
  }
});

test("cero orígenes externos (href/src/srcset/url())", () => {
  const permitido = (u) =>
    u.startsWith("/") ||
    u.startsWith("#") ||
    u.startsWith("mailto:") ||
    u.startsWith("data:") ||
    u.startsWith("https://takabailert.com") ||
    u.startsWith("https://wa.me");
  for (const p of paginas) {
    const html = leer(p);
    const urls = [
      ...[...html.matchAll(/(?:href|src)="([^"]+)"/g)].map((m) => m[1]),
      ...[...html.matchAll(/srcset="([^"]+)"/g)].flatMap((m) =>
        m[1].split(",").map((s) => s.trim().split(/\s+/)[0]),
      ),
      ...[...html.matchAll(/url\(([^)]+)\)/g)].map((m) =>
        m[1].replace(/['"]/g, ""),
      ),
    ];
    for (const u of urls) {
      assert.ok(permitido(u), `${p} referencia un origen no permitido: ${u}`);
    }
  }
});

test("toda <img> declara width y height (CLS)", () => {
  for (const p of paginas) {
    const html = leer(p);
    for (const [tag] of html.matchAll(/<img\b[^>]*>/g)) {
      assert.ok(
        /\bwidth="\d+"/.test(tag),
        `${p}: <img> sin width: ${tag.slice(0, 120)}`,
      );
      assert.ok(
        /\bheight="\d+"/.test(tag),
        `${p}: <img> sin height: ${tag.slice(0, 120)}`,
      );
    }
  }
});

test("presupuestos: JS < 20 KB gz · HTML < 40 KB gz · fuentes < 200 KB", () => {
  const astroDir = join(dist, "_astro");
  const assets = existsSync(astroDir) ? readdirSync(astroDir) : [];
  // JS = ficheros _astro/*.js + scripts INLINE del HTML (Astro inlina los
  // pequeños). Se suma todo para que la aserción no pase por vacuidad.
  const jsFicheros = assets
    .filter((f) => f.endsWith(".js"))
    .reduce((n, f) => n + gz(readFileSync(join(astroDir, f))), 0);
  const index = leer("index.html");
  const inline = [
    ...index.matchAll(/<script type="module">([\s\S]*?)<\/script>/g),
  ]
    .map((m) => m[1])
    .join("");
  assert.ok(
    inline.includes("IntersectionObserver") || jsFicheros > 0,
    "no se encontró el JS de la landing (¿se perdió el <script>?)",
  );
  const jsTotal = jsFicheros + gz(Buffer.from(inline));
  assert.ok(
    jsTotal < 20 * 1024,
    `JS inicial ${jsTotal} B gz ≥ 20 KB (techo del brief: 100 KB)`,
  );

  const fuentes = assets
    .filter((f) => f.endsWith(".woff2"))
    .reduce((n, f) => n + readFileSync(join(astroDir, f)).length, 0);
  assert.ok(fuentes > 0, "no hay fuentes woff2 en dist/_astro");
  assert.ok(fuentes < 200 * 1024, `fuentes ${fuentes} B ≥ 200 KB`);

  for (const p of paginas) {
    const peso = gz(readFileSync(join(dist, p)));
    assert.ok(peso < 40 * 1024, `${p} pesa ${peso} B gz ≥ 40 KB`);
  }
});

test("saneo de estructura: un solo h1, salto al contenido, sin http:// plano", () => {
  for (const p of paginas) {
    const html = leer(p);
    const h1s = [...html.matchAll(/<h1\b/g)].length;
    assert.equal(h1s, 1, `${p} tiene ${h1s} <h1>`);
    assert.ok(
      html.includes('href="#contenido"'),
      `${p} sin salto al contenido`,
    );
    // Los namespaces XML (xmlns="http://www.w3.org/…") son identificadores, no
    // recursos que se descarguen: se eximen.
    const sinNs = html.replaceAll("http://www.w3.org/", "ns:");
    assert.ok(!/["'(]http:\/\//.test(sinNs), `${p} referencia http:// sin TLS`);
  }
});
