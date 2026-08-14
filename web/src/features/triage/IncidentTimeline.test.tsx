// [T-2.75] La bitácora del incidente es lo que un perito lee para reconstruir
// lo ocurrido. Si una notificación que nadie recibió se lee ahí como
// "NOTIFICACIÓN ENVIADA", la evidencia miente — y `incident_actions` es
// justamente la tabla exenta de poda por retención.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ACTION_STATE, ACTUATOR_CHANNELS, CHANNEL_LABEL } from "@takab/sdk";

import { verbosDeNotificacion } from "../../test-utils/incidentActionKinds";
import IncidentTimeline, { kindLabel, type TimelineAction } from "./IncidentTimeline";

function action(kind: string, payload: Record<string, unknown> = {}): TimelineAction {
  return {
    action_id: `a-${kind}`,
    ts: "2026-07-10T03:14:00Z",
    kind,
    actor: "system:notify:sms:cascade",
    payload,
  };
}

function renderTimeline(data: TimelineAction[], staleSince: number | null = null) {
  render(
    <IncidentTimeline
      actions={{ data, loading: false, error: null, staleSince }}
      onRetry={vi.fn()}
    />,
  );
}

/** 2026-08-03 10:41:30 UTC — la hora que el marco tiene que imprimir. */
const HORA = Date.UTC(2026, 7, 3, 10, 41, 30);

describe("kindLabel · enviada ≠ simulada ≠ no entregada", () => {
  it("da tres verbos DISTINTOS, y solo uno dice que se envió", () => {
    const sent = kindLabel(action("notify_sent"));
    const simulated = kindLabel(action("notify_simulated", { simulated: true }));
    const failed = kindLabel(action("notify_failed"));
    expect(new Set([sent, simulated, failed]).size).toBe(3);
    expect(sent).toContain("ENVIADA");
    expect(simulated).not.toContain("ENVIADA");
    expect(failed).not.toContain("ENVIADA");
  });

  it("delata la simulación por el PAYLOAD, no por una lista de kinds", () => {
    // El kind es inventado a propósito: representa el canal que todavía no
    // existe. Una lista de rótulos se queda ciega ante el siguiente; la
    // bandera que el servidor ya escribe, no.
    const label = kindLabel(action("notify_canal_del_futuro", { simulated: true }));
    expect(label).toMatch(/SIMULAD/);
    expect(label).not.toContain("ENVIADA");
  });

  it("no contagia a una acción sin bandera", () => {
    expect(kindLabel(action("ack"))).toBe("ACUSE DE OPERADOR");
    expect(kindLabel(action("notify_sent", { simulated: false }))).not.toMatch(/SIMULAD/);
  });
});

// ---------------------------------------------------------------------------
// [T-2.133] LOS VERBOS DE NOTIFICACIÓN, DERIVADOS DEL ORQUESTADOR
// ---------------------------------------------------------------------------
//
// `T-2.75` dejó tres verbos rotulados aquí a mano y `T-2.109` añadió un CUARTO
// —`notify_no_recipients`: el proveedor existe y entrega, pero en ese inmueble
// no hay ningún teléfono registrado al que despertar— sin que ninguna de las dos
// superficies lo rotulara. En la bitácora que un perito lee salía
// «NOTIFY_NO_RECIPIENTS»; en el checklist BMS, en VERDE.
//
// El censo se lee de las constantes `_KIND_*` del propio orquestador: el quinto
// verbo entrará solo o pondrá esto en rojo.
describe("[T-2.133] la bitácora rotula TODOS los verbos de notificación", () => {
  const VERBOS = verbosDeNotificacion();

  it("el censo trae el cuarto verbo de `T-2.109`", () => {
    expect(VERBOS).toContain("notify_no_recipients");
  });

  it.each(VERBOS)("`%s` no sale crudo en la bitácora", (verbo) => {
    expect(kindLabel(action(verbo))).not.toBe(verbo.toUpperCase());
  });

  it("y sólo UNO de los cuatro afirma que se envió", () => {
    const rotulos = VERBOS.map((v) => kindLabel(action(v)));
    expect(new Set(rotulos).size).toBe(VERBOS.length);
    expect(rotulos.filter((r) => r.includes("ENVIADA"))).toHaveLength(1);
  });

  it("«sin destinatarios» se lee como lo que es: nadie lo recibió", () => {
    const rotulo = kindLabel(action("notify_no_recipients"));
    expect(rotulo).toMatch(/SIN DESTINATARIOS/);
    expect(rotulo).not.toContain("ENVIADA");
  });
});

