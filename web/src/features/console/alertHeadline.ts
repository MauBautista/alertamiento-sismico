// Titular y atribución del banner de alerta del SOC — DERIVADOS del `trigger`.
//
// [T-5.03] Espejo consciente de `mobile/src/features/alert/source.ts`, y por la
// misma razón que aquél: **el titular es una atribución**, no un rótulo. Dice
// quién dijo que hay que protegerse, y esa es la afirmación más grande de la
// pantalla.
//
// Antes de esta ficha el banner llevaba dos textos escritos a fuego —el titular
// y la línea `EDGE · RS4D · REGLAS LOCALES EJECUTADAS · ● AUTO`— para las cuatro
// fuentes. Consecuencias medidas en la auditoría del 2026-09-02: un quórum de
// pánico (`trigger='manual'`, crítico por D-11) salía en el videowall como una
// ALERTA SÍSMICA ejecutada por el RS4D. Dos mentiras en una caja: ni era sísmica
// ni la ejecutó el sensor. Y la app móvil, para ese mismo incidente, pintaba
// «NO ES UNA ALERTA SÍSMICA».
//
// Los literales NO se eligen aquí: los declara `shared/glossary/estados.json`
// (`titulares_de_alerta`), que es la única copia que comparten la consola, la app
// y el panel del gabinete. `alertHeadline.test.ts` compara este módulo contra el
// glosario por igualdad, y `edge/tests/test_glosario_de_estados.py` ata el
// glosario al CHECK de `incidents.trigger` de la base y a las otras dos
// superficies. Cambiar una palabra aquí sin cambiarla allí pone el build en rojo.

/** Los cuatro que admite `incidents.trigger` (CHECK en `db/schema.sql`). */
export type AlertTrigger = "sasmex" | "local_threshold" | "quorum" | "manual";

export interface AlertHeadline {
  /** Titular: QUÉ está pasando y a quién se le atribuye. */
  title: string;
  /** Línea de procedencia: por qué camino llegó. */
  attribution: string;
  /** Píldora corta del modo de actuación. */
  pill: string;
  /** ¿Es una alerta SÍSMICA? Una activación manual no lo es. */
  seismic: boolean;
  /** ¿Nadie mapeó este trigger? Entonces no se atribuye nada a nadie. */
  unknown: boolean;
}

const MAPA: Record<AlertTrigger, Omit<AlertHeadline, "unknown">> = {
  // El contacto seco ES la alerta oficial: la única fuente que puede llevarse
  // ese nombre, y el único titular que el documento de entrega cita literal.
  sasmex: {
    title: "ALERTA SÍSMICA · PROTÉJASE",
    attribution: "EDGE · SASMEX WR-1 · REFLEJO LOCAL EJECUTADO",
    pill: "● AUTO",
    seismic: true,
  },
  // T-2.32: una sola estación NO actúa. Decir «PROTÉJASE» aquí sería prometer
  // una actuación que la política ratificada prohíbe.
  local_threshold: {
    title: "AVISO SÍSMICO · UMBRAL INSTRUMENTAL",
    attribution: "EDGE · RS4D · SOLO AVISO, SIN ACTUACIÓN",
    pill: "● AVISO",
    seismic: true,
  },
  quorum: {
    title: "SISMO CONFIRMADO POR LA RED",
    attribution: "RED · CUÓRUM DE INMUEBLES · COMANDO FIRMADO",
    pill: "● AUTO",
    seismic: true,
  },
  // Ni sísmica ni oficial: alguien la activó. Es el caso que rompía.
  manual: {
    title: "ALERTA ACTIVADA MANUALMENTE",
    attribution: "MANUAL · ACTIVACIÓN HUMANA",
    pill: "● MANUAL",
    seismic: false,
  },
};

export function alertHeadline(trigger: string | null | undefined): AlertHeadline {
  const conocido = trigger != null ? MAPA[trigger as AlertTrigger] : undefined;
  if (conocido !== undefined) {
    return { ...conocido, unknown: false };
  }
  // Fuente no reconocida. Caer al caso sísmico es lo que convierte un olvido en
  // una afirmación falsa, así que no se cae: se nombra el trigger crudo y no se
  // atribuye a nadie. El build lo caza antes que el operador — el censo compara
  // el mapa de arriba contra el CHECK de la base por igualdad.
  return {
    title: "ALERTA ACTIVA · ORIGEN NO RECONOCIDO",
    attribution: `ORIGEN · ${trigger != null ? trigger.toUpperCase() : "S/D"}`,
    pill: "● S/D",
    seismic: false,
    unknown: true,
  };
}
