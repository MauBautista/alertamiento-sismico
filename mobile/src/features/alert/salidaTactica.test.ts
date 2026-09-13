import {
  marcarSalidaTactica,
  reiniciarSalidaTactica,
  salioDeLaCrisis,
} from "./salidaTactica";

describe("[T-7.29] salida táctica de la toma de crisis", () => {
  beforeEach(reiniciarSalidaTactica);

  it("sin marcar nada, la toma se impone", () => {
    expect(salioDeLaCrisis("i-1")).toBe(false);
  });

  it("marcada, este táctico ya no vuelve a la toma de ESE incidente", () => {
    marcarSalidaTactica("i-1");
    expect(salioDeLaCrisis("i-1")).toBe(true);
  });

  it("una alerta NUEVA vuelve a tomar la pantalla", () => {
    // El fallo que este test existe para impedir: con un booleano global, el
    // segundo sismo de la noche no le tomaría la pantalla a quien salió del
    // primero — que es justo cuando más falta hace.
    marcarSalidaTactica("i-1");
    expect(salioDeLaCrisis("i-2")).toBe(false);
  });

  it("sin incidente no se sale de nada", () => {
    marcarSalidaTactica(null);
    expect(salioDeLaCrisis(null)).toBe(false);
    expect(salioDeLaCrisis(undefined)).toBe(false);
  });

  it("reiniciar vuelve a imponer la toma", () => {
    marcarSalidaTactica("i-1");
    reiniciarSalidaTactica();
    expect(salioDeLaCrisis("i-1")).toBe(false);
  });
});
