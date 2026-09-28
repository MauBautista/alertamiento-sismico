// [T-9.64 · D-46] UNA SOLA ESCALA para los sismos: tamaño por MAGNITUD y color por
// la MMI ESTIMADA en el inmueble. Gemela de `web/src/features/console/escalaSismos.ts`.
//
// POR QUÉ SE IMPORTA EL JSON Y NO SE COPIAN LAS CIFRAS (a diferencia de la consola):
// la paleta es la del ShakeMap del USGS, diez colores escritos en hex, y
// `designTokens.test.ts` prohíbe —con razón— un color escrito a mano en
// `mobile/src`. Copiarlos habría obligado a abrirle un agujero a esa guarda; leer
// el fichero compartido no escribe ninguno y deja UNA sola fuente. Metro lo sirve
// porque `metro.config.js` observa `shared/fixtures`. `escala.test.ts` lo cruza
// igualmente contra el fichero y contra `gmice.romano` de la nube.
import escala from "../../../../shared/fixtures/escala-sismos.json";

import { palette } from "@/ui/theme";

type Tamano = { desde_mag: number; radio_px: number };
type GradoMmi = { desde: number; romano: string; color: string };

const TAMANO: readonly Tamano[] = escala.tamano;
const COLOR_MMI: readonly GradoMmi[] = escala.color_mmi;

/** «Tamaño = magnitud · color = intensidad ESTIMADA…», la del fichero. */
export const LEYENDA_ESCALA: string = escala.leyenda;

/**
 * Radio (px) por magnitud: el del mayor umbral alcanzado. Por debajo del primero,
 * el primero —igual que la consola—: el catálogo que se sirve empieza en M 4.0.
 */
export function radioDeMagnitud(magnitud: number): number {
  let radio = TAMANO[0].radio_px;
  for (const t of TAMANO) {
    if (magnitud >= t.desde_mag) {
      radio = t.radio_px;
    }
  }
  return radio;
}

/** El grado ENTERO que se enseña: al entero más cercano y en I…X, como `gmice.romano`. */
function gradoDeMmi(mmi: number): GradoMmi {
  const grado = Math.min(10, Math.max(1, Math.floor(mmi + 0.5)));
  return COLOR_MMI.find((c) => c.desde === grado) ?? COLOR_MMI[COLOR_MMI.length - 1];
}

/** Color de la MMI ESTIMADA; `null` si no hay estimación (no se inventa). */
export function colorDeMmi(mmi: number | null | undefined): string | null {
  return mmi == null ? null : gradoDeMmi(mmi).color;
}

/** El grado en romanos; `null` si no hay estimación. */
export function romanoDeMmi(mmi: number | null | undefined): string | null {
  return mmi == null ? null : gradoDeMmi(mmi).romano;
}

/**
 * Tinta legible sobre un color de la escala: la del fondo de la app sobre los
 * grados claros (I…VIII), la del texto principal sobre los rojos (IX, X). Se
 * decide por la luminancia del propio color, no por una lista de grados.
 */
export function tintaSobre(color: string): string {
  const hex = color.replace("#", "");
  const canal = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const luminancia = 0.2126 * canal(0) + 0.7152 * canal(2) + 0.0722 * canal(4);
  return luminancia > 0.18 ? palette.bg : palette.fg;
}
