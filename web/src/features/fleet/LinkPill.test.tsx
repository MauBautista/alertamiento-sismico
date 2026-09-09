/**
 * [T-6.10 · U-23] EL LATIDO ES UNA AFIRMACIÓN, Y HABÍA QUE PODER SOSTENERLA.
 *
 * `.soc-dot--pulse` late para decir «esto está llegando AHORA». Esta pill lo
 * encendía con `kind === "ok"`, y `kind` sale de `derived_state`, que el
 * servidor deja en OPERATIVO hasta los 5 minutos sin latido
 * (`sin_enlace_min`). Entre medias había una franja de varios minutos en la que
 * el halo seguía latiendo sobre un dato quieto: la regla de oro 7 al revés, y
 * exactamente el defecto que `T-6.30` cerró en el panel del gabinete.
 *
 * El hermano de al lado ya lo hacía bien: el pill de `DetailPanel` late con
 * `liveFresh` y se para. Esto es traer esa regla a la tarjeta de flota.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LinkPill, { LINK_LIVE_MS } from "./LinkPill";

function pintar(props: Partial<Parameters<typeof LinkPill>[0]> = {}) {
  return render(
    <LinkPill
      kind="ok"
      label="MQTT BROKER"
      value="↔ 12.0 ms"
      icon={null}
      frameAgeMs={5_000}
      {...props}
    />,
  );
}

/** El punto que lleva la clase del halo, si la lleva. */
function punto(): HTMLElement {
  const el = document.querySelector(".soc-dot");
  if (el === null) throw new Error("la pill dejó de pintar su punto de estado");
  return el as HTMLElement;
}

describe("[T-6.10] el latido de LinkPill mira la EDAD DEL FRAME, no el veredicto", () => {
  it("con el enlace vivo y el frame fresco, late", () => {
    pintar({ kind: "ok", frameAgeMs: 5_000 });
    expect(punto().className).toContain("soc-dot--pulse");
  });

  it("con el enlace vivo pero el frame VIEJO, se detiene", () => {
    // El servidor sigue diciendo OPERATIVO —y no miente: a los 3 min todavía no
    // es SIN ENLACE—, pero lo que hay en pantalla no está llegando ahora.
    pintar({ kind: "ok", frameAgeMs: LINK_LIVE_MS + 1_000 });
    expect(punto().className).not.toContain("soc-dot--pulse");
  });

  it("y el TEXTO dice lo mismo que el latido, no solo la ausencia de latido", () => {
    // Un halo que se apaga sin decir por qué se lee como un halo que se rompió.
    pintar({ kind: "ok", frameAgeMs: 200_000 });
    const edad = screen.getByTestId("link-frame-age");
    expect(edad.textContent).toMatch(/ÚLTIMO FRAME/i);
    expect(edad.textContent).toMatch(/3 min/);
    // Una sola línea por construcción: la caja de la pill es estrecha y
    // «hace» costaba el salto de renglón (medido a 1440 px).
    expect(edad.textContent).not.toMatch(/hace/);
  });

  it("sin latido fresco NO se pinta nada de edad: el camino sano no gana ruido", () => {
    pintar({ kind: "ok", frameAgeMs: 5_000 });
    expect(screen.queryByTestId("link-frame-age")).toBeNull();
  });

  it("sin frame NUNCA (null) no late, y lo dice como ausencia, no como cero", () => {
    // `S/D` y no «hace 0 s»: un cero afirma que acaba de llegar.
    pintar({ kind: "ok", frameAgeMs: null });
    expect(punto().className).not.toContain("soc-dot--pulse");
    expect(screen.getByTestId("link-frame-age").textContent).toMatch(/S\/D/);
  });

  it("SIN ENLACE no late aunque el frame fuese de hace un segundo", () => {
    // El veredicto del servidor sigue mandando: la frescura sólo puede QUITAR
    // el latido, nunca ponerlo.
    pintar({ kind: "crit", frameAgeMs: 1_000 });
    expect(punto().className).not.toContain("soc-dot--pulse");
  });

  it("el umbral es más estrecho que el del servidor, o no serviría de nada", () => {
    // `sin_enlace_min = 5.0` (api/src/takab_api/settings.py): a los 5 min el
    // servidor ya dice SIN ENLACE y `kind` pasa a `crit` solo. Si este umbral
    // fuera igual o mayor, el latido nunca se detendría por frescura y este
    // arreglo sería decorativo.
    expect(LINK_LIVE_MS).toBeLessThan(5 * 60_000);
    // Y más ancho que la cadencia del edge (`health_heartbeat_s = 60`), o
    // parpadearía en cada latido perdido por jitter de red.
    expect(LINK_LIVE_MS).toBeGreaterThan(60_000);
  });
});
