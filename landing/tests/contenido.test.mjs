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

// [T-5.04] Texto tal como lo LEE una persona: sin etiquetas y con los espacios
// colapsados. Buscar sobre el HTML crudo es frágil —una frase partida por un
// `<strong>` no casa— y además da falsos negativos justo en las afirmaciones
// enfáticas, que son las que más importan aquí.
const texto = (rel) =>
  leer(rel)
    .replace(/<(script|style)[\s\S]*?<\/\1>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();

test("existen las páginas y los ficheros públicos", () => {
  for (const f of [
    ...paginas,
    "robots.txt",
    "sitemap.xml",
    "favicon.svg",
    "og-v1.png",
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

// ═════════════════════════════════════════════════════════════════ [T-5.04]
//
// EL PERÍMETRO DE CLAIMS CUBRÍA CIFRAS Y NORMAS, NO CAPACIDADES.
//
// El test de «cadenas prohibidas» de arriba es bueno y sigue: impide publicar
// mediciones y citar normas. Lo que no impedía es afirmar EN PRESENTE una
// capacidad cuyo gate físico sigue abierto — y por eso pasó en verde, durante
// meses y en producción, que el sitio dijera que el sistema «acciona la válvula
// de gas, los ascensores y las puertas». Ningún gabinete tiene esos tres canales
// cableados; el controlador que los haría está en la lista de materiales marcado
// «Opcional», y el propio registro de gates, al acreditar `G-01`, escribe la
// reserva: «el `readback_ok` de gas_valve/elevator/door_retainer prueba EL CAMINO
// DEL PIN, no que se haya movido una válvula».
//
// Es exactamente el fallo que este repositorio ya cazó una vez —el checklist de
// gas y puertas en verde sin gas ni puertas— reaparecido en la superficie más
// pública que tiene el proyecto.
//
// CÓMO SE DERIVA, y por qué así: los gates y su estado se leen del registro del
// runbook de auditoría, que es donde se marcan presencialmente. La lista de
// gates NO se teclea aquí: se compara por IGUALDAD, así que un gate nuevo obliga
// a decidir qué afirmaciones dependen de él antes de poder seguir. Lo editorial
// —qué frase depende de qué gate— es un juicio, y por eso está escrito abajo con
// su nombre; lo que no puede quedar a juicio es OLVIDARSE de un gate.

const RUNBOOK_GATES = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "takab-docs",
  "runbooks",
  "RUNBOOK-auditoria-cierre.md",
);

/** {gate: {nombre, cerrado}} leído del registro §10 del runbook. */
function gatesDelRegistro() {
  const filas = readFileSync(RUNBOOK_GATES, "utf8")
    .split("\n")
    .filter((l) => /^\| G-\d\d \|/.test(l));
  const out = {};
  for (const fila of filas) {
    const celdas = fila.split("|").map((s) => s.trim());
    // Por CONTENIDO y no por posición: la fila de `G-01` tiene una columna menos
    // que las otras nueve (el registro se llena a mano). Un índice fijo daría
    // «abierto» a un gate acreditado, que es el error caro en esta dirección.
    const cerrado = celdas.slice(2).some((c) => /^\*{0,2}OK\*{0,2}$/.test(c));
    out[celdas[1]] = { nombre: celdas[2], cerrado };
  }
  return out;
}

/**
 * Afirmaciones del sitio que sólo se pueden hacer EN PRESENTE con su gate cerrado.
 *
 * Una entrada por gate, SIEMPRE — la lista vacía es una decisión explícita
 * («ninguna afirmación del sitio depende de este gate»), no un olvido.
 */
const CAPACIDADES_GATEADAS = {
  // Reinicio en frío. Acreditado el 2026-08-24, y con su reserva escrita: lo que
  // se probó de gas/ascensores/puertas fue el camino del pin, no el actuador.
  "G-01": [],
  // «La sirena suena con el gabinete apagado». Es obra pendiente, no prueba
  // pendiente: el relé de enclavamiento y el monoestable no están construidos.
  "G-02": [
    "suena con el gabinete apagado",
    "suena igual por hardware",
    "aunque el gabinete",
  ],
  "G-03": [],
  // La cadena física completa contacto→relé→sirena. Mientras siga abierto, el
  // sitio no puede decir que ACCIONA gas, ascensores o puertas: puede decir que
  // los gobierna por diseño y que se acreditan en la puesta en marcha.
  "G-04": [
    "acciona la sirena, la válvula de gas",
    "acciona sirena, estrobo, gas, ascensores y puertas",
    "cierre de la válvula de gas, retorno de ascensores",
    // La misma promesa en la descripción para buscadores, que es donde más fácil
    // se cuela: no se ve en la página y la lee todo el mundo.
    "acciona sirena, válvula de gas, ascensores y puertas",
  ],
  "G-05": [],
  "G-06": [],
  "G-07": [],
  "G-08": [],
  // Restauración real con su tiempo medido. El sitio no promete ninguna cifra de
  // recuperación, y no puede empezar a hacerlo sin cerrar esto.
  "G-09": ["restauramos", "tiempo de recuperación", "RTO"],
  "G-10": [],
};

test("[T-5.04] el censo de capacidades cubre TODOS los gates del registro", () => {
  const gates = gatesDelRegistro();
  assert.ok(
    Object.keys(gates).length >= 10,
    `el registro de gates se leyó corto: ${Object.keys(gates)}`,
  );
  assert.deepEqual(
    Object.keys(CAPACIDADES_GATEADAS).sort(),
    Object.keys(gates).sort(),
    "hay un gate sin decidir si el sitio afirma algo que dependa de él.\n" +
      "  Añádelo a CAPACIDADES_GATEADAS — con lista vacía si no le afecta, pero DECÍDELO.",
  );
});

test("[T-5.04] el sitio no afirma en presente una capacidad con su gate abierto", () => {
  const gates = gatesDelRegistro();
  const fallos = [];
  for (const [gate, frases] of Object.entries(CAPACIDADES_GATEADAS)) {
    if (gates[gate].cerrado) continue;
    for (const p of paginas) {
      const html = texto(p).toLowerCase();
      for (const frase of frases) {
        if (html.includes(frase.toLowerCase())) {
          fallos.push(
            `${p}: «${frase}» — depende de ${gate} (${gates[gate].nombre}), que sigue ABIERTO.\n` +
              `    Para poder decirlo hay que acreditar ese gate en el registro §10 del ` +
              `runbook de auditoría.\n` +
              `    Mientras tanto: dilo como alcance de diseño, no como hecho presente.`,
          );
        }
      }
    }
  }
  assert.deepEqual(
    fallos,
    [],
    `Capacidades afirmadas sin su gate:\n  ${fallos.join("\n  ")}`,
  );
});

test("[T-5.04] y NO prohíbe de más: lo acreditado se sigue pudiendo decir", () => {
  // La mitad que hace útil a una prohibición. Sin esto, vaciar el sitio entero
  // dejaría los dos tests de arriba en verde.
  const index = texto("index.html");
  const acreditadas = [
    // Opera sin nube: probado con la nube caída, cero pérdida y cero duplicados.
    "sin depender de internet",
    "PROTECCIÓN LOCAL ACTIVA",
    // Evidencia inmutable: dos capas, y el trigger para hasta al superusuario.
    "no se puede reescribir",
    // Aislamiento entre clientes: lo impone la base, no el software.
    "una lectura cruzada devuelve cero filas",
    // Sin cuenta atrás ni magnitud: hay una prueba por superficie.
    "No muestra cuenta regresiva ni magnitud",
    // El deslinde de SASMEX, que es lo que protege al proyecto.
    "no la genera ni la sustituye",
  ];
  for (const frase of acreditadas) {
    assert.ok(
      index.includes(frase),
      `index.html perdió una afirmación ACREDITADA: «${frase}».\n` +
        "  Corregir el perímetro no puede vaciar la venta: esto sí se puede decir.",
    );
  }
});
