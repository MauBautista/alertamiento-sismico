// Dashboard de edificio (T-1.35). Última página placeholder del árbol.
//
// ALCANCE: es la vista del **staff con sesión** — `building_admin`, `inspector` y los
// roles SOC (RBAC §2, columna "Dash Edificio"). **No es la pantalla del ocupante**:
// `occupant`, `brigadista` y `security_guard` tienen `allowed_routes = []` y su
// superficie es la app móvil (T-1.31, diferida). Según US-05, la interfaz del ocupante
// es la SIRENA, no un navegador; y la página local del gabinete es el panel del
// guardia, no una vista pública.
//
// El LiveSocket lo posee AppShell desde T-1.49; esta página lo consume por
// contexto (la salud del gabinete llega por frames `site_state`, no por poll).

import { useState } from "react";
import { useParams } from "react-router";

import { getSiteSitesSiteIdGet } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import StateFrame from "../../components/StateFrame";
import SevTag from "../../components/SevTag";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import { useSiteSoh } from "../console/useSiteSoh";
import HistoryChart from "../telemetry/HistoryChart";
import MultiChannelStrip from "../telemetry/MultiChannelStrip";
import { CHANNELS_STALE_MS, useSiteChannels } from "../telemetry/useSiteChannels";
import { useSiteMetrics } from "../telemetry/useSiteMetrics";
import type { HistoryPreset } from "../telemetry/useSiteMetrics";
import SirenTestPanel from "./SirenTestPanel";
import { SITE_INCIDENTS_STALE_MS, useSiteIncidents } from "./useSiteIncidents";
import { useSirenTest } from "./useSirenTest";

