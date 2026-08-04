import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REDUCED_MOTION_QUERY, useReducedMotion } from "./useReducedMotion";

const original = Object.getOwnPropertyDescriptor(window, "matchMedia");

function stubMatchMedia(matches: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql = {
    matches,
    media: REDUCED_MOTION_QUERY,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn(() => mql),
  });
  return {
    emit: (next: boolean) => {
      mql.matches = next;
      for (const cb of listeners) cb({ matches: next } as MediaQueryListEvent);
    },
    listeners,
  };
}

afterEach(() => {
  if (original) Object.defineProperty(window, "matchMedia", original);
  else delete (window as unknown as Record<string, unknown>).matchMedia;
});

describe("useReducedMotion", () => {
  it("sin matchMedia (jsdom pelado) NO revienta y deja el movimiento como estaba", () => {
    delete (window as unknown as Record<string, unknown>).matchMedia;
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
  });

  it("lee el ajuste del sistema operativo", () => {
    stubMatchMedia(true);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(true);
  });

  it("reacciona al cambio EN CALIENTE (sin recargar la consola)", () => {
    const media = stubMatchMedia(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
    act(() => media.emit(true));
    expect(result.current).toBe(true);
  });

  it("desmontar suelta el listener", () => {
    const media = stubMatchMedia(false);
    const { unmount } = renderHook(() => useReducedMotion());
    expect(media.listeners.size).toBe(1);
    unmount();
    expect(media.listeners.size).toBe(0);
  });
});
