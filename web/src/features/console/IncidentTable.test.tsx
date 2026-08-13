import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import IncidentTable from "./IncidentTable";
import type { LiveIncident } from "./useLiveIncidents";

const NOW = Date.parse("2026-07-08T10:41:35Z");

function incident(id: string, over: Partial<LiveIncident> = {}): LiveIncident {
  return {
    incident_id: id,
    tenant_id: "t-1",
    site_id: `s-${id}`,
    event_id: null,
    opened_at: "2026-07-08T10:41:30Z",
    closed_at: null,
    severity: "critical",
    state: "open",
    trigger: "local_threshold",
    max_pga_g: 0.15,
    max_pgv_cms: 4.2,
    ...over,
  };
}

function renderTable(over: Partial<Parameters<typeof IncidentTable>[0]> = {}) {
  const onAck = vi.fn();
  const onSelect = vi.fn();
  const onRelocate = vi.fn();
  const onRequestDictamen = vi.fn();
  render(
    <IncidentTable
      incidents={[incident("a")]}
      siteInfoOf={() => ({ name: "Planta Cholula", coords: "19.0633°N · 98.3014°W" })}
      nowMs={NOW}
      liveStatus="ready"
      operatorLabel="TENANT_ADMIN · SOC"
      selectedId={null}
      onSelect={onSelect}
      canAck
      onAck={onAck}
      canRelocate
      onRelocate={onRelocate}
      canRequestDictamen
      onRequestDictamen={onRequestDictamen}
      {...over}
    />,
  );
  return { onAck, onSelect, onRelocate, onRequestDictamen };
}

describe("IncidentTable", () => {
  it("pinta la fila con sitio, PGA, hora UTC y edad", () => {
    renderTable();
    expect(screen.getByText("Planta Cholula")).toBeInTheDocument();
    expect(screen.getByText("0.150g")).toBeInTheDocument();
    expect(screen.getByText("10:41:30 UTC")).toBeInTheDocument();
    expect(screen.getByText("T+05s")).toBeInTheDocument();
    expect(screen.getByText("1 ACTIVOS")).toBeInTheDocument();
  });

  it("el pill LIVE refleja el estado del WS con honestidad", () => {
    renderTable({ liveStatus: "connecting" });
    expect(screen.getByTestId("live-pill")).toHaveTextContent("SIN LIVE");
  });

  it("clic en la fila selecciona el incidente", () => {
    const { onSelect } = renderTable();
    fireEvent.click(screen.getByText("Planta Cholula"));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ incident_id: "a" }));
  });

  it("CONFIRMAR ACUSE es two-step y solo con fila seleccionada", () => {
    const { onAck } = renderTable({ selectedId: "a" });
    const button = screen.getByRole("button", { name: /CONFIRMAR ACUSE/ });
    fireEvent.click(button); // arma
    expect(onAck).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA ACUSAR/ }));
    expect(onAck).toHaveBeenCalledWith("a");
  });

  it("sin allowed_actions.ack_incident el acuse queda deshabilitado", () => {
    const { onAck } = renderTable({ canAck: false, selectedId: "a" });
    const button = screen.getByRole("button", { name: /CONFIRMAR ACUSE/ });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onAck).not.toHaveBeenCalled();
  });

  it("muestra la identidad real de la sesión (sin selector de turno)", () => {
    renderTable();
    const operator = screen.getByTestId("operator-label");
    expect(operator).toHaveTextContent("TENANT_ADMIN · SOC");
    // [T-2.50] La aserción original era `queryByRole("combobox") === null`, y
    // pasó a ser falsa al añadir el selector de ORDEN de la cola. Lo que la
    // desviación ratificada prohíbe es un selector de TURNO que permita firmar
    // como otro operador — no cualquier <select> de la pantalla. Se acota al
    // bloque de identidad, que es donde vivía el riesgo.
    const block = operator.closest(".soc-incidents__operator");
    expect(block).not.toBeNull();
    expect(block?.querySelector("select")).toBeNull();
  });

  // ---- T-2.50: orden de la cola -------------------------------------------
  it("ordena por el criterio elegido sin tocar la cola del servidor", () => {
    const critico = incident("crit", { severity: "critical", opened_at: "2026-07-08T10:00:00Z" });
    const reciente = incident("new", { severity: "info", opened_at: "2026-07-08T10:41:30Z" });
    renderTable({ incidents: [reciente, critico] });

    const first = () => screen.getAllByRole("row")[1].textContent ?? "";
    // Default = severidad: el crítico manda aunque sea más viejo.
    expect(first()).toContain("10:00:00 UTC");

    fireEvent.change(screen.getByTestId("incident-order"), { target: { value: "recent" } });
    expect(first()).toContain("10:41:30 UTC");

    fireEvent.change(screen.getByTestId("incident-order"), { target: { value: "age" } });
    expect(first()).toContain("10:00:00 UTC");
  });

  it("ordenar por distancia SIN epicentro lo declara, no baraja las filas", () => {
    renderTable({ incidents: [incident("a"), incident("b", { severity: "info" })] });
    fireEvent.change(screen.getByTestId("incident-order"), { target: { value: "distance" } });
    expect(screen.getByTestId("order-distance-unavailable")).toHaveTextContent(
      "SIN EPICENTRO LOCALIZADO · ORDENADO POR SEVERIDAD",
    );
  });

  it("con epicentro conocido NO muestra el aviso de degradación", () => {
    renderTable({
      epicenter: {
        event_id: "E",
        source: "sasmex",
        lon: -98.3,
        lat: 19.06,
        magnitude: null,
        depth_km: null,
        detected_at: "2026-07-08T10:41:00Z",
      },
    });
    fireEvent.change(screen.getByTestId("incident-order"), { target: { value: "distance" } });
    expect(screen.queryByTestId("order-distance-unavailable")).toBeNull();
  });

  // ---- T-1.51: botones del operador vivos ---------------------------------
  it("REUBICAR EPICENTRO se habilita con permiso + selección y despacha", () => {
    const { onRelocate } = renderTable({ selectedId: "a" });
    fireEvent.click(screen.getByRole("button", { name: /REUBICAR EPICENTRO/ }));
    expect(onRelocate).toHaveBeenCalledWith("a");
  });

  it("SOLICITAR DICTAMEN es two-step y despacha con la fila seleccionada", () => {
    const { onRequestDictamen } = renderTable({ selectedId: "a" });
    fireEvent.click(screen.getByRole("button", { name: /SOLICITAR DICTAMEN TÉCNICO/ }));
    expect(onRequestDictamen).not.toHaveBeenCalled(); // armado, aún no dispara
    fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA SOLICITAR/ }));
    expect(onRequestDictamen).toHaveBeenCalledWith("a");
  });

  it("sin permiso los botones quedan deshabilitados CON explicación (title)", () => {
    const { onRelocate } = renderTable({
      canRelocate: false,
      canRequestDictamen: false,
      selectedId: "a",
    });
    const relocate = screen.getByRole("button", { name: /REUBICAR EPICENTRO/ });
    expect(relocate).toBeDisabled();
    expect(relocate.closest("span")).toHaveAttribute(
      "title",
      expect.stringContaining("Tu rol no tiene esta acción"),
    );
    fireEvent.click(relocate);
    expect(onRelocate).not.toHaveBeenCalled();
  });

  it("con permiso pero sin selección: deshabilitado y el title lo dice", () => {
    renderTable({ selectedId: null });
    const relocate = screen.getByRole("button", { name: /REUBICAR EPICENTRO/ });
    expect(relocate).toBeDisabled();
    expect(relocate.closest("span")).toHaveAttribute(
      "title",
      expect.stringContaining("Selecciona un incidente"),
    );
  });
});

