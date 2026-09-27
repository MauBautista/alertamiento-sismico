// [T-9.11 · D-39] MOVIMIENTO EN EL INMUEBLE — el sensor PROPIO detectó movimiento.
//
// Lo recibe SOLO la brigada (roles con `movement_alert`; la nube filtra y el
// `CrisisWatcher` no enruta nunca al ocupante). Una estación sola NO ordena
// evacuar (T-2.32): esto es un aviso para ir a VERIFICAR, no una alerta sísmica
// oficial, y la pantalla lo dice en el mismo bloque que el titular — la lección
// de T-2.104 es que el texto grande manda.
//
// Presentacional pura, todo por props (patrón de `BuildingAlarmView`): quién
// puede acusar o reportar lo decide la ruta con `allowed_actions`, no esta vista.
// Sin animación que mueva texto, y sin el T+ de la toma sísmica: prestárselo la
// haría leerse como un sismo oficial en curso.
import { type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Pulsable } from "@/ui/Pulsable";
import { timeAgoLabel } from "@/ui/timeAgo";
import { emergency, fontSize, palette, radius, space, touch } from "@/ui/theme";

/** «hace 5 min» desde la apertura del incidente. Fecha ilegible ⇒ «—»: a una
 *  persona no se le enseña un «Invalid Date» ni se le inventa una hora. */
export function haceCuanto(iso: string, nowMs: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return "—";
  }
  return timeAgoLabel(t, nowMs);
}

/** PGA en g con tres decimales, o `null` si el dato no viene: sin dato no se
 *  pinta cifra ninguna (§2.1-A, no se inventan datos). */
export function etiquetaPga(g: number | null | undefined): string | null {
  if (g === null || g === undefined || !Number.isFinite(g)) {
    return null;
  }
  return `${g.toFixed(3)} g`;
}

export const TEXTO_MOVIMIENTO =
  "Se detectó un movimiento en el inmueble. No es una alerta sísmica oficial: verifique el inmueble y reporte daños.";

export type MovementViewProps = {
  /** Apertura del incidente, ya formateada (`haceCuanto`). */
  abiertoLabel: string;
  /** PGA ya formateada (`etiquetaPga`), o `null` si el incidente no la trae. */
  pgaLabel: string | null;
  /** `null` ⇒ sin `damage_report_submit`: el botón no se pinta. Server-driven. */
  onReportarDanos: (() => void) | null;
  /** Hueco para el acuse táctico (`TacticalAckButton`). */
  slotAcuse?: ReactNode;
  /** No `null` ⇒ hay ALARMA DEL INMUEBLE activa a la vez que el movimiento (la
   *  nube manda `building_alarm` también en esta fase): se pinta un bloque
   *  destacado con el botón que la abre. Sin él, un pánico quedaba oculto. */
  onAbrirAlarma?: (() => void) | null;
};

