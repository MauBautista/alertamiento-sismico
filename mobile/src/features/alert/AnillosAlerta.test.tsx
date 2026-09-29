// [T-9.73 · D-47 · D-30] LOS ANILLOS DE LA ALERTA QUE AUTORIZA EVACUAR.
//
// Anillos concéntricos que se expanden DETRÁS de la instrucción de la toma de
// crisis. Tres límites, los de D-30:
//   1. el texto no se mueve — los anillos son vistas aparte, sin `Text`;
//   2. se paran por el ESTADO DEL SERVIDOR (`viva`, que la ruta saca de la fase
//      de `machine.ts`), nunca por un cronómetro del teléfono;
//   3. con «reducir movimiento» queda UN anillo fijo.
// Y sólo con una alerta que AUTORIZA evacuar: SASMEX o el cuórum de red. Una
// estación sola (el umbral local, D-39) o una activación manual no la llevan.
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";
import { Animated } from "react-native";

import { CrisisView } from "./CrisisView";
import { autorizaEvacuar, sourceLabel } from "./source";

import Crisis from "@/app/crisis";

const HIDDEN = { includeHiddenElements: true } as const;
const ANIMADOS = ["crisis-anillo-0", "crisis-anillo-1", "crisis-anillo-2"];

const de = (trigger: string) => sourceLabel({ trigger, max_pga_g: null, node_count: 3 });

const base = { policy: "evacuate" as const, elapsedS: 5, zoneName: null };

// ------------------------------------------------------------------ la regla

describe("autorizaEvacuar · sólo SASMEX o el cuórum de red", () => {
  it("SASMEX y cuórum autorizan", () => {
    expect(autorizaEvacuar("sasmex")).toBe(true);
    expect(autorizaEvacuar("quorum")).toBe(true);
  });

  it("una estación sola, una activación manual o lo desconocido NO", () => {
    for (const t of ["local_threshold", "manual", "misterio", ""]) {
      expect(autorizaEvacuar(t)).toBe(false);
    }
  });
});

// ------------------------------------------------------------------ la vista

describe("CrisisView · anillos", () => {
  let loop: jest.SpyInstance;
  beforeEach(() => {
    loop = jest.spyOn(Animated, "loop");
  });
  afterEach(() => {
    loop.mockRestore();
  });

  it("con alerta viva que AUTORIZA hay tres anillos animados detrás del texto", async () => {
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<CrisisView {...base} source={de("sasmex")} autoriza viva />);
    });
    const capa = v.getByTestId("crisis-anillos", HIDDEN);
    // No se come el toque y el lector de pantalla no la lee.
    expect(capa.props.pointerEvents).toBe("none");
    expect(capa.props.accessibilityElementsHidden).toBe(true);
    for (const id of ANIMADOS) {
      expect(v.getByTestId(id, HIDDEN)).toBeTruthy();
    }
    expect(v.queryByTestId("crisis-anillo-fijo", HIDDEN)).toBeNull();
    // halo (1) + anillos (3): el bucle arrancó para cada uno.
    expect(loop).toHaveBeenCalledTimes(4);
    // El texto sigue ahí, en su sitio.
    expect(v.getByText(/EVACÚE/)).toBeTruthy();
  });

  it("con el cuórum de red también", async () => {
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<CrisisView {...base} source={de("quorum")} autoriza viva />);
    });
    expect(v.getByTestId("crisis-anillo-0", HIDDEN)).toBeTruthy();
  });

  it("con un AVISO de una estación sola NO hay anillos", async () => {
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(
        <CrisisView {...base} source={de("local_threshold")} autoriza={false} viva />,
      );
    });
    expect(v.queryByTestId("crisis-anillos", HIDDEN)).toBeNull();
    // El halo de la alerta viva sigue: los anillos son lo único que se retira.
    expect(v.getByTestId("crisis-halo", HIDDEN)).toBeTruthy();
  });

  it("sin declarar `autoriza` NO hay anillos: ausente no es sí", async () => {
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<CrisisView {...base} source={de("sasmex")} viva />);
    });
    expect(v.queryByTestId("crisis-anillos", HIDDEN)).toBeNull();
  });

  it("cuando el servidor deja de sostener la alerta (movimiento concluido, reingreso) se PARAN", async () => {
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<CrisisView {...base} source={de("sasmex")} autoriza viva />);
    });
    expect(v.getByTestId("crisis-anillo-0", HIDDEN)).toBeTruthy();
    await act(async () => {
      v.rerender(<CrisisView {...base} source={de("sasmex")} autoriza viva={false} />);
    });
    expect(v.queryByTestId("crisis-anillos", HIDDEN)).toBeNull();
    expect(v.getByText(/EVACÚE/)).toBeTruthy();
  });

  it("con «reducir movimiento» queda UN anillo FIJO y nada arranca un bucle", async () => {
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(
        <CrisisView {...base} source={de("sasmex")} autoriza reduceMotion viva />,
      );
    });
    expect(v.getByTestId("crisis-anillo-fijo", HIDDEN)).toBeTruthy();
    for (const id of ANIMADOS) {
      expect(v.queryByTestId(id, HIDDEN)).toBeNull();
    }
    expect(loop).not.toHaveBeenCalled();
  });
});

