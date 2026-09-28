// [T-9.66 · D-46] HISTORIAL SÍSMICO DEL INMUEBLE.
//
// Dos clases de fila en una sola lista por fecha, y no se disfrazan una de otra:
//   · el INCIDENTE es lo que MIDIÓ el gabinete: severidad, estado, clasificación
//     y PGA MEDIDA, con enlace al triage;
//   · el SISMO del catálogo es lo que ahí se habría SENTIDO: magnitud de catálogo
//     (post-hoc, no «preliminar»), lugar, distancia y MMI ESTIMADA (Wald 1999),
//     pintada con la escala compartida con la app (`escalaSismos.ts`), y enlace
//     a su página de USGS.

import { Link } from "react-router";

import SevTag from "../../components/SevTag";
import StateFrame from "../../components/StateFrame";
import Table from "../../components/Table";
import { useNow } from "../../lib/useNow";
import { colorDeMmi } from "../console/escalaSismos";
import { CLASIFICACIONES } from "../triage/useClassification";
import {
  HISTORIAL_DIAS,
  HISTORIAL_STALE_MS,
  useHistorialSismico,
  type EventoHistorial,
} from "./useHistorialSismico";

const ESTADOS: Record<string, string> = {
  open: "ABIERTO",
  acked: "ATENDIDO",
  in_review: "EN REVISIÓN",
  closed: "CERRADO",
};

type Incidente = Extract<EventoHistorial, { incident_id: string }>;
type Sismo = Extract<EventoHistorial, { mmi_estimada: number }>;

function esIncidente(e: EventoHistorial): e is Incidente {
  return e.tipo === "incidente" || (e.tipo === undefined && "incident_id" in e);
}

function fechaDe(e: EventoHistorial): string {
  return esIncidente(e) ? e.opened_at : (e as Sismo).origin_time;
}

function utc(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

function clasificacion(valor: string | null): string {
  if (valor === null) return "SIN CLASIFICAR";
  return CLASIFICACIONES.find((c) => c.value === valor)?.label ?? valor.toUpperCase();
}

function FilaIncidente({ e, canTriage }: { e: Incidente; canTriage: boolean }) {
  const fecha = utc(e.opened_at);
  return (
    <tr data-testid="historial-incidente">
      <td className="soc-mono">
        {canTriage ? (
          <Link className="soc-link" to={`/triage?incident=${e.incident_id}`}>
            {fecha}
          </Link>
        ) : (
          fecha
        )}
      </td>
      <td>
        <span className="bld-hist__kind">INCIDENTE</span>
      </td>
      <td>
        <span className="bld-hist__what">
          <SevTag severity={e.severity} />
          <span className="soc-mono">{ESTADOS[e.estado] ?? e.estado.toUpperCase()}</span>
          <span className="soc-mono">{clasificacion(e.clasificacion)}</span>
        </span>
      </td>
      <td className="soc-mono">
        PGA MEDIDA {e.pga_medida_g === null ? "—" : `${e.pga_medida_g.toFixed(3)} g`}
      </td>
    </tr>
  );
}

function FilaSismo({ e }: { e: Sismo }) {
  const color = colorDeMmi(e.mmi_estimada);
  return (
    <tr data-testid="historial-sismo">
      <td className="soc-mono">{utc(e.origin_time)}</td>
      <td>
        <span className="bld-hist__kind bld-hist__kind--sismo">SISMO · CATÁLOGO</span>
      </td>
      <td>
        <span className="bld-hist__what">
          <span className="soc-mono bld-hist__mag">M {e.magnitude.toFixed(1)}</span>
          <span>{e.place}</span>
          <span className="soc-mono">{Math.round(e.dist_km)} km</span>
          {e.usgs_url !== null && (
            <a className="soc-link" href={e.usgs_url} target="_blank" rel="noopener noreferrer">
              USGS
            </a>
          )}
        </span>
      </td>
      <td className="soc-mono">
        <span className="bld-hist__mmi">
          <span
            className="bld-hist__chip"
            data-testid="historial-mmi"
            style={color === null ? undefined : { background: color }}
            aria-hidden
          />
          MMI ESTIMADA {e.mmi_romano}
        </span>
      </td>
    </tr>
  );
}

export default function HistorialSismicoCard({
  siteId,
  canTriage,
}: {
  siteId: string;
  canTriage: boolean;
}) {
  const historial = useHistorialSismico(siteId);
  const now = useNow(1000);
  const stale =
    !historial.loading &&
    historial.dataUpdatedAt > 0 &&
    now - historial.dataUpdatedAt > HISTORIAL_STALE_MS
      ? historial.dataUpdatedAt
      : null;
  // El servidor ya ordena; aquí se vuelve a ordenar para no depender de ello.
  const eventos = [...historial.eventos].sort((a, b) => fechaDe(b).localeCompare(fechaDe(a)));

  return (
    <div className="bld__card bld__card--wide" data-testid="historial-card">
      <header className="bld__cardhd">
        <h2>HISTORIAL SÍSMICO DEL INMUEBLE</h2>
        <span className="bld-hist__window soc-mono">ÚLTIMOS {HISTORIAL_DIAS} DÍAS</span>
      </header>
      <StateFrame
        label="HISTORIAL SÍSMICO DEL INMUEBLE"
        loading={historial.loading}
        error={historial.error}
        onRetry={historial.refetch}
        empty={eventos.length === 0}
        emptyText={`SIN INCIDENTES NI SISMOS SENTIDOS (MMI ESTIMADA ≥ III) EN ${HISTORIAL_DIAS} DÍAS`}
        staleSince={stale}
      >
        <Table densa>
          <thead>
            <tr>
              <th>FECHA (UTC)</th>
              <th>TIPO</th>
              <th>EVENTO</th>
              <th>EN EL INMUEBLE</th>
            </tr>
          </thead>
          <tbody>
            {eventos.map((e) =>
              esIncidente(e) ? (
                <FilaIncidente key={`i-${e.incident_id}`} e={e} canTriage={canTriage} />
              ) : (
                <FilaSismo
                  key={`s-${(e as Sismo).origin_time}-${(e as Sismo).place}`}
                  e={e as Sismo}
                />
              ),
            )}
          </tbody>
        </Table>
        {historial.atribucion !== null && (
          <p className="bld-hist__attr" data-testid="historial-atribucion">
            {historial.atribucion}
          </p>
        )}
      </StateFrame>
    </div>
  );
}
