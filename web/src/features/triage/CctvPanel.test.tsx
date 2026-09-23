// El panel de evacuación observada (T-3.12.c).
//
// Lo que se prueba aquí es lo que un número solo no dice: que la ausencia se declare, que
// el hallazgo de seguridad se vea antes de leerse, y que el botón de descargar no exista
// para quien la API va a rechazar.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CctvOut } from "@takab/sdk";

import { expectFourStates, type UiState } from "../../test-utils/states";
import CctvPanel from "./CctvPanel";
import type { CctvState } from "./useCctv";
import type { ClipDownload } from "./useClipDownload";

const HORA = Date.now() - 3_600_000;

function estado(over: Partial<CctvState> = {}): CctvState {
  return {
    data: undefined,
    loading: false,
    error: null,
    refetch: vi.fn(),
    dataUpdatedAt: Date.now(),
    staleSince: null,
    ...over,
  };
}

function datos(over: Partial<CctvOut> = {}): CctvOut {
  return {
    incident_id: "11111111-1111-1111-1111-111111111111",
    con_camara: true,
    estado: "análisis disponible",
    clips: [],
    capturas: [
      { papel: "pre", disponible: false, razon: "no hay captura del estado previo" },
      { papel: "egress", disponible: false, razon: "no hay captura" },
      { papel: "peak", disponible: false, razon: "no hay captura" },
      { papel: "reentry", disponible: false, razon: "no hay captura" },
    ],
    evacuacion: null,
    discrepancia: null,
    ...over,
  } as CctvOut;
}

const EVAC = {
  peak_n: 40,
  t50_s: 30,
  t90_s: 50,
  reingreso_antes_del_dictamen: false,
  veredicto_reingreso: "el reingreso empezó 300 s después del dictamen firmado",
  correlacion: "sacudida PGA 0.187 g — la mayor parte salió en 50 s",
  notas: [],
};

/** La descarga del clip, en reposo. */
function descarga(over: Partial<ClipDownload> = {}): ClipDownload {
  return { download: vi.fn(), pendingClipId: null, failure: null, ...over };
}

function pintar(
  over: Partial<CctvState> = {},
  canDownloadClip = false,
  clip: ClipDownload = descarga(),
) {
  return render(
    <CctvPanel cctv={estado(over)} canDownloadClip={canDownloadClip} clipDownload={clip} />,
  );
}

describe("CctvPanel · regla de oro 7", () => {
  it("materializa los 4 estados obligatorios", () => {
    expectFourStates((s: UiState) => (
      <CctvPanel
        cctv={estado({
          loading: s === "loading",
          error: s === "error" ? "boom" : null,
          data: s === "loading" || s === "error" ? undefined : datos({ con_camara: s !== "empty" }),
          staleSince: s === "stale" ? HORA : null,
        })}
        canDownloadClip={false}
        clipDownload={descarga()}
      />
    ));
  });
});

describe("CctvPanel", () => {
  it("sin cámara el panel lo DICE y no pinta una sección vacía", () => {
    pintar({ data: datos({ con_camara: false, estado: "SIN COBERTURA CCTV DECLARADA" }) });
    expect(screen.getByText(/SIN COBERTURA CCTV DECLARADA/)).toBeInTheDocument();
  });

  it("con clip y sin análisis dice PENDIENTE en vez de un cero", () => {
    // Un cero aquí sería una mentira sobre una evacuación que quizá fue perfecta.
    pintar({ data: datos({ estado: "CLIP DISPONIBLE · ANÁLISIS PENDIENTE" }) });
    expect(screen.getByTestId("cctv-estado")).toHaveTextContent("ANÁLISIS PENDIENTE");
  });

  it("pinta las cifras de evacuación cuando existen", () => {
    pintar({ data: datos({ evacuacion: EVAC as never }) });
    expect(screen.getByText("LA MAYOR PARTE FUERA")).toBeInTheDocument();
    expect(screen.getByText("50 s")).toBeInTheDocument();
    expect(screen.getByText(/PGA 0.187 g/)).toBeInTheDocument();
  });

  it("un t90 nulo dice SIN MEDIR y NO cero", () => {
    pintar({ data: datos({ evacuacion: { ...EVAC, t50_s: null } as never }) });
    expect(screen.getByText("SIN MEDIR")).toBeInTheDocument();
  });

  it("el reingreso antes del dictamen se MARCA, no se lee de pasada", () => {
    pintar({
      data: datos({
        evacuacion: {
          ...EVAC,
          reingreso_antes_del_dictamen: true,
          veredicto_reingreso: "⚠ EL REINGRESO EMPEZÓ 110 s ANTES del dictamen firmado",
        } as never,
      }),
    });
    const nodo = screen.getByTestId("cctv-reingreso");
    expect(nodo).toHaveAttribute("data-hallazgo", "si");
    expect(nodo.className).toContain("hallazgo");
  });

  it("la discrepancia se muestra como discrepancia, con las DOS cifras", () => {
    pintar({
      data: datos({
        evacuacion: EVAC as never,
        discrepancia: {
          aforo_camara: 40,
          checkins: 44,
          diferencia: -4,
          lectura: "4 persona(s) MÁS en el pase de lista que en cámara",
        } as never,
      }),
    });
    const nodo = screen.getByTestId("cctv-discrepancia");
    expect(nodo).toHaveTextContent("cámara 40");
    expect(nodo).toHaveTextContent("pase de lista 44");
    // Y en ningún sitio el promedio (42), que no corresponde a ninguna medición.
    expect(nodo).not.toHaveTextContent("42");
  });

  it("los cuatro papeles salen SIEMPRE, con foto o sin ella", () => {
    pintar({ data: datos() });
    const items = screen.getByTestId("cctv-capturas").querySelectorAll("li");
    expect([...items].map((li) => li.getAttribute("data-papel"))).toEqual([
      "pre",
      "egress",
      "peak",
      "reentry",
    ]);
  });

  it("un clip podado dice PURGADO y no ofrece descarga", () => {
    // El hecho sobrevive, la imagen no.
    pintar(
      {
        data: datos({
          clips: [
            {
              clip_id: "c1",
              started_at: "2026-08-30T10:00:00Z",
              ended_at: "2026-08-30T10:11:00Z",
              disponible: false,
              purged_at: "2026-09-30T00:00:00Z",
            } as never,
          ],
        }),
      },
      true,
    );
    expect(screen.getByText(/PURGADO/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /DESCARGAR/ })).toBeNull();
  });

  it("sin `cctv_video` no se ofrece un botón que la API va a rechazar", () => {
    const clip = {
      clip_id: "c1",
      started_at: "2026-08-30T10:00:00Z",
      ended_at: "2026-08-30T10:11:00Z",
      disponible: true,
      purged_at: null,
    } as never;
    pintar({ data: datos({ clips: [clip] }) }, false);
    expect(screen.queryByRole("button", { name: /DESCARGAR/ })).toBeNull();

    pintar({ data: datos({ clips: [clip] }) }, true);
    expect(screen.getByRole("button", { name: /DESCARGAR/ })).toBeInTheDocument();
  });
});