// ---------------------------------------------------------------------------
// [T-2.127] LOS DIEZ KINDS DE ACTUADOR TIENEN RÓTULO, Y SALE DEL MISMO REGISTRO
// ---------------------------------------------------------------------------
//
// `KIND_LABEL` rotulaba `siren_on`/`siren_off` y NADA MÁS: los otros ocho kinds
// de actuador caían en el fallback crudo y la bitácora —lo que un perito lee
// para reconstruir lo ocurrido— decía «GAS_CLOSED». `T-2.119` ya pagó el precio
// de tener dos listas: `ACTION_STATE` daba de alta tres nombres que ningún
// productor escribe jamás, y las filas de gas, ascensores y puertas llevaban
// meses en verde diciendo «todo bien».
//
// Por eso el censo NO es una lista a mano: se deriva de `ACTUATOR_CHANNELS`, el
// mismo registro del que salen `ACTION_STATE` y `CHANNEL_LABEL` para el
// checklist BMS. Un canal nuevo entra solo; un canal renombrado arrastra a la
// bitácora con él.
const KINDS_DE_ACTUADOR: string[] = Object.values(ACTUATOR_CHANNELS).flatMap((spec) => [
  ...Object.keys(spec.kinds),
  // Los tres nombres que ningún productor escribió nunca siguen en el registro
  // porque `incident_actions` es append-only y exenta de poda: una fila de 2026
  // tiene que seguir rotulándose dentro de diez años.
  ...Object.keys(spec.legacyKinds),
]);

describe("[T-2.127] la bitácora rotula los diez kinds de actuador", () => {
  it("el censo no está vacío (si esto falla, el resto de este bloque miente)", () => {
    expect(KINDS_DE_ACTUADOR.length).toBeGreaterThanOrEqual(10);
  });

  it.each(KINDS_DE_ACTUADOR)("`%s` no sale crudo en la bitácora", (kind) => {
    // El fallback es `kind.toUpperCase()`: «GAS_CLOSED», que a un operador no le
    // dice lo mismo que «VÁLVULAS DE GAS CERRADAS».
    expect(kindLabel(action(kind))).not.toBe(kind.toUpperCase());
  });

  it.each(KINDS_DE_ACTUADOR)("`%s` DERIVA su rótulo del registro del checklist", (kind) => {
    // Canal + vocabulario del canal: ni una palabra escrita a mano aquí. Si
    // alguien reescribe «VÁLVULAS DE GAS» o «CERRADAS» en `ACTUATOR_CHANNELS`,
    // la bitácora lo sigue; si alguien añade una segunda lista, esto se pone
    // rojo.
    expect(kindLabel(action(kind))).toBe(`${CHANNEL_LABEL[kind]} ${ACTION_STATE[kind].state}`);
  });

  it("el caso que abrió la ficha: «GAS_CLOSED» pasa a leerse en castellano", () => {
    expect(kindLabel(action("gas_closed"))).toBe("VÁLVULAS DE GAS CERRADAS");
  });

  it("los dos rótulos de sirena que ya existían NO cambian", () => {
    // Se borraron de la lista a mano y ahora se derivan: el texto tiene que ser
    // el MISMO, byte a byte, o esto es una regresión disfrazada de refactor.
    expect(kindLabel(action("siren_on"))).toBe("SIRENA ACTIVADA");
    expect(kindLabel(action("siren_off"))).toBe("SIRENA SILENCIADA");
  });

  it("cada canal da rótulos DISTINTOS a su orden protectora y a la de reposo", () => {
    for (const spec of Object.values(ACTUATOR_CHANNELS)) {
      const rotulos = Object.keys(spec.kinds).map((k) => kindLabel(action(k)));
      expect(new Set(rotulos).size).toBe(rotulos.length);
    }
  });

  it("una orden de actuador SIMULADA sigue delatándose", () => {
    expect(kindLabel(action("gas_closed", { simulated: true }))).toMatch(/SIMULAD/);
  });

  // -------------------------------------------------------------------------
  // LA BITÁCORA ES CRONOLÓGICA: CADA LÍNEA ES UNA ORDEN, NO UN ESTADO
  // -------------------------------------------------------------------------
  it("NO aplica la lógica de estado del checklist: el relé no reescribe la línea", () => {
    // `T-2.119` hizo que el CHECKLIST prefiera `payload.channel_state` sobre el
    // verbo, porque una fila del checklist afirma «cómo está el canal AHORA».
    // Una línea de la bitácora afirma otra cosa: «a esta hora se ejecutó esta
    // orden». Dejar que el censo del relé cambiara el rótulo convertiría la
    // bitácora en un estado con marca de tiempo — y una bitácora que reescribe
    // sus líneas deja de ser evidencia.
    const conRele = action("siren_off", {
      channel_state: {
        channel: "siren",
        energized: true,
        activated: true,
        fail_safe: "NO",
        reason: null,
        alert_latched: true,
      },
    });
    expect(kindLabel(conRele)).toBe("SIRENA SILENCIADA");
  });
});

