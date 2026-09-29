// [T-6.24] Arranque común de jest.
//
// `react-native-safe-area-context` LANZA si nadie montó su `SafeAreaProvider`
// («No safe area value available»), y desde que `@/ui/StateFrame` consulta el
// inset —para que la franja de dato retenido no se dibuje encima del reloj de
// Android— eso alcanzaría a las 115 pruebas que renderizan una pantalla a
// través del marco. Montar el provider en cada una sería ruido repetido en
// sesenta ficheros; la propia librería recomienda simular el módulo en pruebas.
//
// Los valores imitan un teléfono con muesca (el Pixel 8 Pro del banco de
// pruebas): `top: 42` es lo que devuelve de verdad, así que un test que mida
// posiciones mide algo parecido a lo que se ve.
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
  SafeAreaView: ({ children }: { children: React.ReactNode }) => children,
  useSafeAreaInsets: () => ({ top: 42, bottom: 0, left: 0, right: 0 }),
}));

// [T-9.63] El SDK nativo del mapa no carga bajo jest (es un módulo nativo). Cada
// componente se vuelve una `View` que conserva sus props —`coordinates`, `url`,
// `data`, `paint`…—, así las pruebas miden QUÉ se le pide al mapa sin mapa.
jest.mock("@maplibre/maplibre-react-native", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  const componente = (nombre: string) => {
    const Falso = ({
      children,
      ...props
    }: {
      children?: React.ReactNode;
      id?: string;
      testID?: string;
    }) =>
      React.createElement(
        View,
        { ...props, testID: props.testID ?? `maplibre-${nombre}-${props.id ?? ""}` },
        children,
      );
    Falso.displayName = `MapLibre${nombre}`;
    return Falso;
  };
  return {
    Map: componente("Map"),
    Camera: componente("Camera"),
    GeoJSONSource: componente("GeoJSONSource"),
    ImageSource: componente("ImageSource"),
    Layer: componente("Layer"),
  };
});
