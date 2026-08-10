// [T-2.75.a] LA MISMA REGLA EN LAS DOS SUPERFICIES.
//
// `incident_actions` se pinta en dos sitios y hasta hoy cada uno resolvía la
// bandera `simulated` a su manera:
//
//   · `@takab/sdk · bms.ts` (traza BMS de la consola y del panel táctico móvil)
//     prometía en su comentario que «la bandera del payload MANDA sobre el
//     mapa», pero el código consultaba el mapa PRIMERO: un `notify_sent` con
//     `payload.simulated: true` se pintaba «ENVIADA», en verde.
//   · `IncidentTimeline.kindLabel` (bitácora del incidente) sí daba prioridad a
//     la bandera y anotaba «SIMULADA, NADIE LA RECIBIÓ».
//
// El orquestador no escribe hoy esa combinación, así que era un defecto
// LATENTE — de los que se descubren el día que alguien añade un canal y una de
// las dos pantallas dice que el aviso salió. Se ancla aquí, con `kind`
// CONOCIDOS y la bandera puesta, que es justo el caso donde discrepaban: un
// kind desconocido caía en el fallback y coincidían por accidente.

import { describe, expect, it } from "vitest";

import { ACTION_STATE, SIMULATED_VIEW, groupActions, type IncidentActionOut } from "@takab/sdk";

import { kindLabel, type TimelineAction } from "./features/triage/IncidentTimeline";

/** Los `kind` que el mapa YA conoce: el caso en el que las dos discrepaban. */
const KINDS_CONOCIDOS = Object.keys(ACTION_STATE);

function bmsAction(kind: string, payload: Record<string, unknown>): IncidentActionOut {
  return {
    action_id: `a-${kind}`,
    incident_id: "i-1",
    tenant_id: "t-1",
    ts: "2026-07-10T03:14:00Z",
    kind,
    actor: "system:notify:sms:cascade",
    payload,
  } as IncidentActionOut;
}

function timelineAction(kind: string, payload: Record<string, unknown>): TimelineAction {
  return {
    action_id: `a-${kind}`,
    ts: "2026-07-10T03:14:00Z",
    kind,
    actor: "system:notify:sms:cascade",
    payload,
  };
}

describe("la bandera `simulated` manda sobre el mapa · en las DOS superficies", () => {
  it("el caso concreto: `notify_sent` con la bandera NO se lee como enviado", () => {
    expect(groupActions([bmsAction("notify_sent", { simulated: true })])[0].view).toEqual(
      SIMULATED_VIEW,
    );
    expect(kindLabel(timelineAction("notify_sent", { simulated: true }))).toMatch(/SIMULAD/);
  });

  it.each(KINDS_CONOCIDOS)(
    "kind CONOCIDO `%s` + bandera ⇒ ninguna de las dos afirma la entrega",
    (kind) => {
      const view = groupActions([bmsAction(kind, { simulated: true })])[0].view;
      const label = kindLabel(timelineAction(kind, { simulated: true }));

      // Traza BMS: la bandera gana al mapa, sin excepción por estar dado de alta.
      expect(view).toEqual(SIMULATED_VIEW);
      // Bitácora: el mismo veredicto, dicho con las palabras de una bitácora.
      expect(label).toMatch(/SIMULAD/);
    },
  );

  it.each(KINDS_CONOCIDOS)("kind CONOCIDO `%s` SIN bandera: nadie se contagia", (kind) => {
    expect(groupActions([bmsAction(kind, { simulated: false })])[0].view).toEqual(
      ACTION_STATE[kind],
    );
    expect(kindLabel(timelineAction(kind, { simulated: false }))).toBe(
      kindLabel(timelineAction(kind, {})),
    );
  });
});
