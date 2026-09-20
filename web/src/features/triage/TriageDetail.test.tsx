import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
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

/** [T-7.17] La red vacía. Estas suites corren SIN QueryClientProvider a
 *  propósito, así que el hook no puede llamarse aquí: entra por props, como
 *  todo lo demás en este panel. */
const ESTACIONES_VACIAS = {
  data: null,
  loading: false,
  error: false,
  updatedAt: 0,
  refetch: () => {},
};

// [T-5.12] `ClassificationPanel` consulta al servidor y este arnés no monta
// QueryClient: se mockea el hook, como hace `DrillBanner.test`. Este fichero
// prueba que los hechos no dependen del dictamen, no la clasificación —que tiene
// su propio test con sus cuatro estados.
// [T-5.15] `useNotifyChain` monta react-query por el mismo motivo que `useCctv`,
// y esta suite no lleva provider a propósito. Su semántica se prueba en
// `NotifyChain.test.tsx`.
// [T-7.48] `EvidenceVerifier` consume `useVerifyEvidence` (react-query) por la
// MISMA razón que los tres de abajo, y esta suite no monta provider a propósito.
// Su semántica se prueba en `StructuralTriage.test.tsx`, que sí lo monta. Lo que
// este fichero sí comprueba —y es lo que la ficha pedía— es que la huella del
// dictamen se pinte ENTERA y en minúsculas.
vi.mock("./EvidenceVerifier", () => ({
  default: ({ evidenceId }: { evidenceId: string }) => (
    <button data-testid={`verify-${evidenceId}`} type="button">
      VERIFICAR HASH
    </button>
  ),
}));

vi.mock("./useNotifyChain", async () => ({
  ...(await vi.importActual<typeof import("./useNotifyChain")>("./useNotifyChain")),
  useNotifyChain: () => ({
    items: [],
    deliveredCount: 0,
    loading: false,
    readError: false,
    staleSince: null,
    refetch: vi.fn(),
  }),
}));
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
  siteCode: null,
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

  // [T-6.02] Con router: el enlace «IR A FLOTA EDGE» es un <Link>.
  render(
    <MemoryRouter>
      <TriageDetail
        row={ROW}
        detail={detail}
        forensics={FORENSICS}
        cctv={CCTV}
        canDownloadClip={false}
        minNodes={3}
        incidentStaleSince={null}
        estaciones={ESTACIONES_VACIAS}
        canSign={false}
        canExport={false}
        canGenerateReport={false}
        canOpenFleet={false}
        canOpenBuilding
        volverASitioId={null}
        {...props}
      />
    </MemoryRouter>,
  );
}

/**
 * [T-6.14] TRIAGE NO ES UN CALLEJÓN.
 *
 * Se llega aquí desde el wall (SOLICITAR DICTAMEN), y hasta hoy el salto tiraba
 * el riel, el mapa y el filtro: el operador firmaba y volvía —cuando volvía— a
 * una consola en blanco que tenía que armar otra vez. Medido en la auditoría:
 * 3 clics hasta solicitar y 4 más hasta el PDF, con un salto de pantalla en
 * medio y ningún camino de vuelta.
 *
 * Y la ficha del inmueble colgaba de UN enlace en el riel de `/console`: para
 * `inspector` y `building_admin` —que no tienen `/fleet`— ese riel era el único
 * camino a `/building`, teniendo la ruta concedida.
 */
