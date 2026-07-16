// Cadena de custodia (spec §4.2): huella SHA-256 sellada AL CAPTURAR, sobre
// una serialización CANÓNICA (claves ordenadas) para que el mismo dato
// produzca siempre la misma huella.
import * as Crypto from "expo-crypto";

export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`);
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value);
}

export async function sha256OfJson(value: unknown): Promise<string> {
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, canonicalJson(value));
}

export function newId(): string {
  return Crypto.randomUUID();
}
