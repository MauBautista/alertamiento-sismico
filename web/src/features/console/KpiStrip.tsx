// [T-2.50] Tira de KPIs del wall — semáforo de estado tipo Güralp.
//
// CERO endpoints nuevos: todo sale del snapshot del mapa y de la cola de
// incidentes que la pantalla ya pide.
//
// Dos reglas que esta tira existe para respetar:
//
//  · **Los KPIs se cuentan siempre sobre el TOTAL** del alcance del operador, y el
//    recorte del viewport se declara aparte (`MOSTRANDO n DE N`). Un contador que
//    baja al hacer zoom, sin decir que bajó por el zoom, es un dato falso.
//  · **Ausencia ≠ cero.** Sin latencia reportada se pinta `S/D`; "0 ms" se leería
//    como un enlace perfecto (regla de oro 7).

import { Activity, EyeOff, Radio } from "lucide-react";

import { LINK_DEGRADADO, LINK_OPERATIVO, LINK_SIN_ENLACE, LINK_SIN_GABINETE } from "./link";
import { showingLabel, type ConsoleKpis } from "./stats";

export interface KpiStripProps {
  /** KPIs del TOTAL visible para el operador (no del viewport). */
  kpis: ConsoleKpis;
  /** Estaciones realmente pintadas ahora mismo (viewport ∩ filtros). */
  shown: number;
  hideNoLink: boolean;
  onToggleHideNoLink: () => void;
}

type Tone = "ok" | "warn" | "crit" | "muted";

function Kpi({
  label,
  value,
  tone = "muted",
  hint,
}: {
  label: string;
  value: string;
  tone?: Tone;
  hint?: string;
}) {
  return (
    <div className={`soc-kpi soc-kpi--${tone}`} title={hint}>
      <span className="soc-kpi__value">{value}</span>
      <span className="soc-kpi__label">{label}</span>
    </div>
  );
}

/** `null` ⇒ S/D. Jamás 0: un cero se lee como una medición perfecta. */
function num(value: number | null, unit: string, digits = 0): string {
  return value === null ? "S/D" : `${value.toFixed(digits)} ${unit}`;
}

export default function KpiStrip({ kpis, shown, hideNoLink, onToggleHideNoLink }: KpiStripProps) {
  return (
    <section className="soc-kpis" data-testid="kpi-strip" aria-label="Indicadores de la red">
      <div className="soc-kpis__group">
        <span className="soc-kpis__title">
          <Radio size={13} aria-hidden style={{ color: "var(--tk-cyan)" }} />
          ENLACE
        </span>
        <Kpi label={LINK_OPERATIVO} value={String(kpis.operativo)} tone="ok" />
        <Kpi label={LINK_DEGRADADO} value={String(kpis.degradado)} tone="warn" />
        {/* Las CAÍDAS y las estaciones sin hardware NO se suman: mandan a un
            técnico a sitios distintos (T-2.46). */}
        <Kpi
          label={LINK_SIN_ENLACE}
          value={String(kpis.sinEnlace)}
          tone="crit"
          hint="Gabinetes que dejaron de reportar (caídas)"
        />
        <Kpi
          label={LINK_SIN_GABINETE}
          value={String(kpis.sinGabinete)}
          tone="muted"
          hint="Estaciones sin gabinete instalado: no es una caída"
        />
      </div>

      <div className="soc-kpis__group">
        <span className="soc-kpis__title">
          <Activity size={13} aria-hidden style={{ color: "var(--tk-cyan)" }} />
          LATENCIA
        </span>
        <Kpi label="MQTT p50" value={num(kpis.rttP50Ms, "ms")} />
        <Kpi label="MQTT máx" value={num(kpis.rttMaxMs, "ms")} />
        <Kpi label="LAG SEEDLINK máx" value={num(kpis.lagMaxS, "s", 1)} />
      </div>

      <div className="soc-kpis__group">
        <span className="soc-kpis__title">SACUDIDA</span>
        <Kpi
          label="SUPERÓ DISPARO"
          value={String(kpis.trip)}
          tone={kpis.trip > 0 ? "crit" : "ok"}
        />
        <Kpi label="SUPERÓ CAUTELA" value={String(kpis.watch)} tone="warn" />
        <Kpi
          label="SIN MEDICIÓN"
          value={String(kpis.feltDesconocido)}
          tone="muted"
          hint="No reportó: NO significa que no se haya movido"
        />
        <Kpi
          label="INCIDENTES"
          value={`${kpis.incidentesCriticos}/${kpis.incidentesAbiertos}`}
          tone={kpis.incidentesCriticos > 0 ? "crit" : "ok"}
          hint="Críticos / abiertos"
        />
      </div>

      <div className="soc-kpis__group soc-kpis__group--end">
        <span className="soc-kpis__showing" data-testid="kpi-showing">
          {showingLabel(shown, kpis.stations)}
        </span>
        <button
          type="button"
          className={`soc-kpis__filter${hideNoLink ? " soc-kpis__filter--on" : ""}`}
          data-testid="hide-no-link"
          aria-pressed={hideNoLink}
          onClick={onToggleHideNoLink}
        >
          <EyeOff size={12} aria-hidden /> OCULTAR SIN ENLACE
        </button>
      </div>
    </section>
  );
}
