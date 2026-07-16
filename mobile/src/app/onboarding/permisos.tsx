// 0.2 · Permisos de alerta (spec §6/§7): el estado degradado es IMPOSIBLE de
// ignorar — "Su teléfono NO recibirá alertas" en rojo. Se re-verifica al
// volver del background (el usuario pudo tocar ajustes del sistema).
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { AppState, Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { deriveAlertability, type PermissionSnapshot } from "@/services/alertability";
import { getPermissionSnapshot, requestPermissions } from "@/services/push";
import { fontSize, palette, radius, space } from "@/ui/theme";

export default function Permisos() {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<PermissionSnapshot | null>(null);

  useEffect(() => {
    let alive = true;
    // setState solo en la continuación async (regla react-hooks v6).
    const load = () => {
      void getPermissionSnapshot().then((s) => {
        if (alive) {
          setSnapshot(s);
        }
      });
    };
    load();
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        load();
      }
    });
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);

  const alertability = snapshot ? deriveAlertability(snapshot) : null;

  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>CONFIGURACIÓN · PASO 1 DE 3</Text>
      <Text style={styles.title}>Permisos de alerta</Text>

      {alertability?.level === "blocked" ? (
        <View style={[styles.banner, { borderColor: palette.crit }]}>
          <Text style={[styles.bannerTitle, { color: palette.crit }]}>
            Su teléfono NO recibirá alertas
          </Text>
          {alertability.reasons.map((r) => (
            <Text key={r} style={styles.bannerBody}>
              {r}
            </Text>
          ))}
        </View>
      ) : null}
      {alertability?.level === "degraded" ? (
        <View style={[styles.banner, { borderColor: palette.warn }]}>
          <Text style={[styles.bannerTitle, { color: palette.warn }]}>Alertas degradadas</Text>
          {alertability.reasons.map((r) => (
            <Text key={r} style={styles.bannerBody}>
              {r}
            </Text>
          ))}
        </View>
      ) : null}
      {alertability?.level === "ok" ? (
        <View style={[styles.banner, { borderColor: palette.ok }]}>
          <Text style={[styles.bannerTitle, { color: palette.ok }]}>
            Su teléfono recibirá alertas
          </Text>
        </View>
      ) : null}

      <View style={styles.actions}>
        {snapshot && !snapshot.granted && snapshot.canAskAgain ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              void (async () => {
                setSnapshot(await requestPermissions());
              })();
            }}
            style={styles.primaryBtn}
          >
            <Text style={styles.primaryBtnText}>PERMITIR NOTIFICACIONES</Text>
          </Pressable>
        ) : null}
        {snapshot && !snapshot.granted && !snapshot.canAskAgain ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => void Linking.openSettings()}
            style={styles.primaryBtn}
          >
            <Text style={styles.primaryBtnText}>ABRIR AJUSTES DEL SISTEMA</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/onboarding/privacidad")}
          style={styles.ghostBtn}
        >
          <Text style={styles.ghostBtnText}>Continuar</Text>
        </Pressable>
      </View>

      <Text style={styles.foot}>
        LA PUSH ES UN DESPERTADOR BEST-EFFORT: LA PROTECCIÓN DE VIDA ES LA SIRENA DEL EDIFICIO.
        ESTE ESTADO SE RE-VERIFICA EN CADA ARRANQUE.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: palette.bg, padding: space[5], paddingTop: 64 },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "600", marginTop: space[1] },
  banner: {
    marginTop: space[4],
    borderWidth: 1,
    borderRadius: radius.lg,
    backgroundColor: palette.card,
    padding: space[4],
    gap: space[2],
  },
  bannerTitle: { fontSize: fontSize.md, fontWeight: "700" },
  bannerBody: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  actions: { marginTop: space[4], gap: space[3] },
  primaryBtn: {
    backgroundColor: palette.cyan,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
  },
  primaryBtnText: { color: palette.bg, fontWeight: "700", letterSpacing: 1 },
  ghostBtn: {
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
  },
  ghostBtnText: { color: palette.fg },
  foot: {
    marginTop: "auto",
    color: palette.fg3,
    fontSize: fontSize.xs,
    textAlign: "center",
    lineHeight: 16,
    letterSpacing: 0.5,
  },
});
