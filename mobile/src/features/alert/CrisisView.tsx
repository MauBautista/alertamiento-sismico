// Pantallas 1.2/1.3 — INSTRUCTION-FIRST (§2.1-A, espejo del canvas corregido):
// la instrucción gigante ES la pantalla; abajo el T+ ascendente (dato real) y
// la fuente etiquetada. PROHIBIDO cualquier cronómetro regresivo o magnitud
// preliminar. Presentacional puro: todo entra por props (testeable).
import { StyleSheet, Text, View } from "react-native";

import { emergency, fontSize, palette, radius, space } from "@/ui/theme";

import { ALERT_SOURCE_CARRIES_ETA, formatElapsed } from "./machine";
import type { SourceLabel } from "./source";

export type CrisisPolicy = "evacuate" | "shelter" | null;

export type CrisisViewProps = {
  policy: CrisisPolicy;
  source: SourceLabel;
  elapsedS: number;
  zoneName: string | null;
};

const VARIANTS = {
  evacuate: {
    strip: palette.crit,
    stripText: emergency.red.ink,
    bg: emergency.red.bg,
    instruction: "EVACÚE\nAHORA",
    detail: "Diríjase a su ruta de evacuación.\nNo use elevadores.",
    accent: emergency.red.ink,
  },
  shelter: {
    strip: emergency.amber.strip,
    stripText: emergency.amber.onStrip,
    bg: emergency.amber.bg,
    instruction: "REPLIÉGUESE",
    detail: "Diríjase a su zona de seguridad.\nAléjese de ventanas y cristales.",
    accent: emergency.amber.accent,
  },
  // Sin política de zona definida (o sin zona): la instrucción DEFAULT del MVP
  // — jamás adivinar evacuar/replegar por el teléfono.
  none: {
    strip: palette.crit,
    stripText: emergency.red.ink,
    bg: emergency.red.bg,
    instruction: "PROTÉJASE",
    detail: "Aléjese de ventanas y objetos que puedan caer.\nSiga las indicaciones de su brigada.",
    accent: emergency.red.ink,
  },
} as const;

export function CrisisView({ policy, source, elapsedS, zoneName }: CrisisViewProps) {
  const variant = VARIANTS[policy ?? "none"];
  return (
    <View style={[styles.wrap, { backgroundColor: variant.bg }]}>
      <View style={[styles.strip, { backgroundColor: variant.strip }]}>
        <Text style={[styles.stripEyebrow, { color: variant.stripText }]}>
          {source.eyebrow}
        </Text>
        {/* [T-2.104] Del DATO, no escrito a fuego. Antes ponía siempre «ALERTA
            SÍSMICA SASMEX», así que una detección instrumental propia o una
            activación manual se le atribuían al servicio oficial en el texto más
            grande de la pantalla. La decisión vive en `sourceLabel`, junto a la
            etiqueta de abajo, porque es la misma pregunta: de dónde viene esto. */}
        <Text style={[styles.stripTitle, { color: variant.stripText }]}>{source.title}</Text>
      </View>

      <View style={styles.body}>
        <View style={styles.hero}>
          <Text style={styles.actionEyebrow}>— SU INSTRUCCIÓN —</Text>
          <Text style={[styles.instruction, { color: variant.accent }]}>
            {variant.instruction}
          </Text>
          <Text style={styles.detail}>{variant.detail}</Text>
          {zoneName ? (
            <View style={styles.zonePill}>
              <Text style={styles.zonePillText}>ZONA {zoneName.toUpperCase()}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.elapsed}>
          <Text style={styles.elapsedEyebrow}>TIEMPO TRANSCURRIDO DESDE LA ALERTA</Text>
          <Text style={styles.elapsedValue}>{formatElapsed(elapsedS)}</Text>
          <View style={styles.sourcePill}>
            <Text style={styles.sourceText}>{source.label}</Text>
          </View>
          {source.detail ? <Text style={styles.sourceDetail}>{source.detail}</Text> : null}
          {/* §2.1-A: hueco del ETA — SOLO se activa si una fuente futura
              transporta ETA por dato. Con el flag en false, NADA se renderiza. */}
          {ALERT_SOURCE_CARRIES_ETA ? <View testID="eta-slot" /> : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1 },
  strip: { paddingTop: 56, paddingBottom: space[3], paddingHorizontal: space[4], alignItems: "center" },
  stripEyebrow: { fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 2, opacity: 0.85 },
  stripTitle: { fontSize: 24, fontWeight: "700", letterSpacing: 1, marginTop: space[1] },
  body: { flex: 1, paddingHorizontal: space[5], paddingBottom: 40, paddingTop: space[4] },
  hero: { alignItems: "center", marginTop: space[3] },
  actionEyebrow: {
    color: emergency.red.eyebrow,
    fontSize: 10,
    letterSpacing: 2,
    marginBottom: space[2],
  },
  instruction: {
    fontSize: 64,
    lineHeight: 66,
    fontWeight: "800",
    textAlign: "center",
    letterSpacing: 1,
  },
  detail: {
    color: emergency.red.ink2,
    fontSize: fontSize.sm,
    lineHeight: 20,
    textAlign: "center",
    marginTop: space[3],
  },
  zonePill: {
    marginTop: space[4],
    borderWidth: 1,
    borderColor: emergency.onDark.border,
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  zonePillText: { color: emergency.red.ink1, fontSize: fontSize.xs, letterSpacing: 1.5 },
  elapsed: {
    marginTop: "auto",
    alignItems: "center",
    borderTopWidth: 1,
    borderTopColor: emergency.onDark.surface,
    paddingTop: space[4],
  },
  elapsedEyebrow: {
    color: emergency.red.meta,
    fontSize: 10,
    letterSpacing: 2,
    textAlign: "center",
  },
  elapsedValue: {
    color: emergency.red.ink,
    fontSize: 48,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
    marginTop: space[1],
  },
  sourcePill: {
    marginTop: space[2],
    borderWidth: 1,
    borderColor: emergency.onDark.border,
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  sourceText: { color: emergency.red.ink1, fontSize: 10, letterSpacing: 1.5 },
  sourceDetail: { color: emergency.red.ink3, fontSize: fontSize.xs, marginTop: space[1] },
});
