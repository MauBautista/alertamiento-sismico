// 2.3 — registro + subida de evidencia: comprueba la huella, firma el PUT,
// sube los bytes del archivo privado (jamás la galería) y traduce fallos con
// honestidad.
//
// [T-2.108] Este módulo dejó de llamarse desde la cámara: lo llama el motor de
// la cola offline. Por eso ahora cada fallo dice además si es RECUPERABLE
// (reintentar tiene sentido) o de contrato (queda visible como fallido), y por
// eso comprueba el SHA-256 del archivo ANTES de registrar nada — entre la
// captura y la subida puede haber pasado un día.
import { registerAndUploadEvidence } from "./evidence";

const mockRegister = jest.fn();
jest.mock("@takab/sdk", () => ({
  registerEvidenceIncidentsIncidentIdEvidencePost: (...a: unknown[]) => mockRegister(...a),
}));

const mockFile = { bytes: new Uint8Array([1, 2, 3]) as Uint8Array | null };
jest.mock("expo-file-system", () => ({
  File: jest.fn().mockImplementation(() => ({
    bytes: async () => {
      if (mockFileRef.bytes === null) {
        throw new Error("ENOENT");
      }
      return mockFileRef.bytes;
    },
  })),
}));
const mockFileRef = mockFile;

jest.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  digest: jest.fn(async (_alg: string, data: Uint8Array) =>
    Uint8Array.from([data.length, ...Array.from(data).slice(0, 3)]),
  ),
}));

/** Huella de `[1,2,3]` con el mock de digest: longitud 3 + los tres bytes. */
const SHA_OK = "03010203";

const fetchMock = jest.fn();
beforeEach(() => {
  jest.clearAllMocks();
  mockFile.bytes = new Uint8Array([1, 2, 3]);
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
      sha256: SHA_OK,
    });
    expect(out).toEqual({ ok: true, evidenceId: "ev-1" });
    expect(mockRegister.mock.calls[0][0].body.sha256).toBe(SHA_OK);
    expect(fetchMock.mock.calls[0][0]).toBe("https://s3/put?sig");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    // Los bytes que se suben son EXACTAMENTE los que se hashearon.
    expect(fetchMock.mock.calls[0][1].body).toEqual(mockFile.bytes);
  });

  it("sin bucket (dev): registrada sin subir, la huella ya quedó", async () => {
    mockRegister.mockResolvedValue({ data: { evidence_id: "ev-2", upload_url: null } });
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: SHA_OK,
    });
    expect(out).toEqual({ ok: true, evidenceId: "ev-2" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("PUT falla con 403 ⇒ error declarado con el status, y NO recuperable", async () => {
    mockRegister.mockResolvedValue({ data: { evidence_id: "ev", upload_url: "https://s3/put" } });
    fetchMock.mockResolvedValue({ ok: false, status: 403 });
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: SHA_OK,
    });
    expect(out).toEqual({
      ok: false,
      retryable: false,
      reason: expect.stringMatching(/403/),
    });
  });

  it("5xx al registrar ⇒ RECUPERABLE (la cola lo reintenta con backoff)", async () => {
    mockRegister.mockResolvedValue({ data: undefined, response: { status: 503 } });
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: SHA_OK,
    });
    expect(out).toEqual({ ok: false, retryable: true, reason: expect.stringMatching(/503/) });
  });

  it("sin red ⇒ error honesto y RECUPERABLE, nada subido", async () => {
    mockRegister.mockRejectedValue(new TypeError("Network request failed"));
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: SHA_OK,
    });
    expect(out).toEqual({ ok: false, retryable: true, reason: expect.stringMatching(/Sin conexión/) });
  });

  it("el archivo cambió tras la captura ⇒ ni se registra ni se sube (§2.3)", async () => {
    mockFile.bytes = new Uint8Array([9, 9, 9]);
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: SHA_OK,
    });
    expect(out).toEqual({
      ok: false,
      retryable: false,
      reason: expect.stringMatching(/huella SHA-256 no coincide/),
    });
    expect(mockRegister).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("el archivo ya no está en el teléfono ⇒ fallo declarado, sin reintentos", async () => {
    // Reintentar mil veces no devuelve un fichero que el SO borró: se declara
    // y queda visible en la cola en vez de girar para siempre.
    mockFile.bytes = null;
    const out = await registerAndUploadEvidence({
      incidentId: "inc-1",
      uri: "file:///priv/x.jpg",
      sha256: SHA_OK,
    });
    expect(out).toEqual({
      ok: false,
      retryable: false,
      reason: expect.stringMatching(/ya no está en este teléfono/),
    });
    expect(mockRegister).not.toHaveBeenCalled();
  });
});
