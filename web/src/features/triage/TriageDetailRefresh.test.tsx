// [T-7.05 · C-3] EL CRITERIO MEDIBLE, EN LA PANTALLA DONDE SE FIRMA.
//
// No es un test del hook: es el rótulo que el inspector tiene delante. Lo que el
// censo de T-7.04 midió en `/triage` (§5, flujo F1b) fue exactamente esto —
// cabecera «SIN DICTAMEN» a los 81 s con el dictamen en la base desde los 61, y
// FIRMAR sin aparecer hasta cambiar de fila y volver (2 clics)—, así que se
// prueba sobre el mismo componente y con las mismas dos cadenas.
//
// El montaje es el de `TriageDetail.test.tsx` (mismos tres hooks apartados,
// mismo router) con UNA diferencia deliberada: aquí el `detail` NO es un objeto
// de mentira, sino el `useIncidentDetail` real dentro de un QueryClient real.
// Es la única forma de que el test note la diferencia entre refrescarse y no.
//
// ────────────────────────────────────────────────────────────────────────────
// QUÉ QUEDA MEDIDO AQUÍ Y QUÉ NO. El criterio C-3 dice «medido», y conviene que
// la palabra no se estire más de lo que da (revisión adversaria f0r2 · nº4).
//
// MEDIDO EN ESTE FICHERO, en jsdom y con `listDictamens`/`listActions`/
// `listEvidence` mockeados y el reloj falso:
//  · que el rótulo pasa de «SIN DICTAMEN» a «DICTAMEN AUTOMÁTICO PRELIMINAR» y
//    FIRMAR aparece dentro de los 10 s de la emisión SIN tocar la pantalla, con
//    el canal live AUSENTE (`socket = null`) — o sea, el suelo de sondeo solo;
//  · que con el canal live presente el mismo cambio llega SIN avanzar el reloj;
//  · que una CORRECCIÓN posterior (cabeza sin firmar, status distinto) también
//    llega sola;
//  · que el sondeo PARA cuando la cadena queda firmada y cuando el incidente
//    sale de la ventana del worker.
// Es decir: la lógica de la pantalla, contra un servidor de mentira.
//
// NO MEDIDO AQUÍ, y lo ejerce el INTEGRADOR con la pila viva (`make soc-local`,
// un incidente de menos de 60 s, sin tocar nada, cronómetro desde el INSERT del
// dictamen hasta que cambia el rótulo):
//  · (a) con el hub WS vivo: debe llegar en <1 s y sin petición nueva, visible
//    en la pestaña de red;
//  · (b) con el hub caído a propósito: debe llegar en ≤5 s + la petición. Ésta
//    es la corrida que justifica que el suelo exista, y aquí sólo se ha
//    ejercido contra un socket de mentira;
//  · (c) la corrección de verdad: preliminar primero, quórum después (harness
//    de T-2.30…T-2.33), y la pantalla de FIRMA mostrando el status corregido
//    sin recargar.
// Nada de jsdom sustituye a esas tres: lo que aquí se prueba es que la pantalla
// PIDE cuando debe, no que el worker escriba cuando dice.

import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DictamenOut, IncidentOut, SeismicEventOut, ServerFrame } from "@takab/sdk";

import { LiveSocketContext, type LiveSocketLike } from "../../live/socket";
import TriageDetail from "./TriageDetail";
import {
  DICTAMEN_REFETCH_MS,
  DICTAMEN_WATCH_MS,
  type IncidentRefreshHint,
} from "./dictamenRefresh";
import { useIncidentDetail } from "./useIncidentDetail";
import type { TriageRow } from "./model";

const mocks = vi.hoisted(() => ({
  listDictamens: vi.fn(),
  listActions: vi.fn(),
  listEvidence: vi.fn(),
}));

// PARCIAL, con `importOriginal`: el árbol de TriageDetail usa del SDK bastante
// más que estos tres endpoints (topics del canal live incluidos), y un mock
// total deja el fichero ENTERO sin cargar («N tests pasados, 1 test FILE
// fallido») en cuanto alguien toca un import de la rama.
vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
  listDictamensIncidentsIncidentIdDictamensGet: mocks.listDictamens,
  listIncidentActionsIncidentsIncidentIdActionsGet: mocks.listActions,
  listEvidenceIncidentsIncidentIdEvidenceGet: mocks.listEvidence,
}));

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

