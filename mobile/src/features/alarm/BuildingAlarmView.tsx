// [T-2.106] ALARMA DEL INMUEBLE — la sirena del edificio la ordenó una persona.
//
// Decisión de producto (2026-08-09): una activación manual es **alarma del
// inmueble, no evacuación sísmica**. Suena la sirena —que es su diseño— y la app
// la anuncia como tal: SIN instrucción de evacuación sísmica y SIN el contador
// T+ de sismo. Hasta hoy no había superficie ninguna: el quórum de pánico emite
// un `siren/activate` firmado y no crea incidente, así que el edificio sonaba y
// el teléfono del ocupante no decía por qué.
//
// Sigue el patrón de `features/alert/` (presentacional puro, todo por props,
// instruction-first) pero NO reutiliza NADA del titular de crisis sísmica, y esa
// separación es el punto de la tarea, no una casualidad de organización.
//
// Por qué la instrucción es «ATIENDA A SU BRIGADA» y no una orden concreta:
// TAKAB no sabe por qué se activó la alarma —un incendio, una fuga, una riña, un
// simulacro improvisado— y una instrucción inventada sobre una emergencia
// desconocida es peor que ninguna. Lo único honesto que la nube sabe es QUE
// suena y QUIÉN manda en el edificio.
//
// Ámbar y no el rojo de crisis: el color es parte del mensaje, y esta pantalla
// no puede leerse de reojo como la toma sísmica.
import { type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

/** Hora de reloj (HH:MM) del instante en que se ordenó la sirena.
 *
 * Hora, y no un T+ ascendente, a propósito: el cronómetro T+ es de la toma de
 * crisis sísmica (§2.1-A) y prestárselo a esta pantalla la haría leerse como un
 * sismo en curso — justo lo que la decisión de producto prohíbe.
 *
 * Una fecha ilegible devuelve `--:--`: a una persona no se le enseña jamás un
 * «Invalid Date», y fingir una hora sería inventar un dato (§2.1-A).
 */
export function horaDeReloj(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return "--:--";
  }
  return new Date(t).toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export type BuildingAlarmViewProps = {
  /** Hora de reloj ya formateada (`horaDeReloj`): la vista es pura y no toca el reloj. */
  sinceLabel: string;
  zoneName: string | null;
  /** [T-2.147.b] Hueco para el acuse de la brigada. Un NODO, no una bandera de rol:
   *  esta vista no puede decidir quién es táctico —eso lo dice el servidor por
   *  `allowed_actions`— y meterle esa lógica la dejaría de ser presentacional pura,
   *  que es lo que hace que se pueda probar sin sesión ni red. */
  slotAcuse?: ReactNode;
};

export function BuildingAlarmView({ sinceLabel, zoneName, slotAcuse }: BuildingAlarmViewProps) {
  return (
    <View style={styles.wrap}>
      <View style={styles.strip}>
        {/* El deslinde va ARRIBA y en el mismo bloque que el titular: la lección
            de T-2.104 es que el texto grande manda, así que el titular no puede
            quedarse solo diciendo «ALARMA» y dejar el matiz para el pie. */}
        <Text style={styles.stripEyebrow}>NO ES UNA ALERTA SÍSMICA</Text>
        <Text style={styles.stripTitle}>ALARMA DEL INMUEBLE</Text>
      </View>

      <View style={styles.body}>
        <View style={styles.hero}>
          <Text style={styles.actionEyebrow}>— SU INSTRUCCIÓN —</Text>
          <Text style={styles.instruction}>ATIENDA A SU BRIGADA</Text>
          <Text style={styles.detail}>
            Una persona activó la sirena de este edificio.{"\n"}
            Siga las indicaciones de su brigada y del personal de seguridad.
          </Text>
          {zoneName ? (
            <View style={styles.zonePill}>
              <Text style={styles.zonePillText}>ZONA {zoneName.toUpperCase()}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.since}>
          <Text style={styles.sinceEyebrow}>SIRENA ACTIVADA A LAS</Text>
          <Text style={styles.sinceValue}>{sinceLabel}</Text>
          <View style={styles.sourcePill}>
            <Text style={styles.sourceText}>ORIGEN · ACTIVACIÓN MANUAL DEL INMUEBLE</Text>
          </View>
          <Text style={styles.sourceDetail}>
            TAKAB no conoce el motivo de la activación.
          </Text>
        </View>

        {slotAcuse ? <View style={styles.acuse}>{slotAcuse}</View> : null}
      </View>
    </View>
  );
}

const AMBAR = "#E8A700";
/** Exportado para que el acuse (`TacticalAckButton`) no copie el hex.
 *  No sale de `@takab/design-tokens` porque el ámbar de esta pantalla no está en la
 *  paleta: es una excepción local declarada, y **una sola definición** es lo que evita
 *  que las dos mitades de la misma pantalla acaben con ámbares distintos. */
export const AMBAR_CLARO = "#FFCE3A";

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: "#1C1404" },
  strip: {
    backgroundColor: AMBAR,
    paddingTop: 56,
    paddingBottom: space[3],
    paddingHorizontal: space[4],
    alignItems: "center",
  },
  stripEyebrow: { color: "#2A1A00", fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 2 },
  stripTitle: { color: "#2A1A00", fontSize: 24, fontWeight: "700", letterSpacing: 1, marginTop: space[1] },
  body: { flex: 1, paddingHorizontal: space[5], paddingBottom: 40, paddingTop: space[4] },
  hero: { alignItems: "center", marginTop: space[3] },
  acuse: { marginTop: space[4] },
  actionEyebrow: {
    color: "rgba(255,240,210,0.65)",
    fontSize: 10,
    letterSpacing: 2,
    marginBottom: space[2],
  },
  instruction: {
    color: AMBAR_CLARO,
    fontSize: 44,
    lineHeight: 50,
    fontWeight: "800",
    textAlign: "center",
    letterSpacing: 1,
  },
  detail: {
    color: "rgba(255,246,230,0.78)",
    fontSize: fontSize.sm,
    lineHeight: 20,
    textAlign: "center",
    marginTop: space[3],
  },
  zonePill: {
    marginTop: space[4],
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.16)",
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  zonePillText: { color: "rgba(255,246,230,0.85)", fontSize: fontSize.xs, letterSpacing: 1.5 },
  since: {
    marginTop: "auto",
    alignItems: "center",
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.10)",
    paddingTop: space[4],
  },
  sinceEyebrow: {
    color: "rgba(255,235,190,0.7)",
    fontSize: 10,
    letterSpacing: 2,
    textAlign: "center",
  },
  sinceValue: {
    color: palette.fg,
    fontSize: 48,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
    marginTop: space[1],
  },
  sourcePill: {
    marginTop: space[2],
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.16)",
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  sourceText: { color: "rgba(255,246,230,0.85)", fontSize: 10, letterSpacing: 1.5 },
  sourceDetail: {
    color: "rgba(255,246,230,0.7)",
    fontSize: fontSize.xs,
    marginTop: space[1],
    textAlign: "center",
  },
});
