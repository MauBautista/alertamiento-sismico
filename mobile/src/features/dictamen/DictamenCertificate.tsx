// 2.7 · Certificado de reingreso — presentacional. Folio, firmante, vigencia y
// sello del tipo de firma (T-9.33). El PDF (mismo artefacto de la consola) se
// descarga y cachea offline; sin PDF aún, se declara (no se finge).
//
// [T-9.33 · D-49] Con el inmueble BLOQUEADO (por otro evento, o sin la calma), lo
// grande es el bloqueo y el veredicto de este dictamen pasa a ser un dato más: la
// persona lee la grande, y «REINGRESO APROBADO» no puede serlo si no se puede
// entrar.
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { Pulsable } from "@/ui/Pulsable";
import { fontSize, palette, radius, space, touch } from "@/ui/theme";

import type { BloqueoDelInmueble, CertificateView } from "./dictamenView";

export function DictamenCertificate(props: {
  cert: CertificateView;
  /** Lo que el servidor dice del INMUEBLE ahora; `null` si no hay bloqueo. */
  bloqueo?: BloqueoDelInmueble | null;
  downloading: boolean;
  /** Motivo de la última descarga fallida; `null` si no la hubo. */
  downloadError?: string | null;
  pdfCached: boolean;
  onDownloadPdf: () => void;
  onOpenPdf: () => void;
}) {
  const bloqueo = props.bloqueo ?? null;
  const accent =
    bloqueo !== null
      ? bloqueo.tono === "crit"
        ? palette.crit
        : palette.warn
      : props.cert.habitable
        ? palette.ok
        : palette.warn;
  return (
    <View style={styles.wrap}>
      <View style={[styles.card, { borderColor: accent }]} testID="certificate">
        <Text style={styles.eyebrow}>DICTAMEN TÉCNICO DE REINGRESO</Text>
        {bloqueo !== null ? (
          <View accessibilityRole="alert" style={styles.bloqueo} testID="certificado-bloqueo">
            <Text style={[styles.title, { color: accent }]}>{bloqueo.titulo}</Text>
            <Text style={styles.bloqueoDetalle}>{bloqueo.detalle}</Text>
          </View>
        ) : (
          <Text style={[styles.title, { color: accent }]}>{props.cert.title}</Text>
        )}
        {bloqueo !== null ? (
          <View style={styles.row}>
            <Field label="ESTE DICTAMEN" value={props.cert.title} />
          </View>
        ) : null}

        <View style={styles.row}>
          <Field label="FOLIO" value={props.cert.folio} />
          <Field label="FIRMANTE" value={props.cert.signer} />
        </View>
        <View style={styles.row}>
          <Field label="FIRMADO" value={props.cert.signedAt} />
          {props.cert.band !== null ? <Field label="BANDA" value={props.cert.band} /> : null}
        </View>

        <View style={styles.seal}>
          <Text style={styles.sealText}>{props.cert.seal}</Text>
        </View>
      </View>

      {props.cert.hasPdf ? (
        props.pdfCached ? (
          <Pulsable
            accessibilityRole="button"
            onPress={props.onOpenPdf}
            style={styles.pdfBtn}
            testID="open-pdf"
          >
            <Text style={styles.pdfText}>ABRIR CERTIFICADO (PDF) · DISPONIBLE OFFLINE</Text>
          </Pulsable>
        ) : (
          <Pulsable
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
          </Pulsable>
        )
      ) : (
        <Text style={styles.noPdf} testID="no-pdf">
          {props.cert.habitable && bloqueo === null
            ? "El certificado en PDF aún no está disponible. Su reingreso ya está autorizado por la firma de este dictamen."
            : "El certificado en PDF aún no está disponible."}
        </Text>
      )}
      {props.downloadError ? (
        <Text style={styles.downloadError} testID="download-error" accessibilityRole="alert">
          {props.downloadError}
        </Text>
      ) : null}
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
  bloqueo: { gap: space[1] },
  bloqueoDetalle: { color: palette.fg, fontSize: fontSize.sm, lineHeight: 20 },
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
  downloadError: { color: palette.crit, fontSize: fontSize.sm },
  sealText: { color: palette.fg2, fontSize: fontSize.xs, letterSpacing: 1, fontWeight: "700" },
  pdfBtn: {
    minHeight: touch.min,
    justifyContent: "center",
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
