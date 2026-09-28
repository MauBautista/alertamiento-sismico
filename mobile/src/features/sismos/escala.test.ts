// [T-9.64 · D-46] LA ESCALA DE LA APP ES LA DE LA CONSOLA, Y EL GRADO ES EL DE LA NUBE.
//
// Tres sitios tienen que decir lo mismo de un sismo: la consola (tamaño del ◇),
// la app (el círculo de la fila) y la nube (el romano que manda en
// `en_tu_inmueble.mmi_romano`). Si cada suite fabricara sus propias cifras, un
// cambio en una dejaría a las otras rotulando lo de antes con toda tranquilidad.
// Aquí se cruzan: contra `shared/fixtures/escala-sismos.json` (el mismo que lee
// `web/src/features/console/escalaSismos.test.ts`) y contra `gmice.romano`,
// leyendo el código de la nube (patrón de `superficieCostura.test.ts`).
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { colorDeMmi, LEYENDA_ESCALA, radioDeMagnitud, romanoDeMmi, tintaSobre } from "./escala";

interface Escala {
  tamano: { desde_mag: number; radio_px: number }[];
  color_mmi: { desde: number; romano: string; color: string }[];
  leyenda: string;
}

const RAIZ = resolve(process.cwd(), "..");
const ESCALA: Escala = JSON.parse(
  readFileSync(resolve(RAIZ, "shared", "fixtures", "escala-sismos.json"), "utf8"),
);
/** `gmice.py` SIN comentarios: la prosa cita nombres que no son código. */
const GMICE = readFileSync(
  resolve(RAIZ, "api", "src", "takab_api", "shakemap", "gmice.py"),
  "utf8",
).replace(/^\s*#.*$/gm, "");

describe("[T-9.64] la escala de la app es la del fichero compartido", () => {
  it("el fichero trae los cuatro tamaños y los diez grados (si no, esto no mira nada)", () => {
    expect(ESCALA.tamano).toHaveLength(4);
    expect(ESCALA.color_mmi).toHaveLength(10);
  });

  it("cada umbral de magnitud da SU radio, hasta justo antes del siguiente", () => {
    for (const t of ESCALA.tamano) {
      expect(radioDeMagnitud(t.desde_mag)).toBe(t.radio_px);
      expect(radioDeMagnitud(t.desde_mag + 0.9)).toBe(t.radio_px);
    }
  });

  it("por debajo del primer umbral y por encima del último, los extremos (como la consola)", () => {
    expect(radioDeMagnitud(3.2)).toBe(ESCALA.tamano[0].radio_px);
    expect(radioDeMagnitud(8.2)).toBe(ESCALA.tamano[ESCALA.tamano.length - 1].radio_px);
  });

  it("cada grado MMI da SU color y SU romano", () => {
    for (const c of ESCALA.color_mmi) {
      expect(colorDeMmi(c.desde)).toBe(c.color);
      expect(romanoDeMmi(c.desde)).toBe(c.romano);
    }
  });

  it("sin estimación no se inventa un color: `null`", () => {
    expect(colorDeMmi(null)).toBeNull();
    expect(colorDeMmi(undefined)).toBeNull();
    expect(romanoDeMmi(null)).toBeNull();
  });

  it("la leyenda que pinta la app es la del fichero", () => {
    expect(LEYENDA_ESCALA).toBe(ESCALA.leyenda);
  });
});

describe("[T-9.64] el grado se redondea como `gmice.romano` de la nube", () => {
  it("la nube redondea al entero MÁS CERCANO y acota a I…X", () => {
    // Si la nube cambiara de redondeo (truncar, p. ej.), el círculo de la app y
    // el romano que manda el servidor dirían grados distintos en la misma fila.
    expect(GMICE).toMatch(/grado\s*=\s*int\(math\.floor\(mmi\s*\+\s*0\.5\)\)/);
    expect(GMICE).toMatch(/_ROMANOS\[min\(10,\s*max\(1,\s*grado\)\)\s*-\s*1\]/);
  });

  it("los romanos del fichero son los de la nube, en el mismo orden", () => {
    const m = /_ROMANOS\s*=\s*\(([^)]*)\)/.exec(GMICE);
    expect(m).not.toBeNull();
    const nube = [...m![1].matchAll(/"([IVX]+)"/g)].map((x) => x[1]);
    expect(nube).toEqual(ESCALA.color_mmi.map((c) => c.romano));
  });

  it.each([
    [5.5, "VI"],
    [5.49, "V"],
    [2.87, "III"],
    [0.4, "I"],
    [11.2, "X"],
  ])("MMI %s ⇒ %s (el mismo grado que pinta el servidor)", (mmi, romano) => {
    expect(romanoDeMmi(mmi)).toBe(romano);
  });
});

describe("la tinta sobre el círculo se lee en los diez colores", () => {
  it("los grados claros llevan tinta oscura y los rojos, clara", () => {
    const [claro] = ESCALA.color_mmi;
    const rojoOscuro = ESCALA.color_mmi[ESCALA.color_mmi.length - 1];
    expect(tintaSobre(claro.color)).not.toBe(tintaSobre(rojoOscuro.color));
    // VI (amarillo) y V (verde) son claros: tinta oscura, la misma que I.
    expect(tintaSobre(colorDeMmi(6)!)).toBe(tintaSobre(claro.color));
    expect(tintaSobre(colorDeMmi(5)!)).toBe(tintaSobre(claro.color));
  });
});
