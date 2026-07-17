// 1.9 · Botón MANTENER-PRESIONADO para votar el pánico (evita disparos
// accidentales). Al mantener ~1.5 s la barra se llena y confirma el voto.
import { useRef, useState } from "react";
import { Animated, Pressable, StyleSheet, Text } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

const HOLD_MS = 1500;

export function PanicButton(props: { disabled: boolean; label: string; onConfirm: () => void }) {
  const [fill] = useState(() => new Animated.Value(0));
  const anim = useRef<Animated.CompositeAnimation | null>(null);
  const done = useRef(false);

  const start = () => {
    if (props.disabled) {
      return;
    }
    done.current = false;
    fill.setValue(0);
    anim.current = Animated.timing(fill, {
      toValue: 1,
      duration: HOLD_MS,
      useNativeDriver: false,
    });
    anim.current.start(({ finished }) => {
      if (finished && !done.current) {
        done.current = true;
        props.onConfirm();
      }
    });
  };

  const cancel = () => {
    anim.current?.stop();
    Animated.timing(fill, { toValue: 0, duration: 150, useNativeDriver: false }).start();
  };

  const width = fill.interpolate({ inputRange: [0, 1], outputRange: ["0%", "100%"] });

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
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
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
  dim: { opacity: 0.5 },
});
