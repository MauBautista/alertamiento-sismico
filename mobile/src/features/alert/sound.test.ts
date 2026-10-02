// [T-9.06] La carrera arranque/parada del bucle de audio.
//
// `startAlertLoop` espera a `setAudioModeAsync` antes de crear el reproductor.
// Si la alerta termina en ese hueco, la parada no encontraba nada que parar y
// el arranque creaba DESPUÉS un reproductor en bucle huérfano: la sirena del
// teléfono sonando con la alerta ya terminada.
import { createAudioPlayer, setAudioModeAsync } from "expo-audio";
import { Platform } from "react-native";

import { tonoOficialDeLaCompilacion } from "@/services/tonoOficial";

import { startAlertLoop, stopAlertLoop } from "./sound";

type Reproductor = { loop: boolean; play: jest.Mock; pause: jest.Mock; remove: jest.Mock };

jest.mock("expo-audio", () => ({
  setAudioModeAsync: jest.fn(),
  createAudioPlayer: jest.fn(),
}));

jest.mock("@/services/tonoOficial", () => ({
  ...jest.requireActual("@/services/tonoOficial"),
  tonoOficialDeLaCompilacion: jest.fn(() => null),
}));

function setPlatform(os: "ios" | "android") {
  Object.defineProperty(Platform, "OS", { value: os, configurable: true });
}

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

// [T-9.70 · D-50] El bucle de la app sólo corre en `alert_active`, que el servidor sólo
// sirve para un incidente que AUTORIZA evacuar (SASMEX o cuórum): suena el oficial. En
// Android, por el MISMO recurso que el canal (`raw/alerta_oficial`, que el plugin llena
// con el oficial o con el propio). Sin ese recurso —una compilación sin el plugin— y en
// iOS, el tono propio empaquetado: jamás un `require` del oficial, que no está en el repo.
describe("[T-9.70] qué suena en bucle", () => {
  async function fuente(): Promise<unknown> {
    const r = reproductor();
    jest.mocked(setAudioModeAsync).mockResolvedValue(undefined);
    jest.mocked(createAudioPlayer).mockReturnValue(r as never);
    await startAlertLoop();
    return jest.mocked(createAudioPlayer).mock.calls[0]?.[0];
  }

  afterEach(() => setPlatform("ios"));

  it("android con el recurso de la compilación ⇒ raw/alerta_oficial", async () => {
    setPlatform("android");
    jest.mocked(tonoOficialDeLaCompilacion).mockReturnValue("oficial");
    expect(await fuente()).toEqual({ uri: "alerta_oficial" });
  });

  it("android con el propio en ese recurso ⇒ el mismo recurso (lo llenó el plugin)", async () => {
    setPlatform("android");
    jest.mocked(tonoOficialDeLaCompilacion).mockReturnValue("propio");
    expect(await fuente()).toEqual({ uri: "alerta_oficial" });
  });

  it("sin recurso, o en iOS ⇒ el tono propio empaquetado", async () => {
    setPlatform("android");
    jest.mocked(tonoOficialDeLaCompilacion).mockReturnValue(null);
    expect(await fuente()).not.toEqual({ uri: "alerta_oficial" });
    stopAlertLoop();
    jest.mocked(createAudioPlayer).mockReset();
    setPlatform("ios");
    jest.mocked(tonoOficialDeLaCompilacion).mockReturnValue("oficial");
    expect(await fuente()).not.toEqual({ uri: "alerta_oficial" });
  });
});
