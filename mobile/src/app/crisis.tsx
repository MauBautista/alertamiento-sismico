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
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";

import { useSessionStore } from "@/auth/session.store";
import { CrisisView } from "@/features/alert/CrisisView";
import { elapsedSeconds } from "@/features/alert/machine";
import { sourceLabel } from "@/features/alert/source";
import { startAlertLoop, stopAlertLoop } from "@/features/alert/sound";
import { useAlertState } from "@/features/alert/useAlertState";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

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
  const siteId = useWatchedSiteId();
  const { state, data, loading, error, stale, dataUpdatedAt, refetch } = useAlertState(siteId);
  const [nowMs, setNowMs] = useState(() => Date.now());

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

  return (
    <StateFrame
      empty={sinSitio || (data !== null && incident === null)}
      emptyText={sinSitio ? SIN_SITIO : SIN_INCIDENTE}
      error={data === null ? error : null}
      loading={loading}
      onRetry={refetch}
      staleSinceMs={stale && data !== null ? dataUpdatedAt : null}
    >
      {incident !== null && data !== null ? (
        <CrisisView
          elapsedS={elapsedSeconds(incident.opened_at, nowMs)}
          policy={(data.my_zone?.evac_policy as "evacuate" | "shelter" | null) ?? null}
          source={sourceLabel(incident)}
          zoneName={data.my_zone?.name ?? null}
        />
      ) : null}
    </StateFrame>
  );
}
