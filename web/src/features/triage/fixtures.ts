import type { IncidentOut, SeismicEventOut, SiteOut } from "@takab/sdk";

/** Fixtures compartidos por los tests de triage (formas REALES del SDK generado). */

export function anIncident(over: Partial<IncidentOut> = {}): IncidentOut {
  return {
    incident_id: "11111111-1111-1111-1111-111111111111",
    event_uuid: "22222222-2222-2222-2222-222222222222",
    tenant_id: "t-1",
    site_id: "s-1",
    event_id: "evt-1",
    opened_at: "2026-07-08T10:41:00Z",
    closed_at: null,
    severity: "critical",
    state: "open",
    trigger: "local_threshold",
    max_pga_g: 0.15,
    max_pgv_cms: 11.8,
    summary: {},
    ...over,
  };
}

export function anEvent(over: Partial<SeismicEventOut> = {}): SeismicEventOut {
  return {
    event_id: "evt-1",
    source: "quorum",
    magnitude: 6.8,
    epicenter_lon: -98.3,
    epicenter_lat: 19.06,
    depth_km: 32,
    detected_at: "2026-07-08T10:41:00Z",
    meta: {},
    ...over,
  };
}

export function aSite(over: Partial<SiteOut> = {}): SiteOut {
  return {
    site_id: "s-1",
    tenant_id: "t-1",
    code: "CHL-A",
    name: "Planta Cholula",
    criticality: "high",
    lat: 19.06,
    lon: -98.3,
    timezone: "America/Mexico_City",
    status: "active",
    row_version: "1",
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}