// Los tres hooks que montan react-query por su cuenta y no son de esta prueba,
// apartados igual que en `TriageDetail.test.tsx`.
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
vi.mock("./useClassification", async () => ({
  ...(await vi.importActual<typeof import("./useClassification")>("./useClassification")),
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
}));
vi.mock("./StructuralTriage", () => ({
  default: () => <div data-testid="structural-triage" />,
}));

/** El incidente del censo: `484d31d8`, abierto a las 12:46:29.6Z. */
const OPENED_AT = "2026-09-12T12:46:29.600Z";
const T0 = Date.parse(OPENED_AT);
/** `dictamen_settle_s` = 60: el worker lo insertó a los 61 s (medido: 60.1). */
const EMITIDO_EN_MS = 61_000;

const INCIDENT: IncidentOut = {
  incident_id: "484d31d8-2222-3333-4444-555555555555",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: null,
  opened_at: OPENED_AT,
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "sasmex",
  max_pga_g: 0.081,
  max_pgv_cms: 3.2,
} as IncidentOut;

const ROW: TriageRow = {
  incident: INCIDENT,
  event: null as unknown as SeismicEventOut | null,
  siteName: "Torre Norte",
  siteCode: null,
  nodeCount: 3,
};

const HINT: IncidentRefreshHint = { openedAt: INCIDENT.opened_at };

/** El preliminar automático: `signed_by` NULL ⇒ el worker aún puede corregirlo. */
const DICTAMEN = {
  dictamen_id: "d-1",
  tenant_id: "t-1",
  incident_id: INCIDENT.incident_id,
  status: "inhabit_monitor",
  basis: {},
  signed_by: null,
  supersedes_dictamen_id: null,
  created_at: "2026-09-12T12:47:30.000Z",
} as unknown as DictamenOut;

/**
 * LA CORRECCIÓN. `run_dictamen_pass` la inserta cuando la cabeza sigue SIN
 * firmar y el status recalculado difiere —«el quórum corroboró después del
 * preliminar»—: fila NUEVA con `supersedes_dictamen_id`, nunca un UPDATE.
 * `HABITAR · MONITOREO` pasa a `NO HABITAR · INSPECCIÓN`: el cambio de veredicto
 * más caro que esta pantalla puede llegar a ocultar.
 */
const CORRECCION = {
  ...DICTAMEN,
  dictamen_id: "d-2",
  status: "no_inhabit_inspect",
  supersedes_dictamen_id: "d-1",
  created_at: "2026-09-12T12:48:30.000Z",
} as unknown as DictamenOut;

/** La firma del inspector: a partir de aquí la cadena es intocable. */
const FIRMADO = {
  ...CORRECCION,
  dictamen_id: "d-3",
  signed_by: "9f1c0000-0000-4000-8000-000000000000",
  supersedes_dictamen_id: "d-2",
  created_at: "2026-09-12T12:49:30.000Z",
} as unknown as DictamenOut;

const OK = (data: unknown) => ({ data, response: { status: 200 } });

/** El frame que el hub reparte cuando la pasada de dictamen escribe su acción. */
const frameDeDictamen = (incidentId: string) => ({
  type: "incident_action",
  action_id: "a-1",
  incident_id: incidentId,
  tenant_id: INCIDENT.tenant_id,
  site_id: INCIDENT.site_id,
  ts: "2026-09-12T12:47:30.000Z",
  kind: "dictamen",
  actor: "system",
  payload: {},
});

/** Canal live de mentira, con el mismo contrato que `LiveSocketLike`. */
function fakeSocket() {
  const listeners = new Map<string, Set<(frame: ServerFrame) => void>>();
  const socket: LiveSocketLike = {
    subscribe(topic, listener) {
      const set = listeners.get(topic) ?? new Set();
      set.add(listener);
      listeners.set(topic, set);
      return () => set.delete(listener);
    },
    lastFrameAt: () => null,
    status: "ready",
    onStatus: () => () => undefined,
  };
  const emit = (topic: string, frame: ServerFrame) => {
    for (const l of listeners.get(topic) ?? []) l(frame);
  };
  return { socket, emit, listeners };
}

