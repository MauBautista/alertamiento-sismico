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

export const radius = {
  sm: toNumber(tokens.radius.sm),
  md: toNumber(tokens.radius.md),
  lg: toNumber(tokens.radius.lg),
  pill: toNumber(tokens.radius.pill),
} as const;
