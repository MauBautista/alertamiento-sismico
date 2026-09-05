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
    "favicon.png",
    "apple-touch-icon.png",
    "og-v3.png",
  ]) {
    assert.ok(existsSync(join(dist, f)), `falta dist/${f}`);
  }
});

test("v3 usa la identidad entregada y la tarjeta social vigente", () => {
  const index = leer("index.html");
  assert.ok(
    index.includes('href="/favicon.png"'),
    "la metadata no apunta al isotipo negativo usado como favicon",
  );
  assert.ok(
    index.includes('alt="TAKAB Ailert"'),
    "la navegación no contiene el imagotipo accesible de TAKAB Ailert",
  );
  assert.ok(
    index.includes("imagotipo-takab-ailert-negativo"),
    "el build no contiene una variante optimizada del imagotipo entregado",
  );
  assert.ok(
    index.includes("https://takabailert.com/og-v3.png"),
    "la metadata social no apunta a og-v3.png",
  );
  for (const metadata of [
    'property="og:image:alt"',
    'property="og:image:width" content="1200"',
    'property="og:image:height" content="630"',
    'type="application/ld+json"',
  ]) {
    assert.ok(index.includes(metadata), `falta metadata social: ${metadata}`);
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
    "WR-1",
    "Raspberry",
    "quórum",
    "180.1",
    "0.085g",
    "Sitio Dev Puebla",
    "Mariana López",
    "José Torres",
    "Daniel Ruiz",
    "En vivo",
  ];
  for (const p of paginas) {
    const html = leer(p);
    for (const s of prohibidas) {
      assert.ok(!html.includes(s), `${p} contiene la cadena prohibida: ${s}`);
    }
    assert.ok(!/family=(Inter|Roboto)/.test(html), `${p} carga Inter/Roboto`);
  }
});

test("el texto público no insinúa actuadores no acreditados", () => {
  const index = texto("index.html");
  for (const termino of [/\bgas\b/i, /\bascensores?\b/i, /\bpuertas?\b/i]) {
    assert.ok(
      !termino.test(index),
      `index.html nombra un actuador no acreditado: ${termino}`,
    );
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

test("[T-5.04] el rediseño conserva las capacidades acreditadas", () => {
  // La mitad que hace útil a una prohibición. Sin esto, vaciar el sitio entero
  // dejaría los dos tests de arriba en verde.
  const index = texto("index.html");
  const acreditadas = [
    // Autonomía local y continuidad, expresadas como capacidades positivas.
    "Protección local activa",
    "La ruta crítica permanece en el edificio",
    // Evidencia y aislamiento de clientes, también en lenguaje de producto.
    "Cada actualización conserva el historial del incidente",
    "separación de datos por cliente",
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

test("el flujo público cubre inmueble, móvil y recuperación", () => {
  const index = texto("index.html");
  for (const frase of [
    "Gabinetes secundarios amplían el alcance",
    "sirenas y estrobos se activan por zona",
    "Puebla",
    "Tlaxcala",
    "Evacúe ahora",
    "Estoy a salvo",
    "Necesito ayuda",
    "Pase de lista",
    "fotografías",
    "Dictamen técnico",
    "Reingreso controlado",
    "Sismograma",
    "Espectrograma",
    "Conteo y conciliación",
    "T50",
    "T90",
    "Síntesis asistida por IA",
    "Hechos explicados, trazabilidad intacta",
    "Campos reales · datos ilustrativos",
    "Vista táctica",
  ]) {
    assert.ok(index.includes(frase), `falta una etapa del flujo: ${frase}`);
  }
});

test("hero y mapa conservan la secuencia visual solicitada", () => {
  const index = leer("index.html");
  assert.ok(
    !index.includes("RECEPCIÓN DEDICADA"),
    "regresó el receptor independiente que debía retirarse del hero",
  );
  assert.ok(
    index.includes("c-main__activo"),
    "el gabinete principal no contiene su capa de activación",
  );
  assert.equal(
    [...index.matchAll(/class="m-ruta"/g)].length,
    10,
    "cada una de las diez estaciones debe recibir una ruta desde el epicentro",
  );
  assert.equal(
    [...index.matchAll(/class="m-estacion m-estacion--/g)].length,
    10,
    "el mapa perdió estaciones fijas",
  );
  assert.ok(
    !index.includes("m-haz__pulso"),
    "regresó el bloque móvil de la animación anterior",
  );
});