/* =====================================================================
   [T-2.129] DEGRADADO ≠ SIN CONEXIÓN — tres estados, no dos
   ===================================================================== */

describe("[T-2.129] la pastilla del canal live distingue degradado de desconectado", () => {
  const DEGRADADO = [{ topic: "incidents", label: "INCIDENTES", detail: "incident: LockTimeout" }];

  it("canal sano: ● LIVE, sin aviso", () => {
    renderTable();
    expect(screen.getByTestId("live-pill")).toHaveTextContent("● LIVE");
    expect(screen.queryByTestId("live-degraded")).toBeNull();
  });

  it("canal DEGRADADO: la pastilla lo dice y NO dice «SIN LIVE»", () => {
    // La diferencia importa y no es cosmética: «SIN LIVE» le dice al operador
    // que no le llega nada —y por tanto que mire el REST—; «DEGRADADO» le dice
    // que el canal SÍ está entregando pero que se perdió algo por el camino, que
    // es la única de las dos situaciones en la que la cola puede estar
    // incompleta pareciendo completa.
    renderTable({ liveStatus: "ready", degraded: DEGRADADO });
    const pill = screen.getByTestId("live-pill");
    expect(pill).toHaveTextContent("● LIVE DEGRADADO");
    expect(pill.textContent).not.toContain("SIN LIVE");
  });

  it("y explica QUÉ se degradó, sin escupir el error técnico como rótulo", () => {
    renderTable({ liveStatus: "ready", degraded: DEGRADADO });
    const aviso = screen.getByTestId("live-degraded");
    expect(aviso).toHaveTextContent("INCIDENTES");
    expect(aviso).toHaveAttribute("role", "status");
    // El detalle técnico va al `title` (soporte), no al texto que se lee a
    // gritos en una sala de crisis.
    expect(aviso).toHaveAttribute("title", expect.stringContaining("LockTimeout"));
  });

  it("varios topics degradados se enumeran, no se resumen en «algo falla»", () => {
    renderTable({
      liveStatus: "ready",
      degraded: [
        { topic: "incidents", label: "INCIDENTES", detail: null },
        { topic: "features:s-a", label: "SISMOGRAMA", detail: null },
      ],
    });
    const aviso = screen.getByTestId("live-degraded");
    expect(aviso).toHaveTextContent("INCIDENTES");
    expect(aviso).toHaveTextContent("SISMOGRAMA");
  });

  it("SIN CONEXIÓN manda sobre degradado: primero recupera el canal", () => {
    // Con el socket caído, «DEGRADADO» sería ruido: no hay canal que degradar.
    renderTable({ liveStatus: "connecting", degraded: DEGRADADO });
    expect(screen.getByTestId("live-pill")).toHaveTextContent("● SIN LIVE");
    expect(screen.queryByTestId("live-degraded")).toBeNull();
  });
});

describe("formatPga (T-1.50)", () => {
  it("null = sin medición; un pico real diminuto jamás se imprime como 0.000g", async () => {
    const { formatPga } = await import("./IncidentTable");
    expect(formatPga(null)).toBe("—");
    expect(formatPga(0.0004)).toBe("<0.001g");
    expect(formatPga(0.001)).toBe("0.001g");
    expect(formatPga(0.567)).toBe("0.567g");
    expect(formatPga(0)).toBe("0.000g"); // cero MEDIDO sí es cero
  });
});
