#!/usr/bin/env node
// Genera css/tokens.css a partir de tokens.json (única fuente de verdad).
//
//   node scripts/gen-css.mjs           → escribe css/tokens.css
//   node scripts/gen-css.mjs --check   → falla (exit 1) si el committeado difiere
//
// Salida DETERMINISTA (sin fechas): el drift gate compara byte a byte.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TOKENS = path.join(ROOT, "tokens.json");
const OUT = path.join(ROOT, "css", "tokens.css");
const CHECK = process.argv.includes("--check");

const tokens = JSON.parse(readFileSync(TOKENS, "utf8"));

const lines = [
  "/* ==========================================================================",
  "   TAKAB TECHNOLOGY — Design Tokens (CSS custom properties)",
  "   GENERADO por scripts/gen-css.mjs a partir de tokens.json — NO EDITAR A MANO.",
  "   Fuente de verdad: @takab/design-tokens/tokens.json (regen: npm run gen).",
  "   Las @font-face y los @import de fuentes viven en cada app (rutas de assets).",
  "   ========================================================================== */",
  "",
  ":root {",
  ...Object.entries(tokens).map(([name, value]) => `  ${name}: ${value};`),
  "}",
  "",
];
const css = lines.join("\n");

if (CHECK) {
  const committed = existsSync(OUT) ? readFileSync(OUT, "utf8") : "";
  if (committed !== css) {
    console.error("DRIFT: css/tokens.css no coincide con tokens.json — corre `npm run gen`.");
    process.exit(1);
  }
  console.log("css/tokens.css en sincronía con tokens.json.");
} else {
  mkdirSync(path.dirname(OUT), { recursive: true });
  writeFileSync(OUT, css);
  console.log(`Generado ${path.relative(ROOT, OUT)} (${Object.keys(tokens).length} variables).`);
}
