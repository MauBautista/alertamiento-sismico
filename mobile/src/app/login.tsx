// 0.1 · Login (spec §7). Dos accesos por la decisión #7 (T-2.00):
//   · OCUPANTE → pool simple (sin MFA obligatorio; MFA opt-in desde Cuenta)
//   · PERSONAL OPERATIVO → pool principal (MFA ON, no negociable)
// Ambos: Hosted UI + código + PKCE. Un pool sin config se DECLARA (no se finge).
import { Redirect } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { useLogin } from "@/auth/useAuth";
import { fontSize, palette, radius, space } from "@/ui/theme";

export default function Login() {
  const status = useSessionStore((s) => s.status);
  const occupant = useLogin("occupant");
  const tactical = useLogin("tactical");

  if (status === "authenticated" || status === "denied") {
    return <Redirect href="/" />;
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.brand}>
        <Text style={styles.brandName}>TAKAB AILERT</Text>
        <Text style={styles.brandSub}>ALERTAMIENTO SÍSMICO · CONTINUIDAD OPERATIVA</Text>
      </View>

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          disabled={!occupant.ready}
          onPress={occupant.promptAsync}
          style={[styles.primaryBtn, !occupant.ready && styles.btnDisabled]}
        >
          <Text style={styles.primaryBtnText}>INICIAR SESIÓN</Text>
          <Text style={styles.btnSub}>Ocupante · acceso simple</Text>
        </Pressable>
        {!occupant.configured ? (
          <Text style={styles.configWarn}>
            Pool de ocupantes sin configurar (EXPO_PUBLIC_COGNITO_OCCUPANTS_*) — ver mobile/README.md
          </Text>
        ) : null}

        <Pressable
          accessibilityRole="button"
          disabled={!tactical.ready}
          onPress={tactical.promptAsync}
          style={[styles.ghostBtn, !tactical.ready && styles.btnDisabled]}
        >
          <Text style={styles.ghostBtnText}>Acceso personal operativo</Text>
          <Text style={styles.btnSubGhost}>Brigadista / seguridad / inspección · MFA obligatorio</Text>
        </Pressable>
        {!tactical.configured ? (
          <Text style={styles.configWarn}>
            Pool táctico sin configurar (EXPO_PUBLIC_COGNITO_TACTICAL_*) — ver mobile/README.md
          </Text>
        ) : null}

        {occupant.error ? <Text style={styles.error}>{occupant.error}</Text> : null}
        {tactical.error ? <Text style={styles.error}>{tactical.error}</Text> : null}
      </View>

      <Text style={styles.foot}>
        AWS COGNITO · CÓDIGO + PKCE · SU SESIÓN DE OCUPANTE PERMANECE ACTIVA PARA ALERTAR SIN
        LOGIN EN CRISIS
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: palette.bg,
    padding: space[5],
    justifyContent: "center",
    gap: space[6],
  },
  brand: { alignItems: "center", gap: space[2] },
  brandName: {
    color: palette.fg,
    fontSize: 30,
    fontWeight: "700",
    letterSpacing: 3,
  },
  brandSub: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1.5 },
  actions: { gap: space[3] },
  primaryBtn: {
    backgroundColor: palette.cyan,
    borderRadius: radius.lg,
    paddingVertical: space[4],
    alignItems: "center",
    gap: space[1],
  },
  primaryBtnText: {
    color: palette.bg,
    fontSize: fontSize.md,
    fontWeight: "700",
    letterSpacing: 1.5,
  },
  btnSub: { color: palette.bg, fontSize: fontSize.xs, opacity: 0.8 },
  ghostBtn: {
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
    gap: space[1],
  },
  ghostBtnText: { color: palette.fg, fontSize: fontSize.base, fontWeight: "600" },
  btnSubGhost: { color: palette.fg3, fontSize: fontSize.xs },
  btnDisabled: { opacity: 0.4 },
  configWarn: { color: palette.warn, fontSize: fontSize.xs, lineHeight: 16 },
  error: { color: palette.crit, fontSize: fontSize.sm },
  foot: {
    color: palette.fg3,
    fontSize: fontSize.xs,
    textAlign: "center",
    lineHeight: 16,
    letterSpacing: 0.5,
  },
});
