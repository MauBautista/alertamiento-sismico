// [T-6.23 · U-36] El cable entre `AppState` y el `focusManager` de TanStack Query.
//
// `refetchOnWindowFocus` viene puesto por defecto y en React Native NO SE
// DISPARA NUNCA: no hay ventana de la que recuperar el foco. Hasta esta ficha
// eso significaba que traer la app al frente no pedía nada, y con la push en
// simulado la toma de crisis llegaba cuando tocara el sondeo (30 s en reposo).
//
// Se escribe con las dependencias por parámetro —no importando `AppState` ni
// `focusManager` aquí dentro— para poder probar el cable sin simular React
// Native entero: lo que puede romperse es la TRADUCCIÓN de estados, no la
// librería.

/** Lo que este módulo necesita de `AppState` de React Native. */
export interface AppStateLike {
  currentState: string;
  addEventListener(tipo: "change", cb: (estado: string) => void): { remove(): void };
}

/** Lo que necesita del `focusManager` de TanStack Query. */
export interface FocusSink {
  setFocused(focused: boolean): void;
}

/**
 * Ata el ciclo de vida de la app al foco de las consultas. Devuelve la función
 * para soltarlo.
 *
 * `inactive` NO cuenta como fondo: en iOS es la app tapada por el centro de
 * control o por una llamada entrante, y tratarlo como fondo haría que descartar
 * cualquier aviso provocara un ciclo foco→refetch de todas las consultas vivas.
 * Solo `background` suelta el foco.
 */
export function wireAppStateToFocus(appState: AppStateLike, focus: FocusSink): () => void {
  let ultimo: boolean | null = null;
  const aplicar = (estado: string): void => {
    if (estado === "inactive") return;
    const enfocada = estado === "active";
    // Android emite `active` más de una vez al volver al frente; sin esta
    // guarda cada repetición sería otro refetch.
    if (ultimo === enfocada) return;
    ultimo = enfocada;
    focus.setFocused(enfocada);
  };
  const sub = appState.addEventListener("change", aplicar);
  return () => sub.remove();
}
