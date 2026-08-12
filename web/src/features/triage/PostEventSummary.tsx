// Resumen post-evento (T-2.40), calcado del "Post-ShakeAlert Message Summary" de USGS.
//
// Tras cada sismo relevante, USGS publica un post-mortem estandarizado: qué tan lejos
// quedó el epicentro estimado, qué tan lejos la magnitud, cuánto tiempo de aviso hubo
// y cuántas estaciones contribuyeron. Es el documento que convierte "el sistema
// funcionó" en una afirmación verificable — y el que una Protección Civil pide cuando
// evalúa si el servicio vale lo que cuesta.
//
// Los cuatro números salen de `/forensics`. Cuando alguno no se puede calcular se dice
// POR QUÉ: un "0 s de aviso" sin explicación se lee como un fallo del sistema, cuando
// casi siempre significa que ese incidente ni siquiera vino de SASMEX.

import StateFrame from "../../components/StateFrame";
import type { ForensicsOut } from "@takab/sdk";
import type { ForensicsState } from "./useForensics";

const LEAD_REASON: Record<string, string> = {
  not_sasmex: "NO APLICA · el incidente no vino de SASMEX",
  no_peak: "SIN PICO MEDIDO EN LA VENTANA",
  peak_before_alert: "EL PICO PRECEDIÓ A LA ALERTA",
};

function Tile({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "ok" | "warn" | "idle";
}) {
  return (
    <div className={`postevent__tile${tone ? ` postevent__tile--${tone}` : ""}`}>
      <div className="postevent__lbl">{label}</div>
      <div className="postevent__val">{value}</div>
      {note && <div className="postevent__note">{note}</div>}
    </div>
  );
}

export function leadTimeView(f: ForensicsOut): {
  value: string;
  note?: string;
  tone: "ok" | "idle";
} {
  if (f.lead_time_s === null || f.lead_time_s === undefined) {
    return {
      value: "NO CALCULABLE",
      note: LEAD_REASON[f.lead_time_reason ?? ""] ?? f.lead_time_reason ?? undefined,
      tone: "idle",
    };
  }
  return { value: `${f.lead_time_s.toFixed(1)} s`, tone: "ok" };
}

export function catalogView(f: ForensicsOut): { value: string; note?: string } {
  if (!f.catalog || !f.catalog_delta) {
    return {
      value: "SIN COINCIDENCIA",
      note: "Ningún sismo del catálogo de referencia dentro de ±120 s.",
    };
  }
  const d = f.catalog_delta;
  const dist =
    d.km === null || d.km === undefined
      ? "SIN EPICENTRO PROPIO"
      : `${Math.round(d.km)} km ${d.bearing ?? ""}`.trim();
  return {
    value: dist,
    note: `${f.catalog.source} ${f.catalog.catalog_key}${
      f.catalog.magnitude !== null && f.catalog.magnitude !== undefined
        ? ` · M ${f.catalog.magnitude.toFixed(1)}`
        : ""
    } · Δt ${d.dt_s.toFixed(0)} s`,
  };
}

export default function PostEventSummary({ forensics }: { forensics: ForensicsState }) {
  const f = forensics.data;
  return (
    <div className="soc-card postevent" data-testid="post-event-summary">
      <div className="soc-card__hd">
        <div>
          <div>Resumen post-evento</div>
          <div className="soc-card__sub">
            DESEMPEÑO DE LA RED · CONTRASTE CON EL CATÁLOGO DE REFERENCIA
          </div>
        </div>
      </div>
      <StateFrame
        label="RESUMEN POST-EVENTO"
        loading={forensics.loading}
        error={forensics.error}
        onRetry={forensics.refetch}
        empty={f !== undefined && (f.channels ?? []).length === 0 && (f.station_count ?? 0) === 0}
        emptyText="SIN MEDICIONES NI VOTOS PARA ESTE INCIDENTE"
        // [T-2.82.a] El tiempo de aviso ganado y las estaciones que
        // contribuyeron son los números que se citan como desempeño de la red
        // ante una Protección Civil — y congelados se citan exactamente igual.
        // La edad la resuelve `useForensics` con el reloj de toda la pantalla;
        // aquí sólo se declara.
        staleSince={forensics.staleSince}
      >
        {f && (
          <div className="postevent__grid">
            <Tile
              label="TIEMPO DE AVISO GANADO"
              value={leadTimeView(f).value}
              note={leadTimeView(f).note}
              tone={leadTimeView(f).tone}
            />
            <Tile
              label="ESTACIONES QUE CONTRIBUYERON"
              value={String(f.station_count ?? 0)}
              note={(f.station_count ?? 0) === 0 ? "Sin corroboración multi-estación" : undefined}
              tone={(f.station_count ?? 0) >= 3 ? "ok" : "idle"}
            />
            <Tile label="Δ VS CATÁLOGO" value={catalogView(f).value} note={catalogView(f).note} />
            <Tile
              label="PICO MEDIDO"
              value={
                f.peak_pga_g === null || f.peak_pga_g === undefined
                  ? "SIN MEDICIÓN"
                  : `${f.peak_pga_g.toFixed(3)} g`
              }
              // Sin procedencia de calibración el número NO está en gravedades: es un
              // valor relativo, y presentarlo como física sería inventarla.
              note={f.calibrated ? undefined : "UNIDADES RELATIVAS · SENSOR SIN CALIBRAR"}
              tone={f.calibrated ? undefined : "warn"}
            />
          </div>
        )}
      </StateFrame>
    </div>
  );
}
