// [T-2.116 + T-2.110] EL ESTADO DEL RELÉ, LEÍDO — NO INFERIDO.
//
// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre todo lo que
// hay ahí con un `require.context` y un `*.test.tsx` dentro ROMPE EL BUNDLE
// (pasó el 2026-08-08). Aquí se importa la ruta REAL `(brigadista)/panel.tsx`.
//
// ESTE FICHERO ES LA PATA 3 DEL E2E de T-2.116. El acuse que llega a la hoja no
// se escribe a mano: se lee de `edge/tests/vectors/command_ack_siren_arbitrado
// .json`, el MISMO archivo que produce el gabinete real en
// `edge/tests/test_estado_del_rele_en_el_acuse.py` (pata 1) y que persiste la
// nube en `api/tests/commands/test_e2e_estado_del_rele.py` (pata 2). Si el edge
// deja de emitir el campo, cae la pata 1; si la nube deja de guardarlo, la 2; y
// si la app vuelve a inferirlo, ésta.
//
// LOS DOS DEFECTOS QUE CIERRA:
//
//  · T-2.116 — `sirenStillOn()` sondeaba `ack.siren ?? ack.relay_state ??
//    ack.state`, TRES campos que no existen en ningún contrato. Nunca pudo
//    dispararse con datos reales; lo que salvaba la pantalla era el respaldo de
//    T-2.107, que infiere «sigue activa» de la FASE del sitio. La spec §2.2
//    pide lo contrario: «el resultado real llega en el `command_ack` con el
//    estado recalculado del relé».
//  · T-2.110 — `sirenActive` salía de que EXISTIERA un `siren_on` en la traza.
//    `siren_off` no estaba en `ACTION_STATE`, así que nada lo cancelaba: un
//    `siren_on` histórico dejaba la precondición «El gabinete reporta la sirena
//    activa» satisfecha el resto del incidente, y el detalle afirmaba que el
//    gabinete lo reportaba sin que nadie lo hubiera reportado.
import { sirenEvidence, type CommandOut, type IncidentActionOut, type MobileStateOut } from "@takab/sdk";
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

// El acuse REAL del gabinete, generado por la pata 1 del E2E. Se IMPORTA el
// archivo del edge en vez de copiar su contenido: es lo que hace que las tres
// patas hablen del MISMO payload y no de tres que se parecen.
import vector from "../../../../edge/tests/vectors/command_ack_siren_arbitrado.json";

const SITE = "11111111-1111-1111-1111-111111111111";

const ACUSE_DEL_GABINETE = vector as unknown as Record<string, unknown>;

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

const INCIDENTE = {
  incident_id: "inc-1",
  max_pga_g: 0.08,
  node_count: 3,
  opened_at: "2026-08-10T09:59:00Z",
  severity: "high",
  state: "open",
  trigger: "sasmex",
};

function estado(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: "2026-08-10T10:00:00Z",
    phase: "shaking_concluded",
    incident: INCIDENTE,
    latest_tier: "normal",
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, next_scheduled_at: null, last_started_at: null, last_note: null },
    building_alarm: null,
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

function comando(over: Partial<CommandOut> = {}): CommandOut {
  return {
    command_id: "cmd-1",
    tenant_id: "t-1",
    site_id: SITE,
    gateway_id: "g-1",
    issued_by: "u-1",
    channel: "siren",
    action: "deactivate",
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

/** Una fila de la traza BMS del incidente abierto. */
function accion(
  kind: string,
  ts: string,
  payload: Record<string, unknown> = {},
): IncidentActionOut {
  return {
    action_id: `a-${kind}-${ts}`,
    incident_id: "inc-1",
    tenant_id: "t-1",
    ts,
    kind,
    actor: "edge:gw-dev-0001",
    payload,
  } as IncidentActionOut;
}

/** El `channel_state` REAL del gabinete, con `activated` a voluntad. */
function rele(activated: boolean): Record<string, unknown> {
  return {
    channel_state: {
      ...(ACUSE_DEL_GABINETE.channel_state as Record<string, unknown>),
      activated,
      energized: activated,
      reason: activated ? "alert" : null,
      alert_latched: activated,
    },
  };
}

// ------------------------------------------------------------------ arneses

const cliente = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });

