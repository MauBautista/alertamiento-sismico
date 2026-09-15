// [T-7.16] La línea de revisión: qué dice, qué NO dice y cuándo cambia de tiempo verbal.
//
// Lo que fija, por orden de lo que costaría equivocarse:
//
// 1. **No dice «PROTÉJASE» ni viste de alerta.** La sacudida terminó; un rojo
//    aquí manda a la gente a la escalera por un sismo que ya pasó.
// 2. **El contador cuenta HACIA ARRIBA.** Una cuenta atrás hacia el dictamen
//    preliminar sería una espera inventada: cuando el incidente entra en
//    revisión, ese plazo ya venció (ver la cabecera del componente).
// 3. **Pasadas las horas sin clasificar, habla en PASADO.** «ANALIZANDO» en
//    presente doce horas después dice que hay alguien mirando ahora mismo.
// 4. **No cierra nada.** El componente no muta estado: las palabras cambian, el
//    incidente sigue donde el servidor lo dejó.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { LiveIncident } from "../console/useLiveIncidents";
import ReviewLine, { REVIEW_PASADO_MS, transcurrido } from "./ReviewLine";

const ABIERTO = "2026-09-15T12:00:00Z";
const T0 = Date.parse(ABIERTO);

function incidente(over: Partial<LiveIncident> = {}): LiveIncident {
  return {
    incident_id: "11111111-2222-3333-4444-555555555555",
    tenant_id: "t-1",
    site_id: "s-1abcdef0",
    event_id: "EVT-REP-abc",
    opened_at: ABIERTO,
    closed_at: null,
    severity: "critical",
    state: "in_review",
    trigger: "sasmex",
    max_pga_g: 0.1,
    max_pgv_cms: 1,
    ...over,
  };
}

function pintar(props: Partial<Parameters<typeof ReviewLine>[0]> = {}) {
  return render(
    <MemoryRouter>
      <ReviewLine
        incident={incidente()}
        siteName="Edificio Central"
        siteCode="site-dev"
        epicentro={null}
        now={T0 + 47_000}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe("transcurrido · el formato del contador", () => {
  it("mm:ss mientras cabe la hora", () => {
    expect(transcurrido(0)).toBe("00:00");
    expect(transcurrido(47_000)).toBe("00:47");
    expect(transcurrido(125_000)).toBe("02:05");
    expect(transcurrido(3_599_000)).toBe("59:59");
  });

  it("h:mm en cuanto pasa de una hora: 214:07 no se lee", () => {
    expect(transcurrido(3_600_000)).toBe("1:00 h");
    expect(transcurrido(12 * 3_600_000 + 7 * 60_000)).toBe("12:07 h");
  });

  it("un tiempo NEGATIVO —relojes desalineados— no pinta un menos", () => {
    expect(transcurrido(-5_000)).toBe("00:00");
  });
});

describe("ReviewLine · lo que declara", () => {
  it("dice SISMO CONCLUIDO · ANALIZANDO y no una alerta", () => {
    pintar();
    const linea = screen.getByTestId("scene-review");
    expect(linea.textContent).toContain("SISMO CONCLUIDO · ANALIZANDO");
    expect(linea.textContent).not.toContain("PROTÉJASE");
    expect(linea.dataset.kind).toBe("review");
    // `status` y no `alert`: esto informa, no interrumpe. Un lector de pantalla
    // no debe cortar lo que esté leyendo por un sismo que ya terminó.
    expect(linea.getAttribute("role")).toBe("status");
  });

  it("el contador va HACIA ARRIBA desde la apertura", () => {
    pintar({ now: T0 + 47_000 });
    expect(screen.getByTestId("scene-review").textContent).toContain("SISMO HACE 00:47");
  });

  it("sin hora de apertura legible lo DECLARA en vez de pintar un NaN", () => {
    pintar({ incident: incidente({ opened_at: "no es una fecha" }) });
    const texto = screen.getByTestId("scene-review").textContent ?? "";
    expect(texto).toContain("SIN HORA DE APERTURA");
    expect(texto).not.toContain("NaN");
  });

  it("nombra el epicentro SOLO cuando el mapa ya lo tiene", () => {
    pintar({ epicentro: null });
    expect(screen.getByTestId("scene-review").textContent).not.toContain("EPICENTRO");

    pintar({ epicentro: { magnitude: 7.1, source: "external" } });
    expect(screen.getAllByTestId("scene-review")[1].textContent).toContain("EPICENTRO M7.1");
  });

  it("un epicentro SIN magnitud no se inventa una cifra", () => {
    pintar({ epicentro: { magnitude: null, source: "manual" } });
    const texto = screen.getByTestId("scene-review").textContent ?? "";
    expect(texto).toContain("EPICENTRO SIN MAGNITUD");
    expect(texto).not.toContain("M0");
  });

  it("lleva al dictamen por el MISMO enlace profundo que usa la consola", () => {
    pintar();
    const enlace = screen.getByRole("link", { name: "VER DICTAMEN" });
    expect(enlace.getAttribute("href")).toBe(
      "/triage?incident=11111111-2222-3333-4444-555555555555",
    );
  });
});

describe("ReviewLine · el tiempo verbal", () => {
  it("dentro de la retención habla en PRESENTE", () => {
    pintar({ now: T0 + REVIEW_PASADO_MS - 1000 });
    const linea = screen.getByTestId("scene-review");
    expect(linea.textContent).toContain("ANALIZANDO");
    expect(linea.dataset.past).toBe("false");
  });

  it("pasada la retención sin clasificar habla en PASADO y lo dice", () => {
    pintar({ now: T0 + REVIEW_PASADO_MS + 1000 });
    const linea = screen.getByTestId("scene-review");
    expect(linea.textContent).toContain("SISMO CONCLUIDO · SIN CLASIFICAR");
    expect(linea.textContent).toContain("NADIE LO HA CLASIFICADO");
    expect(linea.textContent).not.toContain("ANALIZANDO");
    expect(linea.dataset.past).toBe("true");
  });

  it("la retención del rótulo NO es un cierre: el incidente sigue en revisión", () => {
    // El componente es presentacional. Si algún día alguien le añadiera una
    // mutación, esta prueba no lo caza — pero la firma sí: no recibe ninguna.
    const inc = incidente();
    pintar({ incident: inc, now: T0 + REVIEW_PASADO_MS * 10 });
    expect(inc.state).toBe("in_review");
    expect(inc.closed_at).toBeNull();
  });
});
