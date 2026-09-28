// [T-9.54 · D-45] LA CSP DEJA PASAR LO QUE EL MAPA PIDE, y nada más ancho.
//
// La política de `deploy/cloud/Caddyfile` va en Report-Only hasta que el
// recorrido por rol dé CERO violaciones (T-8.16): cada origen que el mapa pida
// sin estar en la lista es una violación que tumba ese paso. Y no había ninguna
// guarda que cruzara la lista con lo que el código pide de verdad, así que se
// derivan de aquí los orígenes —de las constantes que usa el mapa, no tecleados—.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

vi.mock("maplibre-gl", () => ({ default: {} }));
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import { RELIEVE_TILES } from "./capasDeFondo";
import { MAP_STYLE_URL } from "./MapPanel";

const CADDYFILE = readFileSync(resolve(process.cwd(), "../deploy/cloud/Caddyfile"), "utf8");

/** Las fuentes de una directiva de la cabecera CSP del Caddyfile. */
function directiva(nombre: string): string[] {
  const cabecera = /Content-Security-Policy(?:-Report-Only)?\s+"([^"]+)"/.exec(CADDYFILE);
  expect(cabecera, "el Caddyfile ya no declara la CSP").not.toBeNull();
  const d = cabecera![1]
    .split(";")
    .map((x) => x.trim().split(/\s+/))
    .find(([n]) => n === nombre);
  expect(d, `la CSP no tiene ${nombre}`).toBeDefined();
  return d!.slice(1);
}

/** El prefijo que la CSP tiene que autorizar para una plantilla de teselas. */
function prefijo(plantilla: string): string {
  return plantilla.slice(0, plantilla.indexOf("{"));
}

describe("[T-9.54] la CSP del Caddyfile cubre lo que pide el mapa", () => {
  it("el relieve: su RUTA en img-src y connect-src, no todo s3.amazonaws.com", () => {
    const ruta = prefijo(RELIEVE_TILES).replace(/terrarium\/$/, "");
    expect(ruta).toBe("https://s3.amazonaws.com/elevation-tiles-prod/");
    for (const nombre of ["img-src", "connect-src"]) {
      const fuentes = directiva(nombre);
      expect(fuentes, `${nombre} no deja pasar el relieve`).toContain(ruta);
      // Todo el host abriría cualquier bucket público de S3 a la consola.
      expect(fuentes, `${nombre} abre TODO s3.amazonaws.com`).not.toContain(
        "https://s3.amazonaws.com",
      );
      expect(fuentes).not.toContain("https://s3.amazonaws.com/");
    }
  });

  it("el mapa base sigue cubierto", () => {
    const origen = new URL(MAP_STYLE_URL).origin;
    expect(directiva("img-src")).toContain(origen);
    expect(directiva("connect-src")).toContain(origen);
  });

  it("la superficie (un `blob:`) pasa por img-src Y por connect-src", () => {
    // MapLibre descarga la imagen de una fuente `image` con `fetch`
    // (`ImageRequest.getImage` con `supportImageRefresh`), no con un `<img>`: el
    // `blob:` del PNG lo juzga `connect-src`, y `img-src blob:` solo no basta.
    expect(directiva("img-src")).toContain("blob:");
    expect(directiva("connect-src")).toContain("blob:");
  });
});
