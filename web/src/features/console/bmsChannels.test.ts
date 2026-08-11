// [T-2.119] EL CHECKLIST BMS PINTA EL ESTADO DEL CANAL, NO LA ÚLTIMA ORDEN.
//
// `T-2.110` cerró la sirena y dejó escrito el hallazgo que gobierna esta ficha:
// **`siren_off` en la traza es la ORDEN EJECUTADA, no el relé**. Un `deactivate`
// arbitrado se ejecuta con éxito, escribe `siren_off` y deja la sirena sonando.
// Por eso el censo del relé viaja en el ACK (`channel_state`, `T-2.116`) y por
// eso derivar el estado del verbo —el arreglo obvio— habría creado una mentira
// nueva justo en el caso que la spec describe.
//
// Los otros cuatro canales tenían el mismo hueco, y son PEORES: «gas abierto» y
// «puertas liberadas» son afirmaciones de seguridad de vida. Si el checklist
// dice «CERRADAS» porque alguien mandó la orden y la válvula sigue abierta, eso
// es una mentira en la pantalla de la que depende una decisión.
//
// LA POLARIDAD, que es donde esta ficha podía introducir la mentira nueva: el
// gas es `FAIL_CLOSE` y el retenedor de puerta `NORMALLY_CLOSED`
// (`edge/takab_edge/config/settings.py · DEFAULT_FAILSAFE`), así que
// `energized` significa lo CONTRARIO que en la sirena. El contrato ya resuelve
// esto (`ChannelState`, `edge/takab_edge/contracts.py`): `activated` responde a
// «¿está protegiendo?» y es AGNÓSTICA de la polaridad. Se lee `activated`.
// Leer `energized` habría dicho «gas abierto» con el gas cortado.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  ACTION_STATE,
  ACTUATOR_CHANNELS,
  CHANNEL_LABEL,
  channelEvidence,
  groupActions,
  sirenEvidence,
  type IncidentActionOut,
} from "@takab/sdk";

function accion(
  kind: string,
  ts: string,
  payload: Record<string, unknown> = {},
): IncidentActionOut {
  return {
    action_id: `a-${kind}-${ts}`,
    incident_id: "i-1",
    tenant_id: "t-1",
    ts,
    kind,
    actor: "edge:gw-dev-0001",
    payload,
  } as IncidentActionOut;
}

/** Censo del relé tal y como lo emite el gabinete (schema compartido 1.11.0). */
function rele(channel: string, activated: boolean, energized = activated): Record<string, unknown> {
  return {
    channel_state: {
      channel,
      energized,
      activated,
      fail_safe: channel === "gas_valve" ? "fail_close" : channel === "door_retainer" ? "NC" : "NO",
      reason: null,
      alert_latched: false,
    },
  };
}

// ---------------------------------------------------------------------------
// CENSO: los kinds que el ingest ESCRIBE, no los que alguien creyó que escribía
// ---------------------------------------------------------------------------
//
// No es una lista a mano: se lee `ACK_KIND` del propio ingest. Esto no es celo —
// es el defecto que esta ficha encontró. `ACTION_STATE` daba de alta
// `gas_valve_close`, `elevator_recall` y `door_release`, y **ningún productor
// escribe jamás esos tres kinds**: el ingest escribe `gas_closed`,
// `elevator_recalled` y `door_released`. O sea que las tres filas de gas,
// ascensores y puertas del checklist llevaban desde T-1.50 cayendo en el
// fallback crudo — «GAS_CLOSED», en VERDE, con `kind: 'ok'`— y nadie lo vio
// porque los tests de la consola usaban los mismos nombres inventados.
//
// Es una LECTURA en tiempo de test (no un `import`): no añade una dependencia
// de build de la consola sobre `api/` — cf. `consoleImageCensus.test.ts`, que
// vigila justamente los imports que salen de `web/`.
const HANDLERS = resolve(process.cwd(), "..", "api", "src", "takab_api", "ingest", "handlers.py");