function BuildingDashboard({ siteId }: { siteId: string }) {
  const me = useSessionStore((s) => s.me);
  const now = useNow(1000);
  const [preset, setPreset] = useState<HistoryPreset>("24h");

  const site = useQuery({
    queryKey: ["site", siteId],
    queryFn: async () => {
      const { data, response } = await getSiteSitesSiteIdGet({ path: { site_id: siteId } });
      if (data === undefined) throw new Error(`GET /sites/${siteId} falló (${response.status})`);
      return data;
    },
  });

  const channels = useSiteChannels(siteId);
  const metrics = useSiteMetrics(siteId, preset);
  const incidents = useSiteIncidents(siteId);
  const soh = useSiteSoh(siteId);
  const siren = useSirenTest(siteId);

  const channelsStale =
    !channels.loading &&
    channels.dataUpdatedAt > 0 &&
    now - channels.dataUpdatedAt > CHANNELS_STALE_MS
      ? channels.dataUpdatedAt
      : null;
  const incidentsStale =
    !incidents.loading &&
    incidents.dataUpdatedAt > 0 &&
    now - incidents.dataUpdatedAt > SITE_INCIDENTS_STALE_MS
      ? incidents.dataUpdatedAt
      : null;

  return (
    <section className="bld" data-screen-label="05 Dashboard Edificio">
      <header className="bld__hd">
        {/* El h1 es el título de la PÁGINA: existe antes de que el sitio cargue y no
            cambia con los datos. El nombre del edificio va debajo. */}
        <h1 className="bld__title">DASHBOARD EDIFICIO</h1>
        {/* B-4 (T-1.58): el subtítulo distingue "cargando" de "falló" — un GET
            /sites/{id} caído no puede quedarse en "CARGANDO…" eterno. */}
        <p className="bld__name">
          {site.data?.name ??
            (site.isError ? (
              <>
                SITIO NO DISPONIBLE{" "}
                <button
                  type="button"
                  className="soc-btn soc-btn--secondary"
                  onClick={() => void site.refetch()}
                >
                  REINTENTAR
                </button>
              </>
            ) : (
              "CARGANDO SITIO…"
            ))}
        </p>
        <p className="bld__sub soc-mono">
          <span>{siteId}</span>
          {site.data && (
            <span>
              {" · "}
              {site.data.code} · {site.data.lat.toFixed(4)}, {site.data.lon.toFixed(4)}
            </span>
          )}
        </p>
      </header>

      <div className="bld__grid">
        <div className="bld__card" data-testid="channels-card">
          <header className="bld__cardhd">
            <h2>FEATURES 1 s · POR CANAL</h2>
          </header>
          <StateFrame
            label="CANALES DEL SITIO"
            loading={channels.loading}
            error={channels.error}
            onRetry={channels.refetch}
            empty={channels.channels.length === 0}
            emptyText="SIN FEATURES EN LOS ÚLTIMOS 10 MIN"
            staleSince={channelsStale}
          >
            <MultiChannelStrip channels={channels.channels} calibrated={channels.calibrated} />
          </StateFrame>
        </div>

        <div className="bld__card" data-testid="history-card">
          <StateFrame
            label="HISTORIAL DEL SITIO"
            loading={metrics.loading}
            error={metrics.error}
            onRetry={metrics.refetch}
            empty={metrics.points.length === 0}
            emptyText="SIN MÉTRICAS EN EL RANGO"
          >
            <HistoryChart
              points={metrics.points}
              bucket={metrics.bucket}
              calibrated={metrics.calibrated}
              preset={preset}
              onPreset={setPreset}
            />
          </StateFrame>
        </div>

        <div className="bld__card" data-testid="soh-card">
          <header className="bld__cardhd">
            <h2>SALUD DEL GABINETE</h2>
          </header>
          {/* Sin frame todavía ⇒ S/D. Nunca se inventa salud (regla de oro 10). */}
          <dl className="bld__soh soc-mono">
            <div>
              <dt>NTP OFFSET</dt>
              <dd>
                {soh?.ntp_offset_ms != null
                  ? `±${Math.abs(soh.ntp_offset_ms).toFixed(0)} ms`
                  : "S/D"}
              </dd>
            </div>
            <div>
              <dt>LAG SEEDLINK</dt>
              <dd>{soh?.seedlink_lag_s != null ? `${soh.seedlink_lag_s.toFixed(1)} s` : "S/D"}</dd>
            </div>
            <div>
              <dt>ALIMENTACIÓN</dt>
              <dd>{soh?.power_status ?? "S/D"}</dd>
            </div>
          </dl>
        </div>

        <SirenTestPanel siren={siren} canTest={me?.allowed_actions.siren_test === true} />

        <div className="bld__card bld__card--wide" data-testid="incidents-card">
          <header className="bld__cardhd">
            <h2>INCIDENTES DEL SITIO</h2>
          </header>
          <StateFrame
            label="INCIDENTES DEL SITIO"
            loading={incidents.loading}
            error={incidents.error}
            onRetry={incidents.refetch}
            empty={incidents.incidents.length === 0}
            emptyText="SIN INCIDENTES REGISTRADOS"
            staleSince={incidentsStale}
          >
            <table className="bld__table">
              <thead>
                <tr>
                  <th>APERTURA (UTC)</th>
                  <th>SEVERIDAD</th>
                  <th>ESTADO</th>
                  <th>DISPARO</th>
                </tr>
              </thead>
              <tbody>
                {incidents.incidents.map((i) => (
                  <tr key={i.incident_id}>
                    <td className="soc-mono">{i.opened_at.slice(0, 19).replace("T", " ")}</td>
                    <td>
                      <SevTag severity={i.severity} />
                    </td>
                    <td className="soc-mono">{i.state.toUpperCase()}</td>
                    <td className="soc-mono">{i.trigger.toUpperCase()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </StateFrame>
        </div>
      </div>
    </section>
  );
}

/** Página /building/:siteId — consume el LiveSocket del shell (dueño: AppShell). */
export default function BuildingPage() {
  const { siteId } = useParams<"siteId">();

  if (siteId === undefined) {
    return (
      <section className="soc-placeholder">
        <h1>DASHBOARD EDIFICIO</h1>
        <p className="soc-screen__sub">FALTA EL SITIO EN LA RUTA</p>
      </section>
    );
  }

  return <BuildingDashboard siteId={siteId} />;
}
