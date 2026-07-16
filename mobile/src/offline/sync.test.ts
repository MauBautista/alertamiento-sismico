// Motor de sync + cola persistida: el criterio E2E de T-2.06 a nivel app —
// modo avión ⇒ pending; vuelve la red ⇒ synced SIN duplicar (mismo checkin_id
// en el replay); 4xx de contrato ⇒ failed visible.
import { hasLocalCheckin } from "./queue";
import { resetQueueStoreForTests, configureQueuePersistence, useQueueStore } from "./queue.store";
import { MemoryQueuePersistence } from "./store";
import { drainQueue } from "./sync";

jest.mock("expo-crypto", () => {
  let n = 0;
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    digestStringAsync: jest.fn(async (_alg: string, data: string) => `sha256:${data.length}`),
    randomUUID: jest.fn(() => `uuid-${++n}`),
    getRandomBytesAsync: jest.fn(async () => new Uint8Array(32)),
  };
});

const mockSubmit = jest.fn();
jest.mock("@takab/sdk", () => ({
  submitCheckinIncidentsIncidentIdCheckinsPost: (...args: unknown[]) => mockSubmit(...args),
}));

const PAYLOAD = {
  incident_id: "inc-1",
  status: "safe" as const,
  zone_id: "z-1",
  location: null,
  ts_device: "2026-07-16T10:00:00Z",
};

async function seedQueue() {
  resetQueueStoreForTests();
  configureQueuePersistence(new MemoryQueuePersistence());
  await useQueueStore.getState().hydrate();
  return useQueueStore.getState().enqueueCheckin(PAYLOAD);
}

beforeEach(() => {
  mockSubmit.mockReset();
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
