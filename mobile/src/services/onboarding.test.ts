import * as SecureStore from "expo-secure-store";

import {
  getGpsConsent,
  isOnboardingDone,
  markOnboardingDone,
  setGpsConsent,
} from "./onboarding";

jest.mock("expo-secure-store", () => {
  const mem = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (k: string) => mem.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => {
      mem.set(k, v);
    }),
    deleteItemAsync: jest.fn(async (k: string) => {
      mem.delete(k);
    }),
    __mem: mem,
  };
});

const mem = (SecureStore as unknown as { __mem: Map<string, string> }).__mem;

describe("onboarding local", () => {
  beforeEach(() => mem.clear());

  it("arranca incompleto y sin consentimiento decidido", async () => {
    await expect(isOnboardingDone()).resolves.toBe(false);
    await expect(getGpsConsent()).resolves.toBeNull();
  });

  it("marca completado de forma persistente", async () => {
    await markOnboardingDone();
    await expect(isOnboardingDone()).resolves.toBe(true);
  });

  it("el consentimiento GPS es explícito y revocable", async () => {
    await setGpsConsent(true);
    await expect(getGpsConsent()).resolves.toBe(true);
    await setGpsConsent(false);
    await expect(getGpsConsent()).resolves.toBe(false);
  });
});
