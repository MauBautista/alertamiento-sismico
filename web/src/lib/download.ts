/**
 * Apertura de una URL presignada de descarga. Módulo aparte para poder mockearlo:
 * jsdom no implementa `window.open` de forma útil y los tests no deben abrir nada.
 *
 * `noopener,noreferrer`: la URL presignada lleva credenciales en el query string y
 * jamás debe filtrarse por `window.opener` ni por el header `Referer`.
 */
export function openDownload(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer");
}
