// 2.3 · [T-7.58] — la captura forense **no puede devolver «listo» si la foto no
// quedó en el disco**. Esta evidencia va a `evidence_objects`, que es append-only:
// lo que no se capturó no se recupera después, y el brigadista ya se fue del
// edificio creyendo que mandó la prueba del daño.
//
// Por qué existe este fichero: `capture.ts` era la única pieza de la costura
// forense SIN prueba (watermark.ts y fileHash.ts sí la tenían), y el defecto que
// se midió en el Pixel el 2026-09-19 vivía justo ahí — la foto se perdía al
// moverla y lo que veía el usuario era el `ENOENT` crudo de la plataforma.
//
// El disco de mentira de abajo implementa el contrato DOCUMENTADO de
// `expo-file-system` (SDK 57): «Moves a file synchronously. Updates the `uri`
// property that now points to the new location» — `move()` muta el objeto
// ORIGEN, y el objeto que se le pasa como destino NO se actualiza.
import { captureForensicPhoto } from "./capture";
import type { ForensicMeta } from "./watermark";

/** Disco de mentira: uri → bytes. */
const mockDisco = new Map<string, Uint8Array>();
/** Directorios que existen en el disco de mentira. */
const mockDirs = new Set<string>();
/** Con esto en `true`, `move()` vacía el origen y NO escribe el destino: es el
 *  estado que se midió en el teléfono (el fichero no estaba en ningún lado). */
const mockFalla = { elMovimientoPierdeElFichero: false };

jest.mock("expo-file-system", () => {
  class FakeDirectory {
    uri: string;
    constructor(padre: { uri: string }, nombre: string) {
      this.uri = `${padre.uri}${nombre}/`;
    }
    get exists(): boolean {
      return mockDirs.has(this.uri);
    }
    create(): void {
      mockDirs.add(this.uri);
    }
  }
  class FakeFile {
    uri: string;
    constructor(a: { uri: string } | string, nombre?: string) {
      this.uri = typeof a === "string" ? a : `${a.uri}${nombre ?? ""}`;
    }
    get exists(): boolean {
      return mockDisco.has(this.uri);
    }
    delete(): void {
      mockDisco.delete(this.uri);
    }
    move(destino: { uri: string }): void {
      const bytes = mockDisco.get(this.uri);
      if (bytes === undefined) {
        throw new Error(`ENOENT: ${this.uri}`);
      }
      mockDisco.delete(this.uri);
      if (!mockFalla.elMovimientoPierdeElFichero) {
        mockDisco.set(destino.uri, bytes);
      }
      // El ORIGEN es el que se actualiza. `destino` queda intacto a propósito.
      this.uri = destino.uri;
    }
    async bytes(): Promise<Uint8Array> {
      const b = mockDisco.get(this.uri);
      if (b === undefined) {
        // Literalmente lo que imprimió el teléfono antes del arreglo.
        throw new Error(
          `Call to function 'FileSystemFile.bytes' has been rejected. → ` +
            `java.io.FileNotFoundException: ${this.uri}: open failed: ENOENT`,
        );
      }
      return b;
    }
  }
  return {
    Directory: FakeDirectory,
    File: FakeFile,
    Paths: { document: { uri: "file:///doc/" } },
  };
});

jest.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  digest: jest.fn(async (_alg: string, data: Uint8Array) =>
    Uint8Array.from([data.length, ...Array.from(data).slice(0, 3)]),
  ),
}));

const mockCaptureRef = jest.fn();
jest.mock("react-native-view-shot", () => ({
  captureRef: (...a: unknown[]) => mockCaptureRef(...a),
}));

/** La ruta temporal que devuelve `captureRef` tras hornear la marca. */
const SELLADA = "file:///cache/ReactNative-snapshot-image7.jpg";
const PRIVADA = "file:///doc/forensic/evidence-inc9.jpg";
/** Huella de `[1,2,3]` con el mock de digest: longitud 3 + los tres bytes. */
const SHA_OK = "03010203";

const META: ForensicMeta = {
  tsDevice: "2026-09-19T10:00:00.000Z",
  ntpOffsetMs: -0.2,
  gps: [-99.13, 19.43],
  pgaG: 0.152,
  operatorId: "70000000-0000-0000-0000-00000000bb01",
  siteId: "site-e2e-900",
  incidentId: "11111111-2222-3333-4444-555555555555",
  snapshotStaleSinceMs: null,
};

const VISTA_COMPUESTA = null as never;

beforeEach(() => {
  jest.clearAllMocks();
  mockDisco.clear();
  mockDirs.clear();
  mockFalla.elMovimientoPierdeElFichero = false;
  mockCaptureRef.mockResolvedValue(SELLADA);
  mockDisco.set(SELLADA, new Uint8Array([1, 2, 3]));
});

describe("captureForensicPhoto", () => {
  it("devuelve la ruta PRIVADA donde el fichero está de verdad, con su huella", async () => {
    const out = await captureForensicPhoto(VISTA_COMPUESTA, META, "inc9");

    expect(out.uri).toBe(PRIVADA);
    // Lo que se devuelve no es una ruta construida a mano: ahí hay bytes.
    expect(mockDisco.has(out.uri)).toBe(true);
    // Y el temporal de la caché no se queda detrás (jamás en la galería).
    expect(mockDisco.has(SELLADA)).toBe(false);
    expect(out.bytes).toBe(3);
    expect(out.sha256).toBe(SHA_OK);
    expect(out.meta).toBe(META);
  });

  it("crea el directorio privado la primera vez", async () => {
    expect(mockDirs.has("file:///doc/forensic/")).toBe(false);
    await captureForensicPhoto(VISTA_COMPUESTA, META, "inc9");
    expect(mockDirs.has("file:///doc/forensic/")).toBe(true);
  });

  it("repetir la captura con el mismo id deja la foto NUEVA, no la vieja", async () => {
    mockDisco.set(PRIVADA, new Uint8Array([9, 9]));

    const out = await captureForensicPhoto(VISTA_COMPUESTA, META, "inc9");

    expect(Array.from(mockDisco.get(out.uri) ?? [])).toEqual([1, 2, 3]);
    expect(out.sha256).toBe(SHA_OK);
  });

  // ── el corazón de T-7.58 ────────────────────────────────────────────────
  it("si la foto no quedó en el disco tras moverla, FALLA declarándolo", async () => {
    mockFalla.elMovimientoPierdeElFichero = true;

    await expect(captureForensicPhoto(VISTA_COMPUESTA, META, "inc9")).rejects.toThrow(
      /la foto sellada no quedó en el disco tras moverla/,
    );
  });

  it("ese fallo dice que NO SE GUARDÓ NADA y nombra el fichero — no el ENOENT crudo", async () => {
    mockFalla.elMovimientoPierdeElFichero = true;

    const error = await captureForensicPhoto(VISTA_COMPUESTA, META, "inc9").then(
      () => null,
      (e: unknown) => e as Error,
    );

    expect(error).not.toBeNull();
    const mensaje = String(error?.message);
    // Quien lo lea tiene que saber que la evidencia se perdió…
    expect(mensaje).toMatch(/No se ha guardado nada/);
    // …y CUÁL fichero, para poder perseguirlo.
    expect(mensaje).toContain(PRIVADA);
    // Lo que se veía antes del arreglo era esto, y no dice en qué paso se perdió.
    expect(mensaje).not.toMatch(/FileSystemFile|FileNotFoundException/);
  });
});
