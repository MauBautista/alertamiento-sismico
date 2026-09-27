// [T-9.06] La carrera arranque/parada del bucle de audio.
//
// `startAlertLoop` espera a `setAudioModeAsync` antes de crear el reproductor.
// Si la alerta termina en ese hueco, la parada no encontraba nada que parar y
// el arranque creaba DESPUÉS un reproductor en bucle huérfano: la sirena del
// teléfono sonando con la alerta ya terminada.
import { createAudioPlayer, setAudioModeAsync } from "expo-audio";

import { startAlertLoop, stopAlertLoop } from "./sound";

type Reproductor = { loop: boolean; play: jest.Mock; pause: jest.Mock; remove: jest.Mock };

jest.mock("expo-audio", () => ({
  setAudioModeAsync: jest.fn(),
  createAudioPlayer: jest.fn(),
}));

function reproductor(): Reproductor {
  return { loop: false, play: jest.fn(), pause: jest.fn(), remove: jest.fn() };
}

beforeEach(() => {
  stopAlertLoop();
  jest.mocked(setAudioModeAsync).mockReset();
  jest.mocked(createAudioPlayer).mockReset();
});

describe("startAlertLoop / stopAlertLoop", () => {
  it("arranca un reproductor en bucle y lo libera al parar", async () => {
    const r = reproductor();
    jest.mocked(setAudioModeAsync).mockResolvedValue(undefined);
    jest.mocked(createAudioPlayer).mockReturnValue(r as never);

    await startAlertLoop();
    expect(r.loop).toBe(true);
    expect(r.play).toHaveBeenCalledTimes(1);

    stopAlertLoop();
    expect(r.pause).toHaveBeenCalledTimes(1);
    expect(r.remove).toHaveBeenCalledTimes(1);
  });

  it("parar DURANTE la configuración del audio no deja un bucle huérfano", async () => {
    let liberar: () => void = () => undefined;
    jest.mocked(setAudioModeAsync).mockImplementation(
      () => new Promise<void>((ok) => (liberar = ok)),
    );
    jest.mocked(createAudioPlayer).mockReturnValue(reproductor() as never);

    const arranque = startAlertLoop();
    stopAlertLoop(); // la alerta terminó antes de que el audio estuviera listo
    liberar();
    await arranque;

    expect(createAudioPlayer).not.toHaveBeenCalled();
  });

  it("tras una parada a medias, el SIGUIENTE arranque sí suena", async () => {
    let liberar: () => void = () => undefined;
    jest.mocked(setAudioModeAsync).mockImplementationOnce(
      () => new Promise<void>((ok) => (liberar = ok)),
    );
    const r = reproductor();
    jest.mocked(createAudioPlayer).mockReturnValue(r as never);

    const viejo = startAlertLoop();
    stopAlertLoop();
    jest.mocked(setAudioModeAsync).mockResolvedValue(undefined);
    await startAlertLoop();
    liberar();
    await viejo;

    expect(createAudioPlayer).toHaveBeenCalledTimes(1);
    expect(r.play).toHaveBeenCalledTimes(1);
  });

  it("un segundo arranque mientras el primero se configura no crea dos reproductores", async () => {
    let liberar: () => void = () => undefined;
    jest.mocked(setAudioModeAsync).mockImplementation(
      () => new Promise<void>((ok) => (liberar = ok)),
    );
    jest.mocked(createAudioPlayer).mockReturnValue(reproductor() as never);

    const a = startAlertLoop();
    const b = startAlertLoop();
    liberar();
    await Promise.all([a, b]);

    expect(createAudioPlayer).toHaveBeenCalledTimes(1);
  });
});
