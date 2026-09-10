#!/usr/bin/env node
// [T-6.08] Genera la hoja del HOSTED UI CLÁSICO de Cognito a partir de tokens.json.
//
//   node scripts/gen-cognito-css.mjs           → escribe la hoja en infra/
//   node scripts/gen-cognito-css.mjs --check   → falla (exit 1) si la committeada difiere
//
// POR QUÉ UN GENERADOR Y NO UNA HOJA A MANO
// -----------------------------------------
// Cognito NO acepta custom properties: la hoja que se sube tiene que llevar los
// colores resueltos a literales. Escrita a mano, eso son doce hexes duplicados
// en un fichero que nadie abre —el día que la marca cambie de navy, la consola
// se entera y el login no—. Aquí los literales se DERIVAN, y el `--check` entra
// en `npm run check`, o sea en `make drift`.
//
// QUÉ SE PUEDE ESCRIBIR AQUÍ (medido, no copiado de la documentación)
// -------------------------------------------------------------------
// La API rechaza la hoja entera si cita una clase que no está en su lista. La
// lista de abajo se sacó de la HOJA QUE COGNITO SIRVE, no de un documento:
//
//   curl https://d1lcia0inyjsq.cloudfront.net/20240614193835/css/cognito-login.css
//
// (la referencia el propio HTML del Hosted UI de los dos pools, comprobado el
// 2026-09-09). Son QUINCE, y las dos últimas casi se pierden: un primer barrido
// con `\.[a-zA-Z]+-customizable` se dejó fuera `passwordCheck-notValid` y
// `passwordCheck-valid` por el guion de en medio — y son justo las dos que la
// pantalla de contraseña nueva pinta, que es la primera que ve un operador.
//
// `idpButton`/`socialButton` quedan fuera A PROPÓSITO: los dos pools declaran
// `supported_identity_providers = ["COGNITO"]`, así que esos botones no existen
// — vestir lo que no se tiene es cómo se acaba con una hoja que nadie sabe si
// está viva.
//
// SIN COMENTARIOS EN LA SALIDA, y no es descuido: quien hace el `apply` es una
// persona con una ventana de AWS abierta, y no está verificado que la API
// acepte comentarios en el CSS. Un rechazo ahí le cuesta la ventana. La
// procedencia vive en este generador y en el terraform que la sube.
//
// Salida DETERMINISTA (sin fechas): el drift gate compara byte a byte.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(ROOT, "..", "..");
const TOKENS = path.join(ROOT, "tokens.json");
const OUT = path.join(REPO, "infra", "terraform", "modules", "identity", "cognito-hosted-ui.generated.css");
const CHECK = process.argv.includes("--check");

const t = JSON.parse(readFileSync(TOKENS, "utf8"));

/** Las trece clases que la hoja de Cognito define. Citar cualquier otra hace
 *  que `SetUICustomization` rechace la hoja ENTERA. */
export const CLASES_DE_COGNITO = [
  "background-customizable",
  "banner-customizable",
  "errorMessage-customizable",
  "idpButton-customizable",
  "idpDescription-customizable",
  "inputField-customizable",
  "label-customizable",
  "legalText-customizable",
  "logo-customizable",
  "passwordCheck-notValid-customizable",
  "passwordCheck-valid-customizable",
  "redirect-customizable",
  "socialButton-customizable",
  "submitButton-customizable",
  "textDescription-customizable",
];

/**
 * La pantalla, de fuera hacia dentro. Cada bloque dice qué parte viste y con
 * qué token, porque el porqué no cabe en la salida.
 */
