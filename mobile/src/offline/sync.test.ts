// Motor de sync + cola persistida: el criterio E2E de T-2.06 a nivel app —
// modo avión ⇒ pending; vuelve la red ⇒ synced SIN duplicar (mismo checkin_id
// en el replay); 4xx de contrato ⇒ failed visible.
//
// [T-2.108] Y lo mismo para los OTROS dos tipos que la spec §4.2 exige en la
// cola: la foto forense y el reporte de daños, que hasta esta tarea hacían
// POST directo desde su pantalla y sin red se perdían.
import { hasLocalCheckin, type DamageReportPayload, type EvidencePayload } from "./queue";
import { resetQueueStoreForTests, configureQueuePersistence, useQueueStore } from "./queue.store";
import { MemoryQueuePersistence } from "./store";
import { drainQueue } from "./sync";

jest.mock("expo-crypto", () => {
  let n = 0;
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    digestStringAsync: jest.fn(async (_alg: string, data: string) => `sha256:${data.length}`),
    digest: jest.fn(async (_alg: string, data: Uint8Array) =>
      Uint8Array.from([data.length, ...Array.from(data).slice(0, 3)]),
    ),
    randomUUID: jest.fn(() => `uuid-${++n}`),
    getRandomBytesAsync: jest.fn(async () => new Uint8Array(32)),
  };
});

// El archivo de la foto vive aquí: el test puede ALTERARLO para comprobar que
// la cola detecta la manipulación (criterio de aceptación de §2.3).
const mockFile = { bytes: new Uint8Array([1, 2, 3, 4, 5]) };
jest.mock("expo-file-system", () => ({
  File: jest.fn().mockImplementation(() => ({
    bytes: async () => mockFileRef.bytes,
  })),
}));
const mockFileRef = mockFile;

const mockSubmit = jest.fn();
const mockRegisterEvidence = jest.fn();
const mockSubmitDamage = jest.fn();
jest.mock("@takab/sdk", () => ({
  submitCheckinIncidentsIncidentIdCheckinsPost: (...args: unknown[]) => mockSubmit(...args),
  registerEvidenceIncidentsIncidentIdEvidencePost: (...a: unknown[]) => mockRegisterEvidence(...a),
  submitDamageReportIncidentsIncidentIdDamageReportsPost: (...a: unknown[]) =>
    mockSubmitDamage(...a),
}));

const PAYLOAD = {
  incident_id: "inc-1",
  status: "safe" as const,
  zone_id: "z-1",
  location: null,
  ts_device: "2026-07-16T10:00:00Z",
};

const FOTO: EvidencePayload = {
  incident_id: "inc-1",
  uri: "file:///priv/evidence-1.jpg",
  content_type: "image/jpeg",
  bytes: 5,
  ts_device: "2026-07-16T10:00:00Z",
};

function reporte(refs: string[]): DamageReportPayload {
  return {
    incident_id: "inc-1",
    categories: [{ key: "people_trapped", severity: "critical" }],
    notes: "columna NE",
    zone_id: "z-1",
    evidence_refs: refs,
    ts_device: "2026-07-16T10:00:00Z",
  };
}

/** La huella que sellaría la captura sobre `mockFile.bytes` (mock de digest). */
const SHA_CAPTURA = "050102 03".replace(/ /g, "");

async function nuevaCola() {
  resetQueueStoreForTests();
  configureQueuePersistence(new MemoryQueuePersistence());
  await useQueueStore.getState().hydrate();
}

async function seedQueue() {
  await nuevaCola();
  return useQueueStore.getState().enqueueCheckin(PAYLOAD);
}

const fetchMock = jest.fn();

beforeEach(() => {
  mockSubmit.mockReset();
  mockRegisterEvidence.mockReset();
  mockSubmitDamage.mockReset();
  fetchMock.mockReset();
  mockFile.bytes = new Uint8Array([1, 2, 3, 4, 5]);
  (globalThis as { fetch: unknown }).fetch = fetchMock;
});

