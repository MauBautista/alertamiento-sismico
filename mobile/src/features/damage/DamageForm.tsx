// 2.4 · Formulario rápido de daños — presentacional. Categorías marcables con
// severidad; "personas atrapadas/heridas" resalta como PRIORIDAD MÁXIMA (el
// backend la convierte en notificación inmediata al SOC). Evidencias de 2.3
// ligadas por conteo.
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import {
  DAMAGE_CATEGORIES,
  isUrgent,
  SEVERITIES,
  type DamageKey,
  type SelectedCategory,
  type Severity,
} from "./categories";

const SEV_COLOR: Record<Severity, string> = {
  low: palette.fg3,
  medium: palette.cyan,
  high: palette.warn,
  critical: palette.crit,
};

export function DamageForm(props: {
  selected: Map<DamageKey, Severity>;
  notes: string;
  evidenceCount: number;
  busy: boolean;
  onToggle: (key: DamageKey) => void;
  onSeverity: (key: DamageKey, sev: Severity) => void;
  onNotes: (t: string) => void;
  onAddPhoto: () => void;
  onSubmit: () => void;
}) {
  const chosen: SelectedCategory[] = [...props.selected.entries()].map(([key, severity]) => ({
    key,
    severity,
  }));
  const urgent = isUrgent(chosen);
  const canSubmit = chosen.length > 0 && !props.busy;

  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <Text style={styles.eyebrow}>REPORTE RÁPIDO DE DAÑOS</Text>

      {urgent ? (
        <View style={styles.urgentBanner} testID="urgent-banner">
          <Text style={styles.urgentText}>
            PERSONAS EN RIESGO · PRIORIDAD MÁXIMA — el SOC será notificado de inmediato al enviar.
          </Text>
        </View>
      ) : null}

      {DAMAGE_CATEGORIES.map((cat) => {
        const sev = props.selected.get(cat.key);
        const on = sev !== undefined;
        const danger = cat.key === "people_trapped";
        return (
          <View
            key={cat.key}
            style={[styles.catCard, on && styles.catOn, on && danger && styles.catDanger]}
            testID={`cat-${cat.key}`}
          >
            <Pressable
              accessibilityRole="button"
              onPress={() => props.onToggle(cat.key)}
              style={styles.catHead}
            >
              <Text style={[styles.catMark, { color: on ? palette.ok : palette.fg3 }]}>
                {on ? "✓" : "○"}
              </Text>
              <Text style={[styles.catLabel, danger && styles.catLabelDanger]}>{cat.label}</Text>
            </Pressable>
            {on ? (
              <View style={styles.sevRow}>
                {SEVERITIES.map((s) => (
                  <Pressable
                    accessibilityRole="button"
                    key={s}
                    onPress={() => props.onSeverity(cat.key, s)}
                    style={[
                      styles.sevChip,
                      sev === s && { borderColor: SEV_COLOR[s], backgroundColor: palette.raised },
                    ]}
                    testID={`sev-${cat.key}-${s}`}
                  >
                    <Text style={[styles.sevText, sev === s && { color: SEV_COLOR[s] }]}>
                      {s.toUpperCase()}
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </View>
        );
      })}

      <TextInput
        multiline
        onChangeText={props.onNotes}
        placeholder="Notas (opcional)"
        placeholderTextColor={palette.fg3}
        style={styles.notes}
        testID="damage-notes"
        value={props.notes}
      />

      <Pressable
        accessibilityRole="button"
        onPress={props.onAddPhoto}
        style={styles.photoBtn}
        testID="add-photo"
      >
        <Text style={styles.photoText}>
          CÁMARA FORENSE{props.evidenceCount > 0 ? ` · ${props.evidenceCount} foto(s)` : ""}
        </Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        disabled={!canSubmit}
        onPress={props.onSubmit}
        style={[styles.submitBtn, urgent && styles.submitUrgent, !canSubmit && styles.dim]}
        testID="submit-damage"
      >
        <Text style={styles.submitText}>{props.busy ? "ENVIANDO…" : "ENVIAR REPORTE"}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[2] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  urgentBanner: {
    backgroundColor: palette.crit,
    borderRadius: radius.md,
    padding: space[3],
  },
  urgentText: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "800", letterSpacing: 1 },
  catCard: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[3],
    gap: space[2],
  },
  catOn: { borderColor: palette.borderStrong },
  catDanger: { borderColor: palette.crit },
  catHead: { flexDirection: "row", alignItems: "center", gap: space[2] },
  catMark: { fontSize: fontSize.md, fontWeight: "800", width: 20 },
  catLabel: { color: palette.fg, fontSize: fontSize.md, fontWeight: "600", flex: 1 },
  catLabelDanger: { color: palette.crit },
  sevRow: { flexDirection: "row", gap: space[1], flexWrap: "wrap" },
  sevChip: {
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space[2],
    paddingVertical: 2,
  },
  sevText: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  notes: {
    backgroundColor: palette.card,
    borderColor: palette.borderStrong,
    borderWidth: 1,
    borderRadius: radius.md,
    color: palette.fg,
    padding: space[3],
    minHeight: 64,
    fontSize: fontSize.sm,
    marginTop: space[1],
  },
  photoBtn: {
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[3],
    alignItems: "center",
  },
  photoText: { color: palette.cyan, fontWeight: "700", fontSize: fontSize.sm, letterSpacing: 1 },
  submitBtn: {
    marginTop: space[2],
    backgroundColor: palette.cyan,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
  },
  submitUrgent: { backgroundColor: palette.crit },
  submitText: { color: palette.bg, fontWeight: "800", letterSpacing: 1 },
  dim: { opacity: 0.4 },
});
