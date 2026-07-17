// 2.7 · Certificado de reingreso — presentacional. Folio, firmante, vigencia y
// sello "FIRMA DIGITAL · INSPECTOR". El PDF (mismo artefacto de la consola) se
// descarga y cachea offline; sin PDF aún, se declara (no se finge).
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import type { CertificateView } from "./dictamenView";

export function DictamenCertificate(props: {
  cert: CertificateView;
  downloading: boolean;
  pdfCached: boolean;
  onDownloadPdf: () => void;
  onOpenPdf: () => void;
}) {
  const accent = props.cert.habitable ? palette.ok : palette.warn;
  return (
    <View style={styles.wrap}>
      <View style={[styles.card, { borderColor: accent }]} testID="certificate">
        <Text style={styles.eyebrow}>DICTAMEN TÉCNICO DE REINGRESO</Text>
        <Text style={[styles.title, { color: accent }]}>{props.cert.title}</Text>

        <View style={styles.row}>
          <Field label="FOLIO" value={props.cert.folio} />
          <Field label="FIRMANTE" value={props.cert.signer} />
        </View>
        <Field label="FIRMADO" value={props.cert.signedAt} />

        <View style={styles.seal}>
          <Text style={styles.sealText}>{props.cert.seal}</Text>
        </View>
      </View>

      {props.cert.hasPdf ? (
        props.pdfCached ? (
          <Pressable
            accessibilityRole="button"
            onPress={props.onOpenPdf}
            style={styles.pdfBtn}
            testID="open-pdf"
          >
            <Text style={styles.pdfText}>ABRIR CERTIFICADO (PDF) · DISPONIBLE OFFLINE</Text>
          </Pressable>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={props.downloading}
            onPress={props.onDownloadPdf}
            style={[styles.pdfBtn, props.downloading && styles.dim]}
            testID="download-pdf"
          >
            {props.downloading ? (
              <ActivityIndicator color={palette.cyan} />
            ) : (
              <Text style={styles.pdfText}>DESCARGAR CERTIFICADO (PDF)</Text>
            )}
          </Pressable>
        )
      ) : (
        <Text style={styles.noPdf} testID="no-pdf">
          El certificado en PDF aún no está disponible. Su reingreso ya está autorizado por la
          firma del inspector.
        </Text>
      )}
    </View>
  );
}

function Field(props: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{props.label}</Text>
      <Text style={styles.fieldValue}>{props.value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  card: {
    backgroundColor: palette.card,
    borderWidth: 2,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  title: { fontSize: fontSize.lg, fontWeight: "800", letterSpacing: 1 },
  row: { flexDirection: "row", gap: space[4] },
  field: { gap: 2 },
  fieldLabel: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  fieldValue: { color: palette.fg, fontSize: fontSize.md, fontWeight: "600" },
  seal: {
    alignSelf: "flex-start",
    borderColor: palette.borderStrong,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: 3,
    marginTop: space[2],
  },
  sealText: { color: palette.fg2, fontSize: fontSize.xs, letterSpacing: 1, fontWeight: "700" },
  pdfBtn: {
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[3],
    alignItems: "center",
  },
  pdfText: { color: palette.cyan, fontWeight: "700", fontSize: fontSize.sm, letterSpacing: 1 },
  noPdf: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  dim: { opacity: 0.5 },
});
