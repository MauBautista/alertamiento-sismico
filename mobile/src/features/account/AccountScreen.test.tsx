// [T-8.11 · A-021] Sin red, la pestaña CUENTA seguía siendo la única salida de la
// sesión… y el marco de estados la tapaba entera: con /me/profile caído
// desaparecían CERRAR SESIÓN, permisos y privacidad. El marco ahora envuelve
// SOLO la tarjeta de perfil.
import { fireEvent, render } from "@testing-library/react-native";

import { AccountScreen } from "./AccountScreen";

const mockLogout = jest.fn(async () => ({ push: "skipped", refresh: "none", hostedUi: "skipped" }));
jest.mock("@/auth/logout", () => ({ logout: () => mockLogout() }));

jest.mock("expo-router", () => ({ useRouter: () => ({ push: jest.fn() }) }));

jest.mock("@/services/onboarding", () => ({
  getGpsConsent: async () => null,
  setGpsConsent: async () => undefined,
}));

const mockRefetch = jest.fn();
let mockPerfil: Record<string, unknown>;
jest.mock("@tanstack/react-query", () => ({
  useQuery: () => mockPerfil,
}));

beforeEach(() => {
  mockLogout.mockClear();
  mockRefetch.mockClear();
  mockPerfil = {
    data: undefined,
    isLoading: false,
    isError: true,
    dataUpdatedAt: 0,
    refetch: mockRefetch,
  };
});

describe("1.8 · CUENTA con el perfil caído", () => {
  it("el error se queda en la tarjeta de perfil y CERRAR SESIÓN sigue a la vista", async () => {
    const v = await render(<AccountScreen />);

    expect(v.getByTestId("state-error")).toHaveTextContent(/No se pudo cargar su perfil/);
    expect(v.getByTestId("logout")).toBeTruthy();
    // El marco ya no se come la tarjeta de privacidad ni la de permisos.
    expect(v.getByText("PRIVACIDAD Y PERMISOS")).toBeTruthy();
  });

  it("CERRAR SESIÓN usa el cierre completo, no el local", async () => {
    const v = await render(<AccountScreen />);

    await fireEvent.press(v.getByTestId("logout"));

    expect(mockLogout).toHaveBeenCalledTimes(1);
  });
});
