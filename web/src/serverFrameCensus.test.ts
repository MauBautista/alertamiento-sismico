// [T-2.129] EL CENSO DE LOS FRAMES DEL CANAL LIVE: que ninguno pueda nacer muerto.
//
// El defecto de fondo de esta ficha no era «falta un tipo de frame». Era que el
// cliente DESCARTABA EN SILENCIO todo lo que no reconocía, y por dos puertas a
// la vez: `parseServerFrame` sólo aceptaba `type` de un `Set` escrito a mano en
// `shared/sdk-ts/src/ws.ts`, y `live.ts` enrutaba con un `switch` cuyo `default`
// devolvía `null`. Con eso, cualquier frame que el servidor aprendiera a mandar
// desaparecía sin dejar rastro — y ésa es la razón por la que `T-2.121` tuvo que
// decir «tu live está degradado» CERRANDO EL SOCKET (4503): el estado del
// transporte era el único canal servidor→pantalla que quedaba.
//
// Arreglar sólo el frame nuevo habría dejado el agujero abierto para el
// siguiente. Lo que se ancla aquí es el mecanismo:
//
//   1. LA LISTA SE DERIVA. `SERVER_FRAME_TYPES` sale de las claves de
//      `SERVER_FRAME_ROUTES`, que es `Record<ServerFrameType, …>` sobre la unión
//      `ServerFrame`: un miembro nuevo sin ruta NO COMPILA. Eso lo caza `tsc`,
//      no este fichero.
//   2. LO QUE `tsc` NO PUEDE VER es el otro extremo del cable: que la unión de
//      TypeScript siga cubriendo lo que el servidor manda. Eso es lo que se mide
//      aquí, leyendo `api/src/takab_api/ws/protocol.py` — el PRODUCTOR — en
//      tiempo de test. Un frame Pydantic nuevo pone este fichero rojo.
//
// Es la misma receta que `features/console/bmsChannels.test.ts`, que lee
// `ACK_KIND` del propio ingest, y por el mismo motivo: la lista que se deriva no
// puede divergir; la escrita a mano siempre acaba divergiendo.
//
// Es una LECTURA en tiempo de test, no un `import`: no añade dependencia de
// build de la consola sobre `api/` (cf. `consoleImageCensus.test.ts`).

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import {
  LIVE_HEALTH_FIELDS,
  LiveSocket,
  SERVER_FRAME_ROUTES,
  SERVER_FRAME_TYPES,
  TOPIC_INCIDENTS,
  TOPIC_LIVE_HEALTH,
  TOPIC_SITE_STATE,
  featuresTopic,
  parseServerFrame,
  topicOfFrame,
  type ServerFrame,
} from "@takab/sdk";

const PROTOCOL = resolve(process.cwd(), "..", "api", "src", "takab_api", "ws", "protocol.py");
const TYPES_GEN = resolve(process.cwd(), "..", "shared", "sdk-ts", "src", "gen", "types.gen.ts");
const WS_TS = resolve(process.cwd(), "..", "shared", "sdk-ts", "src", "ws.ts");
const FUENTE = readFileSync(PROTOCOL, "utf8");

/**
 * Los `type` que el SERVIDOR manda, leídos del productor.
 *
 * La señal es estructural y la explica `protocol.py::_server_frame_types`: un
 * frame servidor→cliente declara su discriminante CON DEFAULT
 * (`type: Literal["incident"] = "incident"`), porque el servidor lo construye
 * sin pasarlo; los de cliente→servidor (`auth`, `subscribe`) lo EXIGEN. No hace
 * falta ninguna lista que mantener: la dirección está en el modelo.
 */
export function framesDelServidor(fuente: string): string[] {
  return [...fuente.matchAll(/^\s*type:\s*Literal\["(\w+)"\]\s*=\s*"\1"\s*$/gm)].map((m) => m[1]);
}

/** Y los del cliente, para probar que la señal distingue de verdad. */
export function framesDelCliente(fuente: string): string[] {
  return [...fuente.matchAll(/^\s*type:\s*Literal\["(\w+)"\]\s*$/gm)].map((m) => m[1]);
}

/**
 * Campos declarados por una clase Pydantic de `protocol.py`.
 *
 * El docstring se quita ANTES de mirar: la primera versión de este ayudante
 * contó un campo llamado `frase` que sólo existía dentro de una frase del
 * docstring («La pantalla no lo lee como\n    frase: …»). Un censo que lee prosa
 * como contrato encuentra fantasmas y, peor, puede dejar de encontrar campos.
 */
export function camposDelModelo(fuente: string, clase: string): string[] {
  const cuerpo = fuente.split(`class ${clase}(BaseModel):`)[1]?.split(/\nclass /)[0];
  if (cuerpo === undefined) {
    throw new Error(`${clase} no está en ${PROTOCOL}: el contrato se movió, no está verde`);
  }
  const sinDocstring = cuerpo.replace(/"""[\s\S]*?"""/g, "");
  return [...sinDocstring.matchAll(/^ {4}(\w+):\s/gm)].map((m) => m[1]);
}

