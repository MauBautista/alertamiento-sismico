/** Utilidades de tiempo del SOC (los relojes de tablas y banners van en UTC). */

/** HH:MM:SS UTC de un instante epoch-ms. */
export function utcClock(epochMs: number): string {
  return new Date(epochMs).toISOString().slice(11, 19);
}

/** `YYYY-MM-DD · HH:MM` UTC — sello del historial, donde el día importa. */
export function utcStamp(epochMs: number): string {
  const iso = new Date(epochMs).toISOString();
  return `${iso.slice(0, 10)} · ${iso.slice(11, 16)}`;
}

/** Segundos enteros transcurridos entre un instante y "ahora" (nunca negativo). */
export function secondsSince(epochMs: number, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - epochMs) / 1000));
}

/** Escalones de la edad, del más fino al más grueso. DERIVADO, no enumerado: una
 * magnitud nueva (mil días) cae sola en la unidad más gruesa en vez de necesitar
 * un caso más. */
const AGE_UNITS: ReadonlyArray<{ secs: number; suffix: string }> = [
  { secs: 86_400, suffix: "d" },
  { secs: 3_600, suffix: "h" },
  { secs: 60, suffix: "min" },
  { secs: 1, suffix: "s" },
];

/**
 * [T-2.69] EDAD de un dato en segundos → rótulo corto (`"3 s"`, `"12 min"`, `"21 d"`).
 *
 * La web solo sabía pintar la HORA de un dato (`utcClock` → "HB 14:32 UTC"), y una
 * hora no responde la pregunta que importa delante de una tarjeta: *¿esto de
 * cuándo es?* Un "14:32 UTC" se lee igual de fresco si es de hoy o de hace tres
 * semanas.
 *
 * `null`/`undefined` ⇒ `S/D`, **nunca `"0 s"`**: un cero se lee como "recién
 * visto", que es exactamente la mentira que separa "no hay dato" de "el dato es
 * fresco" (regla de oro 7).
 */
export function ageLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "S/D";
  const s = Math.max(0, Math.floor(seconds));
  const unit = AGE_UNITS.find((u) => s >= u.secs) ?? AGE_UNITS[AGE_UNITS.length - 1];
  return `${Math.floor(s / unit.secs)} ${unit.suffix}`;
}

/**
 * `+M:SS` (o `+H:MM:SS`), o `null` cuando no hay latencia que enseñar.
 *
 * [T-5.14 → T-5.15] Nació en `features/console/drill.ts` para el acuse de un
 * simulacro y la usa también la bitácora del incidente: el transcurrido de un
 * simulacro y el de un incidente son la MISMA magnitud, y dos formatos para
 * ella acabarían divergiendo en la pantalla donde se comparan.
 *
 * `null` para lo que no se puede contar, y NUNCA `"+0:00"`: un cero afirma
 * «ocurrió al instante», que es lo contrario de «no ocurrió».
 */
export function latenciaLegible(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return null;
  // Negativo = el reloj del servidor se movió entre emisión y acuse. No es una
  // respuesta anticipada: es un dato roto, y se calla en vez de pintarse.
  if (seconds < 0) return null;
  const total = Math.round(seconds);
  const s = String(total % 60).padStart(2, "0");
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  return h > 0 ? `+${h}:${String(m).padStart(2, "0")}:${s}` : `+${m}:${s}`;
}
