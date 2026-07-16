// 0.3 · Aviso de privacidad (LFPDPPP): consentimiento GPS EXPLÍCITO y
// revocable. El check-in "necesito ayuda" funciona sin GPS (envía la zona).
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { getGpsConsent, markOnboardingDone, setGpsConsent } from "@/services/onboarding";
import { fontSize, palette, radius, space } from "@/ui/theme";

const BULLETS = [
  "Tratamos su nombre, zona asignada y check-ins de vida como datos de protección civil del inmueble.",
  "Su ubicación GPS solo se envía si usted lo consiente Y solo al pulsar «NECESITO AYUDA».",
  "Los check-ins de un incidente son evidencia: se conservan según la política de evidencia.",
  "Sus datos jamás cruzan a otra organización (aislamiento por cliente).",
];

export default function Privacidad() {
  const router = useRouter();
  const profile = useSessionStore((s) => s.profile);
  const [gps, setGps] = useState(false);

  useEffect(() => {
    void (async () => {
      setGps((await getGpsConsent()) === true);
    })();
  }, []);

  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>CONFIGURACIÓN · PASO 2 DE 3</Text>
      <Text style={styles.title}>Aviso de privacidad</Text>

      <View style={styles.card}>
        {BULLETS.map((b) => (
          <Text key={b} style={styles.bullet}>
            · {b}
          </Text>
        ))}
      </View>

      <View style={styles.consent}>
        <View style={{ flex: 1 }}>
          <Text style={styles.consentTitle}>Compartir GPS en emergencia</Text>
          <Text style={styles.consentSub}>Revocable en Cuenta · sin GPS se envía su zona</Text>
        </View>
        <Switch
          onValueChange={(v) => {
            setGps(v);
            void setGpsConsent(v);
          }}
          thumbColor={gps ? palette.ok : palette.fg3}
          trackColor={{ true: palette.card, false: palette.card }}
          value={gps}
        />
      </View>

      <Pressable
        accessibilityRole="button"
        onPress={() => {
          void (async () => {
            await setGpsConsent(gps);
            if (profile === "occupant") {
              router.push("/onboarding/enrolamiento");
            } else {
              await markOnboardingDone();
              router.replace("/");
            }
          })();
        }}
        style={styles.primaryBtn}
      >
        <Text style={styles.primaryBtnText}>ACEPTAR Y CONTINUAR</Text>
      </Pressable>

      <Text style={styles.foot}>
        EL AVISO COMPLETO LO SIRVE SU ORGANIZACIÓN (LFPDPPP) — SIN LITERALES NORMATIVOS EN LA APP.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: palette.bg, padding: space[5], paddingTop: 64 },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "600", marginTop: space[1] },
  card: {
    marginTop: space[4],
    backgroundColor: palette.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: space[4],
    gap: space[3],
  },
  bullet: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  consent: {
    marginTop: space[4],
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    backgroundColor: palette.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: space[4],
  },
  consentTitle: { color: palette.fg, fontSize: fontSize.base, fontWeight: "500" },
  consentSub: { color: palette.fg3, fontSize: fontSize.xs, marginTop: 2 },
  primaryBtn: {
    marginTop: space[4],
    backgroundColor: palette.cyan,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
  },
  primaryBtnText: { color: palette.bg, fontWeight: "700", letterSpacing: 1 },
  foot: {
    marginTop: "auto",
    color: palette.fg3,
    fontSize: fontSize.xs,
    textAlign: "center",
    lineHeight: 16,
    letterSpacing: 0.5,
  },
});
