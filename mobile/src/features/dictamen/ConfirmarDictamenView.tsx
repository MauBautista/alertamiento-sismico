// [T-9.33 · D-43] CONFIRMAR DICTAMEN — presentacional. Explica la banda y POR QUÉ
// (la procedencia que dejó la regla en `basis`), una lista de revisión corta y
// dos botones grandes: CONFIRMAR y ESCALAR AL INSPECTOR. No decide nada: qué se
// ofrece lo derivan `confirmacionView` (desde la cabeza) y el servidor (permisos).
//
// No es una alarma: la piel es la de trabajo (no la de emergencia a pantalla
// completa) y la banda se lee por su color y, sobre todo, por su texto.
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { Pulsable } from "@/ui/Pulsable";
import { fontSize, palette, radius, space, touch } from "@/ui/theme";

import type { Banda, ConfirmacionView } from "./confirmacion";
import { envioVigente, type Envio } from "./useConfirmarDictamen";

const COLOR_BANDA: Record<Banda, string> = {
  verde: palette.ok,
  amarillo: palette.warn,
  rojo: palette.crit,
};

export type ConfirmarDictamenViewProps = {
  vista: Exclude<ConfirmacionView, { tipo: "sin_dictamen" }>;
  confirmacion: Envio;
  escalado: Envio;
  onConfirmar: () => void;
  /** `null` ⇒ el servidor no concede `request_dictamen`: no se pinta el botón. */
  onEscalar: (() => void) | null;
};

/** [F3·r3] Un 409 que reintentar no arregla: «requiere inspector» (daño ROJO
 *  reportado) o el VERDE que firma el sistema. */
function noSeReintenta(e: Envio): boolean {
  return e.requiereInspector === true || e.loFirmaElSistema === true;
}

function textoConfirmar(e: Envio): string {
  if (e.estado === "enviando") return "CONFIRMANDO…";
  if (e.estado === "hecho") return "DICTAMEN CONFIRMADO";
  if (e.requiereInspector === true) return "NO SE CONFIRMA · ESCALE AL INSPECTOR";
  if (e.loFirmaElSistema === true) return "NO SE CONFIRMA · LO EMITE EL SISTEMA";
  if (e.estado === "error") return "REINTENTAR CONFIRMACIÓN";
  return "CONFIRMAR DICTAMEN";
}

function textoEscalar(e: Envio["estado"]): string {
  if (e === "enviando") return "ESCALANDO…";
  if (e === "hecho") return "ESCALADO AL INSPECTOR";
  if (e === "error") return "REINTENTAR ESCALAR";
  return "ESCALAR AL INSPECTOR";
}