function Envoltura(props: { children: ReactNode }) {
  return <QueryClientProvider client={cliente}>{props.children}</QueryClientProvider>;
}

async function asentar(): Promise<void> {
  await act(async () => {});
}

async function pulsar(v: RenderResult, testID: string): Promise<void> {
  const usuario = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  await usuario.press(v.getByTestId(testID));
}

/** Deslizamiento REAL sobre el `PanResponder` del paso 2. */
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

/** Abre el preflight de SILENCIAR y devuelve la hoja pintada. */
async function abrirSilenciar(v: RenderResult): Promise<void> {
  await waitFor(() => expect(v.getByTestId("ctl-silence")).toBeTruthy());
  await pulsar(v, "ctl-silence");
  await asentar();
}

/** Camino completo: preflight + deslizamiento hasta el acuse. */
async function silenciar(v: RenderResult): Promise<void> {
  await abrirSilenciar(v);
  await pulsar(v, "to-step-2");
  await deslizar(v);
  await waitFor(() => expect(v.getByTestId("ack-title")).toBeTruthy());
}

// ------------------------------------------------------------------ setup

beforeEach(() => {
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
    me: { allowed_actions: { manual_activate: true, siren_silence: true } } as never,
    deniedReason: null,
  });
});

afterEach(() => {
  jest.useRealTimers();
});

// ------------------------------------------------------ E2E · pata 3 (T-2.116)

