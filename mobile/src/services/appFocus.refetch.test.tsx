/**
 * [T-6.23 · U-36] Y QUE EL CABLE DE VERDAD PROVOQUE EL REFETCH.
 *
 * `appFocus.test.ts` prueba la traducción de estados; esto prueba la
 * consecuencia, que es lo que dice el criterio: con el cable puesto, volver al
 * frente vuelve a pedir el dato SIN esperar al sondeo. Se monta un
 * `QueryClient` de verdad y el `focusManager` de verdad; lo único simulado es
 * el `AppState` de Android.
 *
 * Por qué esto y no una medición en el teléfono: se intentó cuatro veces y
 * ninguna concluye —está escrito en la ficha—. Aquí la relación causa→efecto es
 * observable y no depende de que Android decida suspender un temporizador.
 */
import { focusManager, QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

import { wireAppStateToFocus, type AppStateLike } from "./appFocus";

function appStateFalso() {
  const oyentes: ((s: string) => void)[] = [];
  const appState: AppStateLike = {
    currentState: "active",
    addEventListener: (_t, cb) => {
      oyentes.push(cb);
      return { remove: () => undefined };
    },
  };
  return { appState, emitir: (s: string) => oyentes.forEach((f) => f(s)) };
}

describe("[T-6.23] volver al frente vuelve a pedir el dato", () => {
  afterEach(() => focusManager.setFocused(undefined));

  it("con el cable puesto, `active` dispara el refetch sin esperar al sondeo", async () => {
    const a = appStateFalso();
    const soltar = wireAppStateToFocus(a.appState, focusManager);
    let veces = 0;
    const client = new QueryClient({
      // Sin sondeo: si el dato se vuelve a pedir, sólo puede haber sido el foco.
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });
    function Pantalla() {
      const q = useQuery({
        queryKey: ["mobile-state"],
        queryFn: async () => {
          veces += 1;
          return veces;
        },
      });
      return <Text>{String(q.data ?? "—")}</Text>;
    }
    const v = await render(
      <QueryClientProvider client={client}>
        <Pantalla />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(veces).toBe(1));

    a.emitir("background");
    a.emitir("active");
    await waitFor(() => expect(veces).toBe(2));

    await v.unmount();
    soltar();
    client.clear();
  });

  it("sin el cable, el mismo evento no pide nada: el interruptor no es un placebo", async () => {
    // El control negativo. Sin él, este archivo pasaría igual si `focusManager`
    // refrescara por su cuenta — que es justo lo que NO hace en React Native.
    const a = appStateFalso();
    let veces = 0;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Pantalla() {
      const q = useQuery({
        queryKey: ["mobile-state-sin-cable"],
        queryFn: async () => {
          veces += 1;
          return veces;
        },
      });
      return <Text>{String(q.data ?? "—")}</Text>;
    }
    const v = await render(
      <QueryClientProvider client={client}>
        <Pantalla />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(veces).toBe(1));

    a.emitir("background");
    a.emitir("active");
    await new Promise((r) => setTimeout(r, 60));
    expect(veces).toBe(1);

    await v.unmount();
    client.clear();
  });
});
