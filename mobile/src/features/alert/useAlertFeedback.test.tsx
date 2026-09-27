// [T-9.06] SONIDO Y VIBRACIÓN VIVEN Y MUEREN CON `alert_active`.
//
// El sonido ya existía (`sound.ts`) y este hook no lo cambia: lo arranca y lo
// para exactamente donde antes lo hacía el efecto de `crisis.tsx`. Lo nuevo es
// que la vibración va en el MISMO ciclo, así que no puede quedarse una sin la
// otra —la sirena del teléfono callada y el motor vibrando, o al revés—.
import { act, renderHook } from "@testing-library/react-native";
import { AppState, type AppStateStatus, Vibration } from "react-native";

import { startAlertLoop, stopAlertLoop } from "./sound";
import { useAlertFeedback } from "./useAlertFeedback";
import { PATRON_ALERTA, stopAlertVibration } from "./vibration";

jest.mock("./sound", () => ({
  startAlertLoop: jest.fn(async () => undefined),
  stopAlertLoop: jest.fn(),
}));

let vibrate: jest.SpyInstance;
let cancel: jest.SpyInstance;
let escucha: jest.SpyInstance;
let oyentes: ((estado: AppStateStatus) => void)[] = [];
let quitados = 0;

beforeEach(() => {
  oyentes = [];
  quitados = 0;
  escucha = jest.spyOn(AppState, "addEventListener").mockImplementation((_tipo, oyente) => {
    const fn = oyente as (estado: AppStateStatus) => void;
    oyentes.push(fn);
    return {
      remove: () => {
        quitados += 1;
        oyentes = oyentes.filter((o) => o !== fn);
      },
    };
  });
  vibrate = jest.spyOn(Vibration, "vibrate").mockImplementation(() => undefined);
  cancel = jest.spyOn(Vibration, "cancel").mockImplementation(() => undefined);
  stopAlertVibration();
  vibrate.mockClear();
  cancel.mockClear();
  jest.mocked(startAlertLoop).mockClear();
  jest.mocked(stopAlertLoop).mockClear();
});

afterEach(() => {
  vibrate.mockRestore();
  cancel.mockRestore();
  escucha.mockRestore();
});

async function aPrimerPlano(): Promise<void> {
  await act(async () => {
    oyentes.forEach((o) => o("active"));
  });
}

describe("useAlertFeedback", () => {
  it("con la alerta viva: suena Y vibra en bucle", async () => {
    await renderHook(() => useAlertFeedback(true));
    expect(startAlertLoop).toHaveBeenCalledTimes(1);
    expect(vibrate).toHaveBeenCalledWith([...PATRON_ALERTA], true);
  });

  it("sin alerta viva: ni suena ni vibra", async () => {
    await renderHook(() => useAlertFeedback(false));
    expect(startAlertLoop).not.toHaveBeenCalled();
    expect(vibrate).not.toHaveBeenCalled();
  });

  it("al dejar de estar viva: calla el altavoz Y cancela el motor", async () => {
    const h = await renderHook(({ viva }: { viva: boolean }) => useAlertFeedback(viva), {
      initialProps: { viva: true },
    });
    expect(cancel).not.toHaveBeenCalled();

    await h.rerender({ viva: false });

    expect(stopAlertLoop).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("al desmontar la pantalla con la alerta viva: también se cancela todo", async () => {
    const h = await renderHook(() => useAlertFeedback(true));
    await h.unmount();
    expect(stopAlertLoop).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("re-renderizar con la alerta todavía viva NO reinicia nada", async () => {
    const h = await renderHook(({ viva }: { viva: boolean }) => useAlertFeedback(viva), {
      initialProps: { viva: true },
    });
    await h.rerender({ viva: true });
    expect(startAlertLoop).toHaveBeenCalledTimes(1);
    expect(vibrate).toHaveBeenCalledTimes(1);
    expect(cancel).not.toHaveBeenCalled();
  });

  it("al volver a primer plano con la alerta viva RELANZA la vibración", async () => {
    // Android cancela el motor al apagar la pantalla con el botón y no avisa a
    // JS: sin relanzar, la crisis volvía a verse sin zumbido.
    await renderHook(() => useAlertFeedback(true));
    expect(vibrate).toHaveBeenCalledTimes(1);

    await aPrimerPlano();

    expect(cancel).toHaveBeenCalledTimes(1);
    expect(vibrate).toHaveBeenCalledTimes(2);
    expect(vibrate).toHaveBeenLastCalledWith([...PATRON_ALERTA], true);
  });

  it("sin alerta viva, volver a primer plano no vibra (ni se escucha AppState)", async () => {
    await renderHook(() => useAlertFeedback(false));
    expect(oyentes).toHaveLength(0);
    await aPrimerPlano();
    expect(vibrate).not.toHaveBeenCalled();
  });

  it("al terminar la alerta deja de escuchar AppState", async () => {
    const h = await renderHook(({ viva }: { viva: boolean }) => useAlertFeedback(viva), {
      initialProps: { viva: true },
    });
    await h.rerender({ viva: false });
    expect(quitados).toBe(1);
    await aPrimerPlano();
    expect(vibrate).toHaveBeenCalledTimes(1);
  });
});
