// [T-9.64 · D-46] UNA SOLA ESCALA para los sismos: tamaño por MAGNITUD y color
// por MMI ESTIMADA en el inmueble. La fuente es `shared/fixtures/escala-sismos.json`;
// estas cifras son su copia y `escalaSismos.test.ts` las cruza contra ella (la
// imagen de la consola no copia `shared/fixtures`, así que no se importa el JSON).
// La gemela de la app es `mobile/src/features/sismos/escala.ts`.
//
// La paleta es la MMI del ShakeMap del USGS, la que se reconoce.

export interface CorteTamano {
  /** Magnitud desde la que rige el radio. */
  desde: number;
  /** Radio del ◇ en px. */
  radio: number;
}

export interface GradoMmi {
  desde: number;
  romano: string;
  color: string;
}

export const TAMANO: readonly CorteTamano[] = [
  { desde: 4.0, radio: 4 },
  { desde: 5.0, radio: 7 },
  { desde: 6.0, radio: 11 },
  { desde: 7.0, radio: 16 },
];

export const COLOR_MMI: readonly GradoMmi[] = [
  { desde: 1, romano: "I", color: "#FFFFFF" },
  { desde: 2, romano: "II", color: "#BFCCFF" },
  { desde: 3, romano: "III", color: "#A0E6FF" },
  { desde: 4, romano: "IV", color: "#80FFFF" },
  { desde: 5, romano: "V", color: "#7AFF93" },
  { desde: 6, romano: "VI", color: "#FFFF00" },
  { desde: 7, romano: "VII", color: "#FFC800" },
  { desde: 8, romano: "VIII", color: "#FF9100" },
  { desde: 9, romano: "IX", color: "#FF0000" },
  { desde: 10, romano: "X", color: "#C80000" },
];

/**
 * Radio en px por magnitud. Por debajo del primer corte se queda en el mínimo:
 * un sismo del catálogo nunca se vuelve invisible por pequeño.
 */
export function radioDeMagnitud(magnitud: number): number {
  let radio = TAMANO[0].radio;
  for (const corte of TAMANO) {
    if (magnitud >= corte.desde) radio = corte.radio;
  }
  return radio;
}

/** El grado, redondeado al entero más cercano y acotado a I…X (como `gmice.romano`). */
function gradoDeMmi(mmi: number): GradoMmi {
  const grado = Math.min(10, Math.max(1, Math.floor(mmi + 0.5)));
  return COLOR_MMI[grado - 1];
}

/** Color de la MMI ESTIMADA; `null` si no hay estimación (no se inventa). */
export function colorDeMmi(mmi: number | null | undefined): string | null {
  return mmi == null ? null : gradoDeMmi(mmi).color;
}

/** El grado en romanos; `null` si no hay estimación. */
export function romanoDeMmi(mmi: number | null | undefined): string | null {
  return mmi == null ? null : gradoDeMmi(mmi).romano;
}
