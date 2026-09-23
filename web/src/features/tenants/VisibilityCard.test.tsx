import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TenantOut, VisibilityGrantOut } from "@takab/sdk";

import VisibilityCard from "./VisibilityCard";
import type { VisibilityData, VisibilityMutations } from "./useVisibility";

const mocks = vi.hoisted(() => ({
  useVisibilityGrants: vi.fn(),
  useVisibilityMutations: vi.fn(),
}));

vi.mock("./useVisibility", () => ({
  useVisibilityGrants: mocks.useVisibilityGrants,
  useVisibilityMutations: mocks.useVisibilityMutations,
}));

function tenant(id: string, name: string): TenantOut {
  return {
    tenant_id: id,
    code: id,
    name,
    isolation_mode: "logical",
    vertical: null,
    visibility: "private",
    status: "active",
    plan_code: "mvp",
    row_version: "774100",
    created_at: "2026-01-01T00:00:00Z",
  };
}

const GRANTEE = tenant("g-1", "Hospital Uno");
const TARGET = tenant("t-2", "Universidad Dos");

function grantRow(over: Partial<VisibilityGrantOut> = {}): VisibilityGrantOut {
  return {
    grant_id: "gr-1",
    grantee_tenant_id: "g-1",
    target_tenant_id: "t-2",
    target_all: false,
    can_view_metadata: true,
    can_view_data: false,
    created_by: "x",
    created_at: "",
    updated_at: "",
    ...over,
  };
}

function visData(over: Partial<VisibilityData> = {}): VisibilityData {
  return { grants: [], loading: false, error: null, refetch: vi.fn(), ...over };
}

function visMut(over: Partial<VisibilityMutations> = {}): VisibilityMutations {
  return { grant: vi.fn(), revoke: vi.fn(), pending: false, error: null, ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useVisibilityGrants.mockReturnValue(visData());
  mocks.useVisibilityMutations.mockReturnValue(visMut());
});

describe("VisibilityCard", () => {
  it("sin grants declara que el cliente solo ve lo suyo", () => {
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    expect(screen.getByText(/SOLO VE LO SUYO/)).toBeTruthy();
  });

  it("lista los grants entrantes con su target y ejes", () => {
    mocks.useVisibilityGrants.mockReturnValue(visData({ grants: [grantRow()] }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    const row = screen.getByTestId("visibility-grant");
    expect(within(row).getByText(/Universidad Dos/)).toBeTruthy();
    expect(within(row).getByText(/METADATOS/)).toBeTruthy();
  });

  it("conceder a un cliente específico envía target + ejes", () => {
    const grant = vi.fn();
    mocks.useVisibilityMutations.mockReturnValue(visMut({ grant }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    fireEvent.change(screen.getByLabelText(/Conceder que vea a/), { target: { value: "t-2" } });
    fireEvent.click(screen.getByLabelText(/datos en vivo/)); // + datos (metadatos ya está)
    // [A-110] Datos EN VIVO de otro cliente: dos pasos (arma, confirma).
    fireEvent.click(screen.getByRole("button", { name: /Conceder/ }));
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
    expect(grant.mock.calls[0][0]).toEqual({
      grantee_tenant_id: "g-1",
      target_all: false,
      target_tenant_id: "t-2",
      can_view_metadata: true,
      can_view_data: true,
    });
  });

  it("target TODOS manda target_all sin target_tenant_id", () => {
    const grant = vi.fn();
    mocks.useVisibilityMutations.mockReturnValue(visMut({ grant }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    fireEvent.change(screen.getByLabelText(/Conceder que vea a/), { target: { value: "ALL" } });
    fireEvent.click(screen.getByRole("button", { name: /Conceder/ }));
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR/ }));
    expect(grant.mock.calls[0][0]).toEqual(
      expect.objectContaining({ target_all: true, target_tenant_id: null }),
    );
  });

  // [A-110 · T-8.09] Conceder a TODOS los clientes —con datos en vivo incluidos—
  // salía de un solo clic, y el formulario se vaciaba aunque el servidor lo
  // rechazara: el operador se quedaba sin saber qué había pedido.
  it("conceder a TODOS no sale de un solo clic", () => {
    const grant = vi.fn();
    mocks.useVisibilityMutations.mockReturnValue(visMut({ grant }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    fireEvent.change(screen.getByLabelText(/Conceder que vea a/), { target: { value: "ALL" } });
    fireEvent.click(screen.getByRole("button", { name: /Conceder/ }));
    expect(grant).not.toHaveBeenCalled();
  });

  it("si el servidor lo rechaza, lo elegido SIGUE en el formulario", () => {
    const grant = vi.fn(); // nunca llama a onSuccess: el servidor falló
    mocks.useVisibilityMutations.mockReturnValue(visMut({ grant }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    fireEvent.change(screen.getByLabelText(/Conceder que vea a/), { target: { value: "t-2" } });
    fireEvent.click(screen.getByRole("button", { name: /Conceder/ }));
    expect(grant).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText(/Conceder que vea a/)).toHaveValue("t-2");
  });

  it("si sale bien, el formulario se vacía", () => {
    const grant = vi.fn((_body: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
    mocks.useVisibilityMutations.mockReturnValue(visMut({ grant }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    fireEvent.change(screen.getByLabelText(/Conceder que vea a/), { target: { value: "t-2" } });
    fireEvent.click(screen.getByRole("button", { name: /Conceder/ }));
    expect(screen.getByLabelText(/Conceder que vea a/)).toHaveValue("");
  });

  it("Revocar llama al revoke con el grant_id", () => {
    const revoke = vi.fn();
    mocks.useVisibilityMutations.mockReturnValue(visMut({ revoke }));
    mocks.useVisibilityGrants.mockReturnValue(visData({ grants: [grantRow()] }));
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    fireEvent.click(screen.getByRole("button", { name: /Revocar/ }));
    expect(revoke).toHaveBeenCalledWith("gr-1");
  });

  it("sin target elegido, Conceder queda deshabilitado (no se concede a nadie)", () => {
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    expect(screen.getByRole("button", { name: /Conceder/ }).hasAttribute("disabled")).toBe(true);
  });

  it("un error del servidor se muestra, no se traga", () => {
    mocks.useVisibilityMutations.mockReturnValue(
      visMut({ error: "/visibility-grants falló (400)" }),
    );
    render(<VisibilityCard grantee={GRANTEE} allTenants={[GRANTEE, TARGET]} />);
    expect(screen.getByRole("alert").textContent).toMatch(/falló \(400\)/);
  });
});
