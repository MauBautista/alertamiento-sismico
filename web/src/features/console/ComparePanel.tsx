// [T-2.28] Comparativa histórica: sismo de referencia ↔ estación de la flota.
//
// Muestra la distancia LINEAL (epicentral) con rumbo, la hipocentral, el arribo P
// teórico y la curva PGA-vs-distancia de la ley ATTEN-LAW v1 (ver attenuation.ts).
// Los 13 sismos del catálogo son de 1985–2022 y la retención de features es de 24
// meses: NO existe PGA medido para ellos — se declara, jamás se inventa (regla de
// oro 7). Todo es "ESTIMACIÓN TEÓRICA" y el rótulo maestro lo dice en cada render.

import { useMemo, useState } from "react";

import type { CatalogEarthquakeOut, MapSiteState } from "@takab/sdk";

import Modal from "../../components/Modal";
import { bearing16, haversineKm } from "../fleet/geo";
import { attenPoints, hypoKm, pgaLawG, pTravelS, V_P_KM_S } from "./attenuation";
import { CATALOG_COLOR } from "./MapPanel";

export const MASTER_LABEL = "ESTIMACIÓN TEÓRICA · LEY DE ATENUACIÓN SIMPLE — NO ES DATO MEDIDO";
export const NO_MEASURED_NOTE =
  "SIN PGA MEDIDO — EVENTO FUERA DE LA VENTANA DE DATOS (RETENCIÓN 24 MESES)";

const CHART_W = 560;
const CHART_H = 190;
const PAD = { left: 52, right: 14, top: 16, bottom: 24 };

export interface ComparePanelProps {
  quake: CatalogEarthquakeOut;
  sites: MapSiteState[];
  initialSiteId: string | null;
  onClose: () => void;
}

export default function ComparePanel({ quake, sites, initialSiteId, onClose }: ComparePanelProps) {
  const [siteId, setSiteId] = useState<string | null>(initialSiteId ?? sites[0]?.site_id ?? null);
  const site = sites.find((s) => s.site_id === siteId) ?? null;

  const model = useMemo(() => {
    if (site === null) return null;
    const epi = { lat: quake.lat, lon: quake.lon };
    const sta = { lat: site.lat, lon: site.lon };
    const epiKm = haversineKm(sta, epi);
    const rHipo = hypoKm(epiKm, quake.depth_km);
    return {
      epiKm,
      rHipo,
      rumbo: bearing16(sta, epi),
      pArrS: pTravelS(rHipo),
      // "En el epicentro" = la ley en el punto de superficie sobre el hipocentro
      // (R mínimo = profundidad); sin profundidad degrada a la epicentral.
      pgaEpiG: pgaLawG(quake.magnitude, quake.depth_km ?? epiKm),
      pgaStaG: pgaLawG(quake.magnitude, rHipo),
    };
  }, [quake, site]);

  const originUtc = quake.origin_time.slice(0, 16).replace("T", " ");

  return (
    <Modal title="COMPARATIVA HISTÓRICA" onClose={onClose}>
      <div className="soc-compare" data-testid="compare-panel">
        <p className="soc-compare__ctx">
          <span className="soc-mono" style={{ color: CATALOG_COLOR }}>
            M {quake.magnitude.toFixed(1)}
          </span>{" "}
          · {quake.place} · {originUtc} UTC · fuente {quake.source}
          {quake.depth_km !== null && ` · prof ${quake.depth_km.toFixed(0)} km`}
        </p>

        <label className="soc-meta" htmlFor="compare-site">
          ESTACIÓN / SITIO A COMPARAR
        </label>
        {sites.length === 0 ? (
          <p className="soc-compare__note" role="note">
            SIN SITIOS CON COORDENADAS EN EL TENANT
          </p>
        ) : (
          <select
            id="compare-site"
            className="soc-user__input"
            value={siteId ?? ""}
            onChange={(e) => setSiteId(e.target.value)}
          >
            {sites.map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.name}
              </option>
            ))}
          </select>
        )}

        {model !== null && site !== null && (
          <>
            <dl className="soc-compare__facts">
              <div>
                <dt>DISTANCIA EPICENTRAL</dt>
                <dd className="soc-mono">
                  {Math.round(model.epiKm)} km {model.rumbo}
                </dd>
              </div>
              <div>
                <dt>DISTANCIA HIPOCENTRAL</dt>
                <dd className="soc-mono">{Math.round(model.rHipo)} km</dd>
              </div>
              <div>
                <dt>ARRIBO P TEÓRICO</dt>
                <dd className="soc-mono">
                  ~{Math.round(model.pArrS)} s · v_P {V_P_KM_S} km/s
                </dd>
              </div>
              <div>
                <dt>PGA EST. EPICENTRO</dt>
                <dd className="soc-mono">{model.pgaEpiG.toFixed(3)} g</dd>
              </div>
              <div>
                <dt>PGA EST. ESTACIÓN</dt>
                <dd className="soc-mono">{model.pgaStaG.toFixed(3)} g</dd>
              </div>
            </dl>
            {quake.depth_km === null && (
              <p className="soc-compare__note" role="note">
                SIN PROFUNDIDAD REPORTADA — la hipocentral degrada a la epicentral
              </p>
            )}
            <AttenChart quake={quake} epiKm={model.epiKm} siteName={site.name} />
            <p className="soc-compare__note" role="note" data-testid="compare-no-measured">
              {NO_MEASURED_NOTE}
            </p>
          </>
        )}

        <p className="soc-compare__master" role="note">
          {MASTER_LABEL}
        </p>
      </div>
    </Modal>
  );
}

