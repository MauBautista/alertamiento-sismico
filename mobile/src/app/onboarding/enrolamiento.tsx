// 0.4 · Enrolamiento por código de sitio (spec §7): consume
// POST /me/enrollment (site_enrollment_codes → user_zone_assignments, R2).
// Un código vencido/agotado/ajeno devuelve el MISMO 404 — la UI lo declara.
//
// [T-2.79.c] La salida de esta pantalla se rotula POR LO QUE HACE. Antes decía
// «Ya estoy vinculado · continuar»: a quien la nube dejaba tirado se le ofrecía
// una salida cuyo texto AFIRMA algo sobre él que el sistema no puede saber —y
// que para la mayoría era falso—, en estilo de opción descartable y pegada a
// «Sin conexión con el servidor». Quien lee que no está vinculado no la pulsa,
// se queda en el paso 3 de 3 y no llega nunca al check-in de vida ni al botón
// de pánico (reglas de oro 1 y 2).
//
// El equilibrio importa en las dos direcciones: esto NO es un atajo para
// saltarse el enrolamiento. Con red y con código, lo que se ofrece es VINCULAR;
// la salida solo se DESTACA cuando el fallo es de la nube —no del usuario— y
// siempre dice qué se pierde al usarla. Por eso se distingue el fallo del
// servidor del código inválido: culpar al código de un 503 manda a la persona a
// pedir un código nuevo que no arregla nada.
import { enrollMeEnrollmentPost, type EnrollmentOut } from "@takab/sdk";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { setWatchedSite } from "@/services/mySite";
import { markOnboardingDone } from "@/services/onboarding";
import { fontSize, palette, radius, space } from "@/ui/theme";

/** Quién falló: el código que trajo la persona, o la nube. */
type Fallo = "codigo" | "servidor" | null;

const MENSAJE: Record<"codigo" | "servidor", string> = {
  codigo: "Código inválido, vencido o agotado. Pida uno nuevo a su administrador.",
  servidor: "Sin conexión con el servidor. Reintente, o siga adelante y vincúlelo más tarde.",
};

export default function Enrolamiento() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [fallo, setFallo] = useState<Fallo>(null);
  const [result, setResult] = useState<EnrollmentOut | null>(null);

  const submit = () => {
    setBusy(true);
    setFallo(null);
    void (async () => {
      try {
        const res = await enrollMeEnrollmentPost({ body: { code: code.trim() } });
        if (res.data) {
          // El sitio enrolado es el que este dispositivo VIGILA (mobile-state).
          // [T-2.109] Y también el inmueble del token de push: `setWatchedSite`
          // publica en el store observable de T-2.103, y el efecto de
          // `app/_layout.tsx` re-registra el token con este sitio sin que haya
          // que reinstalar ni reiniciar sesión. No se llama aquí a
          // `registerDeviceForPush` a propósito: un solo punto de registro en
          // toda la app es lo que hace imposible que uno de ellos se quede atrás.
          await setWatchedSite(String(res.data.site_id));
          setResult(res.data);
        } else {
          // 4xx = el código (404 cubre vencido/agotado/ajeno). Todo lo demás
          // —5xx, 408, 429, respuesta sin estado— es la nube, y no se le
          // reprocha a quien trajo el papelito.
          const status = res.response?.status ?? 0;
          const delCodigo = status >= 400 && status < 500 && status !== 408 && status !== 429;
          setFallo(delCodigo ? "codigo" : "servidor");
        }
      } catch {
        setFallo("servidor");
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

  // La salida solo se DESTACA cuando el que falló fue el servidor: ahí es la
  // app la que le debe una salida a la persona, no al revés.
  const salidaDestacada = fallo === "servidor";

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
          {fallo ? <Text style={styles.error}>{MENSAJE[fallo]}</Text> : null}
          <Pressable
            accessibilityRole="button"
            disabled={busy || code.trim().length < 4}
            onPress={submit}
            style={[styles.primaryBtn, (busy || code.trim().length < 4) && styles.disabled]}
            testID="enrolamiento-vincular"
          >
            {busy ? (
              <ActivityIndicator color={palette.bg} />
            ) : (
              <Text style={styles.primaryBtnText}>VINCULAR</Text>
            )}
          </Pressable>

          <View
            style={salidaDestacada ? styles.salidaCard : styles.salida}
            testID={salidaDestacada ? "enrolamiento-salida-destacada" : "enrolamiento-salida"}
          >
            <Pressable
              accessibilityRole="button"
              onPress={finish}
              style={salidaDestacada ? styles.salidaBtn : styles.ghostBtn}
              testID="enrolamiento-continuar-sin-vincular"
            >
              <Text style={salidaDestacada ? styles.salidaBtnText : styles.ghostBtnText}>
                {salidaDestacada ? "CONTINUAR SIN VINCULAR" : "Continuar sin vincular"}
              </Text>
            </Pressable>
            {/* Qué se pierde al salir por aquí: continuar a ciegas también es
                una forma de mentir. */}
            <Text style={styles.salidaCosto} testID="enrolamiento-salida-costo">
              Sin edificio vinculado no hay sitio vigilado: no recibirá el check-in de vida por
              zona ni el estado de su edificio. Puede vincularlo después desde Cuenta.
            </Text>
          </View>
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
  salida: { marginTop: space[3], gap: space[2] },
  salidaCard: {
    marginTop: space[4],
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.lg,
    backgroundColor: palette.card,
    padding: space[4],
    gap: space[2],
  },
  ghostBtn: { alignItems: "center", paddingVertical: space[2] },
  ghostBtnText: { color: palette.fg3, fontSize: fontSize.sm },
  salidaBtn: {
    borderWidth: 1,
    borderColor: palette.cyan,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
  },
  salidaBtnText: { color: palette.cyan, fontWeight: "700", letterSpacing: 1 },
  salidaCosto: { color: palette.fg3, fontSize: fontSize.xs, lineHeight: 16, textAlign: "center" },
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
