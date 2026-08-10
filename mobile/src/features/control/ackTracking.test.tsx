// [T-2.107] EL ACUSE DEL GABINETE, POR EL CAMINO REAL DE LA PANTALLA.
//
// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay ahí con un `require.context` y un `*.test.tsx` dentro rompe el bundle
// (ver `tests/app/onboarding/guard.test.tsx`). Aquí se importa la ruta REAL
// `(brigadista)/panel.tsx` y se la conduce como una persona: pulsar el control,
// pasar las precondiciones, deslizar y LEER lo que dice la hoja.
//
// El defecto que cierra: la pantalla guardaba el `CommandOut` de la respuesta
// 201 —que SIEMPRE nace `pending`— y no volvía a preguntar jamás. La rama
// `pending` de `ackState` era la única alcanzable: «ESPERANDO CONFIRMACIÓN DEL
// GABINETE», para siempre. Las ramas `acked`/`rejected`/`expired` eran código
// muerto, y con ellas la frase que la spec §2.2 EXIGE decir en vez de fingir
// éxito: «SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA».
//
// Se asserta el TEXTO que lee la persona (lección de T-2.104: un componente
// presentacional puede llevar una mentira a fuego que ninguna prueba de la
// lógica alcanza).
import type { CommandOut, MobileStateOut } from "@takab/sdk";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  userEvent,
  waitFor,
  type RenderResult,
} from "@testing-library/react-native";
import type { ReactNode } from "react";

import { useSessionStore } from "@/auth/session.store";

import Panel from "@/app/(brigadista)/panel";

const SITE = "11111111-1111-1111-1111-111111111111";

// ------------------------------------------------------------------ mocks

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
}));

jest.mock("expo-secure-store", () => {
  const disco = new Map<string, string>();
  return {
    __disco: disco,
    getItemAsync: jest.fn(async (k: string) => disco.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void disco.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void disco.delete(k)),
  };
});

const mockBio = {
  biometricKeysExist: jest.fn(async () => ({ keysExist: true })),
  isSensorAvailable: jest.fn(async () => ({ available: true })),
  createKeys: jest.fn(async () => ({ publicKey: "QUJDRA==" })),
  createSignature: jest.fn(async () => ({ success: true, signature: "c2ln" })),
};
jest.mock("react-native-biometrics", () => ({
  __esModule: true,
  default: jest.fn(() => mockBio),
}));

// El canal live no transporta acuses (la unión `ServerFrame` no tiene
// `command_ack`): aquí es un socket mudo, para que el ÚNICO camino por el que
// puede llegar el acuse a la pantalla sea el que esta ficha construye.
jest.mock("@/live/socket", () => ({
  getLiveSocket: () => ({
    status: "ready",
    connect: jest.fn(),
    close: jest.fn(),
    onStatus: () => () => undefined,
    subscribe: () => () => undefined,
  }),
}));

const mockSdk = {
  mobileState: jest.fn(),
  listIncidentActions: jest.fn(),
  listCommands: jest.fn(),
  issueNonce: jest.fn(),
  issueCommand: jest.fn(),
  listMyCheckins: jest.fn(),
  registerDeviceKey: jest.fn(),
};

jest.mock("@takab/sdk", () => {
  const actual = jest.requireActual("@takab/sdk");
  return {
    ...actual,
    mobileStateSitesSiteIdMobileStateGet: (...a: unknown[]) => mockSdk.mobileState(...a),
    listIncidentActionsIncidentsIncidentIdActionsGet: (...a: unknown[]) =>
      mockSdk.listIncidentActions(...a),
    listCommandsSitesSiteIdCommandsGet: (...a: unknown[]) => mockSdk.listCommands(...a),
    issueCommandNonceSitesSiteIdCommandNoncePost: (...a: unknown[]) => mockSdk.issueNonce(...a),
    issueCommandSitesSiteIdCommandsPost: (...a: unknown[]) => mockSdk.issueCommand(...a),
    listMyCheckinsIncidentsIncidentIdCheckinsGet: (...a: unknown[]) => mockSdk.listMyCheckins(...a),
    registerDeviceKeyMeDeviceKeysPost: (...a: unknown[]) => mockSdk.registerDeviceKey(...a),
  };
});

jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => "11111111-1111-1111-1111-111111111111",
}));

// ------------------------------------------------------------------ datos

function estado(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: "2026-08-10T10:00:00Z",
    phase: "alert_active",
    incident: null,
    latest_tier: "watch",
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, next_scheduled_at: null, last_started_at: null, last_note: null },
    site_health: {
      status: "OPERATIVO",
      heartbeat_at: "2026-08-10T09:59:30Z",
      age_s: 30,
      has_wr1: true,
      mqtt_rtt_ms: 77,
      seedlink_lag_s: 1,
      ntp_offset_ms: 0,
      cpu_temp_c: 50,
      power_status: "mains",
      battery_pct: 100,
      cert_days_remaining: 90,
    },
    ...over,
  } as MobileStateOut;
}

/** El comando tal cual nace en el 201: SIEMPRE `pending`, con su TTL real
 *  (`api/src/takab_api/settings.py:451` — `command_ttl_s = 30.0`). */
function comando(over: Partial<CommandOut> = {}): CommandOut {
  return {
    command_id: "cmd-1",
    tenant_id: "t-1",
    site_id: SITE,
    gateway_id: "g-1",
    issued_by: "u-1",
    channel: "siren",
    action: "activate",
    event_id: null,
    nonce: "nonce-1",
    issued_at: "2026-08-10T10:00:00Z",
    expires_at: "2026-08-10T10:00:30Z",
    status: "pending",
    ack: null,
    error: null,
    ...over,
  } as CommandOut;
}

// ------------------------------------------------------------------ arneses

const cliente = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: 0 } },
});

function Envoltura(props: { children: ReactNode }) {
  return <QueryClientProvider client={cliente}>{props.children}</QueryClientProvider>;
}

/** Pulsa como una persona. `userEvent` y no `fireEvent.press`: `Pressable`
 *  resuelve su `onPress` a través de `Pressability`, que difiere el disparo, y
 *  `userEvent` sabe adelantar el reloj falso mientras tanto. */
async function pulsar(v: RenderResult, testID: string): Promise<void> {
  const usuario = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  await usuario.press(v.getByTestId(testID));
}

/** Deja asentar efectos y microtareas pendientes.
 *
 *  TRAMPA que costó media tarde: en RNTL 14 `render`, `fireEvent` y `cleanup`
 *  son ASÍNCRONOS. Un `fireEvent` sin `await` deja su `act()` abierto, el
 *  desmontaje del test siguiente cae dentro de ese `act` huérfano y el segundo
 *  `render` del fichero produce un árbol VACÍO — sin error, sin aviso: sólo
 *  «Unable to find …» en todos los tests menos el primero. */
async function asentar(): Promise<void> {
  await act(async () => {});
}

/** Un deslizamiento REAL sobre el `PanResponder` del paso 2: layout + grant +
 *  move + release con el `touchHistory` que `TouchHistoryMath` sabe leer. Sin
 *  esto el ancho es 0, `max` es 0 y el gesto jamás confirma. */
async function deslizar(v: RenderResult): Promise<void> {
  const pista = v.getByTestId("slide-track");
  await fireEvent(pista, "layout", { nativeEvent: { layout: { width: 320, height: 64 } } });
  await asentar();
  const perilla = v.getByTestId("slide-knob");
  const toque = (x: number, previo: number, ts: number) => ({
    touchHistory: {
      touchBank: [
        {
          touchActive: true,
          startPageX: 0,
          startPageY: 0,
          startTimeStamp: 1,
          currentPageX: x,
          currentPageY: 0,
          currentTimeStamp: ts,
          previousPageX: previo,
          previousPageY: 0,
          previousTimeStamp: ts - 1,
        },
      ],
      numberActiveTouches: 1,
      indexOfSingleActiveTouch: 0,
      mostRecentTimeStamp: ts,
    },
  });
  await fireEvent(perilla, "responderGrant", toque(0, 0, 2));
  await fireEvent(perilla, "responderMove", toque(320, 0, 3));
  await fireEvent(perilla, "responderRelease", toque(320, 0, 4));
  await asentar();
}