/** Curva SVG: X lineal (km), Y log por décadas — la ley decae ~1/R y en Y lineal
 * la cola sería una raya pegada al cero. Banda ilustrativa ×3/÷3 (las leyes de
 * atenuación reales dispersan ~1 orden de magnitud). */
function AttenChart({
  quake,
  epiKm,
  siteName,
}: {
  quake: CatalogEarthquakeOut;
  epiKm: number;
  siteName: string;
}) {
  const maxKm = Math.max(epiKm * 1.25, 50);
  const depth = quake.depth_km;
  const points = attenPoints(quake.magnitude, depth, maxKm);
  const vMax = pgaLawG(quake.magnitude, Math.max(depth ?? 1, 1));
  const vEnd = pgaLawG(quake.magnitude, hypoKm(maxKm, depth)) / 3;
  const eTop = Math.ceil(Math.log10(vMax));
  const eBot = Math.floor(Math.log10(Math.max(vEnd, 1e-7)));
  const innerW = CHART_W - PAD.left - PAD.right;
  const innerH = CHART_H - PAD.top - PAD.bottom;
  const xOf = (km: number) => PAD.left + (km / maxKm) * innerW;
  const yOf = (g: number) =>
    PAD.top + ((eTop - Math.log10(Math.max(g, 1e-9))) / (eTop - eBot)) * innerH;
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xOf(p.km).toFixed(1)} ${yOf(p.g).toFixed(1)}`)
    .join(" ");
  const band = [
    ...points.map(
      (p, i) => `${i === 0 ? "M" : "L"} ${xOf(p.km).toFixed(1)} ${yOf(p.g * 3).toFixed(1)}`,
    ),
    ...[...points].reverse().map((p) => `L ${xOf(p.km).toFixed(1)} ${yOf(p.g / 3).toFixed(1)}`),
    "Z",
  ].join(" ");
  const decades: number[] = [];
  for (let e = eTop; e >= eBot; e -= 1) decades.push(e);
  const staG = pgaLawG(quake.magnitude, hypoKm(epiKm, depth));
  const epiG = pgaLawG(quake.magnitude, depth ?? epiKm);

  return (
    <svg
      className="soc-compare__chart"
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      role="img"
      aria-label={`Curva de atenuación estimada de M ${quake.magnitude.toFixed(1)} hasta ${siteName}`}
      data-testid="compare-chart"
    >
      {decades.map((e) => (
        <g key={e}>
          <line
            x1={PAD.left}
            x2={CHART_W - PAD.right}
            y1={yOf(10 ** e)}
            y2={yOf(10 ** e)}
            stroke="rgba(240,242,245,0.10)"
          />
          <text x={4} y={yOf(10 ** e) + 3} className="soc-compare__tick">
            {e >= 0 ? `${10 ** e} g` : `${(10 ** e).toFixed(Math.min(-e, 6))} g`}
          </text>
        </g>
      ))}
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <text key={f} x={xOf(maxKm * f) - 10} y={CHART_H - 8} className="soc-compare__tick">
          {Math.round(maxKm * f)} km
        </text>
      ))}
      <path d={band} fill="rgba(124,231,255,0.08)" stroke="none" />
      <path d={path} fill="none" stroke={CATALOG_COLOR} strokeWidth={1.6} />
      {/* epicentro en x=0 */}
      <circle cx={xOf(0)} cy={yOf(epiG)} r={5} fill="none" stroke="#E040FB" strokeWidth={1.6} />
      <text x={xOf(0) + 8} y={yOf(epiG) - 5} className="soc-compare__mark">
        EPICENTRO
      </text>
      {/* estación en x=epiKm */}
      <rect x={xOf(epiKm) - 3.5} y={yOf(staG) - 3.5} width={7} height={7} fill="#F0F2F5" />
      <text
        x={Math.min(xOf(epiKm) + 8, CHART_W - PAD.right - 90)}
        y={yOf(staG) + 12}
        className="soc-compare__mark"
      >
        {siteName.toUpperCase().slice(0, 18)} · {Math.round(epiKm)} km
      </text>
      <text x={PAD.left} y={PAD.top - 4} className="soc-compare__tick">
        BANDA ILUSTRATIVA ×3 / ÷3 · ATTEN-LAW v1
      </text>
    </svg>
  );
}
