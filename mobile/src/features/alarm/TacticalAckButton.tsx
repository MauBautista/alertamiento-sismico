// [T-2.147.b · D-05] El acuse de la brigada — el botón que faltaba.
//
// **El hueco que cierra, y por qué importa.** `D-05` diseñó la cadena así: el
// quórum de pánico despierta SOLO a los tácticos; si ninguno acusa en ~2 min, se
// avisa al SOC. El endpoint del acuse existe y está probado desde el 2026-08-16
// (`POST /incidents/{id}/tactical-ack`)… y **nadie podía pulsarlo**: no había
// superficie en la app. Así que `T-2.147.c` medía «cero acuses», que era
// literalmente siempre cierto, y **el escalado al SOC saltaba en todos los
// pánicos**. Los dos apagadores que `D-05` diseñó eran uno.
//
// **Lo que este botón NO hace, y es la mitad del diseño:**
// · **No silencia la sirena.** Silenciar es `siren_silence`, otra acción, otro
//   permiso y otro camino (el de emergencia). Un acuse que además apagara la
//   sirena convertiría «me enteré» en «ya está resuelto», que es lo contrario.
// · **No cambia la fase ni el estado del incidente.** Eso es `ack_incident`, que
//   es del SOC. Conflarlos costaría en las dos direcciones (`T-2.147.b`): un
//   brigadista vaciaría la cola del SOC desde el teléfono, y el acuse del SOC
//   contaría como respuesta de la brigada, apagando el escalado sin que nadie
//   hubiera bajado a mirar.
//
// **Quién lo ve se DERIVA del servidor**, nunca de una lista local:
// `allowed_actions.manual_activate` es la MISMA acción con la que la nube elige a
// quién despierta. Que las dos salgan de ahí no es economía: si divergieran,
// alguien despertado sin poder acusar parecería «sin respuesta» para siempre y
// dispararía el escalado por un fallo de permisos.
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { fontSize, radius, space } from "@/ui/theme";

import { AMBAR_CLARO } from "./BuildingAlarmView";

export type AckEstado = "idle" | "enviando" | "acusado" | "error";

export type TacticalAckButtonProps = {
  /** `false` en un ocupante: el botón no se pinta siquiera. Server-driven. */
  visible: boolean;
  estado: AckEstado;
  /** Hora de reloj del acuse, ya formateada. */
  acusadoALas: string | null;
  onPress: () => void;
};

export function TacticalAckButton({
  visible,
  estado,
  acusadoALas,
  onPress,
}: TacticalAckButtonProps) {
  if (!visible) {
    return null;
  }

  if (estado === "acusado") {
    return (
      <View style={styles.acusado} testID="tactical-ack-hecho">
        <Text style={styles.acusadoTitulo}>ACUSE REGISTRADO</Text>
        <Text style={styles.acusadoDetalle}>
          {acusadoALas ? `Respondió a las ${acusadoALas}. ` : ""}
          La sirena sigue sonando: acusar no la apaga.
        </Text>
      </View>
    );
  }

  const enviando = estado === "enviando";
  return (
    <View>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy: enviando, disabled: enviando }}
        disabled={enviando}
        onPress={onPress}
        style={[styles.boton, enviando && styles.botonOcupado]}
        testID="tactical-ack"
      >
        {enviando ? (
          <ActivityIndicator color="#2A1A00" />
        ) : (
          <Text style={styles.botonTexto}>ESTOY ATENDIENDO</Text>
        )}
      </Pressable>
      <Text style={styles.pie}>
        Avisa al centro de monitoreo de que la brigada respondió. No silencia la sirena.
      </Text>
      {estado === "error" ? (
        // Se declara y se deja reintentar: un acuse perdido en silencio haría
        // creer a quien lo pulsó que ya avisó, y el SOC escalaría igual.
        <Text style={styles.error} testID="tactical-ack-error">
          No se pudo registrar el acuse. Vuelva a pulsar.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  boton: {
    backgroundColor: AMBAR_CLARO,
    borderRadius: radius.md,
    paddingVertical: space[4],
    alignItems: "center",
    justifyContent: "center",
    minHeight: 56,
  },
  botonOcupado: { opacity: 0.7 },
  botonTexto: { color: "#2A1A00", fontSize: 18, fontWeight: "800", letterSpacing: 1 },
  pie: {
    color: "rgba(255,246,230,0.7)",
    fontSize: fontSize.xs,
    textAlign: "center",
    marginTop: space[2],
  },
  error: {
    color: "#FF9B8A",
    fontSize: fontSize.xs,
    textAlign: "center",
    marginTop: space[2],
  },
  acusado: {
    borderColor: "rgba(255,206,58,0.5)",
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[3],
    paddingHorizontal: space[4],
    alignItems: "center",
  },
  acusadoTitulo: { color: AMBAR_CLARO, fontSize: fontSize.sm, fontWeight: "800", letterSpacing: 1 },
  acusadoDetalle: {
    color: "rgba(255,246,230,0.75)",
    fontSize: fontSize.xs,
    textAlign: "center",
    marginTop: space[1],
  },
});
