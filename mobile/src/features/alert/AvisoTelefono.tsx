// [T-9.13] El teléfono le dice a su dueño, sin rodeos, cuando NO va a sonar como debe.
//
// El alta (0.2 · permisos) ya lo decía, pero sólo una vez: quien pasó el alta antes de
// que faltara algo, o quien lo quitó después en los ajustes, no volvía a verlo. Medido
// en un Pixel con Android 17 (2026-09-30): la ALERTA SÍSMICA llegó MUDA con «No
// molestar» y la app no avisaba de nada. Este aviso vive arriba de INICIO y del PANEL.
//
// Vista PURA: la derivación la hace `deriveAlertability`; la lectura, `useAlertabilidad`.
import { StyleSheet, Text, View } from "react-native";

import type { Alertability, AlertabilityAccion } from "@/services/alertability";
import { Pulsable } from "@/ui/Pulsable";
import { fontSize, palette, radius, space, touch } from "@/ui/theme";

const TEXTO_ACCION: Record<AlertabilityAccion, string> = {
  permitir_no_molestar: "PERMITIR «NO MOLESTAR»",
  abrir_ajustes: "ABRIR AJUSTES",
};

export function AvisoTelefono(props: {
  alertabilidad: Alertability | null;
  onAccion: (accion: AlertabilityAccion) => void;
}) {
  const a = props.alertabilidad;
  // Sin dato todavía no se afirma nada (ni «todo bien» ni «falla»); con el teléfono
  // en orden, no hay nada que decir.
  if (a === null || a.level === "ok") {
    return null;
  }
  const bloqueado = a.level === "blocked";
  const color = bloqueado ? palette.crit : palette.warn;
  const accion = a.accion;
  return (
    <View
      accessibilityRole="alert"
      style={[styles.card, { borderColor: color }]}
      testID={`aviso-telefono-${a.level}`}
    >
      <Text style={[styles.titulo, { color }]}>
        {bloqueado
          ? "ESTE TELÉFONO NO RECIBIRÁ ALERTAS"
          : "LAS ALERTAS DE ESTE TELÉFONO ESTÁN LIMITADAS"}
      </Text>
      {a.reasons.map((r) => (
        <Text key={r} style={styles.motivo}>
          {r}
        </Text>
      ))}
      {accion ? (
        <Pulsable
          accessibilityRole="button"
          onPress={() => props.onAccion(accion)}
          style={[styles.boton, { borderColor: color }]}
          testID="aviso-telefono-accion"
        >
          <Text style={[styles.botonTexto, { color }]}>{TEXTO_ACCION[accion]}</Text>
        </Pulsable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: palette.card,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
    gap: space[2],
  },
  titulo: { fontSize: fontSize.sm, fontWeight: "800", letterSpacing: 1 },
  motivo: { color: palette.fg, fontSize: fontSize.sm, lineHeight: 20 },
  boton: {
    minHeight: touch.min,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[2],
  },
  botonTexto: { fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
});