describe("drainQueue", () => {
  it("feliz: envía con checkin_id = id del item (idempotencia) y queda synced", async () => {
    const item = await seedQueue();
    mockSubmit.mockResolvedValue({ data: { checkin_id: item.id }, response: { status: 201 } });

    await drainQueue(Date.now());

    expect(mockSubmit).toHaveBeenCalledTimes(1);
    const call = mockSubmit.mock.calls[0][0] as {
      path: { incident_id: string };
      body: { checkin_id: string; ts_device: string };
    };
    expect(call.path.incident_id).toBe("inc-1");
    expect(call.body.checkin_id).toBe(item.id);
    expect(call.body.ts_device).toBe(PAYLOAD.ts_device);
    expect(useQueueStore.getState().items[0].state).toBe("synced");
  });

  it("modo avión ⇒ pending con backoff; vuelve la red ⇒ synced con EL MISMO id", async () => {
    const item = await seedQueue();
    mockSubmit.mockRejectedValueOnce(new TypeError("Network request failed"));

    const t0 = Date.now();
    await drainQueue(t0, () => 0.5);
    const afterFail = useQueueStore.getState().items[0];
    expect(afterFail.state).toBe("pending");
    expect(afterFail.attempts).toBe(1);
    expect(afterFail.next_attempt_at).toBeGreaterThan(t0);
    // el dato local YA cuenta como check-in propio (honestidad: existe y viajará)
    expect(hasLocalCheckin(useQueueStore.getState().items, "inc-1")).toBe(true);

    // antes del vencimiento NO reintenta (respeta el backoff)
    await drainQueue(t0);
    expect(mockSubmit).toHaveBeenCalledTimes(1);

    // vencido y con red: reintenta con el MISMO checkin_id y sincroniza
    mockSubmit.mockResolvedValue({ data: { checkin_id: item.id }, response: { status: 200 } });
    await drainQueue(afterFail.next_attempt_at + 1);
    expect(mockSubmit).toHaveBeenCalledTimes(2);
    const replay = mockSubmit.mock.calls[1][0] as { body: { checkin_id: string } };
    expect(replay.body.checkin_id).toBe(item.id);
    expect(useQueueStore.getState().items[0].state).toBe("synced");
  });

  it("4xx de contrato ⇒ failed visible, sin reintentos y sin contar como propio", async () => {
    await seedQueue();
    mockSubmit.mockResolvedValue({ data: undefined, response: { status: 422 } });

    await drainQueue(Date.now());
    expect(useQueueStore.getState().items[0].state).toBe("failed");
    expect(useQueueStore.getState().items[0].last_error).toBe("HTTP 422");
    expect(hasLocalCheckin(useQueueStore.getState().items, "inc-1")).toBe(false);

    await drainQueue(Date.now() + 10 * 60_000);
    expect(mockSubmit).toHaveBeenCalledTimes(1);
  });

  it("5xx ⇒ recuperable (pending), jamás failed", async () => {
    await seedQueue();
    mockSubmit.mockResolvedValue({ data: undefined, response: { status: 503 } });
    await drainQueue(Date.now());
    expect(useQueueStore.getState().items[0].state).toBe("pending");
  });

  it("un `now` ADELANTADO no dispara reintentos en bucle contra el servidor", async () => {
    // El drenaje reelige el siguiente item tras cada envío. Si el backoff se
    // sellara con `Date.now()` mientras la elección usa un `now` posterior, el
    // item volvería a ser elegible en el acto: un martilleo de cientos de
    // peticiones desde un teléfono con la red a medias.
    await seedQueue();
    mockSubmit.mockRejectedValue(new TypeError("Network request failed"));

    await drainQueue(Date.now() + 60_000, () => 0.5);

    expect(mockSubmit).toHaveBeenCalledTimes(1);
    expect(useQueueStore.getState().items[0].attempts).toBe(1);
  });

  it("poda al drenar: SOLO synced + 24 h desaparece", async () => {
    await seedQueue();
    mockSubmit.mockResolvedValue({ data: { ok: true }, response: { status: 201 } });
    await drainQueue(Date.now());
    expect(useQueueStore.getState().items).toHaveLength(1);

    // 25 h después, la pasada de drenaje la poda
    await drainQueue(Date.now() + 25 * 60 * 60 * 1000);
    expect(useQueueStore.getState().items).toHaveLength(0);
  });

  it("hidratar recupera un uploading interrumpido y lo vuelve a enviar", async () => {
    resetQueueStoreForTests();
    const persistence = new MemoryQueuePersistence();
    configureQueuePersistence(persistence);
    await persistence.upsert({
      id: "id-zombie",
      kind: "checkin",
      payload: PAYLOAD,
      sha256: "h",
      state: "uploading",
      attempts: 1,
      next_attempt_at: 0,
      created_at: 1,
      synced_at: null,
      last_error: null,
      priority: 0,
      server_id: null,
    });
    await useQueueStore.getState().hydrate();
    expect(useQueueStore.getState().items[0].state).toBe("pending");

    mockSubmit.mockResolvedValue({ data: { ok: true }, response: { status: 200 } });
    await drainQueue(Date.now());
    expect(useQueueStore.getState().items[0].state).toBe("synced");
    const sent = mockSubmit.mock.calls[0][0] as { body: { checkin_id: string } };
    expect(sent.body.checkin_id).toBe("id-zombie");
  });
});

// ─── [T-2.108] Los otros dos tipos de la cola ────────────────────────────────