/** Camino completo de la persona: abre el control, pasa el paso 1 y desliza. */
async function emitir(v: RenderResult, boton: "ctl-activate" | "ctl-silence"): Promise<void> {
  await waitFor(() => expect(v.getByTestId(boton)).toBeTruthy());
  await pulsar(v, boton);
  // El paso 2 sólo se alcanza con TODAS las precondiciones cumplidas: si esto
  // no está, el gesto no existe y el test no probaría nada.
  await pulsar(v, "to-step-2");
  await deslizar(v);
  await waitFor(() => expect(v.getByTestId("ack-title")).toBeTruthy());
}

// ------------------------------------------------------------------ setup

beforeEach(() => {
  // Reloj FALSO: el techo de la espera son 35 s reales y esta suite tiene que
  // poder cruzarlos sin esperarlos.
  jest.clearAllMocks();
  jest.useFakeTimers();
  jest.setSystemTime(Date.parse("2026-08-10T10:00:00Z"));
  mockBio.biometricKeysExist.mockResolvedValue({ keysExist: true });
  mockBio.isSensorAvailable.mockResolvedValue({ available: true });
  mockBio.createKeys.mockResolvedValue({ publicKey: "QUJDRA==" });
  mockBio.createSignature.mockResolvedValue({ success: true, signature: "c2ln" });
  (jest.requireMock("expo-secure-store") as { __disco: Map<string, string> }).__disco.set(
    "takab.devicekey.id.v1",
    "key-1",
  );
  mockSdk.mobileState.mockResolvedValue({ data: estado() });
  mockSdk.listIncidentActions.mockResolvedValue({ data: [] });
  mockSdk.listMyCheckins.mockResolvedValue({ data: [] });
  mockSdk.issueNonce.mockResolvedValue({ data: { nonce: "n-1", expires_at: "x", ttl_s: 90 } });
  mockSdk.issueCommand.mockResolvedValue({ data: comando() });
  mockSdk.listCommands.mockResolvedValue({ data: { items: [comando()] } });
  cliente.clear();
  useSessionStore.setState({
    status: "authenticated",
    profile: "tactical",
    idToken: "tok",
    me: {
      allowed_actions: { manual_activate: true, siren_silence: true },
    } as never,
    deniedReason: null,
  });
});

afterEach(() => {
  jest.useRealTimers();
});

// ------------------------------------------------------------------ tests

