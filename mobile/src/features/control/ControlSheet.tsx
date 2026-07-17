// 2.2 · Control remoto Edge — confirmación en 2 pasos (spec §2.2). Paso 1:
// checklist de precondiciones con estado REAL prellenado (no checkbox ciego).
// Paso 2: deslizar para activar (el nonce se pide al iniciar el deslizamiento).
// El ack se muestra tal cual (ackView) — jamás finge éxito.
import type { CommandOut } from "@takab/sdk";
import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import { ackView } from "./ackState";
import type { TacticalAction } from "./service";

export type Precondition = { label: string; met: boolean; detail: string };

const ACTION_COPY: Record<TacticalAction, { title: string; slide: string; color: string }> = {
  activate: {
    title: "ACTIVACIÓN MANUAL DE SIRENA",
    slide: "DESLICE PARA ACTIVAR",
    color: palette.crit,
  },
  deactivate: {
    title: "RETIRAR MI DEMANDA DE SIRENA",
    slide: "DESLICE PARA SILENCIAR",
    color: palette.warn,
  },
};

const KNOB = 56;

function SlideToConfirm(props: { label: string; color: string; onConfirm: () => void; busy: boolean }) {
  const [width, setWidth] = useState(0);
  // `x` se crea una sola vez (initializer de useState); el responder cierra
  // sobre `width`/`onConfirm` vía deps de useMemo — sin refs durante el render
  // (react-hooks/purity) y sin capturar valores rancios.
  const [x] = useState(() => new Animated.Value(0));
  const onConfirm = props.onConfirm;
  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onPanResponderMove: (_e, g) => {
          const max = Math.max(0, width - KNOB);
          x.setValue(Math.min(max, Math.max(0, g.dx)));
        },
        onPanResponderRelease: (_e, g) => {
          const max = Math.max(0, width - KNOB);
          if (g.dx >= max - 8 && max > 0) {
            onConfirm();
          }
          Animated.spring(x, { toValue: 0, useNativeDriver: false }).start();
        },
      }),
    [width, x, onConfirm],
  );

  return (
    <View
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
      style={[styles.slideTrack, { borderColor: props.color }]}
      testID="slide-track"
    >
      <Text style={styles.slideLabel}>{props.label}</Text>
      <Animated.View
        {...responder.panHandlers}
        style={[styles.knob, { backgroundColor: props.color, transform: [{ translateX: x }] }]}
      >
        {props.busy ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.knobText}>→</Text>}
      </Animated.View>
    </View>
  );
}

export function ControlSheet(props: {
  action: TacticalAction;
  preconditions: Precondition[];
  busy: boolean;
  /** null = aún no se emitió; si existe, se muestra su ack honesto. */
  result: CommandOut | null;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [armed, setArmed] = useState(false);
  const copy = ACTION_COPY[props.action];
  const allMet = props.preconditions.every((p) => p.met);

  if (props.result !== null) {
    const view = ackView(props.result);
    const tone = { ok: palette.ok, warn: palette.warn, crit: palette.crit }[view.tone];
    return (
      <View style={styles.sheet}>
        <Text style={[styles.ackTitle, { color: tone }]} testID="ack-title">
          {view.title}
        </Text>
        <Text style={styles.ackDetail}>{view.detail}</Text>
        <Pressable accessibilityRole="button" onPress={props.onClose} style={styles.closeBtn}>
          <Text style={styles.closeText}>CERRAR</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.sheet}>
      <Text style={styles.title}>{copy.title}</Text>

      {!armed ? (
        <>
          <Text style={styles.step}>PASO 1 · PRECONDICIONES</Text>
          {props.preconditions.map((p) => (
            <View key={p.label} style={styles.preRow} testID={`pre-${p.met ? "ok" : "no"}`}>
              <Text style={[styles.preMark, { color: p.met ? palette.ok : palette.crit }]}>
                {p.met ? "✓" : "✕"}
              </Text>
              <View style={styles.preBody}>
                <Text style={styles.preLabel}>{p.label}</Text>
                <Text style={styles.preDetail}>{p.detail}</Text>
              </View>
            </View>
          ))}
          {!allMet ? (
            <Text style={styles.warnNote} testID="pre-blocked">
              No se cumplen todas las precondiciones. Revise el estado real antes de continuar.
            </Text>
          ) : null}
          <Pressable
            accessibilityRole="button"
            disabled={!allMet}
            onPress={() => setArmed(true)}
            style={[styles.primaryBtn, !allMet && styles.dim]}
            testID="to-step-2"
          >
            <Text style={styles.primaryText}>CONTINUAR</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={props.onClose} style={styles.ghostBtn}>
            <Text style={styles.ghostText}>Cancelar</Text>
          </Pressable>
        </>
      ) : (
        <>
          <Text style={styles.step}>PASO 2 · CONFIRMACIÓN BIOMÉTRICA</Text>
          <Text style={styles.hint}>
            El deslizamiento solicita un nonce al servidor y firma la intención con la llave de
            este dispositivo.
          </Text>
          {props.error ? (
            <Text style={styles.errorNote} testID="control-error">
              {props.error}
            </Text>
          ) : null}
          <SlideToConfirm
            busy={props.busy}
            color={copy.color}
            label={copy.slide}
            onConfirm={props.onConfirm}
          />
          <Pressable accessibilityRole="button" onPress={props.onClose} style={styles.ghostBtn}>
            <Text style={styles.ghostText}>Cancelar</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: palette.card,
    borderColor: palette.borderStrong,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  title: { color: palette.fg, fontSize: fontSize.lg, fontWeight: "800", letterSpacing: 1 },
  step: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2, marginTop: space[1] },
  hint: { color: palette.fg2, fontSize: fontSize.sm },
  preRow: { flexDirection: "row", gap: space[2], alignItems: "flex-start" },
  preMark: { fontSize: fontSize.md, fontWeight: "800", width: 18 },
  preBody: { flex: 1, gap: 2 },
  preLabel: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  preDetail: { color: palette.fg3, fontSize: fontSize.xs },
  warnNote: { color: palette.crit, fontSize: fontSize.xs, marginTop: space[1] },
  errorNote: { color: palette.crit, fontSize: fontSize.sm },
  primaryBtn: {
    marginTop: space[2],
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingVertical: space[3],
    alignItems: "center",
  },
  primaryText: { color: palette.bg, fontWeight: "700", letterSpacing: 1 },
  dim: { opacity: 0.4 },
  ghostBtn: { alignItems: "center", paddingVertical: space[2] },
  ghostText: { color: palette.fg3, fontSize: fontSize.sm },
  slideTrack: {
    height: 64,
    borderRadius: radius.pill,
    borderWidth: 2,
    justifyContent: "center",
    alignItems: "center",
    marginTop: space[2],
    backgroundColor: palette.bg,
    overflow: "hidden",
  },
  slideLabel: { color: palette.fg2, fontSize: fontSize.sm, fontWeight: "700", letterSpacing: 1 },
  knob: {
    position: "absolute",
    left: 4,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
  },
  knobText: { color: palette.bg, fontSize: fontSize.xl, fontWeight: "800" },
  ackTitle: { fontSize: fontSize.lg, fontWeight: "800", letterSpacing: 1 },
  ackDetail: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  closeBtn: {
    marginTop: space[2],
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[3],
    alignItems: "center",
  },
  closeText: { color: palette.fg, fontWeight: "700", letterSpacing: 1 },
});
