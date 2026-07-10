// Modal de reubicación (T-1.51): reuso del MapPointPicker + confirmación en
// dos pasos + honestidad del caso "sin evento" (se creará source=manual).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  getEventEventsEventIdGet: vi.fn(),
  relocateEpicenterIncidentsIncidentIdEpicenterPost: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

// El picker real es MapLibre: aquí un stub que expone value y permite mover.
vi.mock("../fleet/MapPointPicker", () => ({
  default: ({
    value,
    onChange,
  }: {
    value: { lon: number; lat: number };
    onChange: (p: { lon: number; lat: number }) => void;
  }) => (
    <div data-testid="picker-stub" data-lon={value.lon} data-lat={value.lat}>
      <button onClick={() => onChange({ lon: -98.5, lat: 18.9 })}>mover-punto</button>
    </div>
  ),
}));

import EpicenterModal from "./EpicenterModal";
import type { LiveIncident } from "./useLiveIncidents";

const INCIDENT: LiveIncident = {
  incident_id: "11111111-2222-3333-4444-555555555555",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: null,
  opened_at: "2026-07-10T03:14:00Z",
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "sasmex",
  max_pga_g: null,
  max_pgv_cms: null,
};

const SITE = { name: "Sitio Dev Puebla", lat: 19.0414, lon: -98.2063 };

function wrap(ui: ReactElement): ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EpicenterModal", () => {
  it("sin evento: avisa que se creará source=manual e inicia en el sitio", () => {
    render(wrap(<EpicenterModal incident={INCIDENT} site={SITE} onClose={vi.fn()} />));
    expect(screen.getByRole("note")).toHaveTextContent("SIN EVENTO SÍSMICO ASOCIADO");
    expect(screen.getByRole("note")).toHaveTextContent("source=manual");
    const picker = screen.getByTestId("picker-stub");
    expect(picker.dataset.lon).toBe("-98.2063");
    expect(sdk.getEventEventsEventIdGet).not.toHaveBeenCalled();
  });

  it("con evento: carga su epicentro actual y anuncia la auditoría del previo", async () => {
    sdk.getEventEventsEventIdGet.mockResolvedValue({
      data: { event_id: "EVT-X", epicenter_lon: -98.72, epicenter_lat: 18.4 },
    });
    render(
      wrap(
        <EpicenterModal
          incident={{ ...INCIDENT, event_id: "EVT-X" }}
          site={SITE}
          onClose={vi.fn()}
        />,
      ),
    );
    expect(screen.getByRole("note")).toHaveTextContent("EVT-X");
    await waitFor(() => expect(screen.getByTestId("picker-stub").dataset.lon).toBe("-98.72"));
  });

  it("confirmación en dos pasos manda el POST exacto y cierra al éxito", async () => {
    sdk.relocateEpicenterIncidentsIncidentIdEpicenterPost.mockResolvedValue({
      data: { event_id: "EVT-MAN-1", created_event: true },
    });
    const onClose = vi.fn();
    render(wrap(<EpicenterModal incident={INCIDENT} site={SITE} onClose={onClose} />));

    fireEvent.click(screen.getByText("mover-punto"));
    fireEvent.change(screen.getByLabelText(/NOTA/), { target: { value: "reporte SSN" } });
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR REUBICACIÓN/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA REUBICAR/ }));

    await waitFor(() =>
      expect(sdk.relocateEpicenterIncidentsIncidentIdEpicenterPost).toHaveBeenCalledWith(
        expect.objectContaining({
          path: { incident_id: INCIDENT.incident_id },
          body: { lon: -98.5, lat: 18.9, note: "reporte SSN" },
        }),
      ),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("error del POST: aviso role=alert y el modal SIGUE abierto", async () => {
    sdk.relocateEpicenterIncidentsIncidentIdEpicenterPost.mockRejectedValue(
      new Error("403 rol sin acceso"),
    );
    const onClose = vi.fn();
    render(wrap(<EpicenterModal incident={INCIDENT} site={SITE} onClose={onClose} />));
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR REUBICACIÓN/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA REUBICAR/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("NO SE PUDO REUBICAR");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("lat,lon manual escrito a mano mueve el punto (blur aplica)", () => {
    render(wrap(<EpicenterModal incident={INCIDENT} site={SITE} onClose={vi.fn()} />));
    const input = screen.getByLabelText(/LAT, LON MANUAL/);
    fireEvent.change(input, { target: { value: "18.9000, -98.5000" } });
    fireEvent.blur(input);
    expect(screen.getByTestId("picker-stub").dataset.lat).toBe("18.9");
  });
});
