// [T-2.144] OCHO VERBOS REALES SE PINTABAN CRUDOS Y EN VERDE, Y UNO DECÍA
// «DAMAGE PEOPLE AT RISK».
//
// `T-2.119` cerró los diez kinds de ACTUADOR y `T-2.133` el cuarto verbo de
// notificación. Quedaba una familia entera sin rotular —ciclo de vida, dictamen,
// pase de lista, inspección— cayendo en el fallback `{ kind: 'ok' }`: VERDE.
// Entre ellos, el que un brigadista escribe al reportar personas atrapadas.
//
// LA PREGUNTA QUE ABRE ESTA FICHA no es cuáles faltan, es **cómo se garantiza
// que el siguiente no falte**. `T-2.133` dejó escrito que el censo en dirección
// productor→registro «no se puede hacer con un barrido honesto», porque
// `headcount_*` los fija un router sobre una sentencia de otro módulo y
// `lifecycle.py` los saca de un `dict`. Era cierto del barrido que buscaba el
// NOMBRE. Este fichero hace el otro: barre el repo entero buscando lo único
// decidible —quién ejecuta un `INSERT INTO incident_actions`—, saca la
// expresión de la columna `kind` POSICIONALMENTE y la resuelve con reglas
// derivadas de código declarado. Lo que no sabe resolver, lo pone en rojo con su
// fichero delante.
//
// Y el resultado inmediato de barrer el repo y no `api/src`: los productores no
// eran siete, eran OCHO. El octavo (`notify_delivered`) lo escribe la función
// PL/pgSQL `app_notify_delivery` desde el webhook del proveedor, y no hay barrido
// de `api/src` —honesto o no— que pueda verlo.

import { describe, expect, it } from "vitest";

import {
  ACTION_STATE,
  ACTUATOR_CHANNELS,
  CHANNEL_LABEL,
  INCIDENT_ACTION_KINDS,
  UNCLASSIFIED_VIEW,
  groupActions,
  type IncidentActionOut,
} from "@takab/sdk";

import {
  PRODUCTORES_EXENTOS,
  destinosDeCicloDeVida,
  ficherosProductores,
  ficherosProductoresDelRepo,
  kindsDeCicloDeVida,
  kindsDeProductores,
  sentenciasProductoras,
} from "../../test-utils/incidentActionKinds";
import { kindLabel } from "../triage/IncidentTimeline";

const KINDS = kindsDeProductores();

function accion(kind: string, payload: Record<string, unknown> = {}): IncidentActionOut {
  return {
    action_id: `a-${kind}`,
    incident_id: "i-1",
    tenant_id: "t-1",
    ts: "2026-08-14T03:14:00Z",
    kind,
    actor: "user:00000000-0000-0000-0000-000000000001",
    payload,
  } as IncidentActionOut;
}

