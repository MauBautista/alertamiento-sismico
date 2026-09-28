// UBICACIÓN: fuera de `src/app/` a propósito (expo-router barre `src/app`).
//
// [F2 · D-42] Pasada la baja de los alias, un rol retirado cierra la sesión con
// motivo `rol_retirado`. El login tiene que decir POR QUÉ y qué hacer: volver a
// entrar no lo arregla hasta que un administrador asigne un rol vigente.
import { render } from "@testing-library/react-native";

import Login from "@/app/login";
import { useSessionStore } from "@/auth/session.store";

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return { Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text> };
});

jest.mock("@/auth/useAuth", () => ({
  useLogin: () => ({ ready: true, configured: true, error: null, promptAsync: jest.fn() }),
}));

const MENSAJE =
  "Tu rol fue retirado. Pide a tu administrador que te asigne uno de los roles vigentes.";

describe("login · motivo del último cierre", () => {
  it("rol retirado ⇒ dice que el rol fue retirado y qué hacer", async () => {
    useSessionStore.setState({ status: "anonymous", signOutReason: "rol_retirado" });
    const { getByText } = await render(<Login />);
    expect(getByText(MENSAJE)).toBeTruthy();
  });

  it("cualquier otro motivo (o ninguno) no lo dice", async () => {
    useSessionStore.setState({ status: "anonymous", signOutReason: "expired" });
    const { queryByText } = await render(<Login />);
    expect(queryByText(MENSAJE)).toBeNull();
  });
});
