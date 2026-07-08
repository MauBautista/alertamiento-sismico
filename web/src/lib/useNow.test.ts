import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useNow } from "./useNow";

describe("useNow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-08T10:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("devuelve el epoch actual y avanza con el intervalo", () => {
    const { result } = renderHook(() => useNow(1000));
    const t0 = result.current;
    expect(t0).toBe(Date.parse("2026-07-08T10:00:00Z"));
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current - t0).toBeGreaterThanOrEqual(3000);
  });

  it("limpia el intervalo al desmontar", () => {
    const { unmount } = renderHook(() => useNow(1000));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