// ---------------------------------------------------------------------------
// EL BARRIDO: ningún productor fuera del corpus, ninguna sentencia sin resolver
// ---------------------------------------------------------------------------
describe("[T-2.144] el barrido de productores no tiene puntos ciegos", () => {
  it("todo fichero del REPO que inserte en la tabla está barrido o declarado exento", () => {
    // Ésta es la aserción que habría cazado al octavo productor el día que
    // nació: `db/schema.sql` y la migración `0040` insertan en la tabla y
    // vivían fuera del único directorio que el censo miraba (`api/src`).
    const barridos = new Set(ficherosProductores());
    const huerfanos = ficherosProductoresDelRepo().filter(
      (f) => !barridos.has(f) && PRODUCTORES_EXENTOS[f] === undefined,
    );
    expect(huerfanos, "productor sin barrer ni declarar exento").toEqual([]);
  });

  it("el corpus incluye a los productores que NO son `api/src`", () => {
    // Sin esto, un refactor que estreche las raíces del barrido volvería a dejar
    // la función PL/pgSQL fuera y el test seguiría verde.
    expect(ficherosProductores()).toContain("db/schema.sql");
    expect(ficherosProductores()).toContain(
      "api/migrations/versions/0040_notify_delivery_receipts.py",
    );
  });

  it("cada exención declara su razón, no sólo su ruta", () => {
    for (const [ruta, razon] of Object.entries(PRODUCTORES_EXENTOS)) {
      expect(razon.length, `exención sin razón: ${ruta}`).toBeGreaterThan(40);
    }
  });

  it("NINGUNA sentencia queda sin resolver: lo que no se entiende se pone en rojo", () => {
    // El fallo de esta aserción nombra el fichero y la expresión: es la
    // diferencia entre «el censo está incompleto y nadie lo sabe» —lo que
    // produjo esta ficha— y «el censo se niega a decir que está completo».
    const sinResolver = sentenciasProductoras()
      .filter((s) => s.kinds.length === 0)
      .map((s) => `${s.fichero}: kind = ${s.expresion || "(sin columna kind)"}`);
    expect(sinResolver).toEqual([]);
  });

  it("el censo no está vacío ni ridículamente corto (si no, todo lo de abajo miente)", () => {
    expect(sentenciasProductoras().length).toBeGreaterThanOrEqual(14);
    expect(KINDS.length).toBeGreaterThanOrEqual(24);
  });

  it("trae los OCHO que esta ficha encontró sin rótulo", () => {
    for (const kind of [
      "fail_open",
      "in_review",
      "close",
      "dictamen_signed",
      "damage_people_at_risk",
      "headcount_closed",
      "headcount_notify",
      // El octavo, que la ficha no listaba porque no está en `api/src`.
      "notify_delivered",
    ]) {
      expect(KINDS, `el censo perdió a ${kind}`).toContain(kind);
    }
  });
});

