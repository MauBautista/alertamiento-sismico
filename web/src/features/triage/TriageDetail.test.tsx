import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DictamenOut, IncidentOut, SeismicEventOut } from "@takab/sdk";

import TriageDetail from "./TriageDetail";
import type { TriageDetailProps } from "./TriageDetail";
import type { TriageRow } from "./model";

// StructuralTriage pide sus propios datos; aquí lo que se prueba es DÓNDE se monta.
vi.mock("./StructuralTriage", () => ({
  default: ({ incidentId }: { incidentId: string }) => (
    <div data-testid="structural-triage">{incidentId}</div>
  ),
}));

const INCIDENT: IncidentOut = {
  incident_id: "11111111-2222-3333-4444-555555555555",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: "EVT-001",
  opened_at: "2026-08-03T10:00:00Z",
  closed_at: null,
  severity: "warning",
  state: "open",
  trigger: "sasmex",
  max_pga_g: 0.081,
  max_pgv_cms: 3.2,
} as IncidentOut;

const EVENT: SeismicEventOut = {
  event_id: "EVT-001",
  source: "local_quorum",
  magnitude: null,
  depth_km: null,
  detected_at: "2026-08-03T09:59:50Z",
  epicenter_lat: 19.06,
  epicenter_lon: -98.3,
  meta: {},
} as SeismicEventOut;

const ROW: TriageRow = {
  incident: INCIDENT,
  event: EVENT,
  siteName: "Torre Norte",
  nodeCount: 3,
};

const FORENSICS = {
  data: undefined,
  loading: false,
  error: null,
  refetch: vi.fn(),
} as unknown as TriageDetailProps["forensics"];

function resource<T>(over: Partial<{ data: T; loading: boolean; error: string | null }> = {}) {
  return {
    data: undefined as T | undefined,
    loading: false,
    error: null,
    disabled: false,
    ...over,
  };
}

function arrange(
  over: Partial<TriageDetailProps["detail"]> = {},
  props: Partial<TriageDetailProps> = {},
) {
  const detail = {
    dictamens: resource<DictamenOut[]>({ data: [] }),
    actions: resource<unknown[]>({ data: [] }),
    evidence: resource<unknown[]>({ data: [] }),
    event: resource<unknown>({ data: EVENT }),
    refetch: vi.fn(),
    sign: vi.fn(),
    signing: false,
    signError: null,
    generatePdf: vi.fn(),
    pdfPending: false,
    downloadEvidence: vi.fn(),
    downloadPending: false,
    exportError: null,
    ...over,
  } as unknown as TriageDetailProps["detail"];

  render(
    <TriageDetail
      row={ROW}
      detail={detail}
      forensics={FORENSICS}
      minNodes={3}
      canSign={false}
      canExport={false}
      canGenerateReport={false}
      {...props}
    />,
  );
}

describe("TriageDetail · los hechos no dependen del dictamen [T-2.39]", () => {
  // EL bug: `<StructuralTriage>` vivía dentro de `{verdict && head && …}` Y dentro
  // del StateFrame del dictamen. Un incidente sin dictamen ocultaba por completo los
  // reportes que los tácticos ya habían enviado desde el edificio.
  it("los reportes de campo se ven SIN dictamen", () => {
    arrange({ dictamens: resource<DictamenOut[]>({ data: [] }) });
    expect(screen.getByTestId("structural-triage")).toBeInTheDocument();
  });

  it("los reportes de campo se ven MIENTRAS carga el dictamen", () => {
    arrange({ dictamens: resource<DictamenOut[]>({ loading: true }) });
    expect(screen.getByTestId("structural-triage")).toBeInTheDocument();
  });

  it("los reportes de campo se ven aunque el dictamen FALLE", () => {
    arrange({ dictamens: resource<DictamenOut[]>({ error: "HTTP 503" }) });
    expect(screen.getByTestId("structural-triage")).toBeInTheDocument();
  });

  it("las métricas medidas tampoco dependen del dictamen", () => {
    arrange();
    expect(screen.getByText("0.081")).toBeInTheDocument();
    expect(screen.getByText("3.2")).toBeInTheDocument();
  });
});

describe("TriageDetail · datos honestos [T-2.39]", () => {
  it("el título encabeza la SACUDIDA MEDIDA, no una magnitud que siempre es null", () => {
    arrange();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "SACUDIDA FUERTE · Torre Norte",
    );
  });

  it("sin PGA el título dice SIN MEDICIÓN, no una banda tranquilizadora", () => {
    render(
      <TriageDetail
        row={{ ...ROW, incident: { ...INCIDENT, max_pga_g: null } }}
        detail={
          {
            dictamens: resource<DictamenOut[]>({ data: [] }),
            actions: resource<unknown[]>({ data: [] }),
            evidence: resource<unknown[]>({ data: [] }),
            event: resource<unknown>({ data: EVENT }),
            refetch: vi.fn(),
            sign: vi.fn(),
            signing: false,
            signError: null,
            generatePdf: vi.fn(),
            pdfPending: false,
            downloadEvidence: vi.fn(),
            downloadPending: false,
            exportError: null,
          } as unknown as TriageDetailProps["detail"]
        }
        forensics={FORENSICS}
        minNodes={3}
        canSign={false}
        canExport={false}
        canGenerateReport={false}
      />,
    );
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("SIN MEDICIÓN");
  });

  it("la magnitud baja a métrica rotulada como del catálogo", () => {
    arrange();
    expect(screen.getByText("MAGNITUD (CATÁLOGO)")).toBeInTheDocument();
    expect(screen.getByText("S/CATÁLOGO")).toBeInTheDocument();
  });

  it("el epicentro por quórum declara que es un centroide, no una localización", () => {
    arrange();
    expect(screen.getByTestId("epicenter-note")).toHaveTextContent(
      /CENTROIDE DE LA RED · NO ES UNA LOCALIZACIÓN SÍSMICA/,
    );
  });

  it("sin epicentro no se pinta la nota", () => {
    arrange({}, { row: { ...ROW, event: { ...EVENT, epicenter_lat: null } } });
    expect(screen.queryByTestId("epicenter-note")).not.toBeInTheDocument();
  });
});
