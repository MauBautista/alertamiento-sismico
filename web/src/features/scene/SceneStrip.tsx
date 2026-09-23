// [T-6.01] LA FRANJA DE ESCENA: alerta, simulacro, mantenimiento y demo en las
// seis rutas, decididos por la tabla de `scene.ts` y pintados UNA vez, en el
// shell.
//
// Este es el ÚNICO componente que lee las cuatro fuentes para pintar escena
// (`src/sceneCensus.test.ts` lo vigila por igualdad): `ConsolePage` sigue
// leyendo incidentes para su cola y su tarjeta, `DrillControls` lee el
// simulacro para gatear INICIAR, y `FleetPage` lee las ventanas para
// administrarlas — ninguno decide qué escena hay ni pinta un banner de escena.
//
// Cada fuente trae su marco con los cuatro estados (regla de oro 7): un fallo de
// lectura del simulacro no puede callar el de mantenimiento, y al revés. En
// escena NORMAL los cuatro marcos están `empty` y la hoja los esconde: la franja
// mide cero (U-45). Mientras una fuente carga, su marco es un chip en línea.
//
// SIN ANIMACIÓN, a propósito: la escena se declara en el primer frame. Lo
// vigila `styles/layoutInvariants.test.ts`.

import { useLocation } from "react-router";

import StateFrame from "../../components/StateFrame";
import { useNow } from "../../lib/useNow";
import { useActiveDrill } from "../console/useActiveDrill";
import { useDemoMode } from "../console/useDemoMode";
import { useLiveIncidents } from "../console/useLiveIncidents";
import { useMaintenanceWindows } from "../console/useMaintenanceWindows";
import { useMapState } from "../console/useMapState";
import AlertLine from "./AlertLine";
import ReviewLine from "./ReviewLine";
import DemoModeBanner from "./DemoModeBanner";
import DrillBanner from "./DrillBanner";
import MaintenanceBanner from "./MaintenanceBanner";
import { WALL_ROUTE, alertKind, resolveScene, sceneAlert, sceneSlot } from "./scene";

/** Sin snapshot fresco de incidentes tras esto, la línea de alerta es DATOS RETENIDOS.
 *  Mismo umbral que el wall (`CONSOLE_STALE_MS`): tres sondeos perdidos. */
export const SCENE_ALERT_STALE_MS = 90_000;

export default function SceneStrip() {
  const now = useNow(1000);
  // En el wall la alerta ya tiene su tarjeta anclada al escenario; la línea de
  // la franja es su eco para las otras cinco rutas (ver `WALL_ROUTE`).
  const wall = useLocation().pathname === WALL_ROUTE;
  const incidents = useLiveIncidents();
  // Sólo para NOMBRAR el sitio de la alerta: `IncidentOut` viaja con `site_id` y
  // el nombre vive en el snapshot del mapa, que /console ya sondea (misma clave
  // de react-query: en el wall no cuesta una petición más).
  const map = useMapState();
  const drill = useActiveDrill();
  const maintenance = useMaintenanceWindows();
  const demo = useDemoMode();

  const alert = sceneAlert(incidents.incidents);
  // [T-8.10 · A-063] Con los epicentros del MISMO snapshot: un aviso que la red
  // corroboró autoriza, igual que en el teléfono. Sin snapshot todavía, la
  // cuenta es desconocida y la regla cae del lado prudente (aviso).
  const kind = alertKind(alert, map.epicenters);
  const scene = resolveScene({
    // [T-7.16] La casilla la decide `sceneSlot`, no este componente: una
    // revisión entra por `notice` y la razón vive en la tabla, con ella.
    ...sceneSlot(kind),
    drill: drill.drill !== null,
    maintenance: maintenance.items.length > 0,
    demo: demo.demo?.active === true,
  });
  const alertSite =
    alert !== null ? (map.sites.find((s) => s.site_id === alert.site_id) ?? null) : null;
  const siteName = alertSite?.name ?? null;
  const siteCode = alertSite?.code ?? null;
  // El epicentro del evento del incidente, si la correlación (o la reproducción,
  // T-7.14) ya lo localizó. Sale del MISMO snapshot del mapa que ya se sondea:
  // la franja no pide nada nuevo para poder nombrarlo.
  const epicentro =
    alert?.event_id != null
      ? (map.epicenters.find((e) => e.event_id === alert.event_id) ?? null)
      : null;
  const alertStale =
    !incidents.loading &&
    incidents.error === null &&
    incidents.dataUpdatedAt > 0 &&
    now - incidents.dataUpdatedAt > SCENE_ALERT_STALE_MS
      ? incidents.dataUpdatedAt
      : null;

  return (
    <div
      className="soc-scene"
      data-scene={scene}
      data-wall={String(wall)}
      data-testid="scene-strip"
    >
      {!wall && (
        <StateFrame
          label="ALERTA"
          className="soc-drill__frame"
          loading={incidents.loading}
          error={incidents.error}
          onRetry={incidents.refetch}
          empty={alert === null}
          emptyText="SIN INCIDENTE CRÍTICO ABIERTO"
          silentEmpty
          staleSince={alertStale}
        >
          {alert !== null && kind === "review" && (
            <ReviewLine
              incident={alert}
              siteName={siteName}
              siteCode={siteCode}
              epicentro={epicentro}
              now={now}
            />
          )}
          {alert !== null && (kind === "alert" || kind === "notice") && (
            <AlertLine incident={alert} kind={kind} siteName={siteName} siteCode={siteCode} />
          )}
        </StateFrame>
      )}
      <DrillBanner data={drill} scene={scene} />
      {/* Leer QUÉ está silenciado lo gatea la API por rol (`maintenance.py`):
          a quien el servidor le dice 403 no se le pinta un fallo de lectura en
          las seis pantallas — no es un fallo, es su alcance. */}
      {!maintenance.forbidden && <MaintenanceBanner data={maintenance} />}
      <DemoModeBanner data={demo} />
    </div>
  );
}
