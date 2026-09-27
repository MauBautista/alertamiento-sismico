// [T-9.11 · D-39] Ruta de MOVIMIENTO EN EL INMUEBLE. La fase la sirve el servidor
// (`phase="building_movement"`) y SOLO a quien tiene `movement_alert`; esta
// pantalla no decide nada, igual que `/alarma-inmueble`.
//
// · **Solo el perfil TÁCTICO.** La nube no se la sirve al ocupante, pero la app
//   no se fía: con perfil de ocupante se vuelve a INICIO sin pintar nada.
// · **No es toma total sin salida:** la brigada tiene que poder ir a REPORTAR
//   DAÑOS, que es justo lo que la pantalla le pide.
// · **No suena el tono sísmico ni hay T+:** una estación sola no es una alerta
//   sísmica oficial (T-2.32); la voz propia la puso ya el canal de la push.
//
// Sin `@takab/sdk` en el cuerpo del módulo: expo-router barre `src/app` y el SDK
// se queda en los hooks y en las vistas.
import { Redirect, useRouter } from "expo-router";

import { useSessionStore } from "@/auth/session.store";
import { horaDeReloj } from "@/features/alarm/BuildingAlarmView";
import { TacticalAckButton } from "@/features/alarm/TacticalAckButton";
import { useTacticalAck } from "@/features/alarm/useTacticalAck";
import { useAlertState } from "@/features/alert/useAlertState";
import { MovementView, etiquetaPga, haceCuanto } from "@/features/movement/MovementView";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

/** Sin sitio vigilado no hay a quién preguntarle: se DICE, no se gira. */
const SIN_SITIO =
  "Este teléfono no está vinculado a ningún edificio, así que no hay movimiento que consultar. Vincúlese con el código de su inmueble.";

/** El servidor SÍ respondió y no hay incidente: vacío honesto, distinto de
 *  «no pudimos preguntar». */
const SIN_MOVIMIENTO = "El servidor no reporta ningún movimiento activo en su edificio.";

export default function Movimiento() {
  const router = useRouter();
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  const siteId = useWatchedSiteId();
  const { state, data, loading, error, staleSinceMs, dataUpdatedAt, refetch } =
    useAlertState(siteId);

  // Quién acusa y quién reporta lo dice el SERVIDOR. El acuse es el mismo
  // endpoint que el de la alarma del inmueble (gateado por `manual_activate`);
  // se exige además `movement_alert`, que es a quien la nube despertó.
  const puedeAcusar = useSessionStore(
    (s) =>
      s.me?.allowed_actions?.manual_activate === true &&
      s.me?.allowed_actions?.movement_alert === true,
  );
  const puedeReportar = useSessionStore(
    (s) => s.me?.allowed_actions?.damage_report_submit === true,
  );
  const incidente = data?.incident ?? null;
  const acuse = useTacticalAck(incidente?.incident_id ?? null);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  // Defensivo: el ocupante NUNCA ve esta pantalla, diga lo que diga la fase.
  if (profile !== "tactical") {
    return <Redirect href="/" />;
  }
  // La fase del SERVIDOR dejó de ser movimiento: se suelta la pantalla. Si lo
  // que hay ahora es un sismo oficial, el `CrisisWatcher` enruta.
  if (state !== null && state !== "building_movement") {
    return <Redirect href="/" />;
  }

  const sinSitio = siteId === null;

  return (
    <StateFrame
      empty={sinSitio || (data !== null && incidente === null)}
      emptyText={sinSitio ? SIN_SITIO : SIN_MOVIMIENTO}
      error={data === null ? error : null}
      loading={loading}
      onRetry={refetch}
      staleSinceMs={staleSinceMs}
    >
      {incidente !== null ? (
        <MovementView
          // «Hace cuánto» contra el instante del ÚLTIMO dato (como INICIO): puro,
          // y avanza con cada sondeo, que en esta fase es el rápido.
          abiertoLabel={haceCuanto(incidente.opened_at, dataUpdatedAt)}
          // La nube manda `building_alarm` también en esta fase (solo a la
          // brigada): una alarma de pánico no puede quedar oculta aquí.
          onAbrirAlarma={
            data?.building_alarm != null ? () => router.push("/alarma-inmueble") : null
          }
          onReportarDanos={puedeReportar ? () => router.push("/(brigadista)/triage") : null}
          pgaLabel={etiquetaPga(incidente.max_pga_g)}
          slotAcuse={
            <TacticalAckButton
              acusadoALas={acuse.acusadoEn ? horaDeReloj(acuse.acusadoEn) : null}
              detalleAcusado="El centro de monitoreo sabe que la brigada está verificando."
              estado={acuse.estado}
              onPress={() => void acuse.acusar()}
              pie="Avisa al centro de monitoreo de que la brigada va a verificar el inmueble."
              visible={puedeAcusar}
            />
          }
        />
      ) : null}
    </StateFrame>
  );
}
