// Pantalla 1.4 · Check-in de vida (spec §7): dos botones GIGANTES con
// transparencia total de qué se enviará. Presentacional puro — la captura de
// GPS, el encolado y el estado derivado viven en la ruta.
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import type { QueueItemState } from "@/offline/queue";
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

/** Estado POSTERIOR al check-in: la verdad de dónde está el dato, sin fingir.
 *  serverConfirmed = el backend ya lo devolvió en /checkins (scope=me). */
export function CheckinStatusView(props: {
  localState: QueueItemState | null;
  serverConfirmed: boolean;
}) {
  const synced = props.serverConfirmed || props.localState === "synced";
  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>CHECK-IN REGISTRADO</Text>
      <View style={[styles.statusCard, synced ? styles.cardOk : styles.cardPending]}>
        <Text style={styles.statusTitle} testID="checkin-status">
          {synced ? "RECIBIDO POR EL SERVIDOR" : "GUARDADO EN ESTE DISPOSITIVO"}
        </Text>
        <Text style={styles.statusBody}>
          {synced
            ? "El personal de emergencia ya cuenta con su estado."
            : "Sin conexión por ahora: se enviará AUTOMÁTICAMENTE en cuanto haya red. No cierre su sesión."}
        </Text>
      </View>
      <Text style={styles.sub}>
        Permanezca en el punto de reunión. El reingreso al inmueble se autoriza únicamente desde
        el centro de mando (recibirá la liberación en esta app).
      </Text>
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
  statusCard: {
    borderRadius: radius.lg,
    borderWidth: 1,
    padding: space[4],
    gap: space[2],
    marginTop: space[3],
  },
  cardOk: { borderColor: palette.ok, backgroundColor: palette.card },
  cardPending: { borderColor: palette.warn, backgroundColor: palette.card },
  statusTitle: { color: palette.fg, fontSize: fontSize.md, fontWeight: "700", letterSpacing: 1 },
  statusBody: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
});