/** `("siren", "activate"): "siren_on",` → `[canal, accion, kind]`. */
export function ackKindDelIngest(fuente: string): [string, string, string][] {
  const bloque = fuente.split("ACK_KIND: dict[tuple[str, str], str] = {")[1]?.split("\n}")[0];
  if (bloque === undefined) {
    throw new Error(`ACK_KIND no encontrado en ${HANDLERS}: el contrato se movió, no está verde`);
  }
  const pares: [string, string, string][] = [];
  for (const m of bloque.matchAll(/\(\s*"(\w+)"\s*,\s*"(\w+)"\s*\)\s*:\s*"(\w+)"/g)) {
    pares.push([m[1], m[2], m[3]]);
  }
  return pares;
}

const ACK_KIND = ackKindDelIngest(readFileSync(HANDLERS, "utf8"));

describe("[T-2.119] censo · todo kind que el ingest escribe tiene vista propia", () => {
  it("el censo no está vacío (si esto falla, el resto de la suite miente)", () => {
    expect(ACK_KIND.length).toBeGreaterThanOrEqual(10);
  });

  it.each(ACK_KIND)(
    "(%s, %s) ⇒ `%s` está dado de alta y NO cae en el fallback",
    (canal, _a, kind) => {
      expect(ACTION_STATE[kind]).toBeDefined();
      // El fallback pinta el kind crudo en mayúsculas y en verde: eso es lo que
      // hacían gas, ascensores y puertas hasta esta ficha.
      expect(ACTION_STATE[kind].state).not.toBe(kind.toUpperCase());
      expect(CHANNEL_LABEL[kind]).toBe(ACTUATOR_CHANNELS[canal].label);
    },
  );

  it("cada kind del ingest pertenece al canal que lo emitió", () => {
    for (const [canal, , kind] of ACK_KIND) {
      expect(ACTUATOR_CHANNELS[canal].kinds).toHaveProperty(kind);
    }
  });
});

// ---------------------------------------------------------------------------
// UNA FILA POR CANAL: el `_off` cancela su `_on`
// ---------------------------------------------------------------------------
describe("[T-2.119] el `_off` cancela su grupo `_on`: una fila por CANAL", () => {
  const CASOS: [string, string, string, string, string][] = [
    // canal, kind protector, kind en reposo, etiqueta, estado esperado tras el _off
    ["siren", "siren_on", "siren_off", "SIRENA", "SILENCIADA"],
    ["strobe", "strobe_on", "strobe_off", "ESTROBO", "APAGADO"],
    ["gas_valve", "gas_closed", "gas_open", "VÁLVULAS DE GAS", "ABIERTAS"],
    ["elevator", "elevator_recalled", "elevator_released", "ELEVADORES", "LIBERADOS"],
    ["door_retainer", "door_released", "door_retained", "RETENEDORES DE PUERTA", "RETENIDOS"],
  ];

  it.each(CASOS)(
    "%s: activar y luego soltar deja UNA fila que dice «%s»",
    (canal, on, off, etiqueta, reposo) => {
      const grupos = groupActions([
        accion(on, "2026-08-11T10:00:00Z"),
        accion(off, "2026-08-11T10:05:00Z"),
      ]);
      expect(grupos).toHaveLength(1);
      expect(grupos[0].id).toBe(canal);
      expect(grupos[0].label).toBe(etiqueta);
      expect(grupos[0].view.state).toBe(reposo);
      // La traza completa sigue ahí: es evidencia, no se pierde al agrupar.
      expect(grupos[0].count).toBe(2);
      expect(grupos[0].trace.map((a) => a.kind)).toEqual([off, on]);
    },
  );

  it.each(CASOS)("%s: y al revés, soltar y volver a activar vuelve a protección", (_c, on, off) => {
    const grupos = groupActions([
      accion(off, "2026-08-11T10:00:00Z"),
      accion(on, "2026-08-11T10:05:00Z"),
    ]);
    expect(grupos).toHaveLength(1);
    expect(grupos[0].view.state).toBe(ACTION_STATE[on].state);
  });

  it("canales distintos NO se funden: cinco actuadores, cinco filas", () => {
    const grupos = groupActions([
      accion("siren_on", "2026-08-11T10:00:00Z"),
      accion("strobe_on", "2026-08-11T10:00:01Z"),
      accion("gas_closed", "2026-08-11T10:00:02Z"),
      accion("elevator_recalled", "2026-08-11T10:00:03Z"),
      accion("door_released", "2026-08-11T10:00:04Z"),
    ]);
    expect(grupos).toHaveLength(5);
    expect(new Set(grupos.map((g) => g.id)).size).toBe(5);
  });
});

