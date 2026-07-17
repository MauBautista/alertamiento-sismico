// 1.9 · Pánico del occupant por quórum-de-2. Emergencia NO sísmica del
// inmueble: se necesitan 2 personas distintas en 30 s para activar la sirena.
// El GPS (con consentimiento) se adjunta para el geofence best-effort.
import { panicVoteSitesSiteIdManualActivationVotesPost } from "@takab/sdk";
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { captureLocation } from "@/features/checkin/location";
import { PanicButton } from "@/features/panic/PanicButton";
import {
  PANIC_DISCLAIMER,
  panicStatusFromVote,
  windowRemaining,
  type PanicStatus,
} from "@/features/panic/panicView";
import { getGpsConsent } from "@/services/onboarding";
import { useWatchedSiteId } from "@/services/mySite";
import { fontSize, palette, radius, space } from "@/ui/theme";

const TONE: Record<PanicStatus["tone"], string> = {
  muted: palette.fg3,
  warn: palette.warn,
  crit: palette.crit,
  ok: palette.ok,
};

export default function Panic() {
  const authed = useSessionStore((s) => s.status) === "authenticated";
  const siteId = useWatchedSiteId();
  const [status, setStatus] = useState<PanicStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [votedAt, setVotedAt] = useState<number | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [gpsConsent, setGpsConsent] = useState(false);

  useEffect(() => {
    let alive = true;
    getGpsConsent().then((g) => alive && setGpsConsent(g === true));
    return () => {
      alive = false;
    };
  }, []);

  // Contador de la ventana mientras se espera la 2ª confirmación.
  useEffect(() => {
    if (votedAt === null || status?.phase !== "counted") {
      return;
    }
    const tick = setInterval(() => setRemaining(windowRemaining(votedAt, 30, Date.now())), 1000);
    return () => clearInterval(tick);
  }, [votedAt, status?.phase]);

  if (!authed) {
    return <Redirect href="/" />;
  }
  if (siteId === null) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>Vincúlese a su edificio para usar la alarma de pánico.</Text>
      </View>
    );
  }

  const vote = () => {
    setBusy(true);
    void (async () => {
      const location = gpsConsent ? await captureLocation() : null;
      const res = await panicVoteSitesSiteIdManualActivationVotesPost({
        path: { site_id: siteId },
        body: { location },
      });
      setBusy(false);
      if (res.data) {
        const st = panicStatusFromVote(res.data);
        setStatus(st);
        if (st.phase === "counted") {
          setVotedAt(Date.now());
          setRemaining(res.data.window_s);
        }
      } else {
        setStatus({
          phase: "error",
          title: "NO SE PUDO ENVIAR",
          detail: "Revise su conexión e intente de nuevo.",
          tone: "warn",
        });
      }
    })();
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <Text style={styles.eyebrow}>ALARMA DEL INMUEBLE · NO SÍSMICA</Text>
      <Text style={styles.title}>Solicitar activación de alarma</Text>
      <View style={styles.disclaimer}>
        <Text style={styles.disclaimerText} testID="panic-disclaimer">
          {PANIC_DISCLAIMER}
        </Text>
      </View>

      {status ? (
        <View style={[styles.statusCard, { borderColor: TONE[status.tone] }]}>
          <Text style={[styles.statusTitle, { color: TONE[status.tone] }]} testID="panic-status">
            {status.title}
          </Text>
          <Text style={styles.statusDetail}>{status.detail}</Text>
          {status.phase === "counted" ? (
            <Text style={styles.countdown} testID="panic-countdown">
              Expira en {remaining} s
            </Text>
          ) : null}
        </View>
      ) : null}

      {status?.phase !== "activated" ? (
        <PanicButton
          disabled={busy}
          label={busy ? "ENVIANDO…" : "MANTENGA PRESIONADO PARA CONFIRMAR"}
          onConfirm={vote}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  center: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: space[5],
  },
  eyebrow: { color: palette.crit, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "700" },
  muted: { color: palette.fg3, fontSize: fontSize.sm, textAlign: "center" },
  disclaimer: {
    backgroundColor: palette.card,
    borderColor: palette.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
  },
  disclaimerText: { color: palette.warn, fontSize: fontSize.sm, lineHeight: 20 },
  statusCard: {
    backgroundColor: palette.card,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[1],
  },
  statusTitle: { fontSize: fontSize.lg, fontWeight: "800", letterSpacing: 1 },
  statusDetail: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  countdown: { color: palette.warn, fontSize: fontSize.sm, fontWeight: "700", marginTop: space[1] },
});
