// 1.9 · Botón MANTENER-PRESIONADO para votar el pánico (evita disparos
// accidentales). Al mantener ~1.5 s se confirma el voto.
//
// [T-6.25 · U-22] DOS CAMBIOS DE FONDO.
//
// 1. La confirmación ya NO cuelga del callback de la animación. Una animación
//    no es un reloj —el sistema puede recortarla, y con `reduceMotion` puesto
//    lo correcto es no animar en absoluto—, así que atar a ella el voto de
//    pánico era atar una decisión a la decoración. Ahora manda un temporizador
//    y la barra sólo acompaña.
// 2. El hold tiene PORTADOR TEXTUAL. Era el único estado de la app que vivía
//    sólo en el movimiento: quien tiene la reducción puesta —o simplemente
//    está mirando el edificio y no el teléfono— no tenía forma de saber cuánto
//    faltaba. Ahora cuenta: MANTENGA · 2 · 1 · CONFIRMADO.
import { useCallback, useEffect, useRef, useState } from "react";
import { Animated, Pressable, StyleSheet, Text } from "react-native";

import { fontSize, palette, radius, space, touch } from "@/ui/theme";
import { useReduceMotion } from "@/ui/useReduceMotion";

export const HOLD_MS = 1500;
/** Cadencia del texto. 250 ms basta para que el segundo cambie a tiempo y no
 *  obliga a repintar en cada frame. */
const TICK_MS = 250;

export function PanicButton(props: { disabled: boolean; label: string; onConfirm: () => void }) {
  const reduceMotion = useReduceMotion();
  const [fill] = useState(() => new Animated.Value(0));
  const anim = useRef<Animated.CompositeAnimation | null>(null);
  const reloj = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tic = useRef<ReturnType<typeof setInterval> | null>(null);
  const desde = useRef<number | null>(null);
  const hecho = useRef(false);
  /** ms que faltan, o `null` si no se está manteniendo; `0` = confirmado. */
  const [restante, setRestante] = useState<number | null>(null);

  const parar = useCallback(() => {
    anim.current?.stop();
    if (reloj.current !== null) clearTimeout(reloj.current);
    if (tic.current !== null) clearInterval(tic.current);
    reloj.current = null;
    tic.current = null;
    desde.current = null;
  }, []);

  // Soltar el temporizador al desmontar: un voto de pánico que se dispara con
  // la pantalla ya cerrada sería peor que no dispararse.
  useEffect(() => parar, [parar]);

  const start = () => {
    if (props.disabled) {
      return;
    }
    hecho.current = false;
    desde.current = Date.now();
    setRestante(HOLD_MS);
    fill.setValue(0);
    // La barra sólo acompaña, y con movimiento reducido no se mueve: salta al
    // final y lo que informa es el texto.
    if (reduceMotion) {
      fill.setValue(1);
    } else {
      anim.current = Animated.timing(fill, {
        toValue: 1,
        duration: HOLD_MS,
        useNativeDriver: false,
      });
      anim.current.start();
    }
    tic.current = setInterval(() => {
      if (desde.current === null) return;
      setRestante(Math.max(0, HOLD_MS - (Date.now() - desde.current)));
    }, TICK_MS);
    reloj.current = setTimeout(() => {
      if (hecho.current) return;
      hecho.current = true;
      setRestante(0);
      parar();
      props.onConfirm();
    }, HOLD_MS);
  };

  const cancel = () => {
    if (hecho.current) {
      return;
    }
    parar();
    setRestante(null);
    if (reduceMotion) {
      fill.setValue(0);
    } else {
      Animated.timing(fill, { toValue: 0, duration: 150, useNativeDriver: false }).start();
    }
  };

  const width = fill.interpolate({ inputRange: [0, 1], outputRange: ["0%", "100%"] });
  const cuenta =
    restante === null
      ? null
      : restante === 0
        ? "CONFIRMADO"
        : `MANTENGA · ${Math.ceil(restante / 1000)}`;

  return (
    <Pressable
      accessibilityRole="button"
      disabled={props.disabled}
      onPressIn={start}
      onPressOut={cancel}
      style={[styles.btn, props.disabled && styles.dim]}
      testID="panic-hold"
    >
      <Animated.View style={[styles.fill, { width }]} pointerEvents="none" />
      <Text style={styles.label}>{props.label}</Text>
      {cuenta !== null ? (
        <Text style={styles.cuenta} testID="panic-cuenta">
          {cuenta}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    minHeight: touch.min,
    backgroundColor: palette.card,
    borderColor: palette.crit,
    borderWidth: 2,
    borderRadius: radius.lg,
    paddingVertical: space[5],
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  fill: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: palette.crit,
    opacity: 0.35,
  },
  label: { color: palette.crit, fontSize: fontSize.md, fontWeight: "800", letterSpacing: 1 },
  cuenta: {
    color: palette.crit,
    fontSize: fontSize.xs,
    fontWeight: "700",
    letterSpacing: 2,
    marginTop: space[1],
  },
  dim: { opacity: 0.5 },
});
