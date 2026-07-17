// Pantalla 1.4 · Check-in de vida (spec §7): dos botones GIGANTES con
// transparencia total de qué se enviará. Presentacional puro — la captura de
// GPS, el encolado y el estado derivado viven en la ruta.
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import { whatWillBeSent } from "./payload";

type Busy = "safe" | "need_help" | null;

export function CheckinView(props: {
  zoneName: string | null;
  gpsConsent: boolean;
  busy: Busy;
  onCheckin: (status: "safe" | "need_help") => void;
}) {
  const disabled = props.busy !== null;
  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>SACUDIDA CONCLUIDA · CHECK-IN DE VIDA</Text>
      <Text style={styles.title}>¿Se encuentra bien?</Text>
      <Text style={styles.sub}>
        Su respuesta llega al personal de emergencia del inmueble. Funciona sin señal: se envía
        en cuanto haya red.
      </Text>

      <Pressable
        accessibilityRole="button"
        disabled={disabled}
        onPress={() => props.onCheckin("safe")}
        style={[styles.btn, styles.btnSafe, disabled && styles.dim]}
        testID="btn-safe"
      >
        {props.busy === "safe" ? (
          <ActivityIndicator color={palette.bg} size="large" />
        ) : (
          <Text style={styles.btnSafeText}>ESTOY BIEN</Text>
        )}
        <Text style={styles.btnCaptionDark}>
          {whatWillBeSent({ status: "safe", gpsConsent: props.gpsConsent, zoneName: props.zoneName })}
        </Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        disabled={disabled}
        onPress={() => props.onCheckin("need_help")}
        style={[styles.btn, styles.btnHelp, disabled && styles.dim]}
        testID="btn-need-help"
      >
        {props.busy === "need_help" ? (
          <ActivityIndicator color={palette.fg} size="large" />
        ) : (
          <Text style={styles.btnHelpText}>NECESITO AYUDA</Text>
        )}
        <Text style={styles.btnCaptionLight}>
          {whatWillBeSent({
            status: "need_help",
            gpsConsent: props.gpsConsent,
            zoneName: props.zoneName,
          })}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: palette.bg, padding: space[5], paddingTop: 72, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "700" },
  sub: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  btn: {
    borderRadius: radius.lg,
    paddingVertical: space[5],
    paddingHorizontal: space[4],
    alignItems: "center",
    gap: space[2],
    marginTop: space[2],
  },
  btnSafe: { backgroundColor: palette.ok },
  btnSafeText: { color: palette.bg, fontSize: fontSize.xl, fontWeight: "800", letterSpacing: 1 },
  btnHelp: { backgroundColor: palette.crit },
  btnHelpText: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "800", letterSpacing: 1 },
  btnCaptionDark: { color: palette.bg, fontSize: fontSize.xs, textAlign: "center", opacity: 0.85 },
  btnCaptionLight: { color: palette.fg, fontSize: fontSize.xs, textAlign: "center", opacity: 0.9 },
  dim: { opacity: 0.5 },
});
