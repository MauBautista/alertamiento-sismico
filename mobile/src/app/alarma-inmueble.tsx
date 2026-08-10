// [T-2.106] Ruta de ALARMA DEL INMUEBLE. La fase la sirve el servidor
// (`phase="building_alarm"`); esta pantalla no decide nada, igual que crisis.
//
// Diferencias DELIBERADAS con `/crisis`, todas por la decisión de producto del
// 2026-08-09 (una activación manual es alarma del inmueble, no evacuación
// sísmica):
//
// · **No suena el tono de alerta.** La sirena del edificio ya está sonando —es
//   el hecho que esta pantalla explica—, y añadirle encima el bucle de alerta
//   sísmica sería atribuirle sismo a un pánico en el único canal que no lleva
//   texto. Es la mentira de T-2.104 en versión sonora.
// · **No es toma total sin salida:** el ocupante tiene que poder llegar al
//   directorio para llamar a su brigada, que es justo lo que la pantalla le
//   pide hacer.
import { Redirect } from "expo-router";
import { ActivityIndicator, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { BuildingAlarmView, horaDeReloj } from "@/features/alarm/BuildingAlarmView";
import { useAlertState } from "@/features/alert/useAlertState";
import { useWatchedSiteId } from "@/services/mySite";
import { fontSize, palette, space } from "@/ui/theme";

export default function AlarmaInmueble() {
  const status = useSessionStore((s) => s.status);
  const siteId = useWatchedSiteId();
  const { state, data } = useAlertState(siteId);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  // La fase del SERVIDOR dejó de ser alarma del inmueble. Si lo que hay ahora es
  // un sismo, el CrisisWatcher enruta; aquí solo se suelta la pantalla.
  if (state !== null && state !== "building_alarm") {
    return <Redirect href="/" />;
  }
  if (!data?.building_alarm) {
    // La push despertó a la app; la VERDAD es mobile-state. Se declara la
    // verificación en curso — jamás se finge una alarma que el servidor no ha
    // confirmado (regla de oro 7).
    return (
      <View style={styles.verifying}>
        <ActivityIndicator color={palette.warn} size="large" />
        <Text style={styles.verifyingText}>VERIFICANDO LA ALARMA CON EL SERVIDOR…</Text>
      </View>
    );
  }

  return (
    <BuildingAlarmView
      sinceLabel={horaDeReloj(data.building_alarm.since)}
      zoneName={data.my_zone?.name ?? null}
    />
  );
}

const styles = {
  verifying: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center",
    justifyContent: "center",
    gap: space[3],
  },
  verifyingText: { color: palette.fg2, fontSize: fontSize.sm, letterSpacing: 1 },
} as const;