// ---------------------------------------------------------------------------
// PRECEDENCIA: el relé recalculado manda sobre el verbo
// ---------------------------------------------------------------------------
describe("[T-2.119] el relé recalculado manda sobre la orden, en los cinco canales", () => {
  it("gas: la orden dice ABRIR y el gabinete declara el relé CERRADO ⇒ CERRADAS", () => {
    const grupos = groupActions([
      accion("gas_closed", "2026-08-11T10:00:00Z"),
      accion("gas_open", "2026-08-11T10:05:00Z", rele("gas_valve", true, false)),
    ]);
    expect(grupos[0].view.state).toBe("CERRADAS");
    expect(grupos[0].evidence).toEqual({
      active: true,
      fromRelay: true,
      at: "2026-08-11T10:05:00Z",
    });
  });

  it("POLARIDAD · `energized:false` en un canal FAIL_CLOSE no es «en reposo»", () => {
    // El gas desenergizado es el estado SEGURO: la válvula está CERRADA. Leer
    // `energized` en vez de `activated` habría pintado «ABIERTAS» con el gas
    // cortado — la mentira nueva que esta ficha tenía que no cometer.
    const evidencia = channelEvidence(
      [accion("gas_open", "2026-08-11T10:00:00Z", rele("gas_valve", true, false))],
      "gas_valve",
    );
    expect(evidencia).toEqual({ active: true, fromRelay: true, at: "2026-08-11T10:00:00Z" });
  });

  it("POLARIDAD · el retenedor `NORMALLY_CLOSED` se lee igual: manda `activated`", () => {
    const grupos = groupActions([
      accion("door_retained", "2026-08-11T10:00:00Z", rele("door_retainer", true, false)),
    ]);
    expect(grupos[0].view.state).toBe("LIBERADOS");
    expect(grupos[0].evidence?.fromRelay).toBe(true);
  });

  it("y la sirena, que es `NORMALLY_OPEN`, conserva su lectura de T-2.110", () => {
    const grupos = groupActions([
      accion("siren_off", "2026-08-11T10:00:00Z", rele("siren", true, true)),
    ]);
    expect(grupos[0].view.state).toBe("ACTIVADA");
    expect(grupos[0].view.kind).toBe("critical");
  });
});

// ---------------------------------------------------------------------------
// `null` = «no pude preguntar», jamás «en reposo»
// ---------------------------------------------------------------------------
describe("[T-2.119] `null` es «no consta», nunca «en reposo»", () => {
  it("un gabinete con firmware viejo (`channel_state: null`) degrada al verbo Y LO DICE", () => {
    const grupos = groupActions([
      accion("gas_closed", "2026-08-11T10:00:00Z", { channel_state: null }),
    ]);
    expect(grupos[0].view.state).toBe("CERRADAS");
    expect(grupos[0].evidence).toEqual({
      active: true,
      fromRelay: false, // ← lo que impide afirmar que el gabinete lo midió
      at: "2026-08-11T10:00:00Z",
    });
  });

  it("sin ninguna actuación del canal, no consta: `null`, no `false`", () => {
    expect(channelEvidence([], "gas_valve")).toBeNull();
    expect(channelEvidence([accion("ack", "2026-08-11T10:00:00Z")], "door_retainer")).toBeNull();
  });

  it("el censo de OTRO canal no se lee como propio", () => {
    // Un `channel_state` de sirena colado en una acción de gas no puede
    // decidir el estado del gas: se descarta y queda el verbo.
    const evidencia = channelEvidence(
      [accion("gas_open", "2026-08-11T10:00:00Z", rele("siren", true))],
      "gas_valve",
    );
    expect(evidencia).toEqual({ active: false, fromRelay: false, at: "2026-08-11T10:00:00Z" });
  });

  it("una acción SIMULADA no sostiene ni desmiente el estado del canal", () => {
    const acciones = [accion("gas_closed", "2026-08-11T10:00:00Z", { simulated: true })];
    expect(channelEvidence(acciones, "gas_valve")).toBeNull();
    // Y la fila lo declara simulada, no «CERRADAS».
    expect(groupActions(acciones)[0].view.state).toMatch(/SIMULADA/);
  });
});

