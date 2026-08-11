// 1.9 · Pánico del occupant por quórum-de-2. Emergencia NO sísmica del
// inmueble: se necesitan 2 personas distintas en 30 s para activar la sirena.
// El GPS (con consentimiento) se adjunta para el geofence best-effort.
//
// [T-2.111] `vote()` no capturaba. El cliente del SDK **lanza** cuando `fetch`
// muere —devolver `{data, error}` es sólo para los HTTP de error—, así que con
// la red caída la promesa se rechazaba antes de `setBusy(false)`: el botón se
// quedaba en «ENVIANDO…» para siempre y la pantalla no decía nada. La rama que
// pinta «NO SE PUDO ENVIAR» ya existía; lo que no llegaba a ella era el camino
// del lanzamiento.
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
import { StateFrame } from "@/ui/StateFrame";
import { fontSize, palette, radius, space } from "@/ui/theme";

const TONE: Record<PanicStatus["tone"], string> = {
  muted: palette.fg3,
  warn: palette.warn,
  crit: palette.crit,
  ok: palette.ok,
};

/** El desenlace de un voto que NO salió. Tiene que decir dos cosas: que no se
 *  contó (nadie va a acudir) y qué hacer ahora. */
const VOTO_FALLIDO: PanicStatus = {
  phase: "error",
  title: "NO SE PUDO ENVIAR",
  detail:
    "Su voto NO se registró: nadie ha sido avisado. Revise su conexión y vuelva a mantener presionado. Si la emergencia es inmediata, avise en persona a la brigada.",
  tone: "warn",
};

export default function Panic() {
  const authed = useSessionStore((s) => s.status) === "authenticated";
  const siteId = useWatchedSiteId();
  const [status, setStatus] = useState<PanicStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [votedAt, setVotedAt] = useState<number | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [windowS, setWindowS] = useState(30);
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
    const tick = setInterval(
      () => setRemaining(windowRemaining(votedAt, windowS, Date.now())),
      1000,
    );
    return () => clearInterval(tick);
  }, [votedAt, status?.phase, windowS]);

  if (!authed) {
    return <Redirect href="/" />;
  }

  const vote = () => {
    if (siteId === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      try {
        const location = gpsConsent ? await captureLocation() : null;
        const res = await panicVoteSitesSiteIdManualActivationVotesPost({
          path: { site_id: siteId },
          body: { location },
        });
        if (res.data) {
          const st = panicStatusFromVote(res.data);
          setStatus(st);
          if (st.phase === "counted") {
            setVotedAt(Date.now());
            setRemaining(res.data.window_s);
            setWindowS(res.data.window_s);
          }
        } else {
          setStatus(VOTO_FALLIDO);
        }
      } catch {
        // El SDK LANZA al morir `fetch`. Sin esto, `setBusy(false)` no corría y
        // el botón se quedaba en «ENVIANDO…» sobre un voto que no existe.
        setStatus(VOTO_FALLIDO);
      } finally {
        setBusy(false);
      }
    })();
  };

  // Sin sitio vigilado no hay a quién pedirle la alarma: se declara como estado
  // (`StateFrame`), no como un texto suelto. Los otros tres van cableados a
  // literal a propósito: esta pantalla NO presenta ningún dato del servidor que
  // pueda estar cargando ni envejecer — el desenlace del voto es el acuse de
  // una acción y vive en su tarjeta, no en el marco.
  return (
    <StateFrame
      empty={siteId === null}
      emptyText="Vincúlese a su edificio para usar la alarma de pánico."
      error={null}
      loading={false}
      staleSinceMs={null}
    >
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
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.crit, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { color: palette.fg, fontSize: fontSize.xl, fontWeight: "700" },
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