describe("foto forense en la cola (§2.3)", () => {
  it("sin red queda pending y NO se registra nada en el servidor", async () => {
    await nuevaCola();
    await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    mockRegisterEvidence.mockRejectedValue(new TypeError("Network request failed"));

    await drainQueue(Date.now(), () => 0.5);

    expect(useQueueStore.getState().items[0].state).toBe("pending");
    // Nada aterrizó: crear la fila del servidor sin poder subir el blob dejaría
    // una evidencia huérfana en el incidente.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("con red sube los BYTES del archivo y guarda el evidence_id del servidor", async () => {
    await nuevaCola();
    await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    mockRegisterEvidence.mockResolvedValue({
      data: { evidence_id: "ev-9", upload_url: "https://s3/put?sig" },
      response: { status: 201 },
    });
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    await drainQueue(Date.now());

    expect(mockRegisterEvidence.mock.calls[0][0].body.sha256).toBe(SHA_CAPTURA);
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(fetchMock.mock.calls[0][1].body).toEqual(mockFile.bytes);
    const item = useQueueStore.getState().items[0];
    expect(item.state).toBe("synced");
    expect(item.server_id).toBe("ev-9");
  });

  it("INTEGRIDAD: si el archivo cambió tras la captura, no se sube nada", async () => {
    // Criterio de aceptación de §2.3. Comprobarlo ANTES de registrar evita
    // ensuciar la cadena de custodia del incidente con un blob que no
    // corresponde a su huella.
    await nuevaCola();
    await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    mockFile.bytes = new Uint8Array([9, 9, 9, 9, 9]);

    await drainQueue(Date.now());

    const item = useQueueStore.getState().items[0];
    expect(item.state).toBe("failed");
    expect(item.last_error).toMatch(/huella SHA-256 no coincide/);
    expect(mockRegisterEvidence).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("la huella sellada en captura NO se recalcula al encolar ni al reintentar", async () => {
    await nuevaCola();
    const item = await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    expect(item.sha256).toBe(SHA_CAPTURA);

    mockRegisterEvidence.mockResolvedValue({ data: undefined, response: { status: 503 } });
    await drainQueue(Date.now(), () => 0.5);
    expect(useQueueStore.getState().items[0].sha256).toBe(SHA_CAPTURA);
  });
});

describe("reporte de daños en la cola (§2.4)", () => {
  it("espera a su foto y se liga al evidence_id REAL en el mismo drenaje", async () => {
    await nuevaCola();
    const foto = await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    await useQueueStore.getState().enqueueDamageReport(reporte([foto.id]), 1);

    mockRegisterEvidence.mockResolvedValue({
      data: { evidence_id: "ev-real", upload_url: null },
      response: { status: 201 },
    });
    mockSubmitDamage.mockResolvedValue({ data: { report_id: "r-1" }, response: { status: 201 } });

    await drainQueue(Date.now());

    expect(mockSubmitDamage.mock.calls[0][0].body.evidence_ids).toEqual(["ev-real"]);
    expect(useQueueStore.getState().items.every((i) => i.state === "synced")).toBe(true);
  });

  it("con la foto aún sin subir, el reporte NO sale a medias", async () => {
    await nuevaCola();
    const foto = await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    await useQueueStore.getState().enqueueDamageReport(reporte([foto.id]), 0);
    mockRegisterEvidence.mockRejectedValue(new TypeError("Network request failed"));

    await drainQueue(Date.now(), () => 0.5);

    // Mandarlo con `evidence_ids: []` sería un reporte que jura no tener fotos.
    expect(mockSubmitDamage).not.toHaveBeenCalled();
    expect(useQueueStore.getState().items[1].state).toBe("pending");
  });

  it("una foto FALLIDA no secuestra al reporte: sale sin ella", async () => {
    await nuevaCola();
    const foto = await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    await useQueueStore.getState().enqueueDamageReport(reporte([foto.id]), 1);
    // 4xx de contrato en la foto: no va a subir nunca.
    mockRegisterEvidence.mockResolvedValue({ data: undefined, response: { status: 422 } });
    mockSubmitDamage.mockResolvedValue({ data: { report_id: "r-1" }, response: { status: 201 } });

    await drainQueue(Date.now());

    expect(useQueueStore.getState().items[0].state).toBe("failed");
    expect(mockSubmitDamage).toHaveBeenCalledTimes(1);
    expect(mockSubmitDamage.mock.calls[0][0].body.evidence_ids).toEqual([]);
  });

  it("PRIORIDAD: el reporte urgente arrastra a SUS fotos al frente de la cola", async () => {
    await nuevaCola();
    // Un check-in encolado ANTES que todo lo demás.
    await useQueueStore.getState().enqueueCheckin(PAYLOAD);
    const foto = await useQueueStore.getState().enqueueEvidence(FOTO, SHA_CAPTURA);
    await useQueueStore.getState().enqueueDamageReport(reporte([foto.id]), 1);

    const orden: string[] = [];
    mockSubmit.mockImplementation(async () => {
      orden.push("checkin");
      return { data: { ok: true }, response: { status: 201 } };
    });
    mockRegisterEvidence.mockImplementation(async () => {
      orden.push("evidence");
      return { data: { evidence_id: "ev-real", upload_url: null }, response: { status: 201 } };
    });
    mockSubmitDamage.mockImplementation(async () => {
      orden.push("damage_report");
      return { data: { report_id: "r" }, response: { status: 201 } };
    });

    await drainQueue(Date.now());

    // La foto hereda la prioridad del reporte que la necesita; el check-in,
    // encolado el primero, cede el turno a las vidas en riesgo (§2.4).
    expect(orden).toEqual(["evidence", "damage_report", "checkin"]);
  });
});
