/**
 * [T-6.16] LA PESTAÑA RESERVADA NUNCA SE QUEDA EN BLANCO.
 *
 * `openPendingDownload` reserva la pestaña dentro del gesto del usuario porque
 * la URL presignada todavía no existe (el servidor tiene que generar el PDF,
 * subirlo y firmarlo). Eso ya estaba bien. Lo que no estaba: durante toda esa
 * espera —10 s medidos en el stack local con el reporte de simulacro— la
 * pestaña era un `about:blank`. Una pestaña en blanco que aparece sola no se
 * distingue de un fallo, y quien la ve la cierra.
 *
 * Y si la petición fallaba, la pestaña se CERRABA. Aparecer y desaparecer no le
 * dice nada a quien acaba de pulsar EXPORTAR: ahora esa misma pestaña declara
 * el motivo.
 *
 * Se prueba con una ventana de mentira porque jsdom no abre pestañas; lo que se
 * fija es el CONTRATO —qué se escribe y cuándo—, no el HTML exacto.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { openPendingDownload } from "./download";

interface VentanaFalsa {
  closed: boolean;
  opener: unknown;
  location: { href: string };
  document: { open: () => void; write: (html: string) => void; close: () => void };
  escrito: string;
}

function ventana(): VentanaFalsa {
  const w: VentanaFalsa = {
    closed: false,
    opener: {},
    location: { href: "about:blank" },
    escrito: "",
    document: {
      open: () => {
        w.escrito = "";
      },
      write: (html: string) => {
        w.escrito += html;
      },
      close: () => {},
    },
  };
  return w;
}

function abrirCon(w: VentanaFalsa | null) {
  const open = vi.fn().mockReturnValue(w);
  vi.stubGlobal("window", { ...globalThis.window, open });
  return { pending: openPendingDownload(), open };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("pestaña reservada", () => {
  it("escribe la espera EN CUANTO se reserva: nunca un about:blank mudo", () => {
    const w = ventana();
    abrirCon(w);
    expect(w.escrito).not.toBe("");
    expect(w.escrito.toLowerCase()).toContain("generando");
    // Y dice que no hay que hacer nada: el operador no tiene que recargar ni
    // adivinar si aquello está vivo.
    expect(w.escrito.toLowerCase()).toContain("se abrirá sola");
  });

  it("corta el acceso del hijo a la ventana que lo abrió", () => {
    const w = ventana();
    abrirCon(w);
    expect(w.opener).toBeNull();
  });

  it("al llegar la URL, navega la pestaña", () => {
    const w = ventana();
    const { pending } = abrirCon(w);
    pending.resolve("https://s3/reporte.pdf?sig=x");
    expect(w.location.href).toBe("https://s3/reporte.pdf?sig=x");
  });

  it("si falla, la pestaña DECLARA el motivo en vez de cerrarse", () => {
    const w = ventana();
    const { pending } = abrirCon(w);
    pending.fail("POST /drills/…/report falló (503)");
    expect(w.closed).toBe(false);
    expect(w.escrito).toContain("503");
    expect(w.escrito.toLowerCase()).toContain("no se pudo generar");
    expect(w.escrito.toLowerCase()).toContain("volver a intentarlo");
  });

  it("una pestaña ya cerrada por la persona no rompe nada", () => {
    const w = ventana();
    const { pending } = abrirCon(w);
    w.closed = true;
    expect(() => pending.resolve("https://s3/x")).not.toThrow();
    expect(() => pending.fail("da igual")).not.toThrow();
    expect(w.location.href).toBe("about:blank");
  });

  it("si el navegador BLOQUEA la reserva, se declara y no se cae", () => {
    // `opened=false` es lo que mira la consola para ofrecer un enlace a mano.
    const { pending } = abrirCon(null);
    expect(pending.opened).toBe(false);
    expect(() => pending.resolve("https://s3/x")).not.toThrow();
    expect(() => pending.fail("x")).not.toThrow();
  });

  it("si escribir la pestaña lanza, la descarga NO se cae con ella", () => {
    const w = ventana();
    w.document.write = () => {
      throw new Error("bloqueado");
    };
    expect(() => abrirCon(w)).not.toThrow();
  });
});
