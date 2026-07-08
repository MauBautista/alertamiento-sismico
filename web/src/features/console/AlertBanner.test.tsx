import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AlertBanner from "./AlertBanner";
import type { LiveIncident } from "./useLiveIncidents";

const INCIDENT: LiveIncident = {
  incident_id: "abcdef12-0000-0000-0000-000000000000",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: "EVT-20260708-1041",
  opened_at: "2026-07-08T10:41:30Z",
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "local_threshold",
  max_pga_g: 0.15,
  max_pgv_cms: 4.2,
};

describe("AlertBanner", () => {
  it("sin incidente crítico no renderiza nada", () => {
    const { container } = render(<AlertBanner incident={null} siteName={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("banner MVP: PROTÉJASE + sitio + EVENT_ID + PGA MAX; sin magnitud ni T-MINUS", () => {
    render(<AlertBanner incident={INCIDENT} siteName="Planta Cholula · Edificio A" />);
    expect(screen.getByRole("alert")).toHaveTextContent("ALERTA SÍSMICA · PROTÉJASE");
    expect(screen.getByRole("alert")).toHaveTextContent("Planta Cholula · Edificio A");
    expect(screen.getByRole("alert")).toHaveTextContent("EVENT_ID EVT-20260708-1041");
    expect(screen.getByRole("alert")).toHaveTextContent("0.150");
    // El WR-1 es booleano: NUNCA magnitud preliminar ni countdown (desviación ratificada).
    expect(screen.getByRole("alert")).not.toHaveTextContent(/T-MINUS/);
    expect(screen.getByRole("alert")).not.toHaveTextContent(/M\s*\d\.\d/);
  });
});
