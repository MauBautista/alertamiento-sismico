// Acceso denegado — el default-deny se DECLARA (spec §8): el rol/superficie
// que respondió /me no tiene superficie móvil.
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { GateDenyReason } from "@/auth/profileGate";
import { useSessionStore } from "@/auth/session.store";
import { fontSize, palette, radius, space } from "@/ui/theme";

const REASON_TEXT: Record<GateDenyReason, string> = {
  no_session: "No hay sesión activa.",
  wrong_surface:
    "Su cuenta no tiene superficie móvil asignada (custom:surface). Pida al administrador de su organización que la habilite.",
  role_not_mobile:
    "Su rol opera desde la consola web, no desde la app móvil (RBAC §3). Si cree que es un error, contacte a su administrador.",
};

export default function Denied() {
  const reason = useSessionStore((s) => s.deniedReason);
  const signOut = useSessionStore((s) => s.signOut);

  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.eyebrow}>ACCESO DENEGADO</Text>
        <Text style={styles.text}>{REASON_TEXT[reason ?? "no_session"]}</Text>
        <Pressable accessibilityRole="button" onPress={signOut} style={styles.btn}>
          <Text style={styles.btnText}>VOLVER AL INICIO DE SESIÓN</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: space[5],
  },
  card: {
    width: "100%",
    backgroundColor: palette.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.crit,
    padding: space[5],
    gap: space[4],
  },
  eyebrow: { color: palette.crit, fontSize: fontSize.xs, letterSpacing: 2, fontWeight: "700" },
  text: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  btn: {
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.md,
    paddingVertical: space[3],
    alignItems: "center",
  },
  btnText: { color: palette.fg, fontSize: fontSize.sm, letterSpacing: 1 },
});