const DEL_SERVIDOR = framesDelServidor(FUENTE);

/* =====================================================================
   NO-VACUIDAD — si el barrido no lee nada, todo lo de abajo miente
   ===================================================================== */

describe("censo de frames WS · el barrido encuentra el productor", () => {
  it("lee `ws/protocol.py` y saca los frames del servidor", () => {
    expect(DEL_SERVIDOR.length).toBeGreaterThanOrEqual(7);
    expect(DEL_SERVIDOR).toContain("ready");
    expect(DEL_SERVIDOR).toContain("incident");
  });

  it("la señal DISTINGUE la dirección: `auth`/`subscribe` no son del servidor", () => {
    // Si esto se rompiera, el censo de abajo exigiría rutas para frames que el
    // cliente MANDA — y alguien las añadiría, tapando la señal para siempre.
    expect(framesDelCliente(FUENTE).sort()).toEqual(["auth", "subscribe"]);
    expect(DEL_SERVIDOR).not.toContain("auth");
    expect(DEL_SERVIDOR).not.toContain("subscribe");
  });
});

/* =====================================================================
   C-1 · TODO FRAME DEL SERVIDOR TIENE RUTA EN EL CLIENTE
   ===================================================================== */

describe("censo · ningún frame del servidor puede caer en el descarte silencioso", () => {
  it("cada `type` de `protocol.py` está en la tabla de rutas del SDK", () => {
    const huerfanos = DEL_SERVIDOR.filter((t) => !(t in SERVER_FRAME_ROUTES)).sort();
    expect(
      huerfanos,
      "frames que el servidor manda y el SDK no sabe repartir. Añádelos a la unión " +
        "`ServerFrame` y a `SERVER_FRAME_ROUTES` (`shared/sdk-ts/src/ws.ts`) — hasta " +
        "entonces llegan al navegador y se tiran, que es el defecto que cierra " +
        `T-2.129:\n${huerfanos.join("\n")}`,
    ).toEqual([]);
  });

  it("y al revés: el SDK no enruta fantasmas que nadie manda", () => {
    const fantasmas = Object.keys(SERVER_FRAME_ROUTES)
      .filter((t) => !DEL_SERVIDOR.includes(t))
      .sort();
    expect(
      fantasmas,
      "rutas para `type` que ya no existen en `ws/protocol.py`: o se borró el frame " +
        "y sobra la ruta, o alguien la escribió a mano sin productor detrás.",
    ).toEqual([]);
  });

  it("`SERVER_FRAME_TYPES` se DERIVA de la tabla: no hay dónde divergir", () => {
    expect([...SERVER_FRAME_TYPES].sort()).toEqual(Object.keys(SERVER_FRAME_ROUTES).sort());
    // Y es lo que gobierna al parser, que era la primera de las dos puertas.
    for (const t of DEL_SERVIDOR) {
      expect(() => parseServerFrame({ type: t })).not.toThrow();
    }
    expect(() => parseServerFrame({ type: "frame-del-futuro" })).toThrow();
  });

  it("cada ruta lleva a un topic real o se declara de PROTOCOLO", () => {
    const rutas: Record<string, string | null> = {};
    for (const t of DEL_SERVIDOR) {
      rutas[t] = topicOfFrame({ type: t, site_id: "s-1" } as unknown as ServerFrame);
    }
    expect(rutas).toEqual({
      ready: null, // protocolo: lo consume `LiveSocket`
      error: null, // protocolo: sale por `onServerError`
      live_health: TOPIC_LIVE_HEALTH,
      incident: TOPIC_INCIDENTS,
      incident_action: TOPIC_INCIDENTS,
      roster: TOPIC_INCIDENTS,
      site_state: TOPIC_SITE_STATE,
      features: featuresTopic("s-1"),
    });
  });
});

/* =====================================================================
   C-2 · EL ESPEJO DE `LiveHealthFrame` NO PUEDE QUEDARSE CORTO
   ===================================================================== */