function arrange(hint: IncidentRefreshHint | null, socket: LiveSocketLike | null = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  function Harness() {
    const detail = useIncidentDetail(INCIDENT.incident_id, null, hint);
    return (
      <TriageDetail
        row={ROW}
        detail={detail}
        forensics={
          {
            data: undefined,
            loading: false,
            error: null,
            refetch: vi.fn(),
          } as unknown as Parameters<typeof TriageDetail>[0]["forensics"]
        }
        cctv={
          {
            data: undefined,
            loading: false,
            error: null,
            refetch: () => undefined,
            dataUpdatedAt: 0,
            staleSince: null,
          } as unknown as Parameters<typeof TriageDetail>[0]["cctv"]
        }
        minNodes={3}
        incidentStaleSince={null}
        estaciones={ESTACIONES_VACIAS}
        canSign
        canExport={false}
        canDownloadClip={false}
        canGenerateReport={false}
        canOpenFleet={false}
        canOpenBuilding={false}
        volverASitioId={null}
      />
    );
  }

  return render(
    <QueryClientProvider client={client}>
      <LiveSocketContext.Provider value={socket}>
        <MemoryRouter>
          <Harness />
        </MemoryRouter>
      </LiveSocketContext.Provider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // El detalle se abre a los 3 s de `opened_at`, como en la corrida del censo.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(T0 + 3_000));
  mocks.listDictamens.mockResolvedValue(OK({ items: [] }));
  mocks.listActions.mockResolvedValue(OK([]));
  mocks.listEvidence.mockResolvedValue(OK({ items: [] }));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("C-3 · el detalle abierto ANTES del dictamen se entera solo", () => {
  it("el rótulo cambia y FIRMAR aparece dentro de los 10 s de la emisión, sin tocar nada", async () => {
    arrange(HINT);

    await waitFor(() => expect(screen.getByText("SIN DICTAMEN")).toBeInTheDocument());
    expect(screen.queryByText(/FIRMAR DICTAMEN/)).toBeNull();

    // El worker emite a los 61 s. La pantalla no se toca: ni un clic.
    await act(async () => {
      vi.advanceTimersByTime(EMITIDO_EN_MS - 3_000);
    });
    mocks.listDictamens.mockResolvedValue(OK({ items: [DICTAMEN] }));

    // LOS 10 S DEL CRITERIO, y ni uno más: con los 30 s de la consola —o con la
    // ausencia de intervalo que medía el censo— aquí no habría pasado nada.
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });

    await waitFor(() =>
      expect(screen.getByText("DICTAMEN AUTOMÁTICO PRELIMINAR")).toBeInTheDocument(),
    );
    expect(screen.getByText(/FIRMAR DICTAMEN/)).toBeInTheDocument();
  });

  it("el frame del canal live lo trae SIN esperar al intervalo", async () => {
    const { socket, emit } = fakeSocket();
    arrange(HINT, socket);

    await waitFor(() => expect(screen.getByText("SIN DICTAMEN")).toBeInTheDocument());
    mocks.listDictamens.mockResolvedValue(OK({ items: [DICTAMEN] }));

    // La pasada de dictamen INSERTA en `incident_actions` (kind `dictamen`) y
    // el hub lo reparte por el topic `incidents`. Cero avance de reloj.
    act(() => {
      emit("incidents", frameDeDictamen(INCIDENT.incident_id) as unknown as ServerFrame);
    });

    await waitFor(() =>
      expect(screen.getByText("DICTAMEN AUTOMÁTICO PRELIMINAR")).toBeInTheDocument(),
    );
  });

  it("una acción de OTRO incidente no invalida esta cadena", async () => {
    const { socket, emit } = fakeSocket();
    arrange(HINT, socket);

    await waitFor(() => expect(screen.getByText("SIN DICTAMEN")).toBeInTheDocument());
    const antes = mocks.listDictamens.mock.calls.length;

    act(() => {
      emit("incidents", {
        ...frameDeDictamen("00000000-0000-4000-8000-00000000ffff"),
        action_id: "a-9",
      } as unknown as ServerFrame);
    });

    // `notifyManager` programa la invalidación por MICROTAREA, así que un solo
    // `await Promise.resolve()` la convertía en llamada al mock hoy y podía
    // dejar de hacerlo mañana — y el test pasaría por vacuidad sin defender el
    // filtro. De ahí el contraejemplo de abajo: se comprueba con el MISMO
    // mecanismo de espera que un frame del PROPIO incidente sí sube la cuenta.
    await act(async () => {
      await Promise.resolve();
    });
    expect(mocks.listDictamens.mock.calls.length).toBe(antes);

    act(() => {
      emit("incidents", {
        ...frameDeDictamen(INCIDENT.incident_id),
        action_id: "a-10",
      } as unknown as ServerFrame);
    });
    await waitFor(() => expect(mocks.listDictamens.mock.calls.length).toBeGreaterThan(antes));
  });

  it("la CORRECCIÓN posterior llega sola: el sondeo no para con la primera fila", async () => {
    // El defecto nº2 de la revisión adversaria f0r2, en la pantalla. El worker
    // no deja de mirar un incidente porque ya tenga dictamen: sólo se aparta
    // cuando la cabeza está FIRMADA (`if row["head_signed_by"] is not None:
    // continue`). Entre el preliminar y el cierre de la ventana puede insertar
    // una corrección con `supersedes_dictamen_id`, y parando con la primera fila
    // el inspector se quedaba mirando HABITAR · MONITOREO con la base diciendo
    // NO HABITAR · INSPECCIÓN. Sin canal live —el escenario para el que existe
    // el suelo— esa corrección no llegaba NUNCA.
    mocks.listDictamens.mockResolvedValue(OK({ items: [DICTAMEN] }));
    const { container } = arrange(HINT);

    // Por el ELEMENTO del veredicto, no por el texto suelto: las cuatro
    // etiquetas viven también en el `<select>` de la firma, y un `getByText`
    // ahí encuentra dos nodos y no distingue el que el inspector lee.
    const veredicto = () => container.querySelector(".triage-detail__verdict-val")?.textContent;
    await waitFor(() => expect(veredicto()).toBe("HABITAR · MONITOREO"));

    // El quórum corrobora después: fila nueva, cabeza aún sin firmar.
    mocks.listDictamens.mockResolvedValue(OK({ items: [CORRECCION, DICTAMEN] }));
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });

    await waitFor(() => expect(veredicto()).toBe("NO HABITAR · INSPECCIÓN"));
    // Y la cadena de custodia enseña las DOS versiones, no una.
    expect(container.querySelector(".triage-detail__chain")?.textContent).toContain(
      "2 VERSIÓN(ES)",
    );
  });
});

