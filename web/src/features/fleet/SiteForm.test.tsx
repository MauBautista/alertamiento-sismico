// [T-6.03] El alta de estación dice SIEMPRE en qué cliente escribe, y sólo deja
// elegir a quien de verdad puede elegir.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SiteOut } from "@takab/sdk";

import SiteForm, { writeTargetLabel } from "./SiteForm";
import type { WriteTarget } from "./SiteForm";

// El picker monta MapLibre, que jsdom no soporta; su comportamiento se prueba aparte.
vi.mock("./MapPointPicker", () => ({
  default: ({ value }: { value: { lat: number; lon: number } }) => (
    <div data-testid="map-point-picker">{`${value.lat},${value.lon}`}</div>
  ),
}));
// La tipología consulta el catálogo con react-query; aquí se prueba el formulario,
// no ese catálogo (tiene su propia suite), así que se sustituye por una caja.
vi.mock("./BuildingTypeField", () => ({
  default: ({ value }: { value: string }) => <input aria-label="TIPO" value={value} readOnly />,
}));

const TENANTS = [
  { tenant_id: "t-1", name: "Industrias del Valle", code: "IDV" },
  { tenant_id: "t-2", name: "Hospital Uno", code: "HOSP-1" },
];

const CHOOSE: WriteTarget = {
  kind: "choose",
  tenants: TENANTS,
  loading: false,
  error: null,
  initialTenantId: null,
};

const OWN: WriteTarget = { kind: "own", tenantId: "t-1", tenantName: "Industrias del Valle" };

const SITE: SiteOut = {
  site_id: "s-1",
  tenant_id: "t-2",
  code: "CHL-A",
  name: "Planta Cholula",
  timezone: "America/Mexico_City",
  criticality: "high",
  lat: 19.06,
  lon: -98.3,
  address: null,
  building_type: null,
  status: "active",
  row_version: "8421",
  created_at: "2026-01-01T00:00:00Z",
};

function renderForm(target: WriteTarget, site?: SiteOut) {
  const onSubmit = vi.fn();
  render(
    <SiteForm
      site={site}
      writeTarget={target}
      submitting={false}
      error={null}
      onSubmit={onSubmit}
      onCancel={vi.fn()}
    />,
  );
  return onSubmit;
}

function fillRequired() {
  fireEvent.change(screen.getByLabelText("CÓDIGO"), { target: { value: "NUEVA" } });
  fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "Torre Norte" } });
}

describe("SiteForm · en qué cliente se escribe (T-6.03)", () => {
  it("un rol de cliente ve el rótulo con su cliente y NO puede elegir otro", () => {
    renderForm(OWN);
    expect(screen.getByTestId("site-form-target")).toHaveTextContent(
      "ESCRIBIENDO EN · Industrias del Valle",
    );
    expect(screen.queryByTestId("site-form-tenant")).toBeNull();
  });

  it("si el catálogo no trajo el nombre, el rótulo dice el identificador, no nada", () => {
    renderForm({ kind: "own", tenantId: "t-1", tenantName: null });
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("CLIENTE t-1");
  });

  it("un rol interno tiene que ELEGIR: sin cliente el envío queda apagado y dice por qué", () => {
    const onSubmit = renderForm(CHOOSE);
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("ELIGE UN CLIENTE");
    fillRequired();
    const submit = screen.getByRole("button", { name: "CREAR ESTACIÓN" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAttribute("title", "Elige el cliente en el que se escribe la estación");
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("elegir un cliente actualiza el rótulo y viaja en los valores", () => {
    const onSubmit = renderForm(CHOOSE);
    fillRequired();
    fireEvent.change(screen.getByTestId("site-form-tenant"), { target: { value: "t-2" } });
    expect(screen.getByTestId("site-form-target")).toHaveTextContent(
      "ESCRIBIENDO EN · Hospital Uno",
    );
    fireEvent.click(screen.getByRole("button", { name: "CREAR ESTACIÓN" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0].tenant_id).toBe("t-2");
  });

  it("la preselección (venir de la ficha del cliente) ya deja el rótulo puesto", () => {
    renderForm({ ...CHOOSE, initialTenantId: "t-2" });
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("Hospital Uno");
    expect(screen.getByTestId("site-form-tenant")).toHaveValue("t-2");
  });

  it("una preselección que NO está en la lista no habilita el envío (sería un 404)", () => {
    renderForm({ ...CHOOSE, initialTenantId: "t-fantasma" });
    fillRequired();
    expect(screen.getByRole("button", { name: "CREAR ESTACIÓN" })).toBeDisabled();
  });

  it("mientras cargan los clientes el selector está apagado y el rótulo lo dice", () => {
    renderForm({ ...CHOOSE, tenants: [], loading: true });
    expect(screen.getByTestId("site-form-tenant")).toBeDisabled();
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("CARGANDO CLIENTES…");
  });

  it("si la lista de clientes falló, se dice y no se puede enviar", () => {
    renderForm({ ...CHOOSE, tenants: [], loading: false, error: "GET /tenants falló (500)" });
    expect(screen.getByTestId("site-form-tenants-error")).toHaveTextContent(
      "SIN LISTA DE CLIENTES · GET /tenants falló (500)",
    );
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("SIN LISTA DE CLIENTES");
    fillRequired();
    expect(screen.getByRole("button", { name: "CREAR ESTACIÓN" })).toBeDisabled();
  });

  it("al EDITAR no hay selector: un sitio no se muda de cliente, y el rótulo dice de quién es", () => {
    renderForm({ kind: "own", tenantId: "t-2", tenantName: "Hospital Uno" }, SITE);
    expect(screen.queryByTestId("site-form-tenant")).toBeNull();
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("ESTACIÓN DE · Hospital Uno");
  });

  it("writeTargetLabel: la prioridad es cliente elegido > cargando > error > elegir", () => {
    expect(writeTargetLabel(CHOOSE, "t-1")).toBe("Industrias del Valle");
    expect(writeTargetLabel({ ...CHOOSE, loading: true, tenants: [] }, null)).toBe(
      "CARGANDO CLIENTES…",
    );
    expect(writeTargetLabel({ ...CHOOSE, tenants: [], error: "x" }, null)).toBe(
      "SIN LISTA DE CLIENTES",
    );
    expect(writeTargetLabel(CHOOSE, null)).toBe("ELIGE UN CLIENTE");
    expect(writeTargetLabel(OWN, null)).toBe("Industrias del Valle");
  });
});
