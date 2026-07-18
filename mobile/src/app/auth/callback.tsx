// Retorno del Hosted UI de Cognito. En iOS el WebBrowser intercepta el redirect
// y el hook (useLogin) completa el intercambio; en ANDROID el deep link
// `takab://auth/callback?code=…&state=…` llega a expo-router como navegación
// (sin esta ruta salía "Unmatched Route"). Aquí validamos el `state` anti-CSRF,
// canjeamos el code con el `code_verifier` guardado y resolvemos la sesión vía
// /me; luego el index (/) reenruta por perfil/onboarding/denegación.
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { type CallbackParams, planCallback } from "@/auth/callback";
import { takePendingAuth } from "@/auth/pendingAuth";
import { exchangeAndResolve } from "@/auth/useAuth";
import { fontSize, palette, radius, space } from "@/ui/theme";

type UiState = { phase: "working" } | { phase: "done" } | { phase: "error"; message: string };

export default function AuthCallback() {
  const params = useLocalSearchParams<CallbackParams>();
  const router = useRouter();
  const [ui, setUi] = useState<UiState>({ phase: "working" });
  const started = useRef(false);

  useEffect(() => {
    if (started.current) {
      return; // el intercambio corre UNA vez (el code es de un solo uso)
    }
    started.current = true;
    void (async () => {
      // Cierra el Custom Tab que quedó detrás del deep link (best-effort).
      try {
        await WebBrowser.dismissBrowser();
      } catch {
        // no había navegador abierto o ya se cerró — no es un fallo
      }
      const plan = planCallback(params, takePendingAuth());
      switch (plan.kind) {
        case "provider_error":
          setUi({ phase: "error", message: plan.message });
          return;
        case "expired":
          setUi({ phase: "error", message: "La sesión de acceso expiró. Vuelva a iniciar sesión." });
          return;
        case "state_mismatch":
          setUi({
            phase: "error",
            message: "No se pudo verificar el origen del acceso. Intente de nuevo.",
          });
          return;
        case "exchange":
          try {
            await exchangeAndResolve(plan.profile, plan.code, plan.codeVerifier);
            setUi({ phase: "done" });
          } catch (err) {
            setUi({ phase: "error", message: err instanceof Error ? err.message : String(err) });
          }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- corre una sola vez al montar
  }, []);

  // El index reenruta por estado de sesión (autenticado/denegado/onboarding).
  if (ui.phase === "done") {
    return <Redirect href="/" />;
  }

  if (ui.phase === "error") {
    return (
      <View style={styles.wrap} testID="auth-callback-error">
        <Text style={styles.title}>NO SE COMPLETÓ EL ACCESO</Text>
        <Text style={styles.message}>{ui.message}</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.replace("/login")}
          style={styles.btn}
        >
          <Text style={styles.btnText}>VOLVER A INICIAR SESIÓN</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.wrap} testID="auth-callback-working">
      <ActivityIndicator color={palette.cyan} size="large" />
      <Text style={styles.message}>Verificando su sesión…</Text>
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
    gap: space[4],
  },
  title: {
    color: palette.fg,
    fontSize: fontSize.md,
    fontWeight: "700",
    letterSpacing: 1.5,
    textAlign: "center",
  },
  message: { color: palette.fg3, fontSize: fontSize.sm, textAlign: "center", lineHeight: 18 },
  btn: {
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    paddingHorizontal: space[5],
  },
  btnText: { color: palette.fg, fontSize: fontSize.base, fontWeight: "600", letterSpacing: 1 },
});
