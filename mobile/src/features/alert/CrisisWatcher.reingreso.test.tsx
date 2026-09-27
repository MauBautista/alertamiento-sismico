// [T-9.04] EL BLOQUEO PERSISTENTE NO ES UNA TOMA DE PANTALLA.
//
// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre ese árbol
// con `require.context` y un `*.test.tsx` ahí dentro rompe el bundle.
//
// El servidor sirve `phase = reentry_blocked` DÍAS después del sismo (un NO
// HABITAR firmado no caduca). Si el vigilante lo tratara como crisis, cada vez
// que el ocupante abriera la app lo arrancaría de donde estuviera. Se pinta en
// INICIO (cartel o franja) y el vigilante no mueve a nadie.
import { act, render } from "@testing-library/react-native";

import { CrisisWatcher } from "./CrisisWatcher";
import { deriveAlertState } from "./machine";

// Prefijo `mock`: jest HOISTEA las factorías y sólo deja tocar esas variables.
const mockPush = jest.fn();
let mockPathname = "/(occupant)/inicio";

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockPathname,
}));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => "sitio-1" }));

let mockReason: string | null = "no_habitable";
// El CONTROL POSITIVO cambia la fase a `alert_active`: sin él, un vigilante roto
// que no empujara NUNCA pasaría todos los casos de «no toma la pantalla».
let mockPhase: "reentry_blocked" | "alert_active" = "reentry_blocked";
jest.mock("./useAlertState", () => ({
  MOBILE_STATE_KEY: "mobile-state",
  useAlertState: () => ({
    // El estado sale de la máquina REAL: si alguien cambia el mapeo de la
    // fase, este test lo ve.
    state: jest.requireActual("./machine").deriveAlertState(mockPhase, false),
    data: {
      phase: mockPhase,
      incident:
        mockPhase === "alert_active"
          ? { incident_id: "i-abierto", opened_at: "2026-09-27T12:00:00Z" }
          : null,
      building_alarm: null,
      reentry: {
        blocked: true,
        dictamen_signed: mockReason === "no_habitable",
        dictamen_status: null,
        incident_id: "i-cerrado",
        reason: mockReason,
      },
    },
  }),
}));

beforeEach(() => {
  mockPush.mockClear();
  mockPathname = "/(occupant)/inicio";
  mockPhase = "reentry_blocked";
});

describe("[T-9.04] CrisisWatcher frente al reingreso bloqueado del servidor", () => {
  it("CONTROL POSITIVO: con alerta viva el MISMO montaje sí empuja a /crisis", async () => {
    mockPhase = "alert_active";
    mockReason = null;
    await act(async () => {
      render(<CrisisWatcher />);
    });
    expect(mockPush).toHaveBeenCalledWith("/crisis");
  });

  it("la máquina lo reconoce (no cae al `default`)", () => {
    expect(deriveAlertState("reentry_blocked", false)).toBe("reentry_blocked");
  });

  it.each(["no_habitable", "pendiente_dictamen", "pendiente_confirmacion", null])(
    "reason=%s ⇒ el vigilante NO toma la pantalla",
    async (reason) => {
      mockReason = reason;
      await act(async () => {
        render(<CrisisWatcher />);
      });
      expect(mockPush).not.toHaveBeenCalled();
    },
  );

  it("tampoco desde otra pestaña: no hay ruta a la que empujar", async () => {
    mockReason = "no_habitable";
    mockPathname = "/(occupant)/directorio";
    await act(async () => {
      render(<CrisisWatcher />);
    });
    expect(mockPush).not.toHaveBeenCalled();
  });
});