describe("[T-2.116 · spec §2.2] el acuse del gabinete trae el estado del relé", () => {
  it("el vector compartido es el acuse arbitrado del gabinete real", () => {
    // Guardia del E2E: si la pata 1 dejara de producir esta forma, este test
    // cae aquí y no en una aserción de UI que costaría media tarde leer.
    expect(ACUSE_DEL_GABINETE.channel).toBe("siren");
    expect(ACUSE_DEL_GABINETE.action).toBe("deactivate");
    expect(ACUSE_DEL_GABINETE.success).toBe(true);
    expect(ACUSE_DEL_GABINETE.channel_state).toMatchObject({
      channel: "siren",
      activated: true,
      reason: "alert",
    });
  });

  it("E2E: silenciar con alerta vigente ⇒ el acuse dice que la sirena sigue energizada", async () => {
    // LA FASE NO PUEDE EXPLICARLO: el sitio está en `shaking_concluded`, así que
    // el respaldo de T-2.107 (`alertActive`) NO se activa. Si la pantalla dice
    // «sigue activa», es porque LEYÓ el relé del acuse.
    mockSdk.mobileState.mockResolvedValue({ data: estado({ phase: "shaking_concluded" }) });
    mockSdk.listIncidentActions.mockResolvedValue({
      data: [accion("siren_on", "2026-08-10T09:59:05Z", rele(true))],
    });
    mockSdk.listCommands.mockResolvedValue({
      data: { items: [comando({ status: "acked", ack: ACUSE_DEL_GABINETE })] },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await silenciar(v);

    await waitFor(
      () =>
        expect(v.getByTestId("ack-title")).toHaveTextContent(
          "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
        ),
      { timeout: 20_000 },
    );
    // …y el porqué sale del ACUSE, nombrando el relé y su motivo.
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/relé de la sirena/i);
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/alerta vigente/i);
    expect(v.queryByText(/^SIRENA SILENCIADA$/)).toBeNull();
  });

  it("el acuse manda sobre la fase: relé APAGADO en plena alerta ⇒ silenciada", async () => {
    // El contraejemplo que impide que la frase vuelva a estar a fuego (lección
    // de T-2.104, al revés). El sitio está en ALERTA y aun así el gabinete
    // declara el relé en reposo: gana el gabinete, que es quien lo midió.
    mockSdk.mobileState.mockResolvedValue({ data: estado({ phase: "alert_active" }) });
    mockSdk.listIncidentActions.mockResolvedValue({
      data: [accion("siren_on", "2026-08-10T09:59:05Z", rele(true))],
    });
    mockSdk.listCommands.mockResolvedValue({
      data: {
        items: [
          comando({
            status: "acked",
            ack: { ...ACUSE_DEL_GABINETE, ...rele(false) },
          }),
        ],
      },
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await silenciar(v);

    await waitFor(() => expect(v.getByTestId("ack-title")).toHaveTextContent("SIRENA SILENCIADA"), {
      timeout: 20_000,
    });
    expect(v.queryByText(/LA SIRENA SIGUE ACTIVA/)).toBeNull();
  });

  it("gabinete sin re-desplegar (acuse sin relé): se sigue explicando, citando la fase", async () => {
    // Degradación honesta: sin el campo, el respaldo de T-2.107 sigue vivo y la
    // pantalla nombra su fuente (la alerta vigente), no un relé que nadie midió.
    mockSdk.mobileState.mockResolvedValue({ data: estado({ phase: "alert_active" }) });
    mockSdk.listCommands.mockResolvedValue({
      data: {
        items: [
          comando({
            status: "acked",
            ack: { channel: "siren", action: "deactivate", success: true, detail: "relay" },
          }),
        ],
      },
    });

    mockSdk.listIncidentActions.mockResolvedValue({
      data: [accion("siren_on", "2026-08-10T09:59:05Z")],
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await silenciar(v);

    await waitFor(
      () =>
        expect(v.getByTestId("ack-title")).toHaveTextContent(
          "SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA",
        ),
      { timeout: 20_000 },
    );
    expect(v.getByTestId("ack-detail")).toHaveTextContent(/ALERTA VIGENTE/);
  });
});

// ------------------------------------ T-2.110 · la regla, aparte de la pantalla

describe("[T-2.110] `sirenEvidence` — el relé manda sobre el verbo", () => {
  it("con censo del relé, el verbo no decide", () => {
    // Una fila `siren_on` cuyo relé dice REPOSO: la orden se ejecutó y el
    // arbitraje la descartó. Si mandara el `kind`, esto diría «sonando».
    const e = sirenEvidence([accion("siren_on", "2026-08-10T10:00:00Z", rele(false))]);
    expect(e).toEqual({ active: false, fromRelay: true, at: "2026-08-10T10:00:00Z" });
  });

  it("sin censo del relé, se usa el verbo y se DECLARA que es el verbo", () => {
    const e = sirenEvidence([accion("siren_off", "2026-08-10T10:00:00Z")]);
    expect(e).toEqual({ active: false, fromRelay: false, at: "2026-08-10T10:00:00Z" });
  });

  it("manda la MÁS RECIENTE, no la primera ni la última de la lista", () => {
    const e = sirenEvidence([
      accion("siren_off", "2026-08-10T10:05:00Z"),
      accion("siren_on", "2026-08-10T10:00:00Z"),
    ]);
    expect(e?.active).toBe(false);
    expect(e?.at).toBe("2026-08-10T10:05:00Z");
  });

  it("sin acciones de sirena devuelve `null` — «no consta», no «apagada»", () => {
    expect(sirenEvidence([])).toBeNull();
    expect(sirenEvidence([accion("gas_closed", "2026-08-10T10:00:00Z")])).toBeNull();
  });

  it("[T-2.75.a] una acción SIMULADA no sostiene ni desmiente nada", () => {
    expect(sirenEvidence([accion("siren_on", "2026-08-10T10:00:00Z", { simulated: true })])).toBeNull();
  });

  it("empate exacto de `ts`: gana SONANDO (nunca minimizar lo que pasa)", () => {
    const e = sirenEvidence([
      accion("siren_off", "2026-08-10T10:00:00Z"),
      accion("siren_on", "2026-08-10T10:00:00Z"),
    ]);
    expect(e?.active).toBe(true);
  });
});

// --------------------------------------------------- T-2.110 · el enclavamiento

describe("[T-2.110] el estado de sirena se LIBERA, y la precondición no se autoriza sola", () => {
  it("ciclo encender→apagar: tras el `siren_off` la precondición es FALSA", async () => {
    // EL DEFECTO, en tres filas: con sólo la primera la precondición quedaba
    // satisfecha el resto del incidente, porque `siren_off` no cancelaba nada.
    mockSdk.listIncidentActions.mockResolvedValue({
      data: [
        accion("siren_on", "2026-08-10T09:59:05Z", rele(true)),
        accion("siren_off", "2026-08-10T09:59:40Z", rele(false)),
      ],
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await abrirSilenciar(v);

    expect(v.getByTestId("pre-no")).toBeTruthy();
    expect(v.getByTestId("pre-blocked")).toBeTruthy();
    expect(v.queryByText(/El gabinete reporta la sirena activa/)).toBeNull();
    expect(v.getByText(/El gabinete reporta el relé de la sirena EN REPOSO/)).toBeTruthy();
  });

  it("mientras el relé sigue energizado la precondición SÍ se cumple", async () => {
    // El contraejemplo: liberar no puede volverse «nunca se puede silenciar».
    mockSdk.listIncidentActions.mockResolvedValue({
      data: [accion("siren_on", "2026-08-10T09:59:05Z", rele(true))],
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await abrirSilenciar(v);

    expect(v.getByTestId("pre-ok")).toBeTruthy();
    expect(v.queryByTestId("pre-blocked")).toBeNull();
    expect(v.getByText(/El gabinete reporta el relé de la sirena ENERGIZADO/)).toBeTruthy();
  });

  it("un `siren_on` cuyo relé dice REPOSO no autoriza nada, aunque sea el único", async () => {
    // La orden se ejecutó y el arbitraje la descartó: el `kind` dice «encender»
    // y el relé dice «apagada». Manda el relé — es lo que la spec §2.1 pide.
    mockSdk.listIncidentActions.mockResolvedValue({
      data: [accion("siren_on", "2026-08-10T09:59:05Z", rele(false))],
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await abrirSilenciar(v);

    expect(v.getByTestId("pre-no")).toBeTruthy();
    expect(v.queryByText(/El gabinete reporta la sirena activa/)).toBeNull();
  });

  it("sin censo del relé se cita la ORDEN, y se dice que es la orden", async () => {
    // Gabinete sin re-desplegar: la traza sólo tiene verbos. Se usa el último,
    // y el detalle NO afirma que el gabinete reporte el relé — porque no lo hizo.
    mockSdk.listIncidentActions.mockResolvedValue({
      data: [accion("siren_on", "2026-08-10T09:59:05Z")],
    });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await abrirSilenciar(v);

    expect(v.getByTestId("pre-ok")).toBeTruthy();
    expect(v.getByText(/última orden ejecutada sobre la sirena fue de ACTIVACIÓN/)).toBeTruthy();
    expect(v.queryByText(/El gabinete reporta el relé/)).toBeNull();
  });

  it("sin ninguna actuación de sirena, la precondición NO se da por buena", async () => {
    mockSdk.listIncidentActions.mockResolvedValue({ data: [] });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await abrirSilenciar(v);

    expect(v.getByTestId("pre-no")).toBeTruthy();
    expect(v.getByText(/No consta ninguna actuación de sirena/)).toBeTruthy();
  });

  it("la ALARMA DE INMUEBLE sostiene la precondición aunque no haya incidente", async () => {
    // [T-2.106] El quórum de pánico enciende la sirena SIN abrir incidente, así
    // que la traza está vacía por diseño. La verdad corroborada de que suena
    // vive en `mobile-state.building_alarm`, y sin ella el táctico no podría
    // silenciar justo la alarma que tiene delante.
    mockSdk.mobileState.mockResolvedValue({
      data: estado({
        phase: "building_alarm",
        incident: null,
        building_alarm: {
          since: "2026-08-10T09:58:00Z",
          ordered_by: "quórum de pánico",
        } as never,
      }),
    });
    mockSdk.listIncidentActions.mockResolvedValue({ data: [] });

    const v = await render(<Panel />, { wrapper: Envoltura });
    await abrirSilenciar(v);

    expect(v.getByTestId("pre-ok")).toBeTruthy();
    expect(v.getByText(/alarma del inmueble/i)).toBeTruthy();
  });
});
