// Pantallas 1.2/1.3 — INSTRUCTION-FIRST (§2.1-A, espejo del canvas corregido):
// la instrucción gigante ES la pantalla; abajo el T+ ascendente (dato real) y
// la fuente etiquetada. PROHIBIDO cualquier cronómetro regresivo o magnitud
// preliminar. Presentacional puro: todo entra por props (testeable).
import { useEffect, useState } from "react";
import { Animated, Pressable, StyleSheet, Text, View } from "react-native";

import { emergency, fontSize, motion, palette, radius, space } from "@/ui/theme";

import { ALERT_SOURCE_CARRIES_ETA, formatElapsed } from "./machine";
import type { SourceLabel } from "./source";

export type CrisisPolicy = "evacuate" | "shelter" | null;

export type CrisisViewProps = {
  policy: CrisisPolicy;
  source: SourceLabel;
  elapsedS: number;
  zoneName: string | null;
  /** [T-7.29] Salida de la toma — SOLO para el perfil táctico.
   *
   * Ausente (el caso del ocupante) no se pinta nada: de una evacuación no se
   * sale con el dedo. Presente, pinta el único control de esta pantalla. El
   * brigadista es quien tiene que abrir TRIAGE, la lista o el directorio
   * MIENTRAS la alerta sigue viva, y durante el ensayo del 2026-09-12 su
   * teléfono le enseñaba «PROTÉJASE» y nada más. */
  onSalir?: (() => void) | null;
  /**
   * [T-7.19 · D-30] ¿El SERVIDOR todavía sostiene esta alerta?
   *
   * Es la condición 3 de la decisión: el halo se detiene POR ESTADO, nunca por
   * un cronómetro del teléfono. Hoy la ruta de crisis redirige en cuanto la fase
   * deja de ser `alert_active`, así que parecería que basta con eso — pero un
   * componente presentacional cuya animación dependa de una garantía de
   * enrutado se rompe en silencio el día que alguien lo monte en otro sitio (la
   * franja de alerta viva del brigadista, por ejemplo). Entra por prop, y las
   * pruebas fijan las dos direcciones.
   */
  viva: boolean;
  /**
   * Preferencia de movimiento reducido del sistema. Entra por PROP porque esta
   * vista es presentacional: el hook vive en la ruta, como en `SiteNotices`.
   */
  reduceMotion?: boolean;
};

/** Opacidad del anillo en reposo — la que se queda puesta sin animación. */
const HALO_REPOSO = 0.28;
/** Opacidad en el pico del latido. */
const HALO_PICO = 0.85;

const VARIANTS = {
  evacuate: {
    strip: palette.crit,
    stripText: emergency.red.ink,
    bg: emergency.red.bg,
    instruction: "EVACÚE\nAHORA",
    detail: "Diríjase a su ruta de evacuación.\nNo use elevadores.",
    accent: emergency.red.ink,
  },
  shelter: {
    strip: emergency.amber.strip,
    stripText: emergency.amber.onStrip,
    bg: emergency.amber.bg,
    instruction: "REPLIÉGUESE",
    detail: "Diríjase a su zona de seguridad.\nAléjese de ventanas y cristales.",
    accent: emergency.amber.accent,
  },
  // Sin política de zona definida (o sin zona): la instrucción DEFAULT del MVP
  // — jamás adivinar evacuar/replegar por el teléfono.
  none: {
    strip: palette.crit,
    stripText: emergency.red.ink,
    bg: emergency.red.bg,
    instruction: "PROTÉJASE",
    detail: "Aléjese de ventanas y objetos que puedan caer.\nSiga las indicaciones de su brigada.",
    accent: emergency.red.ink,
  },
} as const;

