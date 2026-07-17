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
    fireEvent.click(screen.getByRole("button", { name: /Conceder/ }));
    expect(grant).toHaveBeenCalledWith({
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
    expect(grant).toHaveBeenCalledWith(
      expect.objectContaining({ target_all: true, target_tenant_id: null }),
    );
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
