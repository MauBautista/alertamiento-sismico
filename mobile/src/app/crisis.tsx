// Ruta de crisis (1.2/1.3) — TOMA TOTAL: sin gesto de regreso ni descarte
// mientras el SERVIDOR reporte alerta activa (spec §7). La salida la decide
// la fase del backend, jamás un botón local.
//
// [T-2.111] Esta pantalla resolvía `if (!data?.incident)` con un spinner y el
// rótulo «VERIFICANDO ALERTA CON EL SERVIDOR…», que era honesto sólo mientras
// la consulta estuviera realmente en vuelo. Sin sitio vigilado la consulta ni
// se habilita (`enabled: siteId != null`) y `data` es null PARA SIEMPRE: el
// ocupante se quedaba mirando girar la pantalla que existe para decirle si
// tiene que evacuar. Ahora los cuatro estados los declara `StateFrame`, igual
// que en `triage.tsx` (T-2.108) y que en la consola.
import { Redirect, useRouter } from "expo-router";
import { useEffect, useState } from "react";

import { useSessionStore } from "@/auth/session.store";
import { CrisisView } from "@/features/alert/CrisisView";
import { elapsedSeconds } from "@/features/alert/machine";
import { sourceLabel } from "@/features/alert/source";
import { marcarSalidaTactica } from "@/features/alert/salidaTactica";
import { startAlertLoop, stopAlertLoop } from "@/features/alert/sound";
import { useAlertState } from "@/features/alert/useAlertState";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { useReduceMotion } from "@/ui/useReduceMotion";

/** Sin sitio vigilado no hay a quién preguntarle: se DICE, no se gira. El
 *  ocupante llega aquí por una push o por el `CrisisWatcher`, así que la salida
 *  tiene que ser una instrucción, no un callejón. */
const SIN_SITIO =
  "Este teléfono no está vinculado a ningún edificio, así que no hay alerta que consultar. Vincúlese con el código de su inmueble para recibir la instrucción de crisis.";

/** El servidor SÍ respondió y no hay incidente abierto. Es un vacío honesto y
 *  tranquilizador, y hay que distinguirlo de «no pudimos preguntar». */
const SIN_INCIDENTE = "El servidor no reporta ninguna alerta activa en su edificio.";

export default function Crisis() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { state, data, loading, error, staleSinceMs, refetch } = useAlertState(siteId);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const reduceMotion = useReduceMotion();

  // T+ ascendente: tick de 1 s mientras la pantalla vive.
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1_000);
    return () => clearInterval(timer);
  }, []);

  // Sonido en loop SOLO durante alert_active (la push CRISIS ya sonó al llegar).
  useEffect(() => {
    if (state === "alert_active") {
      void startAlertLoop();
      return () => stopAlertLoop();
    }
    return undefined;
  }, [state]);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  // La fase del SERVIDOR dejó de ser alerta: la sacudida concluida pasa al
  // check-in de vida (1.4); lo demás regresa al inicio.
  if (state === "checkin_pending" || state === "reentry_blocked") {
    return <Redirect href="/checkin" />;
  }
  // [T-2.106] El sismo pasó y lo que queda sonando es la alarma del inmueble:
  // se entrega la pantalla que la explica, en vez de soltar al ocupante en el
  // inicio con una sirena sonando y ninguna razón a la vista.
  if (state === "building_alarm") {
    return <Redirect href="/alarma-inmueble" />;
  }
  if (state !== null && state !== "alert_active") {
    return <Redirect href="/" />;
  }

  // La push despertó a la app; la VERDAD es mobile-state. Los cuatro estados se
  // declaran: cargando (consulta en vuelo), error (no se pudo preguntar, con
  // reintento), vacío (sin sitio vigilado, o el servidor dice que no hay
  // alerta) y retenido (hay instrucción pero es VIEJA — se pinta con el banner,
  // jamás como si fuera de este segundo).
  const sinSitio = siteId === null;
  const incident = data?.incident ?? null;

  // [T-7.29] La salida es SOLO del perfil táctico, y se decide aquí —no en la
  // vista— porque es una regla de producto, no de pintura: el ocupante no puede
  // salir de una evacuación con el dedo, y el brigadista tiene trabajo que hacer
  // dentro de la app mientras la alerta sigue viva.
  const salir =
    profile === "tactical"
      ? () => {
          stopAlertLoop(); // el altavoz de ESTE teléfono; la sirena del edificio no se toca
          marcarSalidaTactica(incident?.incident_id ?? null);
          router.replace("/(brigadista)/panel");
        }
      : null;

  return (
    <StateFrame
      empty={sinSitio || (data !== null && incident === null)}
      emptyText={sinSitio ? SIN_SITIO : SIN_INCIDENTE}
      error={data === null ? error : null}
      loading={loading}
      onRetry={refetch}
      staleSinceMs={staleSinceMs}
    >
      {incident !== null && data !== null ? (
        <CrisisView
          elapsedS={elapsedSeconds(incident.opened_at, nowMs)}
          policy={(data.my_zone?.evac_policy as "evacuate" | "shelter" | null) ?? null}
          onSalir={salir}
          reduceMotion={reduceMotion}
          source={sourceLabel(incident)}
          // [T-7.19 · D-30] El halo vive mientras el SERVIDOR sostiene la alerta.
          // `alert_active` es exactamente eso: en cuanto la fase pasa a
          // `shaking_concluded` esta ruta redirige al check-in, y aun así la
          // condición viaja explícita — una animación que dependa de que el
          // enrutado la desmonte se rompe en silencio el día que alguien monte
          // esta vista en otro sitio.
          viva={state === "alert_active"}
          zoneName={data.my_zone?.name ?? null}
        />
      ) : null}
    </StateFrame>
  );
}
