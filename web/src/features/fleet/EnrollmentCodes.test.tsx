import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EnrollmentCodeOut, SiteOut } from "@takab/sdk";

import { expectFourStates } from "../../test-utils/states";
import EnrollmentCodes, { REVEAL_MS } from "./EnrollmentCodes";
import { generateEnrollmentCode } from "./useEnrollmentCodes";
import type { EnrollmentCodesData } from "./useEnrollmentCodes";

const mocks = vi.hoisted(() => ({
  useEnrollmentCodes: vi.fn(),
  useCreateEnrollmentCode: vi.fn(),
  useRevokeEnrollmentCode: vi.fn(),
}));

vi.mock("./useEnrollmentCodes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./useEnrollmentCodes")>();
  return { ...actual, ...mocks };
});

const SITE = {
  site_id: "s-1",
  tenant_id: "t-1",
  code: "MTY-01",
  name: "Torre Norte",
} as unknown as SiteOut;

function code(over: Partial<EnrollmentCodeOut> = {}): EnrollmentCodeOut {
  return {
    code: "ABCD2345",
    site_id: "s-1",
    zone_id: null,
    grants_role: "occupant",
    expires_at: "2026-09-01T00:00:00Z",
    max_uses: 25,
    uses: 3,
    active: true,
    ...over,
  };
}

function codesData(over: Partial<EnrollmentCodesData> = {}): EnrollmentCodesData {
  return {
    codes: [code()],
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

function mutation(over: Record<string, unknown> = {}) {
  return { mutate: vi.fn(), reset: vi.fn(), isPending: false, error: null, ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.useEnrollmentCodes.mockReturnValue(codesData());
  mocks.useCreateEnrollmentCode.mockReturnValue(mutation());
  mocks.useRevokeEnrollmentCode.mockReturnValue(mutation());
});

afterEach(() => {
  vi.useRealTimers();
});

function renderCard() {
  return render(<EnrollmentCodes site={SITE} onClose={vi.fn()} />);
}

describe("generateEnrollmentCode · el código es un secreto operativo", () => {
  it("usa el CSPRNG del navegador, no Math.random()", () => {
    const spy = vi.spyOn(crypto, "getRandomValues");
    generateEnrollmentCode();
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it("evita los caracteres que se confunden al dictarlo (0/O, 1/I/L)", () => {
    // Se dicta por teléfono y se teclea en un móvil, a veces a oscuras: cada par
    // ambiguo es un enrolamiento fallido en el peor momento.
    for (let i = 0; i < 200; i += 1) {
      expect(generateEnrollmentCode()).toMatch(/^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}$/);
    }
  });

  it("cumple el patrón que el servidor exige (EnrollmentCodeIn)", () => {
    expect(generateEnrollmentCode()).toMatch(/^[A-Za-z0-9][A-Za-z0-9._-]*$/);
  });
});

describe("EnrollmentCodes · regla de oro 7", () => {
  it("materializa los 4 estados obligatorios", () => {
    expectFourStates((state) => {
      mocks.useEnrollmentCodes.mockReturnValue(
        codesData({
          loading: state === "loading",
          error: state === "error" ? "SIN PERMISO" : null,
          codes: state === "empty" ? [] : [code()],
          // No hay poll, pero el listado SÍ envejece: otro admin puede revocar un
          // código desde otra sesión y esta pestaña lo seguiría mostrando activo.
          dataUpdatedAt: state === "stale" ? Date.now() - 400_000 : Date.now(),
        }),
      );
      return <EnrollmentCodes site={SITE} onClose={vi.fn()} />;
    });
  });
});

describe("EnrollmentCodes · el código nuevo no vive en el DOM más de lo necesario", () => {
  it("se destaca al crearlo y desaparece solo tras REVEAL_MS", () => {
    vi.useFakeTimers();
    const create = mutation({
      mutate: vi.fn((_args, opts) => opts?.onSuccess?.()),
    });
    mocks.useCreateEnrollmentCode.mockReturnValue(create);
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: "GENERAR CÓDIGO" }));
    const shown = screen.getByTestId("fresh-code").textContent ?? "";
    expect(shown).toMatch(/[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}/);

    act(() => {
      vi.advanceTimersByTime(REVEAL_MS + 1000);
    });
    expect(screen.queryByTestId("fresh-code")).toBeNull();
  });

  it("OCULTAR lo retira antes de que expire el temporizador", () => {
    const create = mutation({ mutate: vi.fn((_args, opts) => opts?.onSuccess?.()) });
    mocks.useCreateEnrollmentCode.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "GENERAR CÓDIGO" }));
    fireEvent.click(screen.getByRole("button", { name: "OCULTAR" }));
    expect(screen.queryByTestId("fresh-code")).toBeNull();
  });

  it("NO persiste nada en localStorage ni sessionStorage (CLAUDE.md §8)", () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    const create = mutation({ mutate: vi.fn((_args, opts) => opts?.onSuccess?.()) });
    mocks.useCreateEnrollmentCode.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "GENERAR CÓDIGO" }));
    expect(local).not.toHaveBeenCalled();
    local.mockRestore();
  });
});

