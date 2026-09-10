/**
 * [T-6.23 · U-36] VOLVER DEL FONDO TIENE QUE REFRESCAR.
 *
 * TanStack Query refresca al recuperar el foco… de una VENTANA, y en React
 * Native no hay ninguna: sin atar `AppState` al `focusManager`, el
 * `refetchOnWindowFocus` que trae por defecto no se dispara nunca. El efecto
 * medido en la auditoría: sin push (está en simulado), traer la app al frente
 * no pedía nada y la toma de crisis llegaba cuando tocara el sondeo — 8.5 s
 * medidos, hasta 30 en reposo. Para quien abre la app porque el edificio está
 * sonando, esos segundos son la pantalla.
 *
 * Lo que se prueba aquí es el CABLE, no la librería: que se suscribe, que
 * traduce los estados de Android a foco, y que se puede soltar.
 */
import { wireAppStateToFocus, type AppStateLike, type FocusSink } from "./appFocus";

function arnes() {
  const oyentes: ((s: string) => void)[] = [];
  let quitado = 0;
  const appState: AppStateLike = {
    currentState: "active",
    addEventListener: (_tipo, cb) => {
      oyentes.push(cb);
      return { remove: () => { quitado += 1; } };
    },
  };
  const focos: boolean[] = [];
  const sink: FocusSink = { setFocused: (v) => focos.push(v) };
  return { appState, sink, focos, emitir: (s: string) => oyentes.forEach((f) => f(s)), quitados: () => quitado, oyentes };
}

describe("[T-6.23] AppState → focusManager", () => {
  it("se suscribe UNA vez al cambio de estado de la app", () => {
    const a = arnes();
    wireAppStateToFocus(a.appState, a.sink);
    expect(a.oyentes).toHaveLength(1);
  });

  it("volver al frente DA el foco: eso es lo que dispara el refetch", () => {
    const a = arnes();
    wireAppStateToFocus(a.appState, a.sink);
    a.emitir("background");
    a.emitir("active");
    expect(a.focos).toEqual([false, true]);
  });

  it("`inactive` NO quita el foco: es el estado de un aviso encima, no del fondo", () => {
    // En iOS `inactive` es la app tapada por el centro de control o una llamada
    // entrante. Tratarlo como fondo haría que cada notificación provocara un
    // ciclo foco→refetch al descartarla.
    const a = arnes();
    wireAppStateToFocus(a.appState, a.sink);
    a.emitir("inactive");
    expect(a.focos).toEqual([]);
  });

  it("no repite el foco si el estado no cambió", () => {
    // Android emite `active` más de una vez al volver; cada repetición sería
    // otro refetch de todas las consultas vivas.
    const a = arnes();
    wireAppStateToFocus(a.appState, a.sink);
    a.emitir("background");
    a.emitir("active");
    a.emitir("active");
    expect(a.focos).toEqual([false, true]);
  });

  it("devuelve cómo soltarlo, y soltarlo quita el oyente", () => {
    const a = arnes();
    const soltar = wireAppStateToFocus(a.appState, a.sink);
    soltar();
    expect(a.quitados()).toBe(1);
  });
});