describe("[T-2.107] el acuse REAL del gabinete llega a la pantalla", () => {
  it("el gabinete ACUSÓ: la hoja deja de decir «esperando» y declara la ejecución", async () => {
    // Primera consulta: el gabinete todavía no acusa. Segunda: ya acusó. Así
    // la espera se pinta de verdad antes de resolverse, en vez de por carrera.
    mockSdk.listCommands.mockResolvedValueOnce({ data: { items: [comando()] } });
    mockSdk.listCommands.mockResolvedValue({
      data: {
        items: [
          comando({
            status: "acked",
            ack: { channel: "siren", action: "activate", success: true, detail: "relay" },
          }),
        ],
      },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-activate");

    // Primer pintado honesto: el 201 nace pending y eso es lo que se sabe.
    await waitFor(() =>
      expect(v.getByTestId("ack-title")).toHaveTextContent("ESPERANDO CONFIRMACIÓN DEL GABINETE"),
    );

    // …y el sondeo trae el acuse REAL. Sin esto la pantalla se queda en la
    // espera para siempre: ES EL DEFECTO DE ESTA FICHA.
    await waitFor(
      () => expect(v.getByTestId("ack-title")).toHaveTextContent("SIRENA ACTIVADA"),
      { timeout: 20_000 },
    );
    expect(mockSdk.listCommands).toHaveBeenCalled();
    expect(mockSdk.listCommands).toHaveBeenCalledWith(
      expect.objectContaining({ path: { site_id: SITE } }),
    );
  });

  it("el gabinete RECHAZÓ: se lee el rechazo y su causa, no un éxito fingido", async () => {
    mockSdk.listCommands.mockResolvedValue({
      data: { items: [comando({ status: "rejected", error: "relé de sirena en falla" })] },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-activate");

    await waitFor(
      () => expect(v.getByTestId("ack-title")).toHaveTextContent("EL GABINETE RECHAZÓ EL COMANDO"),
      { timeout: 20_000 },
    );
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/relé de sirena en falla/);
  });

  it("el servidor lo declaró EXPIRADO: se pinta su lápida, distinta de «sin confirmación»", async () => {
    // `GET /sites/{id}/commands` corre `EXPIRE_SITE` antes de listar: preguntar
    // es lo que hace que el pendiente vencido se marque `expired`.
    mockSdk.listCommands.mockResolvedValue({
      data: { items: [comando({ status: "expired", error: "sin ack dentro del TTL" })] },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-activate");

    await waitFor(
      () => expect(v.getByTestId("ack-title")).toHaveTextContent("COMANDO EXPIRADO SIN ACUSE"),
      { timeout: 20_000 },
    );
    // El veredicto del SERVIDOR no se confunde con el techo local.
    expect(v.queryByText(/SIN CONFIRMACIÓN DEL GABINETE/)).toBeNull();
  });
});

describe("[T-2.107] la espera tiene TECHO — jamás un giro eterno", () => {
  it("el pendiente que nunca resuelve se DECLARA vencido con su número de segundos", async () => {
    // El servidor contesta siempre `pending` (comando emitido, gabinete mudo).
    mockSdk.listCommands.mockResolvedValue({ data: { items: [comando({ status: "pending" })] } });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-activate");

    await waitFor(() =>
      expect(v.getByTestId("ack-title")).toHaveTextContent("ESPERANDO CONFIRMACIÓN DEL GABINETE"),
    );
    // La espera se rotula con su techo desde el primer instante: nadie mira un
    // indicador sin saber cuánto va a durar.
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/hasta 35 s/);

    // TTL real del comando (expires_at − issued_at = 30 s, tiempo del SERVIDOR)
    // + gracia de sondeo = 35 s.
    await waitFor(
      () => expect(v.getByTestId("ack-title")).toHaveTextContent("SIN CONFIRMACIÓN DEL GABINETE"),
      { timeout: 60_000 },
    );
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/^Pasaron 35 s /);
    expect(v.getByTestId("ack-detail")).toHaveTextContent(
      /NO se sabe si el gabinete ejecutó la orden/,
    );
  });

  it("si el sondeo NO puede preguntar, la espera igual vence y se declara", async () => {
    // Sin red hacia la nube: nunca habrá veredicto. La pantalla no puede
    // quedarse esperando por eso.
    mockSdk.listCommands.mockRejectedValue(new Error("sin red"));

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-activate");

    await waitFor(
      () => expect(v.getByTestId("ack-title")).toHaveTextContent("SIN CONFIRMACIÓN DEL GABINETE"),
      { timeout: 60_000 },
    );
  });
});

describe("[T-2.107 · spec §2.2] silenciar con alerta vigente NO apaga la sirena", () => {
  const INCIDENTE = {
    incident_id: "inc-1",
    max_pga_g: 0.08,
    node_count: 3,
    opened_at: "2026-08-10T09:59:00Z",
    severity: "high",
    state: "open",
    trigger: "sasmex",
  };

  /** La sirena SONANDO de verdad, según la traza BMS del incidente abierto —
   *  que es de donde sale el preflight de silenciar. */
  const SIRENA_SONANDO = [
    {
      action_id: "a-1",
      incident_id: "inc-1",
      tenant_id: "t-1",
      ts: "2026-08-10T09:59:05Z",
      kind: "siren_on",
      actor: "system",
      payload: {},
    },
  ];

  beforeEach(() => {
    mockSdk.listIncidentActions.mockResolvedValue({ data: SIRENA_SONANDO });
    mockSdk.issueCommand.mockResolvedValue({ data: comando({ action: "deactivate" }) });
  });

  it("acuse REAL de hoy (sin censo del relé) + alerta vigente ⇒ se explica el porqué", async () => {
    // Este es el `ack` que el ingest persiste HOY
    // (`api/src/takab_api/ingest/handlers.py`, `handle_command_ack`): no trae
    // el estado del relé, porque el gabinete tampoco lo manda.
    mockSdk.mobileState.mockResolvedValue({
      data: estado({ phase: "alert_active", incident: INCIDENTE as never }),
    });
    mockSdk.listCommands.mockResolvedValue({
      data: {
        items: [
          comando({
            action: "deactivate",
            status: "acked",
            ack: {
              channel: "siren",
              action: "deactivate",
              success: true,
              latency_s: 0.12,
              detail: "relay",
            },
          }),
        ],
      },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-silence");

    await waitFor(
      () =>
        expect(v.getByTestId("ack-title")).toHaveTextContent(
          "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
        ),
      { timeout: 20_000 },
    );
    // El porqué, con su fuente nombrada.
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/ALERTA VIGENTE/);
    expect(v.getByTestId("ack-detail")).toHaveTextContent(
      /el arbitraje mantiene la sirena hasta que la alerta cese/,
    );
    // Y JAMÁS el éxito fingido.
    expect(v.queryByText(/^SIRENA SILENCIADA$/)).toBeNull();
    // La sirena, en efecto, sigue sonando en la traza del gabinete.
    expect(v.getByTestId("bms-siren_on")).toHaveTextContent(/SIRENA\s*ACTIVADA/);
  });

  it("cuando el acuse SÍ trae el relé recalculado, manda el acuse", async () => {
    // Camino que el contrato habilitará: el ack con el estado del relé. La
    // lectura no depende de la fase — la manda el gabinete.
    mockSdk.mobileState.mockResolvedValue({
      data: estado({ phase: "shaking_concluded", incident: INCIDENTE as never }),
    });
    mockSdk.listCommands.mockResolvedValue({
      data: {
        items: [
          comando({
            action: "deactivate",
            status: "acked",
            ack: { channel: "siren", action: "deactivate", success: true, siren: "on" },
          }),
        ],
      },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-silence");

    await waitFor(
      () =>
        expect(v.getByTestId("ack-title")).toHaveTextContent(
          "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
        ),
      { timeout: 20_000 },
    );
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/otra demanda \(alerta vigente\) mantiene la sirena/);
  });

  it("sin alerta vigente el retiro SÍ silencia: la frase no está a fuego", async () => {
    // El contraejemplo que impide que «LA SIRENA SIGUE ACTIVA» sea otra
    // mentira cableada (lección de T-2.104, al revés).
    mockSdk.mobileState.mockResolvedValue({
      data: estado({ phase: "shaking_concluded", incident: INCIDENTE as never }),
    });
    mockSdk.listCommands.mockResolvedValue({
      data: {
        items: [
          comando({
            action: "deactivate",
            status: "acked",
            ack: { channel: "siren", action: "deactivate", success: true, detail: "relay" },
          }),
        ],
      },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await emitir(v, "ctl-silence");

    await waitFor(() => expect(v.getByTestId("ack-title")).toHaveTextContent("SIRENA SILENCIADA"), {
      timeout: 20_000,
    });
    expect(v.queryByText(/LA SIRENA SIGUE ACTIVA/)).toBeNull();
  });
});
