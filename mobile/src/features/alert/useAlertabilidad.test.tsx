// [T-9.13] La comprobación se REPITE al volver a la app: es cuando la persona
// viene de conceder el acceso a «No molestar» en los ajustes del sistema.
import { act, renderHook } from "@testing-library/react-native";
import { AppState, Linking, type AppStateStatus } from "react-native";

import { abrirAccesoNoMolestar, getAlertabilitySnapshot } from "@/services/push";

import { ejecutarAccionDelTelefono, useAlertabilidad } from "./useAlertabilidad";

jest.mock("@/services/push", () => ({
  getAlertabilitySnapshot: jest.fn(),
  abrirAccesoNoMolestar: jest.fn(async () => undefined),
}));
const snapshot = getAlertabilitySnapshot as jest.Mock;
const abrirNoMolestar = abrirAccesoNoMolestar as jest.Mock;

describe("useAlertabilidad", () => {
  it("carga al montar y RE-comprueba al volver a primer plano", async () => {
    let alCambiar: ((s: AppStateStatus) => void) | undefined;
    const sub = jest.spyOn(AppState, "addEventListener").mockImplementation((_t, fn) => {
      alCambiar = fn as (s: AppStateStatus) => void;
      return { remove: jest.fn() } as never;
    });
    snapshot.mockResolvedValueOnce({
      granted: true,
      canAskAgain: true,
      iosCriticalAllowed: null,
      androidDndBypass: false,
    });
    const { result } = await renderHook(() => useAlertabilidad());
    await act(async () => {});
    expect(result.current?.level).toBe("degraded");

    snapshot.mockResolvedValueOnce({
      granted: true,
      canAskAgain: true,
      iosCriticalAllowed: null,
      androidDndBypass: true,
    });
    await act(async () => {
      alCambiar?.("active");
    });
    expect(snapshot).toHaveBeenCalledTimes(2);
    expect(result.current?.level).toBe("ok");
    sub.mockRestore();
  });

  it("si la lectura falla, no inventa un «todo bien»: se queda sin dato", async () => {
    const sub = jest
      .spyOn(AppState, "addEventListener")
      .mockReturnValue({ remove: jest.fn() } as never);
    snapshot.mockRejectedValueOnce(new Error("nativo"));
    const { result } = await renderHook(() => useAlertabilidad());
    await act(async () => {});
    expect(result.current).toBeNull();
    sub.mockRestore();
  });
});

describe("ejecutarAccionDelTelefono", () => {
  it("PERMITIR «NO MOLESTAR» abre ese ajuste; si no se puede, los de la app", async () => {
    const ajustes = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
    ejecutarAccionDelTelefono("permitir_no_molestar");
    expect(abrirNoMolestar).toHaveBeenCalledTimes(1);
    expect(ajustes).not.toHaveBeenCalled();
    abrirNoMolestar.mockRejectedValueOnce(new Error("sin actividad"));
    ejecutarAccionDelTelefono("permitir_no_molestar");
    await Promise.resolve();
    await Promise.resolve();
    expect(ajustes).toHaveBeenCalledTimes(1);
    ajustes.mockRestore();
  });

  it("ABRIR AJUSTES abre los de la app", () => {
    const ajustes = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
    ejecutarAccionDelTelefono("abrir_ajustes");
    expect(ajustes).toHaveBeenCalledTimes(1);
    ajustes.mockRestore();
  });
});
