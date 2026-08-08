// 0.3 · Aviso de privacidad (T-2.79): el texto lo SIRVE el servidor, versionado
// y sellado por digest, y lo que se registra es QUÉ texto se aceptó y cuándo.
//
// Antes esta pantalla llevaba cuatro viñetas escritas a mano aquí y un pie que
// decía "el aviso completo lo sirve su organización". La persona aceptaba un
// resumen del repositorio de la app y no quedaba constancia de nada. Ahora:
//
// * el cuerpo que se lee es el SERVIDO (párrafos del propio aviso, no un
//   resumen aparte — un resumen que se enseña pero no se sella deja consentir
//   un texto distinto del que se leyó);
// * al aceptar se manda el DIGEST que estaba en pantalla, así que si el aviso
//   cambió entre la lectura y el botón el servidor lo rechaza (409) en vez de
//   apuntar que se aceptó un texto que nadie vio;
// * si el texto es PROVISIONAL, lo dice.
//
// **Y NO BLOQUEA.** Si el servidor no contesta, o no hay aviso publicado, se
// puede continuar igual: el onboarding no puede dejar a un ocupante fuera de la
// app de emergencias por un trámite de cumplimiento (reglas de oro 1 y 2). El
// consentimiento GPS sigue siendo local al dispositivo y revocable: es un
// consentimiento distinto, sobre un dato distinto.
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { getGpsConsent, markOnboardingDone, setGpsConsent } from "@/services/onboarding";
import { decideConsent, fetchConsentStatus, needsConsent } from "@/services/privacy";
import type { ConsentStatus } from "@/services/privacy";
import { StateFrame } from "@/ui/StateFrame";
import { fontSize, palette, radius, space } from "@/ui/theme";

export default function Privacidad() {
  const router = useRouter();
  const profile = useSessionStore((s) => s.profile);
  const [gps, setGps] = useState(false);
  const [status, setStatus] = useState<ConsentStatus | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setStatus(await fetchConsentStatus());
    } catch {
      // "No se pudo preguntar" NO es "no hay aviso": mezclarlos pintaría
      // "nada que aceptar" con la red caída.
      setError("No se pudo consultar el aviso de privacidad.");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      setGps((await getGpsConsent()) === true);
      await cargar();
    })();
  }, [cargar]);

  const continuar = useCallback(async () => {
    await setGpsConsent(gps);
    if (profile === "occupant") {
      router.push("/onboarding/enrolamiento");
    } else {
      await markOnboardingDone();
      router.replace("/");
    }
  }, [gps, profile, router]);

  const aceptarYContinuar = useCallback(async () => {
    const notice = status?.notice ?? null;
    if (notice && needsConsent(status?.state ?? "missing")) {
      setEnviando(true);
      try {
        const ok = await decideConsent("accept", notice.digest);
        if (!ok) {
          // 409: el aviso cambió mientras estaba en pantalla. Se relee y se
          // vuelve a pedir; NO se sigue como si se hubiera aceptado.
          setEnviando(false);
          await cargar();
          setError("El aviso cambió mientras lo leía. Vuelva a leerlo, por favor.");
          return;
        }
      } catch {
        // El registro falló, pero el onboarding NO se detiene: dejar a alguien
        // fuera de la app de emergencias por esto sería el peor intercambio
        // posible. Se reintenta desde Cuenta.
      } finally {
        setEnviando(false);
      }
    }
    await continuar();
  }, [cargar, continuar, status]);

  const notice = status?.notice ?? null;
  const estado = status?.state ?? "missing";
  const yaAceptado = status !== null && !needsConsent(estado);

  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>CONFIGURACIÓN · PASO 2 DE 3</Text>
      <Text style={styles.title}>Aviso de privacidad</Text>

      <View style={styles.frame}>
        <StateFrame
          empty={!cargando && error === null && notice === null}
          emptyText="SU ORGANIZACIÓN NO TIENE AVISO PUBLICADO. PUEDE CONTINUAR."
          error={error}
          loading={cargando}
          staleSinceMs={null}
        >
          {notice && (
            <View style={styles.card} testID="privacy-notice">
              <Text style={styles.noticeTitle}>{notice.title}</Text>
              <Text style={styles.meta}>
                v{notice.version} ·{" "}
                {notice.source === "tenant" ? "de su organización" : "de la plataforma"}
              </Text>
              {notice.provisional && (
                <Text style={styles.provisional}>
                  TEXTO PROVISIONAL · pendiente de revisión jurídica
                </Text>
              )}
              {estado === "stale" && (
                <Text style={styles.cambio} testID="privacy-changed">
                  Este aviso cambió desde que usted lo aceptó. Su consentimiento anterior se
                  conserva tal como lo dio.
                </Text>
              )}
              <ScrollView style={styles.body}>
                {notice.paragraphs.map((p) => (
                  <Text key={p.slice(0, 48)} style={styles.bullet}>
                    {p}
                  </Text>
                ))}
                <Text style={styles.digest}>Sello del texto: {notice.digest.slice(0, 16)}…</Text>
              </ScrollView>
            </View>
          )}
        </StateFrame>
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
        disabled={enviando}
        onPress={() => void aceptarYContinuar()}
        style={styles.primaryBtn}
        testID="privacy-accept"
      >
        <Text style={styles.primaryBtnText}>
          {enviando ? "REGISTRANDO…" : yaAceptado ? "CONTINUAR" : "ACEPTAR Y CONTINUAR"}
        </Text>
      </Pressable>

      <Text style={styles.foot}>
        SU CONSENTIMIENTO QUEDA REGISTRADO CON LA VERSIÓN EXACTA QUE ACEPTÓ. NUNCA BLOQUEA EL
        CHECK-IN DE VIDA NI LA PETICIÓN DE AYUDA.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: palette.bg, padding: space[5], paddingTop: 64 },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "600", marginTop: space[1] },
  frame: { flex: 1, marginTop: space[4] },
  card: {
    flex: 1,
    backgroundColor: palette.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: space[4],
  },
  noticeTitle: { color: palette.fg, fontSize: fontSize.base, fontWeight: "600" },
  meta: { color: palette.fg3, fontSize: fontSize.xs, marginTop: 2 },
  provisional: {
    color: palette.warn ?? palette.fg3,
    fontSize: fontSize.xs,
    letterSpacing: 1,
    marginTop: space[2],
  },
  cambio: { color: palette.fg2, fontSize: fontSize.xs, marginTop: space[2], lineHeight: 18 },
  body: { marginTop: space[3] },
  bullet: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20, marginBottom: space[2] },
  digest: { color: palette.fg3, fontSize: fontSize.xs, marginTop: space[2] },
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
    marginTop: space[3],
    color: palette.fg3,
    fontSize: fontSize.xs,
    textAlign: "center",
    lineHeight: 16,
    letterSpacing: 0.5,
  },
});