export function CrisisView({
  policy,
  source,
  elapsedS,
  zoneName,
  onSalir,
  viva,
  reduceMotion = false,
}: CrisisViewProps) {
  const variant = VARIANTS[policy ?? "none"];
  // [T-7.19 · D-30] EL HALO. Se anima la CARCASA —un anillo sobre el borde de la
  // pantalla—, nunca la tipografía: la instrucción es legible desde el primer
  // frame, que es lo que la prohibición del §5.3 protegía y esta decisión
  // conserva. `useNativeDriver` porque `opacity` la mueve el compositor sin
  // pasar por el puente: un halo que compita por el hilo de JS con la consulta
  // de estado retrasaría justo lo que no puede retrasarse.
  // `useState` con inicializador perezoso y no `useRef(...).current`: leer un
  // ref durante el render es lo que prohíbe `react-hooks`, y es la misma forma
  // que ya usan `LatidoPunto` y `PanicButton`.
  const [halo] = useState(() => new Animated.Value(HALO_REPOSO));
  useEffect(() => {
    if (!viva || reduceMotion) {
      // Quieto y PUESTO. Apagar bien una animación es que siga leyéndose como
      // estado: el anillo no desaparece, deja de latir.
      halo.setValue(viva ? HALO_REPOSO : 0);
      return undefined;
    }
    const mitad = motion.alertaMs / 2;
    const bucle = Animated.loop(
      Animated.sequence([
        Animated.timing(halo, {
          toValue: HALO_PICO,
          duration: mitad,
          useNativeDriver: true,
        }),
        Animated.timing(halo, {
          toValue: HALO_REPOSO,
          duration: mitad,
          useNativeDriver: true,
        }),
      ]),
    );
    bucle.start();
    return () => {
      bucle.stop();
      halo.setValue(HALO_REPOSO);
    };
  }, [halo, viva, reduceMotion]);

  return (
    <View style={[styles.wrap, { backgroundColor: variant.bg }]}>
      <Animated.View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        pointerEvents="none"
        style={[styles.halo, { borderColor: variant.accent, opacity: halo }]}
        testID="crisis-halo"
      />
      <View style={[styles.strip, { backgroundColor: variant.strip }]}>
        <Text style={[styles.stripEyebrow, { color: variant.stripText }]}>
          {source.eyebrow}
        </Text>
        {/* [T-2.104] Del DATO, no escrito a fuego. Antes ponía siempre «ALERTA
            SÍSMICA SASMEX», así que una detección instrumental propia o una
            activación manual se le atribuían al servicio oficial en el texto más
            grande de la pantalla. La decisión vive en `sourceLabel`, junto a la
            etiqueta de abajo, porque es la misma pregunta: de dónde viene esto. */}
        <Text style={[styles.stripTitle, { color: variant.stripText }]}>{source.title}</Text>
      </View>

      <View style={styles.body}>
        <View style={styles.hero}>
          <Text style={styles.actionEyebrow}>— SU INSTRUCCIÓN —</Text>
          <Text style={[styles.instruction, { color: variant.accent }]}>
            {variant.instruction}
          </Text>
          <Text style={styles.detail}>{variant.detail}</Text>
          {zoneName ? (
            <View style={styles.zonePill}>
              <Text style={styles.zonePillText}>ZONA {zoneName.toUpperCase()}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.elapsed}>
          <Text style={styles.elapsedEyebrow}>TIEMPO TRANSCURRIDO DESDE LA ALERTA</Text>
          <Text style={styles.elapsedValue}>{formatElapsed(elapsedS)}</Text>
          <View style={styles.sourcePill}>
            <Text style={styles.sourceText}>{source.label}</Text>
          </View>
          {source.detail ? <Text style={styles.sourceDetail}>{source.detail}</Text> : null}
          {/* §2.1-A: hueco del ETA — SOLO se activa si una fuente futura
              transporta ETA por dato. Con el flag en false, NADA se renderiza. */}
          {ALERT_SOURCE_CARRIES_ETA ? <View testID="eta-slot" /> : null}
        </View>

        {onSalir ? (
          <View style={styles.salida}>
            <Pressable
              accessibilityRole="button"
              onPress={onSalir}
              style={styles.salidaBoton}
              testID="crisis-salir-tactico"
            >
              <Text style={styles.salidaTexto}>SILENCIAR Y VOLVER AL PANEL</Text>
            </Pressable>
            {/* Salir de la PANTALLA no es que se acabó la alerta, y decirlo aquí
                cuesta una línea: quien pulsa se lleva la franja de alerta viva a
                todas las pestañas y puede volver tocándola. */}
            <Text style={styles.salidaNota}>
              La alerta sigue activa. Volverá a esta instrucción tocando la franja roja.
            </Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1 },
  // El anillo va por ENCIMA del fondo y por DEBAJO de todo lo que se lee: no
  // intercepta toques (`pointerEvents`) y está oculto para el lector de
  // pantalla, que ya tiene la instrucción y la fuente.
  halo: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    borderWidth: 4,
    borderRadius: radius.md,
    zIndex: 1,
  },
  // El objetivo táctil no baja del mínimo de T-6.20 (48 dp) ni con guantes:
  // esto se pulsa en una evacuación, no en un escritorio.
  salida: { marginTop: space[4], alignItems: "center" },
  salidaBoton: {
    minHeight: 52,
    justifyContent: "center",
    paddingHorizontal: space[5],
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: emergency.red.ink,
  },
  salidaTexto: {
    color: emergency.red.ink,
    fontSize: fontSize.sm,
    fontWeight: "700",
    letterSpacing: 1,
  },
  salidaNota: {
    color: emergency.red.ink2,
    fontSize: fontSize.xs,
    marginTop: space[2],
    textAlign: "center",
  },
  strip: { paddingTop: 56, paddingBottom: space[3], paddingHorizontal: space[4], alignItems: "center" },
  stripEyebrow: { fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 2, opacity: 0.85 },
  stripTitle: { fontSize: 24, fontWeight: "700", letterSpacing: 1, marginTop: space[1] },
  body: { flex: 1, paddingHorizontal: space[5], paddingBottom: 40, paddingTop: space[4] },
  hero: { alignItems: "center", marginTop: space[3] },
  actionEyebrow: {
    color: emergency.red.eyebrow,
    fontSize: 10,
    letterSpacing: 2,
    marginBottom: space[2],
  },
  instruction: {
    fontSize: 64,
    lineHeight: 66,
    fontWeight: "800",
    textAlign: "center",
    letterSpacing: 1,
  },
  detail: {
    color: emergency.red.ink2,
    fontSize: fontSize.sm,
    lineHeight: 20,
    textAlign: "center",
    marginTop: space[3],
  },
  zonePill: {
    marginTop: space[4],
    borderWidth: 1,
    borderColor: emergency.onDark.border,
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  zonePillText: { color: emergency.red.ink1, fontSize: fontSize.xs, letterSpacing: 1.5 },
  elapsed: {
    marginTop: "auto",
    alignItems: "center",
    borderTopWidth: 1,
    borderTopColor: emergency.onDark.surface,
    paddingTop: space[4],
  },
  elapsedEyebrow: {
    color: emergency.red.meta,
    fontSize: 10,
    letterSpacing: 2,
    textAlign: "center",
  },
  elapsedValue: {
    color: emergency.red.ink,
    fontSize: 48,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
    marginTop: space[1],
  },
  sourcePill: {
    marginTop: space[2],
    borderWidth: 1,
    borderColor: emergency.onDark.border,
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  sourceText: { color: emergency.red.ink1, fontSize: 10, letterSpacing: 1.5 },
  sourceDetail: { color: emergency.red.ink3, fontSize: fontSize.xs, marginTop: space[1] },
});