// ---------------------------------------------------------------------------
// DESEMPATE: la lectura que NO tranquiliza
// ---------------------------------------------------------------------------
describe("[T-2.119] empate exacto de `ts`: gana la lectura que no tranquiliza", () => {
  it("sirena: gana SONANDO — no minimizar lo que está pasando (T-2.110)", () => {
    const grupos = groupActions([
      accion("siren_off", "2026-08-11T10:00:00Z"),
      accion("siren_on", "2026-08-11T10:00:00Z"),
    ]);
    expect(grupos[0].view.state).toBe("ACTIVADA");
  });

  it("estrobo: igual que la sirena, gana ACTIVADO", () => {
    const grupos = groupActions([
      accion("strobe_off", "2026-08-11T10:00:00Z"),
      accion("strobe_on", "2026-08-11T10:00:00Z"),
    ]);
    expect(grupos[0].view.state).toBe("ACTIVADO");
  });

  it("gas: gana ABIERTAS — jamás afirmar que el gas está cortado sin saberlo", () => {
    // Aquí la doctrina de la sirena se INVIERTE, y no aplanarla es la ficha:
    // en la sirena la lectura alarmante es «sigue sonando»; en el gas la
    // lectura alarmante es «sigue ABIERTO». Decir «CERRADAS» sin certeza es la
    // frase que hace que nadie vaya a cerrar la válvula.
    const grupos = groupActions([
      accion("gas_closed", "2026-08-11T10:00:00Z"),
      accion("gas_open", "2026-08-11T10:00:00Z"),
    ]);
    expect(grupos[0].view.state).toBe("ABIERTAS");
  });

  it("ascensores: gana LIBERADOS — puede haber gente en una cabina", () => {
    const grupos = groupActions([
      accion("elevator_recalled", "2026-08-11T10:00:00Z"),
      accion("elevator_released", "2026-08-11T10:00:00Z"),
    ]);
    expect(grupos[0].view.state).toBe("LIBERADOS");
  });

  it("puertas: gana RETENIDOS — la salida no está garantizada", () => {
    const grupos = groupActions([
      accion("door_released", "2026-08-11T10:00:00Z"),
      accion("door_retained", "2026-08-11T10:00:00Z"),
    ]);
    expect(grupos[0].view.state).toBe("RETENIDOS");
  });
});

// ---------------------------------------------------------------------------
// El contrato que móvil ya consume no se mueve
// ---------------------------------------------------------------------------
describe("[T-2.119] `sirenEvidence` sigue siendo exactamente lo que móvil consume", () => {
  it("misma forma EXACTA: {active, fromRelay, at} y nada más", () => {
    const e = sirenEvidence([accion("siren_on", "2026-08-10T10:00:00Z", rele("siren", false))]);
    // `toEqual` es estricto con las claves de más: móvil lo asserta así en
    // `estadoDelRele.test.tsx`, y un campo nuevo aquí lo pondría en rojo.
    expect(e).toEqual({ active: false, fromRelay: true, at: "2026-08-10T10:00:00Z" });
  });

  it("es `channelEvidence(_, 'siren')`, no una copia que pueda derivar", () => {
    const acciones = [
      accion("siren_on", "2026-08-10T10:00:00Z"),
      accion("siren_off", "2026-08-10T10:00:05Z", rele("siren", true)),
    ];
    expect(sirenEvidence(acciones)).toEqual(channelEvidence(acciones, "siren"));
  });

  it("una acción de gas no es evidencia de la sirena", () => {
    expect(sirenEvidence([accion("gas_closed", "2026-08-10T10:00:00Z")])).toBeNull();
  });
});