describe("TriageDetail · el camino de vuelta y la ficha del edificio", () => {
  it("con `volver` hay UN clic de regreso al riel, con el sitio en foco", () => {
    arrange({}, { volverASitioId: "s-1" });
    const volver = screen.getByTestId("triage-volver");
    expect(volver).toHaveAttribute("href", "/console?sitio=s-1");
    // Que diga a DÓNDE vuelve: «volver» a secas no distingue el riel del
    // historial de donde se venía.
    expect(volver).toHaveTextContent(/MONITOREO/);
  });

  it("sin `volver` no se inventa un regreso", () => {
    // A triage también se entra por su pestaña. Un botón «volver al riel» ahí
    // manda a una pantalla en la que el operador nunca estuvo.
    arrange({}, { volverASitioId: null });
    expect(screen.queryByTestId("triage-volver")).not.toBeInTheDocument();
  });

  it("el sitio del incidente tiene entrada a su ficha de edificio", () => {
    arrange();
    expect(screen.getByTestId("triage-building-link")).toHaveAttribute("href", "/building/s-1");
  });

  it("sin la ruta concedida, el enlace al edificio NO se pinta", () => {
    // [T-6.02] Un enlace no promete lo que el rol no tiene: mandaría a SIN
    // ACCESO. Ningún rol web está hoy en este caso, y por eso mismo el gate
    // tiene que existir antes de que lo esté.
    arrange({}, { canOpenBuilding: false });
    expect(screen.queryByTestId("triage-building-link")).not.toBeInTheDocument();
  });
});

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
    // [T-6.14] Este caso montaba el panel A MANO —sin router y con la lista de
    // props copiada— y por eso se rompía cada vez que el componente ganaba una:
    // el `<Link>` de esta ficha lo tiró. `arrange` ya monta el router y `props`
    // se esparce al final, así que el `row` se sustituye sin duplicar nada.
    arrange({}, { row: { ...ROW, incident: { ...INCIDENT, max_pga_g: null } } });
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("SIN MEDICIÓN");
  });

  it("la magnitud baja a métrica rotulada como del catálogo", () => {
    arrange();
    expect(screen.getByText("MAGNITUD (CATÁLOGO)")).toBeInTheDocument();
    // [T-5.10] Sin fuente ni hora de consulta el estado es `sin_dato_externo`,
    // y se pinta con su texto — no con un hueco ni con un número sin origen.
    expect(screen.getByText("SIN DATO EXTERNO")).toBeInTheDocument();
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
        estaciones: ESTACIONES_VACIAS,
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

describe("TriageDetail · ningún enlace promete lo que el rol no tiene [T-6.02]", () => {
  // Sin miniSEED archivado y con el incidente fuera de la ventana de backfill
  // (ROW abre el 2026-08-03), la nota ofrece verificar el enlace de la estación.
  it("con /fleet en allowed_routes, la nota enlaza a FLOTA EDGE", () => {
    arrange({}, { canExport: true, canOpenFleet: true });
    expect(screen.getByTestId("miniseed-note")).toHaveTextContent("SIN miniSEED ARCHIVADO");
    expect(screen.getByRole("link", { name: "IR A FLOTA EDGE" })).toHaveAttribute("href", "/fleet");
    expect(screen.queryByTestId("fleet-link-denied")).toBeNull();
  });

  it("[U-38] sin /fleet (inspector, building_admin) no hay enlace: la ausencia se declara", () => {
    arrange({}, { canExport: true, canOpenFleet: false });
    expect(screen.queryByRole("link", { name: "IR A FLOTA EDGE" })).toBeNull();
    expect(screen.getByTestId("fleet-link-denied")).toHaveTextContent(
      "Su rol no accede a FLOTA EDGE",
    );
  });

  it("FIRMAR DICTAMEN apagado dice por qué: el gate, no un gris mudo", () => {
    // El botón vive dentro del marco DICTAMEN: hace falta una cadena para verlo.
    arrange({ dictamens: resource<DictamenOut[]>({ data: [DICTAMEN] }) }, { canSign: false });
    const firmar = screen.getByRole("button", { name: /FIRMAR DICTAMEN/ });
    expect(firmar).toBeDisabled();
    expect(firmar.getAttribute("title")).toMatch(/sign_dictamen/);
  });

  it("…y con permiso no lleva ninguna excusa", () => {
    arrange({ dictamens: resource<DictamenOut[]>({ data: [DICTAMEN] }) }, { canSign: true });
    const firmar = screen.getByRole("button", { name: /FIRMAR DICTAMEN/ });
    expect(firmar).toBeEnabled();
    expect(firmar).not.toHaveAttribute("title");
  });
});

// ═══════════════════ [T-7.48] la huella del archivo, entera y comparable
//
// ⚠️ Estas líneas del marcado NO las tocaba NINGÚN test antes de esta ficha:
// `grep -rn sha256 web/src --include=*.test.*` no devolvía nada de este panel.
// Por eso el truncado a 16 caracteres sobrevivió a `T-5.26` —que cerró
// exactamente ese defecto en el papel— y por eso el hash se pintaba en
// mayúsculas sin que nadie lo notara.

describe("[T-7.48] la huella del ARCHIVO", () => {
  const SHA_DICTAMEN = "a".repeat(63) + "9";
  const SHA_MINISEED = "b".repeat(63) + "7";

  function conEvidencia(extra: Partial<EvidenceObject>[] = []) {
    const base: EvidenceObject[] = [
      {
        created_at: "2026-09-19T10:00:00Z",
        evidence_id: "ev-miniseed",
        kind: "miniseed",
        s3_key: "k/ms",
        sha256: SHA_MINISEED,
      } as EvidenceObject,
      {
        created_at: "2026-09-19T11:00:00Z",
        evidence_id: "ev-dictamen",
        kind: "report_pdf",
        s3_key: "k/pdf",
        sha256: SHA_DICTAMEN,
      } as EvidenceObject,
      ...(extra as EvidenceObject[]),
    ];
    return arrange({ evidence: resource<EvidenceObject[]>({ data: base }) });
  }

  it("pinta los 64 caracteres del dictamen, no 16", () => {
    conEvidencia();
    // Entero: un hash truncado no verifica nada (T-5.26).
    expect(screen.getByText(SHA_DICTAMEN)).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(`${SHA_DICTAMEN.slice(0, 16)}…`))).toBeNull();
  });

  it("y los del miniSEED también, que llevaban truncados desde siempre", () => {
    conEvidencia();
    expect(screen.getByText(SHA_MINISEED)).toBeInTheDocument();
  });

  it("NO lo pinta en mayúsculas: `sha256sum` emite minúsculas", () => {
    conEvidencia();
    const valor = screen.getByText(SHA_DICTAMEN);
    // El texto del DOM ya es minúscula; lo que engañaba era el `text-transform`
    // de `soc-meta`. Se fija que el elemento no lleve esa clase, que es lo único
    // que un test de jsdom puede afirmar aquí — jsdom no calcula el estilo.
    expect(valor.className).not.toContain("soc-meta");
    expect(valor.textContent).toBe(valor.textContent?.toLowerCase());
  });

  it("dice QUÉ identifica cada huella, porque hay dos y no son la misma", () => {
    conEvidencia();
    // T-7.43: la del CONTENIDO identifica una exportación y no se compara entre
    // dos; la del ARCHIVO sí. Pintarlas sin rótulo reproduce el defecto de
    // portada que cerró T-7.42.
    expect(screen.getByText(/Dictamen emitido · sha256 del archivo/i)).toBeInTheDocument();
    expect(screen.getByText(/miniSEED archivado · sha256 del archivo/i)).toBeInTheDocument();
  });

  it("ofrece VERIFICAR el dictamen, que es lo que el papel prometía", () => {
    conEvidencia();
    expect(screen.getByTestId("verify-ev-dictamen")).toBeInTheDocument();
  });

  it("con VARIAS exportaciones se ofrece la MÁS RECIENTE", () => {
    // `evidence_objects` es append-only y un incidente se exporta más de una vez
    // (la variante ejecutiva y la técnica, o el mismo modelo dos días distintos).
    // Quien abre Triage quiere comprobar el papel que tiene en la mano.
    const SHA_VIEJO = "c".repeat(64);
    conEvidencia([
      {
        created_at: "2026-09-18T08:00:00Z",
        evidence_id: "ev-dictamen-viejo",
        kind: "report_pdf",
        s3_key: "k/pdf-viejo",
        sha256: SHA_VIEJO,
      } as EvidenceObject,
    ]);
    expect(screen.getByText(SHA_DICTAMEN)).toBeInTheDocument();
    expect(screen.queryByText(SHA_VIEJO)).toBeNull();
  });

  it("sin dictamen exportado no inventa una huella ni un botón", () => {
    arrange({ evidence: resource<EvidenceObject[]>({ data: [] }) });
    expect(screen.queryByText(/sha256 del archivo/i)).toBeNull();
    expect(screen.queryByTestId(/^verify-/)).toBeNull();
  });
});