// ------------------------------------------------------------------ la ruta

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = Date.now();

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
    useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  };
});
jest.mock("@/features/alert/sound", () => ({
  startAlertLoop: jest.fn(async () => undefined),
  stopAlertLoop: jest.fn(),
}));
jest.mock("@/features/alert/vibration", () => ({
  PATRON_ALERTA: [0],
  startAlertVibration: jest.fn(),
  restartAlertVibration: jest.fn(),
  stopAlertVibration: jest.fn(),
}));
jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: null; profile: string | null }) => unknown) =>
    sel({ status: "authenticated", me: null, profile: "occupant" }),
}));
jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => SITE }));

let mockSnapshot: Record<string, unknown>;
jest.mock("@/features/alert/useAlertState", () => ({ useAlertState: () => mockSnapshot }));

function conTrigger(trigger: string, phase = "alert_active", state = "alert_active") {
  const data = {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase,
    incident: {
      incident_id: "inc-1",
      opened_at: new Date(AHORA - 5_000).toISOString(),
      trigger,
      severity: "high",
      state: "open",
      max_pga_g: null,
      node_count: 3,
    },
    latest_tier: "evacuate_or_hold",
    my_zone: { zone_id: "z-1", name: "Piso 12", evac_policy: "evacuate" },
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
  } as unknown as MobileStateOut;
  return {
    state,
    data,
    hasOwnCheckin: false,
    refetch: jest.fn(),
    dataUpdatedAt: AHORA,
    loading: false,
    error: null,
    staleSinceMs: null,
  };
}

describe("ruta de crisis · la autorización sale del trigger del SERVIDOR", () => {
  it.each(["sasmex", "quorum"])("%s ⇒ anillos", async (trigger) => {
    mockSnapshot = conTrigger(trigger);
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<Crisis />);
    });
    expect(v.getByTestId("crisis-anillos", HIDDEN)).toBeTruthy();
    await v.unmount();
  });

  it.each(["local_threshold", "manual"])("%s ⇒ sin anillos", async (trigger) => {
    mockSnapshot = conTrigger(trigger);
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<Crisis />);
    });
    // La toma sí está (el control): lo que falta son los anillos.
    expect(v.getByTestId("crisis-halo", HIDDEN)).toBeTruthy();
    expect(v.queryByTestId("crisis-anillos", HIDDEN)).toBeNull();
    await v.unmount();
  });

  it("movimiento del inmueble ⇒ la ruta no pinta la toma, ni anillos", async () => {
    mockSnapshot = conTrigger("local_threshold", "building_movement", "building_movement");
    let v!: Awaited<ReturnType<typeof render>>;
    await act(async () => {
      v = await render(<Crisis />);
    });
    expect(v.getByTestId("redirect")).toBeTruthy();
    expect(v.queryByTestId("crisis-anillos", HIDDEN)).toBeNull();
    await v.unmount();
  });
});
