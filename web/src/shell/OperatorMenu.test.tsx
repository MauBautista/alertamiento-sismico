// Menú del operador (T-1.49): nombre editable con fallback honesto al rol.

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ME_FIXTURES } from "../test-utils/meFixtures";
import OperatorMenu from "./OperatorMenu";

const mocks = vi.hoisted(() => ({
  useProfile: vi.fn(),
  useProfileMutation: vi.fn(),
  mutate: vi.fn(),
}));

vi.mock("../auth/useProfile", () => ({
  useProfile: mocks.useProfile,
  useProfileMutation: mocks.useProfileMutation,
}));

function seed(): void {
  useSessionStore.setState({
    status: "authenticated",
    origin: "dev",
    idToken: "t",
    me: ME_FIXTURES.soc_operator,
  });
}

beforeEach(() => {
  resetSessionStoreForTests();
  mocks.mutate.mockReset();
  mocks.useProfile.mockReturnValue({ data: undefined });
  mocks.useProfileMutation.mockReturnValue({
    mutate: mocks.mutate,
    isPending: false,
    isError: false,
  });
});

describe("OperatorMenu", () => {
  it("sin perfil muestra el ROL como fallback honesto (nunca inventa nombre)", () => {
    seed();
    render(<OperatorMenu />);
    expect(screen.getByRole("button", { expanded: false })).toHaveTextContent("soc_operator");
  });

  it("con display_name lo muestra y el caption conserva rol · sub8", () => {
    mocks.useProfile.mockReturnValue({
      data: { user_sub: "u", display_name: "M. Rodríguez", updated_at: null },
    });
    seed();
    render(<OperatorMenu />);
    const btn = screen.getByRole("button", { expanded: false });
    expect(btn).toHaveTextContent("M. Rodríguez");

    fireEvent.click(btn);
    expect(screen.getByText(/soc_operator · sub-soc_/)).toBeInTheDocument();
  });

  it("guarda el nombre NORMALIZADO (trim + colapso de espacios)", () => {
    seed();
    render(<OperatorMenu />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.change(screen.getByLabelText("NOMBRE DE OPERADOR"), {
      target: { value: "  Mauricio   B.  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR" }));
    expect(mocks.mutate).toHaveBeenCalledWith("Mauricio B.", expect.anything());
  });

  it("GUARDAR queda deshabilitado con nombre vacío/espacios", () => {
    seed();
    render(<OperatorMenu />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.change(screen.getByLabelText("NOMBRE DE OPERADOR"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "GUARDAR" })).toBeDisabled();
    expect(mocks.mutate).not.toHaveBeenCalled();
  });

  it("error de guardado ⇒ aviso con role=alert (el menú no se cierra)", () => {
    mocks.useProfileMutation.mockReturnValue({
      mutate: mocks.mutate,
      isPending: false,
      isError: true,
    });
    seed();
    render(<OperatorMenu />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("alert")).toHaveTextContent("NO SE PUDO GUARDAR");
  });

  it("SALIR dispara logout() del store", () => {
    seed();
    const logout = vi.fn().mockResolvedValue(undefined);
    useSessionStore.setState({ logout });
    render(<OperatorMenu />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.click(screen.getByRole("button", { name: /Cerrar sesión/ }));
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