describe("IncidentTimeline", () => {
  it("pinta la fila simulada con marca propia, no como una acción cualquiera", () => {
    renderTimeline([action("notify_simulated", { simulated: true })]);
    const row = screen.getByText(/SIMULAD/);
    expect(row.className).toContain("timeline__kind--undelivered");
  });

  it("una notificación entregada NO lleva la marca", () => {
    renderTimeline([action("notify_sent", { deadline_met: true })]);
    const row = screen.getByText("NOTIFICACIÓN ENVIADA");
    expect(row.className).not.toContain("timeline__kind--undelivered");
  });

  it("[T-2.133] «sin destinatarios» lleva la marca: tampoco llegó a nadie", () => {
    // La marca no es «hubo una avería», es «esto no llegó a nadie». Un sitio sin
    // teléfonos registrados es exactamente ese caso, y sin la marca la línea se
    // leía igual que una entrega buena.
    renderTimeline([action("notify_no_recipients", { tokens_del_sitio: 0 })]);
    const row = screen.getByText(/SIN DESTINATARIOS/);
    expect(row.className).toContain("timeline__kind--undelivered");
  });
});

describe("IncidentTimeline · una bitácora vieja no es la bitácora [T-2.82.a]", () => {
  it("con el dato viejo lo dice, y sigue enseñando lo que sí llegó", () => {
    // La bitácora es la reconstrucción de lo ocurrido que se lee ANTES de
    // firmar. Una reconstrucción a la que le faltan las últimas acciones porque
    // el enlace se cayó, presentada como completa, es una reconstrucción falsa
    // de un incidente — y aquí se firma encima.
    renderTimeline([action("ack")], HORA);
    const panel = screen.getByTestId("incident-timeline");
    expect(panel).toHaveTextContent("DATOS RETENIDOS · 10:41:30 UTC");
    expect(panel).toHaveTextContent("ACUSE DE OPERADOR");
  });

  it("bitácora VACÍA y vieja: la ausencia se FECHA, no se afirma en presente", () => {
    // El par en disputa de T-2.79.d. "SIN ACCIONES REGISTRADAS PARA ESTE
    // INCIDENTE" afirma un hecho sobre el mundo que la consola no puede
    // comprobar si lleva un cuarto de hora sin respuesta.
    renderTimeline([], HORA);
    const panel = screen.getByTestId("incident-timeline");
    expect(panel).toHaveTextContent("SIN ACCIONES REGISTRADAS PARA ESTE INCIDENTE");
    expect(panel).toHaveTextContent("así estaba a las 10:41:30 UTC");
    expect(panel).toHaveTextContent("desde entonces no se ha podido confirmar");
  });

  it("con el dato fresco, la bitácora vacía se afirma tal cual", () => {
    renderTimeline([]);
    const panel = screen.getByTestId("incident-timeline");
    expect(panel).toHaveTextContent("SIN ACCIONES REGISTRADAS PARA ESTE INCIDENTE");
    expect(panel).not.toHaveTextContent("DATOS RETENIDOS");
  });
});
