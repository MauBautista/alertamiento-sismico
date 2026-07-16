// T-2.01 — paridad del paquete de tokens: la consola migró a
// @takab/design-tokens SIN cambio visual. Este test ancla (1) que el CSS
// generado ≡ tokens.json, (2) los valores pre-migración (los que vivían en
// web/src/styles/colors_and_type.css hasta 1f3ab7f), (3) el drift gate del
// generador y (4) los contratos semánticos compartidos con el móvil.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import {
  cssVariables,
  DERIVED_STATE_PILL,
  INCIDENT_SEVERITY,
  KIND_COLOR,
  tokens,
  toNumber,
  UNKNOWN_DERIVED_STATE_KIND,
  UNKNOWN_SEVERITY_KIND,
} from "@takab/design-tokens";
import { describe, expect, it } from "vitest";

const require_ = createRequire(import.meta.url);
const pkgDir = path.dirname(require_.resolve("@takab/design-tokens/package.json"));
const tokensCss = readFileSync(path.join(pkgDir, "css", "tokens.css"), "utf8");

/** Parsea las declaraciones `--tk-*: valor;` del :root generado. */
function parseCssVariables(source: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [, name, value] of source.matchAll(/^\s*(--tk-[a-z0-9-]+):\s*(.+?);$/gm)) {
    out[name] = value;
  }
  return out;
}

describe("design tokens · paridad css ↔ json", () => {
  it("css/tokens.css contiene exactamente las variables de tokens.json", () => {
    expect(parseCssVariables(tokensCss)).toEqual(cssVariables);
  });

  it("el generador está en sincronía (drift gate)", () => {
    // Lanza el --check del paquete: si alguien editó el css a mano o cambió
    // tokens.json sin regenerar, esto revienta.
    expect(() =>
      execFileSync(process.execPath, [path.join("scripts", "gen-css.mjs"), "--check"], {
        cwd: pkgDir,
      }),
    ).not.toThrow();
  });
});

describe("design tokens · anclas de identidad visual (valores pre-migración)", () => {
  // Muestras de cada grupo, byte a byte contra lo que la consola servía antes
  // de T-2.01. Si un valor cambia aquí, ES un cambio visual deliberado.
  it.each([
    ["--tk-navy-700", "#1A3E62"],
    ["--tk-cyan", "#00BFFF"],
    ["--tk-status-normal", "#00E676"],
    ["--tk-status-warning", "#FFC107"],
    ["--tk-status-critical", "#FF5252"],
    ["--tk-fg-1", "#F0F2F5"],
    ["--tk-surface-0", "#0E2336"],
    ["--tk-border", "rgba(240, 242, 245, 0.08)"],
    ["--tk-text-base", "14px"],
    ["--tk-radius-pill", "999px"],
    ["--tk-dur-base", "180ms"],
    ["--tk-focus-ring", "0 0 0 2px var(--tk-navy-900), 0 0 0 4px var(--tk-cyan)"],
  ] as const)("%s = %s", (name, value) => {
    expect(cssVariables[name]).toBe(value);
  });

  it("la fuente de datos técnicos sigue siendo JetBrains Mono", () => {
    expect(cssVariables["--tk-font-mono"]).toContain("'JetBrains Mono'");
    expect(tokens.font.mono).toBe(cssVariables["--tk-font-mono"]);
  });

  it("la vista estructurada resuelve a los MISMOS valores que las CSS vars", () => {
    expect(tokens.color.status.critical).toBe(cssVariables["--tk-status-critical"]);
    expect(tokens.color.surface[0]).toBe(cssVariables["--tk-surface-0"]);
    expect(tokens.fontSize["5xl"]).toBe(cssVariables["--tk-text-5xl"]);
    expect(toNumber(tokens.fontSize.base)).toBe(14);
  });
});

describe("design tokens · contratos semánticos (web ≡ móvil)", () => {
  it("severidad de incidente → tono/etiqueta (contrato de SevTag)", () => {
    expect(INCIDENT_SEVERITY).toEqual({
      critical: { kind: "crit", label: "CRÍTICO" },
      warning: { kind: "warn", label: "ADVERTENCIA" },
      watch: { kind: "warn", label: "VIGILANCIA" },
      info: { kind: "ok", label: "NORMAL" },
    });
    // Desconocido ⇒ ámbar; jamás degradar a ok.
    expect(UNKNOWN_SEVERITY_KIND).toBe("warn");
  });

  it("derived_state → tono del pill (contrato de SiteCard)", () => {
    expect(DERIVED_STATE_PILL).toEqual({
      OPERATIVO: "ok",
      DEGRADADO: "warn",
      "SIN ENLACE": "crit",
    });
    expect(UNKNOWN_DERIVED_STATE_KIND).toBe("warn");
  });

  it("tono → color del semáforo resuelve a los tokens de status", () => {
    expect(KIND_COLOR).toEqual({
      ok: cssVariables["--tk-status-normal"],
      warn: cssVariables["--tk-status-warning"],
      crit: cssVariables["--tk-status-critical"],
    });
  });
});
