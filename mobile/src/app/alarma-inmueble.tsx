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
//
// [T-2.117] Esta pantalla resolvía `if (!data?.building_alarm)` con un spinner y
// el rótulo «VERIFICANDO LA ALARMA CON EL SERVIDOR…» — el defecto GEMELO del que
// T-2.111 cerró en `crisis.tsx`. Sin sitio vigilado la consulta ni se habilita
// (`enabled: siteId != null`) y `data` es null PARA SIEMPRE: el ocupante se
// quedaba mirando girar la pantalla que existe para explicarle por qué suena la
// sirena de su edificio. Ahora los cuatro estados los declara `StateFrame`.
import { Redirect } from "expo-router";

import { useSessionStore } from "@/auth/session.store";
import { BuildingAlarmView, horaDeReloj } from "@/features/alarm/BuildingAlarmView";
import { TacticalAckButton } from "@/features/alarm/TacticalAckButton";
import { useTacticalAck } from "@/features/alarm/useTacticalAck";
import { useAlertState } from "@/features/alert/useAlertState";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

/** Sin sitio vigilado no hay a quién preguntarle: se DICE, no se gira. Se llega
 *  aquí por una push o por el `CrisisWatcher`, así que la salida tiene que ser
 *  una instrucción, no un callejón. */
const SIN_SITIO =
  "Este teléfono no está vinculado a ningún edificio, así que no hay alarma que consultar. Vincúlese con el código de su inmueble para recibir el aviso de su edificio.";

/** El servidor SÍ respondió y no hay alarma abierta. Es un vacío honesto, y hay
 *  que distinguirlo de «no pudimos preguntar»: si suena algo y esto lo tapara
 *  con una frase tranquilizadora, sería la mentira de `lista.tsx` (T-2.111). */
const SIN_ALARMA = "El servidor no reporta ninguna alarma activa en su edificio.";

export default function AlarmaInmueble() {
  const status = useSessionStore((s) => s.status);
  const siteId = useWatchedSiteId();
  const { state, data, loading, error, staleSinceMs, refetch } = useAlertState(siteId);

  // [T-2.147.b] Quién puede acusar lo dice el SERVIDOR, con la MISMA acción que usa
  // para elegir a quién despierta el push (`roles_with_action("manual_activate")`).
  // Una lista de roles escrita aquí divergiría de aquélla el día que entrara un rol
  // nuevo, y entonces alguien despertado sin poder acusar parecería «sin respuesta»
  // para siempre: el escalado al SOC saltaría por un fallo de permisos.
  const puedeAcusar = useSessionStore((s) => s.me?.allowed_actions?.manual_activate === true);
  // El incidente `trigger='manual'` que `D-11` abre. `mobile_state` lo sirve sin
  // filtrar por trigger, así que su id ya viajaba: no hizo falta tocar el contrato.
  const incidenteManual =
    data?.incident?.trigger === "manual" ? (data.incident.incident_id ?? null) : null;
  const acuse = useTacticalAck(incidenteManual);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  // La fase del SERVIDOR dejó de ser alarma del inmueble. Si lo que hay ahora es
  // un sismo, el CrisisWatcher enruta; aquí solo se suelta la pantalla.
  if (state !== null && state !== "building_alarm") {
    return <Redirect href="/" />;
  }

  // La push despertó a la app; la VERDAD es mobile-state. Los cuatro estados se
  // declaran: cargando (consulta en vuelo), error (no se pudo preguntar, con
  // reintento), vacío (sin sitio vigilado, o el servidor dice que no hay alarma)
  // y retenido (hay alarma pero el dato es VIEJO — se pinta con el banner,
  // jamás como si fuera de este segundo). Nunca se finge una alarma que el
  // servidor no ha confirmado (regla de oro 7).
  const sinSitio = siteId === null;
  const alarma = data?.building_alarm ?? null;

  return (
    <StateFrame
      empty={sinSitio || (data !== null && alarma === null)}
      emptyText={sinSitio ? SIN_SITIO : SIN_ALARMA}
      error={data === null ? error : null}
      loading={loading}
      onRetry={refetch}
      staleSinceMs={staleSinceMs}
    >
      {alarma !== null && data !== null ? (
        <BuildingAlarmView
          sinceLabel={horaDeReloj(alarma.since)}
          slotAcuse={
            <TacticalAckButton
              acusadoALas={acuse.acusadoEn ? horaDeReloj(acuse.acusadoEn) : null}
              estado={acuse.estado}
              onPress={() => void acuse.acusar()}
              visible={puedeAcusar && incidenteManual !== null}
            />
          }
          zoneName={data.my_zone?.name ?? null}
        />
      ) : null}
    </StateFrame>
  );
}
