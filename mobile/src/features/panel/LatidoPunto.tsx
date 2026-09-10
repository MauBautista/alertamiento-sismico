// [T-6.25 · U-22] El punto que late MIENTRAS EL DATO LLEGA.
//
// Latir es afirmar «esto está llegando ahora», así que el latido cuelga de la
// frescura del último frame y no del estado del socket (`livePill.ts`). Es la
// misma regla que T-6.30 dejó escrita en el panel del gabinete —«latir con dato
// retenido es la regla de oro 7 al revés»— y que T-6.10 trajo a la consola.
//
// Y se consulta la preferencia del sistema: con movimiento reducido el punto se
// queda quieto y ENCENDIDO. No desaparece —sería perder el estado— sino que
// deja de moverse; lo que informa es el rótulo del pill, que es el portador.
import { useEffect, useState } from "react";
import { Animated, StyleSheet } from "react-native";

import { motion } from "@/ui/theme";
import { useReduceMotion } from "@/ui/useReduceMotion";

export function LatidoPunto(props: { color: string; late: boolean }) {
  const reduceMotion = useReduceMotion();
  // `useState` con inicializador y no `useRef().current`: leer una ref durante
  // el render lo prohíbe `react-hooks/refs`, y es el mismo idioma que usa
  // `PanicButton` para su barra.
  const [valor] = useState(() => new Animated.Value(1));
  const anima = props.late && !reduceMotion;

  useEffect(() => {
    if (!anima) {
      // Reposo VISIBLE: el punto sigue diciendo el estado con su color.
      valor.setValue(1);
      return undefined;
    }
    const bucle = Animated.loop(
      Animated.sequence([
        Animated.timing(valor, {
          toValue: 0.3,
          duration: motion.pulseMs / 2,
          useNativeDriver: true,
        }),
        Animated.timing(valor, {
          toValue: 1,
          duration: motion.pulseMs / 2,
          useNativeDriver: true,
        }),
      ]),
    );
    bucle.start();
    return () => bucle.stop();
  }, [anima, valor]);

  return (
    <Animated.View
      style={[styles.punto, { backgroundColor: props.color, opacity: valor }]}
      testID={anima ? "live-latido" : "live-punto"}
    />
  );
}

const styles = StyleSheet.create({
  punto: { width: 6, height: 6, borderRadius: 3, marginRight: 6 },
});
