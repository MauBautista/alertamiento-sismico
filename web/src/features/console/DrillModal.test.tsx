// DrillModal (T-2.48): a quién, cuánto, cuándo y por qué se hace el simulacro.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ listSitesSitesGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import DrillModal from "./DrillModal";

const SITES = [
  { site_id: "s-1", name: "Torre A", code: "TA", status: "active" },
  { site_id: "s-2", name: "Torre B", code: "TB", status: "active" },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderModal(over: Partial<Parameters<typeof DrillModal>[0]> = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  render(
    <DrillModal pending={false} error={null} onSubmit={onSubmit} onClose={onClose} {...over} />,
    {
      wrapper,
    },
  );
  return { onSubmit, onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(Date.parse("2026-08-04T18:00:00Z"));
  sdk.listSitesSitesGet.mockResolvedValue({ data: SITES, response: { status: 200 } });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DrillModal", () => {
  it("sin selección explícita manda site_ids null (el servidor resuelve comandables)", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
    expect(onSubmit).toHaveBeenCalledWith({
      siteIds: null,
      durationS: 300,
      note: null,
      scheduledAt: null,
    });
  });

  it("multiselección de sitios", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Torre A"));
    fireEvent.click(screen.getByLabelText("Torre B"));
    fireEvent.click(screen.getByLabelText("Torre B")); // se deselecciona
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ siteIds: ["s-1"] }));
  });

  it("duración y nota viajan en la petición", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/DURACIÓN/), { target: { value: "900" } });
    fireEvent.change(screen.getByLabelText(/NOTA/), { target: { value: "simulacro trimestral" } });
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ durationS: 900, note: "simulacro trimestral" }),
    );
  });

  it("en modo PROGRAMAR manda scheduled_at en UTC y no dispara nada", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("PROGRAMAR"));
    const when = new Date(Date.parse("2026-08-05T12:00:00Z"));
    // El input local se rellena con el valor que produce el mismo instante UTC.
    const local = new Date(when.getTime() - when.getTimezoneOffset() * 60_000)
      .toISOString()
      .slice(0, 16);
    fireEvent.change(screen.getByLabelText(/FECHA Y HORA/), { target: { value: local } });
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ scheduledAt: "2026-08-05T12:00:00.000Z" }),
    );
  });

  it("una fecha pasada NO se envía: se rechaza con motivo", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("PROGRAMAR"));
    fireEvent.change(screen.getByLabelText(/FECHA Y HORA/), {
      target: { value: "2026-08-03T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("FUTURO");
  });

  it("programar sin fecha tampoco envía nada", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("PROGRAMAR"));
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("si /sites falla lo dice: no inventa una lista vacía de sitios", async () => {
    sdk.listSitesSitesGet.mockResolvedValue({ data: undefined, response: { status: 500 } });
    renderModal();
    await waitFor(() => expect(screen.getByText(/GET \/sites falló/)).toBeInTheDocument());
    // Aun así se puede lanzar a todos los comandables: el servidor es la autoridad.
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeEnabled();
  });

  it("rotula que un simulacro NO toca relés", async () => {
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    expect(screen.getByTestId("drill-modal")).toHaveTextContent("CERO RELÉS");
  });

  it("mientras la mutación está en vuelo no se puede disparar dos veces", async () => {
    renderModal({ pending: true });
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeDisabled();
  });
});
