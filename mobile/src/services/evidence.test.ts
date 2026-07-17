// 2.3 — registro + subida de evidencia: firma el PUT, sube los bytes del
// archivo privado (jamás la galería) y traduce fallos con honestidad.
import { registerAndUploadEvidence } from "./evidence";

const mockRegister = jest.fn();
jest.mock("@takab/sdk", () => ({
  registerEvidenceIncidentsIncidentIdEvidencePost: (...a: unknown[]) => mockRegister(...a),
}));
jest.mock("expo-file-system", () => ({
  File: jest.fn().mockImplementation(() => ({
    bytes: async () => new Uint8Array([1, 2, 3]),
  })),
}));

const fetchMock = jest.fn();
beforeEach(() => {
  jest.clearAllMocks();
  (globalThis as { fetch: unknown }).fetch = fetchMock;
});

describe("registerAndUploadEvidence", () => {
  it("registra con el SHA-256 declarado y sube los bytes por el PUT presignado", async () => {
    mockRegister.mockResolvedValue({
      data: { evidence_id: "ev-1", upload_url: "https://s3/put?sig" },
    });
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/evidence-1.jpg",
      sha256: "a".repeat(64),
    });
    expect(out).toEqual({ ok: true, evidenceId: "ev-1" });
    expect(mockRegister.mock.calls[0][0].body.sha256).toBe("a".repeat(64));
    expect(fetchMock.mock.calls[0][0]).toBe("https://s3/put?sig");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
  });

  it("sin bucket (dev): registrada sin subir, la huella ya quedó", async () => {
    mockRegister.mockResolvedValue({ data: { evidence_id: "ev-2", upload_url: null } });
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: "b".repeat(64),
    });
    expect(out).toEqual({ ok: true, evidenceId: "ev-2" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("PUT falla ⇒ error declarado con el status", async () => {
    mockRegister.mockResolvedValue({ data: { evidence_id: "ev", upload_url: "https://s3/put" } });
    fetchMock.mockResolvedValue({ ok: false, status: 403 });
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: "c".repeat(64),
    });
    expect(out).toEqual({ ok: false, reason: expect.stringMatching(/403/) });
  });

  it("sin red ⇒ error honesto, nada subido", async () => {
    mockRegister.mockRejectedValue(new TypeError("Network request failed"));
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: "d".repeat(64),
    });
    expect(out.ok).toBe(false);
  });
});