// ---------------------------------------------------------------------------
// LAS DOS SUPERFICIES, DEL MISMO REGISTRO
// ---------------------------------------------------------------------------
describe("[T-2.144] todo productor tiene rótulo en las DOS superficies", () => {
  it.each(KINDS)("`%s` tiene vista y rótulo en el checklist BMS", (kind) => {
    expect(ACTION_STATE[kind], `${kind} sin vista`).toBeDefined();
    expect(CHANNEL_LABEL[kind], `${kind} sin rótulo`).toBeDefined();
  });

  it.each(KINDS)("`%s` NO cae en el fallback del checklist", (kind) => {
    expect(ACTION_STATE[kind]).not.toEqual(UNCLASSIFIED_VIEW);
    // Ni pinta el nombre de la constante: «DAMAGE PEOPLE AT RISK» era eso.
    expect(ACTION_STATE[kind].state).not.toBe(kind.toUpperCase());
    expect(CHANNEL_LABEL[kind]).not.toBe(kind.replaceAll("_", " ").toUpperCase());
  });

  it.each(KINDS)("`%s` NO cae en el fallback de la bitácora", (kind) => {
    expect(kindLabel({ action_id: "a", ts: "2026-08-14T00:00:00Z", kind, actor: "x" })).not.toMatch(
      /SIN CLASIFICAR/,
    );
  });

  it.each(KINDS)("`%s` se lee en castellano, no como constante en inglés", (kind) => {
    // El defecto era literalmente éste: el `kind` en bruto, en inglés y con
    // guiones bajos, en la pantalla de un SOC.
    const fila = `${CHANNEL_LABEL[kind]} ${ACTION_STATE[kind].state}`;
    expect(fila).not.toMatch(/_/);
    expect(fila.toLowerCase()).not.toContain(kind.split("_")[0].toLowerCase() + "_");
  });

  it("los rótulos salen del REGISTRO, no de una lista paralela", () => {
    // Las dos familias y nada más. Una tercera lista escrita a mano es el
    // defecto que `T-2.119`, `T-2.127`, `T-2.133` y ésta han pagado ya cuatro
    // veces.
    const delRegistro = new Set([
      ...Object.keys(INCIDENT_ACTION_KINDS),
      ...Object.values(ACTUATOR_CHANNELS).flatMap((s) => [
        ...Object.keys(s.kinds),
        ...Object.keys(s.legacyKinds),
      ]),
    ]);
    expect([...Object.keys(ACTION_STATE)].filter((k) => !delRegistro.has(k))).toEqual([]);
    expect([...Object.keys(CHANNEL_LABEL)].filter((k) => !delRegistro.has(k))).toEqual([]);
  });

  it("censo inverso: el registro no da de alta nombres que nadie escribe", () => {
    // La dirección de `T-2.133`, ahora resuelta con el mismo motor. Aquí murieron
    // `drill_start` y `drill_stop`, que la bitácora rotulaba y que son valores de
    // `commands.action`, no de `incident_actions.kind`.
    const muertos = Object.keys(INCIDENT_ACTION_KINDS).filter((k) => !KINDS.includes(k));
    expect(muertos, "entrada del registro sin productor").toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// PRODUCTO: lo que el operador lee, y con qué severidad
// ---------------------------------------------------------------------------
describe("[T-2.144] `damage_people_at_risk` es lo primero de esta ficha", () => {
  it("dice PERSONAS EN RIESGO, en español, y NO es verde", () => {
    const vista = ACTION_STATE.damage_people_at_risk;
    expect(vista.state).toBe("PERSONAS EN RIESGO");
    expect(vista.kind).toBe("critical");
    expect(CHANNEL_LABEL.damage_people_at_risk).toBe("REPORTE DE DAÑOS");
  });

  it("y la bitácora dice quién está en riesgo y dónde", () => {
    expect(
      kindLabel({
        action_id: "a",
        ts: "2026-08-14T00:00:00Z",
        kind: "damage_people_at_risk",
        actor: "x",
      }),
    ).toBe("PERSONAS EN RIESGO REPORTADAS EN SITIO");
  });

  it("la fila del checklist se pinta CRÍTICA de punta a punta", () => {
    const grupo = groupActions([accion("damage_people_at_risk")])[0];
    expect(grupo.label).toBe("REPORTE DE DAÑOS");
    expect(grupo.view).toEqual({ state: "PERSONAS EN RIESGO", kind: "critical" });
  });
});

describe("[T-2.144] la severidad de los otros siete, una por una", () => {
  it("`fail_open` NO es verde: nadie confirmó nada en ese sitio", () => {
    // Y su `warning` no es una opinión: es la misma severidad que
    // `incident/fail_open.py` le pone al incidente sintético que abre.
    expect(ACTION_STATE.fail_open.kind).toBe("warning");
    expect(CHANNEL_LABEL.fail_open).toMatch(/ENLACE/);
  });

  it("`headcount_notify` NO es verde: hay personas sin localizar", () => {
    expect(ACTION_STATE.headcount_notify.kind).toBe("warning");
  });

  it("los procedimientos CUMPLIDOS sí son verdes, y eso no es inflar el tablero", () => {
    // La ficha avisaba de esto: subir la severidad de lo que está bien hace un
    // tablero que grita por todo, y ése se ignora igual que uno que calla.
    for (const kind of ["in_review", "close", "dictamen_signed", "headcount_closed"]) {
      expect(ACTION_STATE[kind].kind, `${kind} no debería gritar`).toBe("ok");
    }
  });

  it("`notify_delivered` es verde LEGÍTIMO, y distinto de `notify_sent`", () => {
    // «lo entregamos al proveedor» y «el proveedor lo entregó al teléfono» son
    // dos afirmaciones distintas; la migración `0040` las separó a propósito.
    expect(ACTION_STATE.notify_delivered.kind).toBe("ok");
    expect(ACTION_STATE.notify_delivered.state).not.toBe(ACTION_STATE.notify_sent.state);
    expect(CHANNEL_LABEL.notify_delivered).not.toBe(CHANNEL_LABEL.notify_sent);
  });

  it("`close` y `in_review` no se funden en la misma fila del checklist", () => {
    const etiquetas = groupActions([accion("close"), accion("in_review")]).map((g) => g.label);
    expect(new Set(etiquetas).size).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// EL FALLBACK DEJÓ DE SER VERDE
// ---------------------------------------------------------------------------
describe("[T-2.144] un kind sin clasificar no es «todo bien»", () => {
  it("el fallback del checklist NO es `ok`", () => {
    expect(UNCLASSIFIED_VIEW.kind).not.toBe("ok");
    // `warning`, no `critical`: pide que alguien lo mire, no que se evacúe.
    expect(UNCLASSIFIED_VIEW.kind).toBe("warning");
  });

  it("y lo DICE: la píldora no repite el nombre de la constante", () => {
    const grupo = groupActions([accion("verbo_del_futuro")])[0];
    expect(grupo.view).toEqual(UNCLASSIFIED_VIEW);
    expect(grupo.view.state).toBe("SIN CLASIFICAR");
    // El nombre crudo sigue estando: en la columna de la izquierda, que es
    // donde sirve para ir a buscar quién lo escribe.
    expect(grupo.label).toBe("VERBO DEL FUTURO");
  });

  it("la bitácora tampoco lo hace pasar por un verbo de TAKAB", () => {
    expect(
      kindLabel({
        action_id: "a",
        ts: "2026-08-14T00:00:00Z",
        kind: "verbo_del_futuro",
        actor: "x",
      }),
    ).toBe("VERBO_DEL_FUTURO · SIN CLASIFICAR");
  });

  it("la bandera `simulated` sigue mandando sobre el fallback", () => {
    // El orden importa: una acción simulada de un kind desconocido tiene que
    // seguir declarándose simulada, no «sin clasificar».
    const vista = groupActions([accion("verbo_del_futuro", { simulated: true })])[0].view;
    expect(vista.state).toMatch(/SIMULADA/);
  });

  it("NINGÚN kind conocido se contagia del fallback", () => {
    // El aviso de la ficha, comprobado: cambiar el fallback no puede volver
    // ámbar nada que hoy esté clasificado y bien.
    for (const kind of Object.keys(ACTION_STATE)) {
      expect(ACTION_STATE[kind], `${kind} se quedó sin clasificar`).not.toEqual(UNCLASSIFIED_VIEW);
    }
  });
});

// ---------------------------------------------------------------------------
// EL LÍMITE RESIDUAL, DECLARADO Y VIGILADO
// ---------------------------------------------------------------------------
describe("[T-2.144] el hueco que la resolución NO puede ver, vigilado aparte", () => {
  it("todo destino del ciclo de vida tiene entrada en `_ACTION_KIND`", () => {
    // `lifecycle.py` hace `_ACTION_KIND.get(new_state, new_state)`: un estado
    // destino SIN entrada escribiría su propio nombre como `kind`, y la
    // resolución —que lee los VALORES del `dict`— no lo vería. Mientras los tres
    // destinos estén mapeados, el `.get` por defecto es inalcanzable. Si alguien
    // añade un cuarto estado, esto se pone rojo ANTES de que el kind exista.
    const mapa = kindsDeCicloDeVida();
    const sinMapear = destinosDeCicloDeVida().filter((d) => mapa[d] === undefined);
    expect(sinMapear, "estado destino que escribiría su propio nombre como kind").toEqual([]);
  });

  it("y los kinds que ese `dict` declara son los que el registro rotula", () => {
    for (const kind of Object.values(kindsDeCicloDeVida())) {
      expect(INCIDENT_ACTION_KINDS[kind], `${kind} sin rótulo`).toBeDefined();
    }
  });
});
