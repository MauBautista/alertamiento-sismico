// [T-8.11 · A-062] EL TOQUE SE VE.
//
// Medido al auditar para la presentación: 57 `<Pressable>` y ni un solo
// `pressed` ni `android_ripple` en toda la app. `Pressable` NO trae respuesta
// visual de serie, así que cada toque parecía ignorado hasta que llegaba la
// respuesta del servidor — y con la red de una sala de demostración eso son
// segundos en los que el cliente vuelve a pulsar.
//
// Qué se afirma aquí:
//   · al pulsar baja la OPACIDAD y hay onda de Android del color del tema: es
//     instantáneo, no es movimiento, y se da siempre;
//   · la ESCALA sutil sí es movimiento: solo si el sistema NO pide reducirlo;
//   · lo que el llamador ya declaró (su `opacity` de atenuado, su `transform`)
//     no se pisa — la respuesta es RELATIVA a su estilo.
import { act, fireEvent, render } from "@testing-library/react-native";
import { AccessibilityInfo, Platform, processColor, Text } from "react-native";

import { tokens } from "@takab/design-tokens";

import { estiloAlPulsar, Pulsable, reiniciarMovimientoParaTests, toque } from "./Pulsable";

/** El evento que RN entrega al conceder el responder (forma medida por RNTL). */
function toqueDeResponder() {
  return {
    currentTarget: { measure: () => undefined },
    target: {},
    preventDefault: () => undefined,
    isDefaultPrevented: () => false,
    stopPropagation: () => undefined,
    isPropagationStopped: () => false,
    persist: () => undefined,
    isPersistent: () => false,
    timeStamp: 0,
    nativeEvent: {
      changedTouches: [],
      identifier: 0,
      locationX: 0,
      locationY: 0,
      pageX: 0,
      pageY: 0,
      target: 0,
      timestamp: Date.now(),
      touches: [],
    },
  };
}

type Estilo = { opacity?: number; transform?: Record<string, number>[] } | null | undefined;

/** El estilo APLANADO que el host está pintando ahora mismo. */
function pintado(el: { props: { style?: unknown } }): { opacity?: number; transform?: Record<string, number>[] } {
  const aplanar = (s: unknown): Record<string, unknown> =>
    Array.isArray(s) ? Object.assign({}, ...s.map(aplanar)) : ((s ?? {}) as Record<string, unknown>);
  return aplanar(el.props.style) as { opacity?: number; transform?: Record<string, number>[] };
}

const reduceMotion = AccessibilityInfo.isReduceMotionEnabled as jest.Mock;

beforeEach(() => {
  reiniciarMovimientoParaTests();
  reduceMotion.mockImplementation(() => Promise.resolve(false));
});

describe("Pulsable · la regla pura", () => {
  it("sin pulsar no toca el estilo del llamador", () => {
    const base = { minHeight: 48 };
    const out = estiloAlPulsar(base, false, false) as Estilo[];
    expect(out).toEqual([base, null]);
  });

  it("pulsado: baja la opacidad y encoge un poco (movimiento permitido)", () => {
    const out = estiloAlPulsar({ minHeight: 48 }, true, false) as Estilo[];
    expect(out[1]?.opacity).toBe(toque.opacidad);
    expect(out[1]?.transform).toEqual([{ scale: toque.escala }]);
    expect(toque.opacidad).toBeLessThan(1);
    expect(toque.escala).toBeLessThan(1);
    // «Sutil» es una cota, no un adjetivo: más de un 5 % se lee como animación.
    expect(toque.escala).toBeGreaterThanOrEqual(0.95);
  });

  it("pulsado con movimiento REDUCIDO: la opacidad sí, la escala NO", () => {
    const out = estiloAlPulsar({ minHeight: 48 }, true, true) as Estilo[];
    expect(out[1]?.opacity).toBe(toque.opacidad);
    expect(out[1]?.transform).toBeUndefined();
  });

  it("es relativa: un botón atenuado se atenúa MÁS, no se aclara", () => {
    const out = estiloAlPulsar([{ minHeight: 48 }, { opacity: 0.5 }], true, true) as Estilo[];
    expect(out[1]?.opacity).toBeCloseTo(0.5 * toque.opacidad);
  });

  it("no pisa el `transform` que el llamador ya declaró", () => {
    const out = estiloAlPulsar({ transform: [{ translateX: 4 }] }, true, false) as Estilo[];
    expect(out[1]?.transform).toEqual([{ translateX: 4 }, { scale: toque.escala }]);
  });

  it("la onda es el cian del tema, salido del paquete de tokens", () => {
    expect(toque.ripple).toBe(tokens.color.cyan.a15);
  });
});

describe("Pulsable · montado, responde al dedo", () => {
  async function montar(onPress = jest.fn()) {
    const v = await render(
      <Pulsable accessibilityRole="button" onPress={onPress} style={{ minHeight: 48 }} testID="b">
        <Text>OK</Text>
      </Pulsable>,
    );
    // El sistema contesta la preferencia de movimiento de forma asíncrona.
    await act(async () => {});
    return v;
  }

  it("en reposo no está atenuado; al pulsar SÍ; al soltar vuelve y dispara onPress", async () => {
    const onPress = jest.fn();
    const v = await montar(onPress);
    const host = v.getByTestId("b");
    expect(pintado(host).opacity).toBeUndefined();

    await act(async () => {
      fireEvent(host, "responderGrant", toqueDeResponder());
    });
    expect(pintado(v.getByTestId("b")).opacity).toBe(toque.opacidad);
    expect(pintado(v.getByTestId("b")).transform).toEqual([{ scale: toque.escala }]);

    await act(async () => {
      fireEvent(v.getByTestId("b"), "responderRelease", toqueDeResponder());
    });
    // Pressability retiene el «pulsado» un mínimo de 130 ms antes de soltarlo.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });
    expect(pintado(v.getByTestId("b")).opacity).toBeUndefined();
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("con movimiento reducido en el sistema, pulsar NO escala", async () => {
    reduceMotion.mockImplementation(() => Promise.resolve(true));
    const v = await montar();

    await act(async () => {
      fireEvent(v.getByTestId("b"), "responderGrant", toqueDeResponder());
    });
    expect(pintado(v.getByTestId("b")).opacity).toBe(toque.opacidad);
    expect(pintado(v.getByTestId("b")).transform).toBeUndefined();
  });

  it("una sola suscripción a la preferencia, por muchos botones que haya", async () => {
    const alta = AccessibilityInfo.addEventListener as jest.Mock;
    const antes = alta.mock.calls.filter((c) => c[0] === "reduceMotionChanged").length;
    await render(
      <>
        {Array.from({ length: 30 }, (_, i) => (
          <Pulsable key={i} onPress={() => undefined} style={{ minHeight: 48 }}>
            <Text>{i}</Text>
          </Pulsable>
        ))}
      </>,
    );
    await act(async () => {});
    const despues = alta.mock.calls.filter((c) => c[0] === "reduceMotionChanged").length;
    // Un pase de lista de 200 personas son 400 botones: 400 consultas al puente
    // nativo al montar la pantalla no son gratis.
    expect(despues - antes).toBe(1);
  });

  it("en Android lleva la onda nativa con el color del tema", async () => {
    const so = jest.replaceProperty(Platform, "OS", "android");
    try {
      const v = await montar();
      const fondo = (v.getByTestId("b").props as { nativeBackgroundAndroid?: { color: unknown } })
        .nativeBackgroundAndroid;
      expect(fondo?.color).toBe(processColor(toque.ripple));
    } finally {
      so.restore();
    }
  });
});
