// 1.5 · Bloqueo de reingreso — letrero rojo persistente + línea de tiempo del
// incidente + punto de reunión. Se libera ÚNICAMENTE con reentry_approved del
// backend (la ruta redirige al cambiar la fase); aquí no hay botón de salida.
// Strings NORMATIVOS solo desde compliance_labels (§2.1-C) — vacío = nada.
import type { SiteAssetOut } from "@takab/sdk";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import type { TimelineStep } from "./timeline";

const STEP_COLOR = {
  done: palette.ok,
  current: palette.warn,
  pending: palette.fg3,
} as const;

export function ReentryBlockedView(props: {
  timeline: TimelineStep[];
  assemblyPoint: SiteAssetOut | null;
  complianceLabels: Record<string, string>;
}) {
  const labels = Object.entries(props.complianceLabels);
  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <View style={styles.sign} testID="reentry-sign">
        <Text style={styles.signTitle}>REINGRESO PROHIBIDO</Text>
        <Text style={styles.signSub}>Evaluación estructural en curso</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>LÍNEA DE TIEMPO</Text>
        {props.timeline.map((step) => (
          <View key={step.key} style={styles.stepRow} testID={`step-${step.key}`}>
            <View style={[styles.dot, { backgroundColor: STEP_COLOR[step.state] }]} />
            <View style={styles.stepBody}>
              <Text
                style={[
                  styles.stepLabel,
                  step.state === "pending" ? styles.stepPending : null,
                ]}
              >
                {step.label}
              </Text>
              {step.detail ? <Text style={styles.stepDetail}>{step.detail}</Text> : null}
            </View>
          </View>
        ))}
      </View>

      {props.assemblyPoint ? (
        <View style={styles.card} testID="assembly-point">
          <Text style={styles.cardTitle}>PUNTO DE REUNIÓN</Text>
          <Text style={styles.assemblyTitle}>{props.assemblyPoint.title}</Text>
          {props.assemblyPoint.description ? (
            <Text style={styles.stepDetail}>{props.assemblyPoint.description}</Text>
          ) : null}
        </View>
      ) : null}

      {labels.length > 0 ? (
        <View style={styles.card} testID="compliance-labels">
          {labels.map(([key, value]) => (
            <Text key={key} style={styles.compliance}>
              {value}
            </Text>
          ))}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  sign: {
    backgroundColor: palette.crit,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[1],
  },
  signTitle: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "800", letterSpacing: 2 },
  signSub: { color: palette.fg, fontSize: fontSize.sm, opacity: 0.9 },
  card: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  cardTitle: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  stepRow: { flexDirection: "row", gap: space[2], alignItems: "flex-start" },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 5 },
  stepBody: { flex: 1, gap: 2 },
  stepLabel: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  stepPending: { color: palette.fg3, fontWeight: "400" },
  stepDetail: { color: palette.fg2, fontSize: fontSize.xs },
  assemblyTitle: { color: palette.fg, fontSize: fontSize.md, fontWeight: "700" },
  compliance: { color: palette.fg3, fontSize: fontSize.xs, lineHeight: 16 },
});
