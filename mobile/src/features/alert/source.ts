// Etiqueta de FUENTE del evento (spec §2.1-A) — solo datos REALES del payload:
//   sasmex          → booleano del WR-1: SIN magnitud, SIN epicentro, SIN ETA.
//   local_threshold → PGA instrumental MEDIDO por el gabinete (si ya existe).
//   quorum          → estaciones corroborantes (meta.node_count, mismo dato
//                     que el pill "CONFIRMADO · N estaciones" del Triage).
//   manual          → activación manual.
// Desconocido ⇒ el trigger crudo en mayúsculas — jamás inventar.

export type SourceInput = {
  trigger: string;
  max_pga_g: number | null;
  node_count: number | null;
};

export type SourceLabel = {
  /** Titular de la toma de crisis: A QUIÉN se atribuye la alerta.
   *
   * [T-2.104] Vive aquí y no en la vista porque es la MISMA decisión que la
   * etiqueta de abajo: de dónde viene esto. `CrisisView` lo tenía escrito a
   * fuego como «ALERTA SÍSMICA SASMEX` para las cuatro fuentes, así que un
   * umbral instrumental de una sola estación —o una activación manual— le decía
   * a todo el edificio, en el texto más grande de la pantalla, que había
   * alertado el servicio oficial. Medido el 2026-08-09: al mover el sensor con
   * la mano, la app tituló «ALERTA SÍSMICA SASMEX» mientras la píldora de abajo
   * decía, correctamente, «FUENTE · REGLAS LOCALES».
   *
   * Por qué importa más de lo que parece: TAKAB **no genera** la alerta oficial
   * —la recibe— y el documento de entrega deslinda explícitamente la cobertura y
   * los falsos positivos de SASMEX. Atribuirle una detección propia invierte ese
   * deslinde: el día que el umbral local se dispare de más, el ocupante culpa a
   * SASMEX. Y choca con la política ratificada en T-2.32, que degradó la
   * detección instrumental de una sola estación a AVISO precisamente porque una
   * estación sola no es autoridad. */
  title: string;
  /** Antetítulo: QUÉ CLASE de alerta es. Una activación manual no es sísmica. */
  eyebrow: string;
  label: string;
  /** Dato adicional REAL (PGA medido / estaciones) o null. */
  detail: string | null;
};

const SISMICA = "● ALERTA SÍSMICA ACTIVA";

/** PGA legible: ≥0.01g con 2 decimales; menor, en mg (piso MEMS 0.6-1.1 mg). */
export function formatPga(pgaG: number): string {
  if (pgaG >= 0.01) {
    return `${pgaG.toFixed(2)}g`;
  }
  return `${(pgaG * 1000).toFixed(1)}mg`;
}

export function sourceLabel(input: SourceInput): SourceLabel {
  switch (input.trigger) {
    case "sasmex":
      // Contacto seco = booleano. Nada más que decir — y eso ES lo honesto.
      // ES el único caso que puede titular con el nombre del servicio oficial.
      return {
        title: "ALERTA SÍSMICA SASMEX",
        eyebrow: SISMICA,
        label: "FUENTE · SASMEX WR-1",
        detail: null,
      };
    case "local_threshold":
      return {
        title: "SISMO DETECTADO EN ESTE EDIFICIO",
        eyebrow: SISMICA,
        label: "FUENTE · REGLAS LOCALES",
        detail:
          input.max_pga_g != null
            ? `PGA ${formatPga(input.max_pga_g)} MEDIDO`
            : null,
      };
    case "quorum":
      return {
        title: "SISMO CONFIRMADO POR LA RED",
        eyebrow: SISMICA,
        label: "FUENTE · CUÓRUM DE RED",
        detail:
          input.node_count != null
            ? `CONFIRMADO · ${input.node_count} ESTACIONES`
            : null,
      };
    case "manual":
      // NI sísmica ni oficial: alguien la activó. El antetítulo lo dice.
      return {
        title: "ALERTA ACTIVADA MANUALMENTE",
        eyebrow: "● ALERTA ACTIVA",
        label: "FUENTE · ACTIVACIÓN MANUAL",
        detail: null,
      };
    default:
      // Fuente desconocida: se nombra el trigger crudo y NO se atribuye a nadie.
      //
      // [T-5.03] Y tampoco se titula como sismo. Hasta el 2026-09-02 este caso
      // devolvía «ALERTA SÍSMICA» con el antetítulo sísmico: un trigger nuevo
      // —el quinto que alguien añada al CHECK de `incidents.trigger`— habría
      // salido en la pantalla más grande del teléfono afirmando que hubo un
      // sismo, sin que nadie lo hubiera dicho. Caer al caso sísmico es lo que
      // convierte un olvido en una afirmación falsa.
      return {
        title: "ALERTA ACTIVA · ORIGEN NO RECONOCIDO",
        eyebrow: "● ALERTA ACTIVA",
        label: `FUENTE · ${input.trigger.toUpperCase()}`,
        detail: null,
      };
  }
}
