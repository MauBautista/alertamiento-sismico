import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  DictamenOut,
  EventDetailOut,
  EvidenceObject,
  IncidentOut,
  SeismicEventOut,
} from "@takab/sdk";

import TriageDetail from "./TriageDetail";
import type { TriageDetailProps } from "./TriageDetail";
import type { TriageRow } from "./model";

// [T-5.12] `ClassificationPanel` consulta al servidor y este arnés no monta
// QueryClient: se mockea el hook, como hace `DrillBanner.test`. Este fichero
// prueba que los hechos no dependen del dictamen, no la clasificación —que tiene
// su propio test con sus cuatro estados.
vi.mock("./useClassification", async () => {
  const real = await vi.importActual<typeof import("./useClassification")>("./useClassification");
  return {
    ...real,
    useClassification: () => ({
      items: [],
      current: null,
      loading: false,
      readError: false,
      updatedAt: 0,
      refetch: vi.fn(),
      clasificar: vi.fn(),
      pending: false,
    }),
  };
});

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

/** Cabeza de cadena preliminar (`signed_by: null`), como la que se lee al firmar. */
const DICTAMEN = {
  dictamen_id: "d-1",
  tenant_id: "t-1",
  incident_id: INCIDENT.incident_id,
  status: "inhabit_monitor",
  basis: {},
  signed_by: null,
  supersedes_dictamen_id: null,
  created_at: "2026-08-03T10:30:00Z",
} as unknown as DictamenOut;

const FORENSICS = {
  data: undefined,
  loading: false,
  error: null,
  refetch: vi.fn(),
} as unknown as TriageDetailProps["forensics"];

function resource<T>(
  over: Partial<{
    data: T;
    loading: boolean;
    error: string | null;
    staleSince: number | null;
  }> = {},
) {
  return {
    data: undefined as T | undefined,
    loading: false,
    error: null,
    disabled: false,
    staleSince: null,
    ...over,
  };
}

/** [T-3.12.c] CCTV sin datos: el panel existe en todos los escenarios de este arnés. */
const CCTV = {
  data: undefined,
  loading: false,
  error: null,
  refetch: () => {},
  dataUpdatedAt: 0,
  staleSince: null,
};

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
      cctv={CCTV}
      canDownloadClip={false}
      minNodes={3}
      incidentStaleSince={null}
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
        cctv={CCTV}
        canDownloadClip={false}
        minNodes={3}
        incidentStaleSince={null}
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

/* =====================================================================
   T-2.82.a · la frescura del dato en la pantalla donde se FIRMA
   ===================================================================== */

const HORA = Date.UTC(2026, 7, 3, 10, 41, 30);

function conForensics(over: Partial<{ staleSince: number | null }>) {
  return {
    ...FORENSICS,
    dataUpdatedAt: over.staleSince ?? 0,
    staleSince: over.staleSince ?? null,
  } as unknown as TriageDetailProps["forensics"];
}

describe("TriageDetail · la edad del dato llega a los paneles [T-2.82.a]", () => {
  it("el marco normativo declarado RECIBE la frescura del forense", () => {
    // Antes recibía el valor por defecto de su propia prop (`= null`): el panel
    // aceptaba una edad y nadie se la pasaba nunca, así que afirmaba «este dato
    // no puede envejecer» en la pantalla donde el inspector firma.
    arrange({}, { forensics: conForensics({ staleSince: HORA }) });
    const tarjeta = screen.getByTestId("declared-card");
    expect(tarjeta.textContent ?? "").toContain("DATOS RETENIDOS · 10:41:30 UTC");
  });

  it("y con el dato viejo NO afirma que el cliente no declaró nada", () => {
    // El par en disputa de T-2.79.d, en su peor sitio: sin marco declarado Y
    // con el dato viejo, «SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE» sería
    // una acusación sobre el cliente que no se puede comprobar. Gana `stale` y
    // la ausencia va FECHADA.
    arrange({}, { forensics: conForensics({ staleSince: HORA }) });
    const tarjeta = screen.getByTestId("declared-card");
    expect(tarjeta.textContent ?? "").toContain("desde entonces no se ha podido confirmar");
  });

  it("con el dato fresco, el panel se comporta igual que siempre", () => {
    arrange({}, { forensics: conForensics({ staleSince: null }) });
    const tarjeta = screen.getByTestId("declared-card");
    expect(tarjeta.textContent ?? "").not.toContain("DATOS RETENIDOS");
    expect(tarjeta.textContent ?? "").toContain("SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE");
  });

  it("la EVIDENCIA archivada declara su edad, y su ausencia va fechada", () => {
    // «SIN EVIDENCIA ARCHIVADA PARA ESTE INCIDENTE» junto al botón de descargar
    // el miniSEED es justo la ausencia no verificable que T-2.79.d decidió no
    // afirmar: con la lista congelada, la consola no sabe si no hay evidencia o
    // si lleva un cuarto de hora sin poder preguntar.
    arrange({ evidence: resource<EvidenceObject[]>({ data: [], staleSince: HORA }) });
    const panel = screen.getByText(/SIN EVIDENCIA ARCHIVADA PARA ESTE INCIDENTE/);
    expect(panel.textContent ?? "").toContain("así estaba a las 10:41:30 UTC");
    expect(panel.textContent ?? "").toContain("desde entonces no se ha podido confirmar");
  });

  it("el marco del botón FIRMAR DICTAMEN declara la edad de la cadena", () => {
    // Éste es EL marco: dentro está el botón que firma. La cadena de custodia
    // que se enseña ahí puede haber crecido una versión desde la última
    // respuesta, y firmar sobre una cadena vieja es el acto exacto que la regla
    // de oro 7 protege.
    arrange({ dictamens: resource<DictamenOut[]>({ data: [DICTAMEN], staleSince: HORA }) });
    const marco = screen.getByText(/FIRMAR DICTAMEN/).closest('[data-state="stale"]');
    expect(marco).not.toBeNull();
    expect(marco?.textContent ?? "").toContain("DATOS RETENIDOS · 10:41:30 UTC");
    expect(marco?.textContent ?? "").toContain("CADENA DE CUSTODIA");
  });

  it("la edad del INCIDENTE baja hasta el panel del quórum", () => {
    // La rama `absent` de `QuorumNodes` no habla del evento (no hay): habla del
    // incidente, cuya frescura sólo conoce la página.
    arrange(
      { event: resource<EventDetailOut>({ data: undefined }) },
      {
        row: { ...ROW, incident: { ...INCIDENT, event_id: null } },
        incidentStaleSince: HORA,
      },
    );
    const panel = screen.getByText(/INCIDENTE SIN EVENTO SÍSMICO ASOCIADO/);
    expect(panel.textContent ?? "").toContain("así estaba a las 10:41:30 UTC");
  });

  it("con todo fresco, ni un solo panel anuncia datos retenidos", () => {
    arrange({}, { forensics: conForensics({ staleSince: null }) });
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
  });
});
