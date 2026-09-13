// [T-7.29] EL VIGILANTE TIENE QUE RESPETAR LA SALIDA DEL TÁCTICO.
//
// El botón de salir de la toma no sirve de nada por sí solo: `CrisisWatcher`
// re-impone `/crisis` en cada render mientras la fase sea `alert_active`, así
// que sin esta excepción el brigadista volvería a la pantalla de instrucción
// en el render siguiente al toque — y parecería que el botón no hace nada.
//
// La excepción es POR INCIDENTE, y ese es el segundo test: una alerta nueva
// vuelve a tomar la pantalla aunque saliera de la anterior.
import { act, render } from "@testing-library/react-native";

import { CrisisWatcher } from "./CrisisWatcher";
import { marcarSalidaTactica, reiniciarSalidaTactica } from "./salidaTactica";

// El prefijo `mock` no es estilo: jest HOISTEA las factorías de `jest.mock`
// por encima de las constantes del módulo, y solo deja tocar variables que
// empiecen así. Sin él: «Invalid variable access».
const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/(brigadista)/panel",
}));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({
    remove: jest.fn(),
  })),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => "sitio-1" }));

let mockIncidente = "i-1";
jest.mock("./useAlertState", () => ({
  MOBILE_STATE_KEY: "mobile-state",
  useAlertState: () => ({
    state: "alert_active",
    data: { incident: { incident_id: mockIncidente } },
  }),
}));

beforeEach(() => {
  mockPush.mockClear();
  reiniciarSalidaTactica();
  mockIncidente = "i-1";
});

describe("[T-7.29] salida táctica y toma de pantalla", () => {
  it("sin salir, la toma se IMPONE (conducta de siempre)", async () => {
    await act(async () => {
      render(<CrisisWatcher />);
    });
    expect(mockPush).toHaveBeenCalledWith("/crisis");
  });

  it("tras salir de ESTE incidente, ya no lo devuelve a la pantalla", async () => {
    marcarSalidaTactica("i-1");
    await act(async () => {
      render(<CrisisWatcher />);
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("una alerta NUEVA vuelve a tomar la pantalla", async () => {
    marcarSalidaTactica("i-1");
    mockIncidente = "i-2";
    await act(async () => {
      render(<CrisisWatcher />);
    });
    expect(mockPush).toHaveBeenCalledWith("/crisis");
  });
});