export function ConfirmarDictamenView({
  vista,
  confirmacion: envio,
  escalado,
  onConfirmar,
  onEscalar,
}: ConfirmarDictamenViewProps) {
  const color = COLOR_BANDA[vista.banda];
  // [F3·r3] El resultado de un envío vale para SU dictamen: con otra cabeza
  // confirmable se vuelve a ofrecer (defensa además de la del hook).
  const confirmacion =
    vista.tipo === "confirmable" ? envioVigente(envio, vista.dictamenId) : envio;
  const confirmarTerminal =
    confirmacion.estado === "enviando" ||
    confirmacion.estado === "hecho" ||
    noSeReintenta(confirmacion);
  const escalarTerminal = escalado.estado === "enviando" || escalado.estado === "hecho";

  return (
    <ScrollView contentContainerStyle={styles.body} style={styles.wrap}>
      <View style={[styles.banda, { borderColor: color }]} testID="confirmar-banda">
        <Text style={[styles.bandaEyebrow, { color }]}>DICTAMEN AUTOMÁTICO</Text>
        <Text accessibilityRole="header" style={styles.bandaTitulo}>
          {vista.titulo}
        </Text>
      </View>

      {vista.tipo === "ya_firmado" ? (
        <View style={styles.bloque} testID="confirmar-firmado">
          <Text style={styles.eyebrow}>YA NO HAY NADA QUE CONFIRMAR</Text>
          <Text style={styles.texto}>El dictamen vigente ya está firmado.</Text>
          <Text style={styles.sello}>{vista.firmante}</Text>
        </View>
      ) : (
        <>
          <View style={styles.bloque} testID="confirmar-porque">
            <Text style={styles.eyebrow}>POR QUÉ ESTA BANDA</Text>
            {vista.porque.map((p) => (
              <Text key={p} style={styles.item}>
                • {p}
              </Text>
            ))}
          </View>

          {vista.tipo === "confirmable" ? (
            <View style={styles.bloque} testID="confirmar-revision">
              <Text style={styles.eyebrow}>ANTES DE CONFIRMAR, REVISE</Text>
              {vista.revision.map((r, i) => (
                <Text key={r} style={styles.item}>
                  {i + 1}. {r}
                </Text>
              ))}
            </View>
          ) : vista.tipo === "lo_firma_el_sistema" ? (
            <View style={styles.bloque} testID="confirmar-lo-firma-el-sistema">
              <Text style={styles.texto}>
                Un dictamen verde no se confirma desde la brigada: lo emite el sistema cuando
                termina la espera sin daños reportados. Si encuentra daño, repórtelo o escálelo
                al inspector.
              </Text>
            </View>
          ) : (
            <View style={styles.bloque} testID="confirmar-solo-inspector">
              <Text style={styles.texto}>
                {vista.banda === "rojo"
                  ? "Un dictamen en rojo no se confirma desde la brigada: lo firma el inspector."
                  : "Este dictamen no salió de la regla automática: no se confirma desde la brigada, lo firma el inspector."}
              </Text>
            </View>
          )}

          {vista.tipo === "confirmable" ? (
            <View style={styles.accion}>
              <Pulsable
                accessibilityRole="button"
                accessibilityState={{ disabled: confirmarTerminal, busy: confirmacion.estado === "enviando" }}
                disabled={confirmarTerminal}
                onPress={onConfirmar}
                style={[styles.boton, { backgroundColor: color }]}
                testID="confirmar-dictamen"
              >
                {confirmacion.estado === "enviando" ? (
                  <ActivityIndicator color={palette.bg} />
                ) : null}
                <Text style={styles.botonTexto}>{textoConfirmar(confirmacion)}</Text>
              </Pulsable>
              {confirmacion.mensaje !== null ? (
                <Text
                  style={confirmacion.estado === "error" ? styles.error : styles.ok}
                  testID="confirmar-mensaje"
                >
                  {confirmacion.mensaje}
                </Text>
              ) : null}
            </View>
          ) : null}

          <View style={styles.accion}>
            {onEscalar !== null ? (
              <>
                <Pulsable
                  accessibilityRole="button"
                  accessibilityState={{ disabled: escalarTerminal, busy: escalado.estado === "enviando" }}
                  disabled={escalarTerminal}
                  onPress={onEscalar}
                  style={styles.botonSecundario}
                  testID="escalar-inspector"
                >
                  <Text style={styles.botonSecundarioTexto}>{textoEscalar(escalado.estado)}</Text>
                </Pulsable>
                {escalado.mensaje !== null ? (
                  <Text
                    style={escalado.estado === "error" ? styles.error : styles.ok}
                    testID="escalar-mensaje"
                  >
                    {escalado.mensaje}
                  </Text>
                ) : null}
              </>
            ) : (
              <Text style={styles.texto} testID="escalar-sin-permiso">
                Si no puede confirmarlo, avise a la administración del inmueble para que lo
                solicite al inspector.
              </Text>
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: palette.bg },
  body: { paddingHorizontal: space[5], paddingTop: 56, paddingBottom: 40, gap: space[4] },
  banda: {
    borderWidth: 2,
    borderRadius: radius.lg,
    padding: space[4],
    backgroundColor: palette.card,
    alignItems: "center",
  },
  bandaEyebrow: { fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1.5 },
  bandaTitulo: {
    color: palette.fg,
    fontSize: fontSize.xl,
    fontWeight: "800",
    textAlign: "center",
    marginTop: space[2],
  },
  bloque: {
    backgroundColor: palette.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: palette.border,
    padding: space[4],
    gap: space[2],
  },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1.2 },
  texto: { color: palette.fg2, fontSize: fontSize.base, lineHeight: 22 },
  item: { color: palette.fg, fontSize: fontSize.base, lineHeight: 22 },
  sello: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "700", letterSpacing: 1 },
  accion: { gap: space[2] },
  boton: {
    minHeight: touch.min * 1.5,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: space[2],
    paddingHorizontal: space[4],
  },
  botonTexto: { color: palette.bg, fontSize: fontSize.lg, fontWeight: "800", letterSpacing: 1 },
  botonSecundario: {
    minHeight: touch.min * 1.5,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: palette.cyan,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space[4],
  },
  botonSecundarioTexto: {
    color: palette.cyan,
    fontSize: fontSize.lg,
    fontWeight: "800",
    letterSpacing: 1,
  },
  error: { color: palette.crit, fontSize: fontSize.sm },
  ok: { color: palette.ok, fontSize: fontSize.sm },
});
