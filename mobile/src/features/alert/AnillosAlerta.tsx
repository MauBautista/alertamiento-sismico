// [T-9.73 · D-47, que enmienda D-30] Anillos concéntricos de la alerta que
// AUTORIZA evacuar (SASMEX o cuórum de red).
//
// Los límites de D-30, uno por uno:
//   1. El texto NO se mueve. Este fichero no pinta ni un `Text`: son vistas
//      aparte, montadas DETRÁS de la instrucción, que sólo cambian `opacity` y
//      `transform: scale`.
//   2. Se para por ESTADO. Quien monta esto es `CrisisView`, y sólo mientras
//      `viva` (la fase del servidor es `alert_active`) y `autoriza`. Desmontar
//      detiene los bucles en la limpieza del efecto; no hay cronómetro propio.
//   3. «Reducir movimiento» ⇒ UN anillo fijo, puesto: deja de moverse, no de
//      leerse.
//
// `Animated` de React Native y no Reanimated: es lo que ya usa el halo de la
// misma pantalla y lo que fija la guarda de §5.4 en
// `CrisisView.primerFrame.test.tsx`. Con `useNativeDriver`, `opacity` y
// `transform` los mueve el compositor sin pasar por el hilo de JS, que es el
// que consulta el estado de la alerta.
import { useEffect, useState } from "react";
import { Animated, Easing, StyleSheet, View } from "react-native";

import { motion } from "@/ui/theme";

/** Tres anillos desfasados un tercio de período: siempre hay uno naciendo. */
const N_ANILLOS = 3;
/** Un anillo tarda dos períodos del halo en expandirse: mismo ritmo, más lento. */
const PERIODO_MS = motion.alertaMs * 2;
/** Diámetro en reposo (dp). Escalado ×1.8 cubre el ancho de la instrucción. */
const DIAMETRO = 200;
const ESCALA_INICIO = 0.3;
const ESCALA_FIN = 1.8;
const OPACIDAD_INICIO = 0.55;
/** Opacidad del anillo FIJO con «reducir movimiento». */
const OPACIDAD_FIJA = 0.35;

export type AnillosAlertaProps = {
  color: string;
  reduceMotion: boolean;
};

export function AnillosAlerta({ color, reduceMotion }: AnillosAlertaProps) {
  const [fases] = useState(() =>
    Array.from({ length: N_ANILLOS }, () => new Animated.Value(0)),
  );

  useEffect(() => {
    if (reduceMotion) {
      return undefined;
    }
    const bucles = fases.map((v) =>
      Animated.loop(
        Animated.timing(v, {
          toValue: 1,
          duration: PERIODO_MS,
          easing: Easing.out(Easing.quad),
          useNativeDriver: true,
        }),
      ),
    );
    const todo = Animated.stagger(PERIODO_MS / N_ANILLOS, bucles);
    todo.start();
    return () => {
      todo.stop();
      for (const v of fases) {
        v.setValue(0);
      }
    };
  }, [fases, reduceMotion]);

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={styles.capa}
      testID="crisis-anillos"
    >
      {reduceMotion ? (
        <View
          style={[styles.anillo, { borderColor: color, opacity: OPACIDAD_FIJA }]}
          testID="crisis-anillo-fijo"
        />
      ) : (
        fases.map((v, i) => (
          <Animated.View
            // El orden de los anillos es fijo: el índice ES su identidad.
            key={i}
            style={[
              styles.anillo,
              {
                borderColor: color,
                opacity: v.interpolate({
                  inputRange: [0, 1],
                  outputRange: [OPACIDAD_INICIO, 0],
                }),
                transform: [
                  {
                    scale: v.interpolate({
                      inputRange: [0, 1],
                      outputRange: [ESCALA_INICIO, ESCALA_FIN],
                    }),
                  },
                ],
              },
            ]}
            testID={`crisis-anillo-${i}`}
          />
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // Llena el contenedor del texto y centra los anillos sobre él. Va PRIMERO en
  // el árbol, así que todo lo que se lee se pinta encima.
  capa: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: "center",
    justifyContent: "center",
  },
  anillo: {
    position: "absolute",
    width: DIAMETRO,
    height: DIAMETRO,
    borderRadius: DIAMETRO / 2,
    borderWidth: 3,
  },
});