export function MovementView({
  abiertoLabel,
  pgaLabel,
  onReportarDanos,
  slotAcuse,
  onAbrirAlarma = null,
}: MovementViewProps) {
  return (
    <View style={styles.wrap}>
      <View style={styles.strip}>
        <Text style={styles.stripEyebrow}>SENSOR DEL INMUEBLE · NO ES ALERTA OFICIAL</Text>
      </View>

      <View style={styles.body}>
        {onAbrirAlarma !== null ? (
          <View style={styles.alarma} testID="movimiento-alarma-bloque">
            <Text accessibilityRole="header" style={styles.alarmaTitulo}>
              ALARMA DEL INMUEBLE ACTIVA
            </Text>
            <Text style={styles.alarmaTexto}>
              Además del movimiento, una persona activó la sirena de este edificio.
            </Text>
            <Pulsable
              accessibilityRole="button"
              onPress={onAbrirAlarma}
              style={styles.alarmaBoton}
              testID="movimiento-alarma"
            >
              <Text style={styles.alarmaBotonTexto}>VER LA ALARMA</Text>
            </Pulsable>
          </View>
        ) : null}

        <View style={styles.hero}>
          <Text accessibilityRole="header" style={styles.title}>
            MOVIMIENTO EN EL INMUEBLE
          </Text>
          <Text style={styles.detail}>{TEXTO_MOVIMIENTO}</Text>
        </View>

        <View style={styles.datos}>
          <View style={styles.dato}>
            <Text style={styles.datoEyebrow}>DETECTADO</Text>
            <Text style={styles.datoValor}>{abiertoLabel}</Text>
          </View>
          {pgaLabel !== null ? (
            <View style={styles.dato} testID="movimiento-pga">
              <Text style={styles.datoEyebrow}>ACELERACIÓN MÁX. (PGA)</Text>
              <Text style={styles.datoValor}>{pgaLabel}</Text>
            </View>
          ) : null}
        </View>

        {onReportarDanos !== null ? (
          <Pulsable
            accessibilityRole="button"
            onPress={onReportarDanos}
            style={styles.reportar}
            testID="movimiento-reportar"
          >
            <Text style={styles.reportarTexto}>REPORTAR DAÑOS</Text>
          </Pulsable>
        ) : null}

        {slotAcuse ? <View style={styles.acuse}>{slotAcuse}</View> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: emergency.amber.bg },
  strip: {
    backgroundColor: emergency.amber.strip,
    paddingTop: 56,
    paddingBottom: space[3],
    paddingHorizontal: space[4],
    alignItems: "center",
  },
  stripEyebrow: {
    color: emergency.amber.onStrip,
    fontSize: fontSize.xs,
    fontWeight: "700",
    letterSpacing: 1.5,
    textAlign: "center",
  },
  body: { flex: 1, paddingHorizontal: space[5], paddingBottom: 40, paddingTop: space[4] },
  hero: { alignItems: "center", marginTop: space[3] },
  title: {
    color: emergency.amber.accent,
    fontSize: 36,
    lineHeight: 42,
    fontWeight: "800",
    textAlign: "center",
    letterSpacing: 1,
  },
  detail: {
    color: emergency.amber.ink2,
    fontSize: fontSize.base,
    lineHeight: 22,
    textAlign: "center",
    marginTop: space[3],
  },
  datos: {
    flexDirection: "row",
    justifyContent: "center",
    gap: space[5],
    marginTop: space[5],
    borderTopWidth: 1,
    borderTopColor: emergency.onDark.surface,
    paddingTop: space[4],
  },
  dato: { alignItems: "center" },
  datoEyebrow: { color: emergency.amber.meta, fontSize: 10, letterSpacing: 2 },
  datoValor: {
    color: palette.fg,
    fontSize: fontSize.xl,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
    marginTop: space[1],
  },
  reportar: {
    marginTop: "auto",
    backgroundColor: emergency.amber.accent,
    borderRadius: radius.md,
    minHeight: touch.min,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: space[4],
  },
  reportarTexto: {
    color: emergency.amber.onStrip,
    fontSize: 20,
    fontWeight: "800",
    letterSpacing: 1,
  },
  acuse: { marginTop: space[4] },
  // La piel de la cabecera de `BuildingAlarmView` (franja ámbar sólida): la
  // brigada la reconoce como LA alarma del inmueble, y resalta sobre el ámbar
  // oscuro del movimiento. Nada de rojo: el rojo es de la alerta sísmica.
  alarma: {
    backgroundColor: emergency.amber.strip,
    borderRadius: radius.md,
    padding: space[4],
    marginBottom: space[3],
  },
  alarmaTitulo: {
    color: emergency.amber.onStrip,
    fontSize: fontSize.xl,
    fontWeight: "800",
    letterSpacing: 1,
    textAlign: "center",
  },
  alarmaTexto: {
    color: emergency.amber.onStrip,
    fontSize: fontSize.base,
    lineHeight: 22,
    textAlign: "center",
    marginTop: space[2],
  },
  alarmaBoton: {
    marginTop: space[3],
    backgroundColor: emergency.amber.onStrip,
    borderRadius: radius.md,
    minHeight: touch.min,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: space[3],
  },
  alarmaBotonTexto: {
    color: emergency.amber.strip,
    fontSize: fontSize.lg,
    fontWeight: "800",
    letterSpacing: 1,
  },
});