const REGLAS = [
  // El lienzo entero: el navy de la consola, para que el salto desde /login no
  // sea de un producto a otro.
  [".background-customizable", { "background-color": t["--tk-surface-0"] }],
  // La banda del imagotipo. De fábrica es `lightgray`: es lo que hace que la
  // pantalla se lea como de AWS y no como nuestra.
  [".banner-customizable", { "background-color": t["--tk-surface-1"], padding: "22px 0 22px 0" }],
  // El imagotipo cabe al 70 % de la banda: al 60 % de fábrica la palabra
  // "AILERT" se queda por debajo del tamaño en el que se lee.
  [".logo-customizable", { "max-width": "70%", "max-height": "70%" }],
  // Rótulos de los campos y textos de apoyo.
  [".label-customizable", { color: t["--tk-fg-2"] }],
  [".textDescription-customizable", { color: t["--tk-fg-3"], "padding-top": "10px" }],
  [".idpDescription-customizable", { color: t["--tk-fg-3"] }],
  [".legalText-customizable", { color: t["--tk-fg-3"], "font-size": "11px" }],
  // Los campos: fondo del lienzo con borde tenue, como los de la consola.
  [
    ".inputField-customizable",
    {
      "background-color": t["--tk-surface-0"],
      color: t["--tk-fg-1"],
      border: `1px solid ${t["--tk-border-strong"]}`,
    },
  ],
  // El botón que envía: cian de acento con TINTA OSCURA. Blanco sobre este cian
  // da 1.9:1 — la misma trampa que T-6.09 sacó de la tira de alerta.
  [
    ".submitButton-customizable",
    {
      "background-color": t["--tk-brand"],
      color: t["--tk-navy-900"],
      "font-weight": "700",
    },
  ],
  // El error usa la TINTA crítica (T-6.09), no el rojo anclado: sobre el navy,
  // el ancla se queda en 5.01 y la tinta llega a 7.01.
  [
    ".errorMessage-customizable",
    {
      color: t["--tk-status-critical-text"],
      "background-color": t["--tk-surface-1"],
      border: `1px solid ${t["--tk-status-critical"]}`,
    },
  ],
  // La pantalla de CONTRASEÑA NUEVA, que es la primera que ve un operador dado
  // de alta. Sus dos avisos son de fábrica `#DF3312` y `#19BF00`: sobre el navy
  // el rojo cae a 3.52:1, así que se traen a la paleta —y de paso el verde sube
  // de 2.47 (sobre el blanco de fábrica NO pasaba AA) a 9.59.
  [".passwordCheck-notValid-customizable", { color: t["--tk-status-critical-text"] }],
  [".passwordCheck-valid-customizable", { color: t["--tk-status-normal"] }],
  // OJO: en la hoja de Cognito esta clase es sólo `text-align: center`, y el
  // color del enlace lo pone el `a` de Bootstrap (`#337AB7`). Si la clase está
  // en el propio enlace, esta línea lo arregla; si está en un contenedor, el
  // enlace se queda en 3.51:1 sobre el navy —el ÚNICO elemento que empeora— y
  // hará falta `.redirect-customizable a`, que no se escribe aquí porque una
  // clase que la API no acepte tumba la hoja ENTERA. Se decide en el `apply`,
  // que es donde un rechazo es barato y se ve.
  [".redirect-customizable", { color: t["--tk-brand"] }],
];

const css =
  REGLAS.map(
    ([sel, props]) =>
      `${sel} {\n${Object.entries(props)
        .map(([k, v]) => `  ${k}: ${v};`)
        .join("\n")}\n}`,
  ).join("\n\n") + "\n";

// Guarda del propio generador: una clase fuera de la lista de Cognito haría
// que la API rechace la hoja entera, y eso se descubriría en la ventana de AWS
// de otra persona.
const fuera = REGLAS.map(([sel]) => sel.slice(1)).filter((c) => !CLASES_DE_COGNITO.includes(c));
if (fuera.length > 0) {
  console.error(`Clases que Cognito NO acepta: ${fuera.join(", ")}`);
  process.exit(1);
}

if (CHECK) {
  const committed = existsSync(OUT) ? readFileSync(OUT, "utf8") : "";
  if (committed !== css) {
    console.error(
      "DRIFT: la hoja del Hosted UI no coincide con tokens.json — corre `npm run gen:cognito`.",
    );
    process.exit(1);
  }
  console.log("cognito-hosted-ui.generated.css en sincronía con tokens.json.");
} else {
  mkdirSync(path.dirname(OUT), { recursive: true });
  writeFileSync(OUT, css);
  console.log(`Generado ${path.relative(REPO, OUT)} (${REGLAS.length} reglas).`);
}