// [T-8.08 · A-014] EL BOTÓN QUE NO HACÍA NADA.
//
// `CctvPanel` pintaba DESCARGAR CLIP con `onDownloadClip?.(clip_id)` y
// `TriagePage` nunca le pasaba el callback: el `?.` convertía el clic en nada,
// sin error, delante del cliente. Ahora la descarga es una prop OBLIGATORIA —el
// compilador no deja montar el panel sin ella— y el clic tiene tres desenlaces
// visibles: en curso, fallo declarado, o la pestaña con el vídeo.
describe("CctvPanel · DESCARGAR CLIP descarga [A-014]", () => {
  const CLIP = {
    clip_id: "c1",
    started_at: "2026-08-30T10:00:00Z",
    ended_at: "2026-08-30T10:11:00Z",
    disponible: true,
    purged_at: null,
  } as never;

  it("pide ESE clip, por su id", () => {
    const clip = descarga();
    pintar({ data: datos({ clips: [CLIP] }) }, true, clip);
    fireEvent.click(screen.getByRole("button", { name: "DESCARGAR CLIP" }));
    expect(clip.download).toHaveBeenCalledWith("c1");
  });

  it("mientras se firma la URL el botón se apaga y DICE que está en curso", () => {
    pintar({ data: datos({ clips: [CLIP] }) }, true, descarga({ pendingClipId: "c1" }));
    const boton = screen.getByRole("button", { name: /PREPARANDO/ });
    expect(boton).toBeDisabled();
  });

  it("un fallo se declara junto a los clips, no se traga", () => {
    pintar(
      { data: datos({ clips: [CLIP] }) },
      true,
      descarga({
        failure: { clipId: "c1", message: "EL CLIP YA NO ESTÁ: la retención de vídeo lo podó" },
      }),
    );
    expect(screen.getByTestId("cctv-clip-error")).toHaveTextContent(/retención de vídeo/);
    expect(screen.getByTestId("cctv-clip-error")).toHaveAttribute("role", "alert");
  });

  // [T-8.08 · verificador] La descarga vive en `TriagePage`, que cambia de
  // incidente sin desmontarse. Lo que dice de un clip que NO es de este panel
  // es de otro incidente, y aquí sería mentira.
  it("el fallo de un clip de OTRO incidente no se pinta aquí", () => {
    pintar(
      { data: datos({ clips: [CLIP] }) },
      true,
      descarga({ failure: { clipId: "clip-de-otro", message: "EL CLIP YA NO ESTÁ" } }),
    );
    expect(screen.queryByTestId("cctv-clip-error")).toBeNull();
  });

  it("un clip de OTRO incidente en vuelo no apaga los botones de éste", () => {
    pintar({ data: datos({ clips: [CLIP] }) }, true, descarga({ pendingClipId: "clip-de-otro" }));
    expect(screen.getByRole("button", { name: "DESCARGAR CLIP" })).toBeEnabled();
  });

  it("uno de ESTE panel en vuelo sí apaga los demás: un clip a la vez", () => {
    const OTRO = { ...(CLIP as object), clip_id: "c2" } as never;
    pintar({ data: datos({ clips: [CLIP, OTRO] }) }, true, descarga({ pendingClipId: "c1" }));
    expect(screen.getByRole("button", { name: "DESCARGAR CLIP" })).toBeDisabled();
  });
});
