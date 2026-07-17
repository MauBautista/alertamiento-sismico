// "datos de hace X min" (contrato StateFrame): edad HONESTA del dato, jamás
// negativa (un reloj adelantado no convierte datos viejos en frescos).
export function timeAgoLabel(sinceMs: number, nowMs: number): string {
  const s = Math.max(0, Math.floor((nowMs - sinceMs) / 1000));
  if (s < 60) {
    return "hace segundos";
  }
  const m = Math.floor(s / 60);
  if (m < 60) {
    return `hace ${m} min`;
  }
  const h = Math.floor(m / 60);
  if (h < 24) {
    return `hace ${h} h`;
  }
  return `hace ${Math.floor(h / 24)} d`;
}
