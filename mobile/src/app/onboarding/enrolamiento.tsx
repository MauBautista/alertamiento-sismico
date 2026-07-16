// 0.4 · Enrolamiento por código de sitio (spec §7): consume
// POST /me/enrollment (site_enrollment_codes → user_zone_assignments, R2).
// Un código vencido/agotado/ajeno devuelve el MISMO 404 — la UI lo declara.
import { enrollMeEnrollmentPost, type EnrollmentOut } from "@takab/sdk";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { setWatchedSite } from "@/services/mySite";
import { markOnboardingDone } from "@/services/onboarding";
import { fontSize, palette, radius, space } from "@/ui/theme";

export default function Enrolamiento() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EnrollmentOut | null>(null);

  const submit = () => {
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        const res = await enrollMeEnrollmentPost({ body: { code: code.trim() } });
        if (res.data) {
          // El sitio enrolado es el que este dispositivo VIGILA (mobile-state).
          await setWatchedSite(String(res.data.site_id));
          setResult(res.data);
        } else {
          setError("Código inválido, vencido o agotado. Pida uno nuevo a su administrador.");
        }
      } catch {
        setError("Sin conexión con el servidor. Intente de nuevo.");
      } finally {
        setBusy(false);
      }
    })();
  };

  const finish = () => {
    void (async () => {
      await markOnboardingDone();
      router.replace("/");
    })();
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>CONFIGURACIÓN · PASO 3 DE 3</Text>
      <Text style={styles.title}>Vincular a su edificio</Text>
      <Text style={styles.sub}>Ingrese el código que le entregó el administrador del inmueble.</Text>

      {result === null ? (
        <>
          <TextInput
            autoCapitalize="characters"
            autoCorrect={false}
            editable={!busy}
            onChangeText={setCode}
            placeholder="CÓDIGO-DE-SITIO"
            placeholderTextColor={palette.fg3}
            style={styles.input}
            value={code}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable
            accessibilityRole="button"
            disabled={busy || code.trim().length < 4}
            onPress={submit}
            style={[styles.primaryBtn, (busy || code.trim().length < 4) && styles.disabled]}
          >
            {busy ? (
              <ActivityIndicator color={palette.bg} />
            ) : (
              <Text style={styles.primaryBtnText}>VINCULAR</Text>
            )}
          </Pressable>
          <Pressable accessibilityRole="button" onPress={finish} style={styles.ghostBtn}>
            <Text style={styles.ghostBtnText}>Ya estoy vinculado · continuar</Text>
          </Pressable>
        </>
      ) : (
        <>
          <View style={styles.okCard}>
            <Text style={styles.okTitle}>Vinculado a {result.site_name}</Text>
            <Text style={styles.okBody}>
              Zona: {result.zone_name ?? "sin zona asignada"}
              {result.evac_policy ? ` · política: ${result.evac_policy}` : ""}
            </Text>
          </View>
          <Pressable accessibilityRole="button" onPress={finish} style={styles.primaryBtn}>
            <Text style={styles.primaryBtnText}>TERMINAR</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: palette.bg, padding: space[5], paddingTop: 64 },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "600", marginTop: space[1] },
  sub: { color: palette.fg3, fontSize: fontSize.sm, marginTop: space[1] },
  input: {
    marginTop: space[4],
    backgroundColor: palette.card,
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.lg,
    color: palette.fg,
    fontSize: fontSize.lg,
    letterSpacing: 2,
    paddingHorizontal: space[4],
    paddingVertical: space[3],
    textAlign: "center",
  },
  error: { color: palette.crit, fontSize: fontSize.sm, marginTop: space[2] },
  primaryBtn: {
    marginTop: space[4],
    backgroundColor: palette.cyan,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
  },
  primaryBtnText: { color: palette.bg, fontWeight: "700", letterSpacing: 1 },
  ghostBtn: { marginTop: space[3], alignItems: "center", paddingVertical: space[2] },
  ghostBtnText: { color: palette.fg3, fontSize: fontSize.sm },
  disabled: { opacity: 0.4 },
  okCard: {
    marginTop: space[4],
    borderWidth: 1,
    borderColor: palette.ok,
    borderRadius: radius.lg,
    backgroundColor: palette.card,
    padding: space[4],
    gap: space[2],
  },
  okTitle: { color: palette.fg, fontSize: fontSize.md, fontWeight: "600" },
  okBody: { color: palette.fg2, fontSize: fontSize.sm },
});