describe("C-3 · el refresco PARA cuando ya no puede traer nada", () => {
  it("con la cadena FIRMADA no se vuelve a sondear", async () => {
    // La condición de parada del worker es la de aquí: cabeza firmada ⇒ «el
    // juicio del inspector manda» y la pasada automática ya no la toca.
    mocks.listDictamens.mockResolvedValue(OK({ items: [FIRMADO, CORRECCION, DICTAMEN] }));
    arrange(HINT);

    await waitFor(() => expect(screen.getByText("DICTAMEN FIRMADO")).toBeInTheDocument());
    const antes = mocks.listDictamens.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(DICTAMEN_REFETCH_MS * 6);
    });
    expect(mocks.listDictamens.mock.calls.length).toBe(antes);
  });

  it("fuera de la ventana del worker no se sondea, ni con la cadena vacía", async () => {
    // Un incidente viejo: `run_dictamen_pass` sólo mira los de
    // `opened_at >= now - lookback_s`, así que aquí no puede llegar nada — ni
    // preliminar ni corrección. Sondear sería un temporizador sin nada al otro
    // lado, que es el defecto que esta ficha vino a quitar.
    vi.setSystemTime(new Date(T0 + DICTAMEN_WATCH_MS + 60_000));
    arrange(HINT);

    await waitFor(() => expect(screen.getByText("SIN DICTAMEN")).toBeInTheDocument());
    const antes = mocks.listDictamens.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(DICTAMEN_REFETCH_MS * 6);
    });
    expect(mocks.listDictamens.mock.calls.length).toBe(antes);
  });

  it("sin la fila del incidente tampoco: sin ancla no hay hora de parada", async () => {
    // El defecto nº3 de la revisión adversaria f0r2, en la pantalla: con el
    // tercer argumento por defecto a `null`, éste era el sondeo perpetuo que le
    // tocaba por omisión al siguiente llamador. Ahora `null` significa «sin
    // suelo, me fío del canal live», y hay que escribirlo a mano.
    arrange(null);

    await waitFor(() => expect(screen.getByText("SIN DICTAMEN")).toBeInTheDocument());
    const antes = mocks.listDictamens.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(DICTAMEN_REFETCH_MS * 6);
    });
    expect(mocks.listDictamens.mock.calls.length).toBe(antes);
  });
});
