// [T-5.03] EL TITULAR DEL BANNER ES UNA ATRIBUCIÓN, y se DERIVA del `trigger`.
//
// El defecto que cierra, medido en la auditoría V1-COMERCIAL del 2026-09-02:
// `ConsolePage` elegía el incidente a destacar sólo por `severity === "critical"`
// y `AlertBanner` llevaba DOS textos escritos a fuego —«ALERTA SÍSMICA ·
// PROTÉJASE» y «EDGE · RS4D · REGLAS LOCALES EJECUTADAS · ● AUTO»— sin mirar el
// `trigger` ni una vez. Un quórum de pánico (`trigger='manual'`, severidad
// crítica por D-11) salía por tanto como una alerta sísmica ejecutada por el
// sensor, mientras la app móvil pintaba «NO ES UNA ALERTA SÍSMICA» para EL MISMO
// incidente. Es el defecto de T-2.104 —ya corregido en el móvil— reintroducido
// del lado de la consola, y la lección de entonces vuelve a aplicar tal cual: un
// componente presentacional puede llevar una mentira a fuego que ninguna prueba
// de la lógica alcanza.
//
// Por qué el censo va contra el GLOSARIO y no contra una lista de aquí: el
// glosario es la única copia que las tres superficies comparten, y
// `edge/tests/test_glosario_de_estados.py` lo ata por su parte al CHECK de
// `incidents.trigger` en la base y a los literales del panel y del móvil. Una
// lista escrita en este fichero sólo se compararía consigo misma.
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { alertHeadline } from "./alertHeadline";

const RAIZ = resolve(process.cwd(), "..");
const GLOSARIO = JSON.parse(
  readFileSync(join(RAIZ, "shared", "glossary", "estados.json"), "utf-8"),
) as {
  titulares_de_alerta: {
    detecta_sismica: string[];
    por_trigger: Record<string, { es_sismica: boolean; es_oficial: boolean; consola: string }>;
    desconocido: { es_sismica: boolean; consola: string };
  };
};

const TITULARES = GLOSARIO.titulares_de_alerta;
const TRIGGERS = Object.keys(TITULARES.por_trigger).sort();

describe("alertHeadline · el titular sale del trigger, no de la severidad", () => {
  it("el glosario declara los cuatro triggers, y no se lee vacío", () => {
    // Guarda de no-vacuidad: sin esto, un glosario sin `por_trigger` dejaría en
    // verde todos los casos parametrizados de abajo por no tener ninguno.
    expect(TRIGGERS.length).toBe(4);
    expect(TRIGGERS).toEqual(["local_threshold", "manual", "quorum", "sasmex"]);
  });

  it("cubre EXACTAMENTE los triggers del glosario: ni uno de más, ni uno de menos", () => {
    const cubiertos = TRIGGERS.filter((t) => !alertHeadline(t).unknown).sort();
    expect(cubiertos).toEqual(TRIGGERS);
  });

  it.each(TRIGGERS)("%s titula con el término que le asigna el glosario", (trigger) => {
    expect(alertHeadline(trigger).title).toBe(TITULARES.por_trigger[trigger].consola);
  });

  it.each(TRIGGERS)("%s declara si es sísmica igual que el glosario", (trigger) => {
    expect(alertHeadline(trigger).seismic).toBe(TITULARES.por_trigger[trigger].es_sismica);
  });

  it.each(TRIGGERS)(
    "%s: un trigger NO sísmico no puede titularse ni atribuirse como sísmico",
    (trigger) => {
      const h = alertHeadline(trigger);
      if (h.seismic) return;
      const texto = `${h.title} ${h.attribution} ${h.pill}`;
      for (const raiz of TITULARES.detecta_sismica) {
        expect(texto).not.toContain(raiz);
      }
    },
  );

  it("SÓLO el contacto del WR-1 se lleva el nombre del servicio oficial", () => {
    const conSasmex = TRIGGERS.filter((t) =>
      `${alertHeadline(t).title} ${alertHeadline(t).attribution}`.includes("SASMEX"),
    );
    expect(conSasmex).toEqual(["sasmex"]);
  });

  it("un trigger que nadie mapeó NO cae a «alerta sísmica»: se rotula desconocido", () => {
    const h = alertHeadline("teletransporte");
    expect(h.unknown).toBe(true);
    expect(h.seismic).toBe(false);
    expect(h.title).toBe(TITULARES.desconocido.consola);
    // Nombra el trigger crudo — no atribuye, pero tampoco lo esconde.
    expect(h.attribution).toContain("TELETRANSPORTE");
    for (const raiz of TITULARES.detecta_sismica) {
      expect(`${h.title} ${h.attribution}`).not.toContain(raiz);
    }
  });

  it("sin trigger (dato ausente) tampoco inventa una alerta sísmica", () => {
    const h = alertHeadline(null);
    expect(h.unknown).toBe(true);
    expect(h.seismic).toBe(false);
    expect(h.attribution).toContain("S/D");
  });
});