describe("EnrollmentCodes · el listado enmascara por defecto", () => {
  it("un código existente sale enmascarado, con la misma longitud", () => {
    renderCard();
    const row = screen.getByTestId("enrollment-row");
    expect(row.textContent).not.toContain("ABCD2345");
    expect(row.textContent).toContain("••••••••");
  });

  it("VER lo revela y vuelve a ocultarlo (acto explícito, no por defecto)", () => {
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "VER" }));
    expect(screen.getByTestId("enrollment-row").textContent).toContain("ABCD2345");
    fireEvent.click(screen.getByRole("button", { name: "OCULTAR" }));
    expect(screen.getByTestId("enrollment-row").textContent).not.toContain("ABCD2345");
  });
});

describe("EnrollmentCodes · vigencia, usos y revocación", () => {
  it("manda la caducidad calculada y el tope de usos", () => {
    const create = mutation();
    mocks.useCreateEnrollmentCode.mockReturnValue(create);
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "GENERAR CÓDIGO" }));
    const [args] = create.mutate.mock.calls[0];
    expect(args.siteId).toBe("s-1");
    expect(args.maxUses).toBe(25);
    expect(Date.parse(args.expiresAt)).toBeGreaterThan(Date.now());
  });

  it("un tope de usos vacío significa SIN TOPE, no cero", () => {
    const create = mutation();
    mocks.useCreateEnrollmentCode.mockReturnValue(create);
    renderCard();
    fireEvent.change(screen.getByLabelText(/Usos máximos/), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "GENERAR CÓDIGO" }));
    expect(create.mutate.mock.calls[0][0].maxUses).toBeNull();
  });

  it("elegir 'Sin caducidad' avisa de lo que significa", () => {
    renderCard();
    expect(screen.queryByTestId("no-expiry-warning")).toBeNull();
    fireEvent.change(screen.getByLabelText("Vigencia"), { target: { value: "3" } });
    expect(screen.getByTestId("no-expiry-warning").textContent).toMatch(/para siempre/);
  });

  it("un código vencido se rotula VENCIDO, no 'vence'", () => {
    mocks.useEnrollmentCodes.mockReturnValue(
      codesData({ codes: [code({ expires_at: "2020-01-01T00:00:00Z" })] }),
    );
    renderCard();
    expect(screen.getByTestId("enrollment-row").textContent).toMatch(/VENCIDO/);
  });

  it("REVOCAR desactiva; un revocado ya no ofrece el botón", () => {
    const revoke = mutation();
    mocks.useRevokeEnrollmentCode.mockReturnValue(revoke);
    const { rerender } = renderCard();
    fireEvent.click(screen.getByRole("button", { name: "REVOCAR" }));
    expect(revoke.mutate).toHaveBeenCalledWith({ siteId: "s-1", code: "ABCD2345" });

    mocks.useEnrollmentCodes.mockReturnValue(codesData({ codes: [code({ active: false })] }));
    rerender(<EnrollmentCodes site={SITE} onClose={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "REVOCAR" })).toBeNull();
    expect(screen.getByTestId("enrollment-row").textContent).toMatch(/REVOCADO/);
  });

  it("un error del servidor se muestra literal", () => {
    mocks.useCreateEnrollmentCode.mockReturnValue(
      mutation({ error: new Error("SIN PERMISO · tu rol no administra los códigos") }),
    );
    renderCard();
    expect(screen.getByTestId("enrollment-error").textContent).toMatch(/SIN PERMISO/);
  });

  it("dice que el código SOLO concede el rol occupant", () => {
    renderCard();
    expect(screen.getByText(/enrolado como OCUPANTE/i)).toBeTruthy();
  });
});