describe("censo · el frame de salud del canal es el MISMO a los dos lados", () => {
  it("los campos del espejo TS son los del modelo Pydantic", () => {
    expect(Object.keys(LIVE_HEALTH_FIELDS).sort()).toEqual(
      camposDelModelo(FUENTE, "LiveHealthFrame").sort(),
    );
  });

  it("el espejo local ya NO existe: `LiveHealthFrame` sale del contrato", () => {
    // HISTORIA, porque explica por qué este test cambió de forma:
    // `LiveHealthFrame` nació escrito A MANO en `ws.ts`, porque el contrato se
    // regenera UNA vez al cerrar el lote y `src/index.ts` hace `export *` de
    // `./gen` Y de `./ws`: con los dos exportando el mismo nombre, la ambigüedad
    // rompe el build. La versión anterior de este test era una guarda de UN SOLO
    // USO — afirmaba que el contrato todavía NO traía el tipo, para ponerse roja
    // en cuanto lo trajera y entregar la instrucción de borrar el espejo.
    //
    // Cumplió (2026-08-13, al regenerar el contrato del lote). Y entonces
    // quedaba roja para siempre, porque su aserción ya no podía volver a ser
    // cierta. Un andamio con fecha de caducidad hay que retirarlo cuando caduca;
    // dejarlo habría sido un rojo permanente que alguien acabaría silenciando —
    // y con él se iría también la vigilancia de que el espejo no vuelva.
    //
    // Ésta es su forma PERMANENTE: la que sigue siendo cierta mañana.
    const gen = readFileSync(TYPES_GEN, "utf8");
    const ws = readFileSync(WS_TS, "utf8");

    expect(
      gen.includes("export type LiveHealthFrame"),
      "el contrato dejó de publicar `LiveHealthFrame`: o se borró del modelo Pydantic, o el " +
        "SDK está sin regenerar (`make drift` lo diría).",
    ).toBe(true);

    expect(
      /^export interface LiveHealthFrame\b/m.test(ws),
      "`ws.ts` volvió a declarar `LiveHealthFrame` a mano. El contrato ya lo trae, así que " +
        "son DOS verdades sobre el mismo cable y `index.ts` no compilará por la ambigüedad " +
        "del doble `export *`. Impórtalo de `./gen`.",
    ).toBe(false);

    expect(
      /import type \{[^}]*\bLiveHealthFrame\b[^}]*\} from '\.\/gen'/s.test(ws),
      "`ws.ts` debe importar `LiveHealthFrame` de `./gen`: es de donde sale la verdad.",
    ).toBe(true);
  });
});

/* =====================================================================
   C-3 · LA CONDUCTA: repartir o AVISAR, nunca callarse
   ===================================================================== */

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string): void {
    this.sent.push(data);
  }
  close(code = 1000): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code });
  }
  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  message(frame: unknown): void {
    this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
  }
}

function socketListo() {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  const onUnknownFrame = vi.fn();
  const onServerError = vi.fn();
  const socket = new LiveSocket({
    url: "ws://localhost/api/ws",
    getToken: () => "tok-1",
    onUnauthorized: vi.fn(),
    onUnknownFrame,
    onServerError,
  });
  return { socket, onUnknownFrame, onServerError };
}

describe("`LiveSocket` · ningún camino termina en silencio", () => {
  it("un `type` que este cliente no conoce DEJA RASTRO (y no tumba el canal)", () => {
    const { socket, onUnknownFrame } = socketListo();
    const enIncidentes = vi.fn();
    socket.subscribe(TOPIC_INCIDENTS, enIncidentes);
    socket.connect();
    const ws = FakeWebSocket.instances.at(-1)!;
    ws.open();
    ws.message({ type: "ready" });

    ws.message({ type: "frame-del-futuro", cosa: 1 });
    expect(onUnknownFrame).toHaveBeenCalledTimes(1);
    expect(onUnknownFrame.mock.calls[0][1].message).toMatch(/desconocido/);

    ws.message("esto no es json");
    expect(onUnknownFrame).toHaveBeenCalledTimes(2);

    // El canal sigue vivo y repartiendo: el aviso no es una excusa para morir.
    ws.message({ type: "incident", incident_id: "i-1" });
    expect(enIncidentes).toHaveBeenCalledTimes(1);
    socket.close();
    vi.unstubAllGlobals();
  });

  it("el `error` de protocolo SE ENTREGA en vez de descartarse", () => {
    // Ésta es la frase literal de la ficha: «live.ts descarta los frames error».
    // Una suscripción denegada se veía igual que una concedida y muda.
    const { socket, onServerError } = socketListo();
    socket.connect();
    const ws = FakeWebSocket.instances.at(-1)!;
    ws.open();
    ws.message({ type: "ready" });
    ws.message({ type: "error", detail: "rol sin acceso al topic" });
    expect(onServerError).toHaveBeenCalledWith({
      type: "error",
      detail: "rol sin acceso al topic",
    });
    socket.close();
    vi.unstubAllGlobals();
  });

  it("`live_health` llega a sus oyentes SIN pedirle nada al servidor", () => {
    const { socket } = socketListo();
    const enSalud = vi.fn();
    socket.subscribe(TOPIC_LIVE_HEALTH, enSalud);
    socket.subscribe(TOPIC_INCIDENTS, vi.fn());
    socket.connect();
    const ws = FakeWebSocket.instances.at(-1)!;
    ws.open();
    ws.message({ type: "ready" });

    // El servidor rechazaría `{"type":"subscribe","topic":"live_health"}` con
    // «topic inválido»: es un frame que él dirige, no un flujo al que apuntarse.
    const enviados = ws.sent.map((s) => JSON.parse(s) as Record<string, unknown>);
    expect(enviados.filter((f) => f.type === "subscribe").map((f) => f.topic)).toEqual([
      TOPIC_INCIDENTS,
    ]);

    ws.message({ type: "live_health", degraded: true, topic: "incidents", detail: "x" });
    expect(enSalud).toHaveBeenCalledWith({
      type: "live_health",
      degraded: true,
      topic: "incidents",
      detail: "x",
    });
    socket.close();
    vi.unstubAllGlobals();
  });
});
