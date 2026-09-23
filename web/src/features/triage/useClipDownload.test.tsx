// [T-8.08 · A-014] La descarga del clip de CCTV: la misma forma que el miniSEED.
//
// `POST /cctv/clips/{clip_id}/download` devuelve una URL pre-firmada de 300 s y
// deja su fila en `audit_log` (el vídeo son personas). La pestaña se RESERVA en
// el gesto —si se abre al volver la respuesta, el navegador la bloquea en
// silencio— y se navega cuando la URL llega; si falla, esa misma pestaña lo dice.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useClipDownload } from "./useClipDownload";

const mocks = vi.hoisted(() => ({
  downloadClipCctvClipsClipIdDownloadPost: vi.fn(),
  openPendingDownload: vi.fn(),
  resolve: vi.fn(),
  fail: vi.fn(),
}));

vi.mock("@takab/sdk", () => ({
  downloadClipCctvClipsClipIdDownloadPost: mocks.downloadClipCctvClipsClipIdDownloadPost,
}));
vi.mock("../../lib/download", () => ({ openPendingDownload: mocks.openPendingDownload }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.openPendingDownload.mockReturnValue({
    opened: true,
    resolve: mocks.resolve,
    fail: mocks.fail,
  });
});

describe("useClipDownload", () => {
  it("reserva la pestaña EN el gesto y la navega a la URL firmada", async () => {
    mocks.downloadClipCctvClipsClipIdDownloadPost.mockResolvedValue({
      data: { url: "https://s3/clip.mp4?firma", expires_in: 300 },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useClipDownload(), { wrapper });
    act(() => result.current.download("c1"));
    // Síncrono, dentro del clic: es lo único que el navegador acepta como gesto.
    expect(mocks.openPendingDownload).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mocks.resolve).toHaveBeenCalledWith("https://s3/clip.mp4?firma"));
    expect(mocks.downloadClipCctvClipsClipIdDownloadPost).toHaveBeenCalledWith({
      path: { clip_id: "c1" },
    });
    await waitFor(() => expect(result.current.pendingClipId).toBeNull());
    expect(result.current.failure).toBeNull();
  });

  it("mientras vuela, dice QUÉ clip está en curso", async () => {
    let soltar: (v: unknown) => void = () => undefined;
    mocks.downloadClipCctvClipsClipIdDownloadPost.mockReturnValue(
      new Promise((r) => {
        soltar = r;
      }),
    );
    const { result } = renderHook(() => useClipDownload(), { wrapper });
    act(() => result.current.download("c7"));
    await waitFor(() => expect(result.current.pendingClipId).toBe("c7"));
    soltar({ data: { url: "u", expires_in: 300 }, response: { status: 200 } });
    await waitFor(() => expect(result.current.pendingClipId).toBeNull());
  });

  it("un 410 dice que la RETENCIÓN lo podó, en la pestaña y en la consola", async () => {
    // 410 y no 404: el clip existió y su huella sigue en el reporte (cctv.py).
    mocks.downloadClipCctvClipsClipIdDownloadPost.mockResolvedValue({
      data: undefined,
      response: { status: 410 },
    });
    const { result } = renderHook(() => useClipDownload(), { wrapper });
    act(() => result.current.download("c1"));
    await waitFor(() => expect(result.current.failure?.message).toMatch(/retención de vídeo/));
    expect(mocks.fail).toHaveBeenCalledWith(expect.stringMatching(/retención de vídeo/));
    expect(mocks.resolve).not.toHaveBeenCalled();
  });

  it("cualquier otro fallo se declara con su código, no se traga", async () => {
    mocks.downloadClipCctvClipsClipIdDownloadPost.mockResolvedValue({
      data: undefined,
      response: { status: 503 },
    });
    const { result } = renderHook(() => useClipDownload(), { wrapper });
    act(() => result.current.download("c1"));
    await waitFor(() => expect(result.current.failure?.message).toMatch(/503/));
    expect(mocks.fail).toHaveBeenCalled();
  });
});

describe("useClipDownload · el fallo y la espera dicen DE QUÉ clip son", () => {
  // [T-8.08 · verificador] La mutación vive en `TriagePage`, que cambia de
  // incidente sin desmontarse: un fallo sin su clip se pintaba bajo los clips de
  // CUALQUIER incidente. El hook dice qué clip falló; el panel lo casa con los
  // suyos (`CctvPanel.test`).
  it("el fallo lleva el clip que lo tuvo", async () => {
    mocks.downloadClipCctvClipsClipIdDownloadPost.mockResolvedValue({
      data: undefined,
      response: { status: 410 },
    });
    const { result } = renderHook(() => useClipDownload(), { wrapper });
    act(() => result.current.download("clip-de-A"));
    await waitFor(() => expect(result.current.failure?.clipId).toBe("clip-de-A"));
  });

  it("pedir otro clip con el primero en vuelo no deja huérfana la pestaña del primero", async () => {
    // Ya no se apagan los botones de OTRO incidente mientras uno vuela: el
    // segundo clic es posible, y la pestaña que se reservó en el primero tiene
    // que llegar a SU vídeo igual.
    const soltar: Record<string, (v: unknown) => void> = {};
    mocks.downloadClipCctvClipsClipIdDownloadPost.mockImplementation(
      ({ path }: { path: { clip_id: string } }) =>
        new Promise((r) => {
          soltar[path.clip_id] = r;
        }),
    );
    const pestanaA = { opened: true, resolve: vi.fn(), fail: vi.fn() };
    const pestanaB = { opened: true, resolve: vi.fn(), fail: vi.fn() };
    mocks.openPendingDownload.mockReturnValueOnce(pestanaA).mockReturnValueOnce(pestanaB);
    const { result } = renderHook(() => useClipDownload(), { wrapper });
    act(() => result.current.download("clip-de-A"));
    act(() => result.current.download("clip-de-B"));
    await waitFor(() => expect(result.current.pendingClipId).toBe("clip-de-B"));
    soltar["clip-de-A"]({ data: { url: "https://s3/a.mp4", expires_in: 300 }, response: {} });
    soltar["clip-de-B"]({ data: { url: "https://s3/b.mp4", expires_in: 300 }, response: {} });
    await waitFor(() => expect(pestanaA.resolve).toHaveBeenCalledWith("https://s3/a.mp4"));
    await waitFor(() => expect(pestanaB.resolve).toHaveBeenCalledWith("https://s3/b.mp4"));
  });
});
