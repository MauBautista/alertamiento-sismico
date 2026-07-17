// 2.3 · Cámara forense — captura con marca de agua HORNEADA en el pixel.
// Flujo: CameraView toma la foto → se compone con la marca (watermarkLines) en
// un View capturado por view-shot → archivo privado + SHA-256 → registro y
// subida por el PUT presignado. La foto JAMÁS va a la galería del sistema.
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Crypto from "expo-crypto";
import { useRouter } from "expo-router";
import { useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { captureForensicPhoto } from "@/features/forensic/capture";
import { watermarkLines, type ForensicMeta } from "@/features/forensic/watermark";
import { useDamageDraft } from "@/features/damage/draft.store";
import { registerAndUploadEvidence } from "@/services/evidence";
import { useWatchedSiteId } from "@/services/mySite";
import { fontSize, palette, radius, space } from "@/ui/theme";

export default function Camera() {
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { data } = useAlertState(siteId);
  const me = useSessionStore((s) => s.me);
  const addEvidence = useDamageDraft((s) => s.addEvidence);

  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const composeRef = useRef<View>(null);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const incidentId = data?.incident?.incident_id ?? null;
  const meta: ForensicMeta = {
    tsDevice: new Date().toISOString(),
    ntpOffsetMs: null, // el offset del último sync se adjunta en T-2.11
    gps: null, // GPS con consentimiento se integra en el flujo de captura
    pgaG: data?.incident?.max_pga_g ?? null, // null ⇒ "pendiente de sync" honesto
    operatorId: me?.sub ?? "desconocido",
    siteId: siteId ?? "",
  };

  if (!permission) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={palette.cyan} />
      </View>
    );
  }
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.hint}>La cámara forense necesita permiso de cámara.</Text>
        <Pressable accessibilityRole="button" onPress={requestPermission} style={styles.btn}>
          <Text style={styles.btnText}>CONCEDER PERMISO</Text>
        </Pressable>
      </View>
    );
  }
  if (incidentId === null) {
    return (
      <View style={styles.center}>
        <Text style={styles.hint}>Sin incidente activo: no se levanta evidencia forense.</Text>
      </View>
    );
  }

  const take = () => {
    setBusy(true);
    setError(null);
    void (async () => {
      const shot = await cameraRef.current?.takePictureAsync({ quality: 0.9 });
      setBusy(false);
      if (shot?.uri) {
        setPhotoUri(shot.uri);
      } else {
        setError("No se pudo capturar la foto.");
      }
    })();
  };

  const use = () => {
    if (composeRef.current === null) {
      return;
    }
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        const id = Crypto.randomUUID();
        const captured = await captureForensicPhoto(composeRef as never, meta, id);
        const out = await registerAndUploadEvidence({
          incidentId,
          uri: captured.uri,
          sha256: captured.sha256,
        });
        setBusy(false);
        if (out.ok) {
          addEvidence(out.evidenceId);
          router.back();
        } else {
          setError(out.reason);
        }
      } catch {
        setBusy(false);
        setError("No se pudo procesar la evidencia.");
      }
    })();
  };

  if (photoUri === null) {
    return (
      <View style={styles.fill}>
        <CameraView ref={cameraRef} style={styles.fill} />
        <View style={styles.controls}>
          <Pressable accessibilityRole="button" onPress={take} style={styles.shutter}>
            {busy ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.shutterText}>CAPTURAR</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.back()}>
            <Text style={styles.cancel}>Cancelar</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.fill}>
      {/* View COMPUESTO que view-shot captura: la marca queda en el bitmap. */}
      <View collapsable={false} ref={composeRef} style={styles.fill}>
        <CameraView style={styles.fill} />
        <View pointerEvents="none" style={styles.watermark}>
          {watermarkLines(meta).map((line) => (
            <Text key={line} style={styles.watermarkText}>
              {line}
            </Text>
          ))}
        </View>
      </View>
      <View style={styles.controls}>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable accessibilityRole="button" disabled={busy} onPress={use} style={styles.shutter}>
          {busy ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.shutterText}>USAR ESTA FOTO</Text>}
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => setPhotoUri(null)}>
          <Text style={styles.cancel}>Repetir</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: palette.bg },
  center: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center",
    justifyContent: "center",
    gap: space[3],
    padding: space[5],
  },
  hint: { color: palette.fg2, fontSize: fontSize.sm, textAlign: "center" },
  controls: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: space[4],
    gap: space[2],
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.4)",
  },
  shutter: {
    backgroundColor: palette.cyan,
    borderRadius: radius.pill,
    paddingVertical: space[3],
    paddingHorizontal: space[5],
    alignItems: "center",
  },
  shutterText: { color: palette.bg, fontWeight: "800", letterSpacing: 1 },
  cancel: { color: palette.fg2, fontSize: fontSize.sm },
  error: { color: palette.crit, fontSize: fontSize.sm },
  btn: {
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingVertical: space[3],
    paddingHorizontal: space[4],
  },
  btnText: { color: palette.bg, fontWeight: "700", letterSpacing: 1 },
  watermark: {
    position: "absolute",
    left: space[3],
    bottom: space[3],
    backgroundColor: "rgba(0,0,0,0.55)",
    padding: space[2],
    borderRadius: radius.sm,
    gap: 2,
  },
  watermarkText: { color: "#fff", fontSize: fontSize.xs, fontWeight: "600" },
});
