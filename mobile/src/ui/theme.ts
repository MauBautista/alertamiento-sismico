// Tema RN derivado de @takab/design-tokens (T-2.01): mismos valores que la
// consola, resueltos desde la fuente única. Nada de colores horneados aquí.
import { tokens, toNumber } from "@takab/design-tokens";

export const palette = {
  bg: tokens.color.surface[0],
  card: tokens.color.surface[1],
  raised: tokens.color.surface[2],
  fg: tokens.color.fg.primary,
  fg2: tokens.color.fg.secondary,
  fg3: tokens.color.fg.tertiary,
  border: tokens.color.border.base,
  borderStrong: tokens.color.border.strong,
  cyan: tokens.color.cyan.base,
  ok: tokens.color.status.normal,
  warn: tokens.color.status.warning,
  crit: tokens.color.status.critical,
} as const;

export const fontSize = {
  xs: toNumber(tokens.fontSize.xs),
  sm: toNumber(tokens.fontSize.sm),
  base: toNumber(tokens.fontSize.base),
  md: toNumber(tokens.fontSize.md),
  lg: toNumber(tokens.fontSize.lg),
  xl: toNumber(tokens.fontSize.xl),
} as const;

export const space = {
  1: toNumber(tokens.space[1]),
  2: toNumber(tokens.space[2]),
  3: toNumber(tokens.space[3]),
  4: toNumber(tokens.space[4]),
  5: toNumber(tokens.space[5]),
  6: toNumber(tokens.space[6]),
} as const;

/**
 * [T-6.20] Objetivos táctiles. `min` es el alto mínimo de cualquier control;
 * `slopHasta` es la salida para los controles que viven DENTRO de una fila
 * densa —los chips de LLAMAR/VERIFICAR de un pase de lista de 200 personas—,
 * donde crecer el botón hasta el mínimo empujaría la lista fuera de pantalla:
 * el control se ve pequeño y el área que responde al dedo es la del mínimo.
 * El alto visible se le pasa desde su propio estilo, no a ojo, para que la
 * cuenta siga siendo cierta si alguien lo cambia.
 */
export const touch = {
  min: toNumber(tokens.touch.min),
} as const;

export function slopHasta(altoVisible: number): {
  top: number;
  bottom: number;
  left: number;
  right: number;
} {
  const s = Math.max(0, Math.ceil((touch.min - altoVisible) / 2));
  return { top: s, bottom: s, left: s, right: s };
}

export const radius = {
  sm: toNumber(tokens.radius.sm),
  md: toNumber(tokens.radius.md),
  lg: toNumber(tokens.radius.lg),
  pill: toNumber(tokens.radius.pill),
} as const;
