import type {
  DictamenOut,
  EvidenceObject,
  IncidentOut,
  QuorumVoteOut,
  RuleSetOut,
  SeismicEventOut,
  SiteOut,
} from "@takab/sdk";

import { citaDeProcedencia, pintaCifra, rotuloProcedencia } from "./procedencia";

/** Estados del CHECK de ``dictamens.status`` (db/schema.sql), de menor a mayor gravedad. */
export type DictamenStatus =
  | "normal_operation"
  | "inhabit_monitor"
  | "restricted"
  | "no_inhabit_inspect";

export type VerdictKind = "ok" | "warn" | "crit";

const VERDICT: Record<DictamenStatus, { label: string; kind: VerdictKind }> = {
  normal_operation: { label: "OPERACIÓN NORMAL", kind: "ok" },
  inhabit_monitor: { label: "HABITAR · MONITOREO", kind: "warn" },
  restricted: { label: "ACCESO RESTRINGIDO", kind: "warn" },
  no_inhabit_inspect: { label: "NO HABITAR · INSPECCIÓN", kind: "crit" },
};

/** Los 4 status que el inspector puede firmar (orden del DDL). */
export const SIGNABLE_STATUS: readonly DictamenStatus[] = [
  "normal_operation",
  "inhabit_monitor",
  "restricted",
  "no_inhabit_inspect",
];

/** Etiqueta del veredicto. Status desconocido se muestra CRUDO en ámbar: jamás
 * se degrada a "operación normal" un valor que no entendemos. */
export function verdictOf(status: string): { label: string; kind: VerdictKind } {
  return VERDICT[status as DictamenStatus] ?? { label: status.toUpperCase(), kind: "warn" };
}

/**
 * Cabeza de la cadena de dictámenes. El servidor la devuelve más-reciente-primero
 * (``queries/dictamens.select_dictamens``); no reordenamos por ``created_at`` porque
 * dos versiones pueden compartir timestamp y el orden del servidor es el autoritativo.
 */
export function chainHead(dictamens: DictamenOut[] | undefined): DictamenOut | null {
  return dictamens && dictamens.length > 0 ? dictamens[0] : null;
}

/** ``signed_by IS NULL`` ⇒ dictamen automático preliminar (schemas/dictamens.py). */
export function isPreliminary(d: DictamenOut | null): boolean {
  return d !== null && d.signed_by === null;
}

export interface TriageRow {
  incident: IncidentOut;
  /** Contexto sísmico del catálogo; null si el incidente no referencia evento. */
  event: SeismicEventOut | null;
  siteName: string;
  /** ``seismic_events.meta.node_count`` (lo escribe el motor de incidentes). */
  nodeCount: number | null;
}

function nodeCountOf(event: SeismicEventOut | null): number | null {
  const raw = event?.meta["node_count"];
  return typeof raw === "number" ? raw : null;
}

/**
 * Fila del historial = incidente (por sitio: PGA/PGV/severidad/estado) enriquecido
 * con su evento sísmico (magnitud/epicentro/nodos). Ningún endpoint devuelve esta
 * forma: el mockup confundía evento y incidente, y se compone en el cliente.
 */
export function buildRows(
  incidents: IncidentOut[] | undefined,
  events: SeismicEventOut[] | undefined,
  sites: SiteOut[] | undefined,
): TriageRow[] {
  if (!incidents) {
    return [];
  }
  const byEvent = new Map((events ?? []).map((e) => [e.event_id, e]));
  const bySite = new Map((sites ?? []).map((s) => [s.site_id, s]));
  return incidents.map((incident) => {
    const event = incident.event_id ? (byEvent.get(incident.event_id) ?? null) : null;
    return {
      incident,
      event,
      siteName: bySite.get(incident.site_id)?.name ?? `SITIO ${incident.site_id.slice(0, 8)}`,
      nodeCount: nodeCountOf(event),
    };
  });
}

export interface QuorumNode {
  sensorId: string;
  /** Código del sitio, serial del sensor, o "OTRA RED" si la RLS lo oculta. */
  label: string;
  /** true = el voto viene de una estación que este tenant no puede ver. */
  foreign: boolean;
  deltaS: number | null;
  counted: boolean;
  isAnchor: boolean;
}

export interface QuorumView {
  nodes: QuorumNode[];
  /** Votos que el motor contó para el quórum. */
  countedNodes: number;
}

/**
 * Fuente de ``seismic_events`` que el motor de quórum de la NUBE escribe SÓLO
 * cuando el quórum se alcanzó (``incident/engine.py``: "cuando alcanzan el quórum
 * crea UN seismic_events (source 'local_quorum') + quorum_votes por miembro").
 */
export const CORROBORATED_SOURCE = "local_quorum";

/**
 * ¿El quórum se cumplió? Es un HECHO DEL SERVIDOR, no una comparación del cliente.
 *
 * Re-derivarlo como ``countedNodes >= min_nodes`` del rule_set activo es incorrecto:
 * el motor prefiere el rule_set de SITIO sobre el de tenant y evalúa con la versión
 * vigente en su momento, así que un `min_nodes` editado después —o de otro scope—
 * produciría un veredicto que jamás se aplicó a este evento histórico.
 */
export function isCorroborated(event: { source: string } | null | undefined): boolean {
  return event?.source === CORROBORATED_SOURCE;
}

/**
 * Offsets por nodo de la regla de quórum. ``delta_s`` viene del motor
 * (``incident/quorum.py``: detected_at − ancla). El ancla es la detección más
 * temprana ⇒ el menor ``delta_s``; si ninguno lo trae, el ``detected_at`` menor.
 */
export function quorumView(votes: QuorumVoteOut[] | undefined): QuorumView {
  const list = votes ?? [];
  let anchorId: string | null = null;
  if (list.length > 0) {
    const withDelta = list.filter((v) => v.delta_s !== null);
    const pool = withDelta.length > 0 ? withDelta : list;
    const anchor = pool.reduce((best, v) => {
      if (withDelta.length > 0) {
        return (v.delta_s as number) < (best.delta_s as number) ? v : best;
      }
      return v.detected_at < best.detected_at ? v : best;
    });
    anchorId = anchor.sensor_id;
  }
  const nodes = list.map((v) => {
    // [T-2.39] El servidor resuelve el nombre bajo RLS. Que venga nulo NO es un
    // fallo: significa que el voto es de una estación de otro cliente, y decirlo
    // es más honesto —y más útil— que ocho hex de un uuid.
    const named = v.site_code ?? v.station_serial ?? null;
    return {
      sensorId: v.sensor_id,
      label: named ?? "OTRA RED",
      foreign: named === null,
      deltaS: v.delta_s,
      counted: v.counted,
      isAnchor: v.sensor_id === anchorId,
    };
  });
  return { nodes, countedNodes: nodes.filter((n) => n.counted).length };
}

/**
 * Config del rule_set ACTIVO que aplica a un sitio, resuelto como lo hace el motor
 * (`incident/engine.py` y `commands/sync.py`): scope `site` preferente sobre
 * `tenant`, y a igualdad de scope la versión más alta.
 */
export function activeConfigFor(
  ruleSets: RuleSetOut[] | undefined,
  siteId: string | null,
): Record<string, unknown> | undefined {
  const active = (ruleSets ?? []).filter((r) => r.is_active);
  const applicable = active.filter(
    (r) => (r.scope_type === "site" && r.scope_id === siteId) || r.scope_type === "tenant",
  );
  if (applicable.length === 0) {
    return undefined;
  }
  const best = applicable.reduce((a, b) => {
    const aSite = a.scope_type === "site" ? 1 : 0;
    const bSite = b.scope_type === "site" ? 1 : 0;
    if (aSite !== bSite) {
      return aSite > bSite ? a : b;
    }
    return b.version > a.version ? b : a;
  });
  return best.config;
}

/** ``config.quorum.min_nodes`` del rule_set activo; null si no está configurado.
 * Se muestra como CONTEXTO de la configuración actual, nunca como veredicto de un
 * evento pasado (ver ``isCorroborated``). */
export function minNodesFrom(config: Record<string, unknown> | undefined): number | null {
  const quorum = config?.["quorum"];
  if (!quorum || typeof quorum !== "object" || Array.isArray(quorum)) {
    return null;
  }
  const raw = (quorum as Record<string, unknown>)["min_nodes"];
  return typeof raw === "number" ? raw : null;
}

/**
 * miniSEED archivado del incidente. Sin fila ``kind='miniseed'`` NO hay descarga:
 * no existe generación bajo demanda y el waveform crudo nunca se transmite en
 * continuo (regla de oro 9) — sólo sube a S3 en eventos confirmados.
 */
export function miniseedOf(evidence: EvidenceObject[] | undefined): EvidenceObject | null {
  return (evidence ?? []).find((e) => e.kind === "miniseed") ?? null;
}

/**
 * [T-2.43] Ventana en la que el crudo del evento todavía puede estar subiendo.
 *
 * El gabinete no transmite waveform en continuo: lo archiva y lo sube DESPUÉS de que
 * el evento se confirma, y esa subida compite con el enlace del sitio. Antes de que
 * pase esta ventana, "no hay miniSEED" no significa lo mismo que después.
 */
export const BACKFILL_WINDOW_MS = 15 * 60_000;

export type MiniseedKind = "forbidden" | "loading" | "error" | "backfill" | "absent" | "ready";

export interface MiniseedView {
  kind: MiniseedKind;
  /** Rótulo del botón. */
  label: string;
  /** Por qué está así, en lenguaje accionable. Va al `title` y al panel. */
  hint: string;
  enabled: boolean;
  /** Solo cuando la causa probable es el enlace del gabinete. */
  fleetLink: boolean;
}

/**
 * Estado del botón de miniSEED. Seis estados DISTINGUIBLES, porque "deshabilitado"
 * sin explicación es indistinguible de "roto" para quien está operando.
 *
 * No se ofrece generación bajo demanda a propósito: pedirle el crudo al gabinete
 * abriría una superficie de comando en el proceso que toca sirena, gas, ascensores y
 * puertas (reglas de oro 4 y 8) para una función de reporte, y violaría la 9 —el crudo
 * solo sube en eventos confirmados—. Además el buffer del edge es finito: un evento
 * viejo ya no existe en el gabinete, así que el comando fallaría igual.
 */
export function miniseedState(args: {
  canExport: boolean;
  loading: boolean;
  error: boolean;
  miniseed: EvidenceObject | null;
  /** Apertura del incidente en ms epoch. */
  openedAt: number;
  now: number;
}): MiniseedView {
  const { canExport, loading, error, miniseed, openedAt, now } = args;
  if (!canExport) {
    return {
      kind: "forbidden",
      label: "EXPORTAR miniSEED",
      hint: "Requiere la acción export.",
      enabled: false,
      fleetLink: false,
    };
  }
  if (loading) {
    return {
      kind: "loading",
      label: "EXPORTAR miniSEED",
      hint: "Cargando la evidencia del incidente…",
      enabled: false,
      fleetLink: false,
    };
  }
  if (error) {
    return {
      kind: "error",
      label: "EXPORTAR miniSEED",
      hint: "No se pudo cargar la evidencia del incidente. Reintente.",
      enabled: false,
      fleetLink: false,
    };
  }
  if (miniseed !== null) {
    return {
      kind: "ready",
      label: "EXPORTAR miniSEED",
      hint: "Forma de onda cruda archivada de este evento.",
      enabled: true,
      fleetLink: false,
    };
  }
  if (Number.isFinite(openedAt) && now - openedAt < BACKFILL_WINDOW_MS) {
    return {
      kind: "backfill",
      label: "BACKFILL EN CURSO",
      hint:
        "El gabinete archiva el crudo y lo sube después de confirmar el evento; " +
        "todavía puede llegar. Vuelva a consultar en unos minutos.",
      enabled: false,
      fleetLink: false,
    };
  }
  return {
    kind: "absent",
    label: "SIN miniSEED ARCHIVADO",
    hint:
      "Este incidente no tiene forma de onda cruda archivada. El crudo no se transmite " +
      "en continuo: sube solo en eventos confirmados y no puede pedirse a demanda. " +
      "Verifique el enlace de la estación.",
    enabled: false,
    fleetLink: true,
  };
}

/** Formatea el epicentro. No hay geocodificación inversa: se muestran coordenadas. */
export function epicenterOf(event: SeismicEventOut | null): string {
  if (!event || event.epicenter_lat === null || event.epicenter_lon === null) {
    return "—";
  }
  return `${event.epicenter_lat.toFixed(2)}, ${event.epicenter_lon.toFixed(2)}`;
}

export type MagnitudeKind = "catalog" | "absent" | "no-event";

export interface MagnitudeView {
  kind: MagnitudeKind;
  label: string;
  /** Por qué falta, para el `title` del elemento. */
  title: string;
  /** [T-5.10] Fuente y hora de consulta. Presente sólo cuando se pinta la cifra. */
  cita?: string;
}

/**
 * Magnitud del catálogo (post-hoc, nullable). Jamás una magnitud preliminar (§14).
 *
 * [T-2.39] Deja de devolver "—" para TODO. Hoy `seismic_events.magnitude` se inserta
 * siempre NULL —no hay ingesta de catálogo que la rellene—, así que un guion en esa
 * celda se leía como "el dato falló". Son dos ausencias distintas y el operador tiene
 * que poder distinguirlas: el incidente no tiene evento asociado, o lo tiene y el
 * catálogo aún no lo enriqueció.
 */
export function magnitudeOf(event: SeismicEventOut | null): MagnitudeView {
  if (!event) {
    return {
      kind: "no-event",
      label: "SIN EVENTO",
      title: "El incidente no está asociado a un evento sísmico de red.",
    };
  }
  // [T-5.10] **Con procedencia, o no se pinta.** La condición dejó de ser «hay
  // número» para ser «hay número Y consta de dónde salió y cuándo se preguntó».
  //
  // No es más estricto por gusto: hasta esta ficha la rama del catálogo era
  // inalcanzable en producción —`seismic_events.magnitude` se inserta SIEMPRE en
  // NULL— y el día que alguien escribiera un número, éste habría aparecido en la
  // consola **sin fuente ni hora**, indistinguible de una cifra medida por
  // nosotros. Ahora esa rama es alcanzable sólo con procedencia completa.
  const estado = event.procedencia ?? "sin_dato_externo";
  const cita = citaDeProcedencia(event.procedencia_fuente, event.procedencia_consultada_en);
  if (
    event.magnitude === null ||
    event.magnitude === undefined ||
    !pintaCifra(estado) ||
    cita === null
  ) {
    return {
      kind: "absent",
      label: rotuloProcedencia(estado),
      title:
        "La magnitud la publica una fuente oficial; TAKAB no la calcula " +
        "(blueprint §14). Sin fuente y hora de consulta, no se muestra.",
    };
  }
  return {
    kind: "catalog",
    label: `M ${event.magnitude.toFixed(1)}`,
    title: `Magnitud publicada por la fuente. ${cita}.`,
    cita,
  };
}

export type EpicenterKind = "none" | "centroid" | "manual" | "external";

export interface EpicenterView {
  kind: EpicenterKind;
  label: string;
  /** Qué ES ese punto. Sin esto, un centroide se lee como una localización. */
  note: string;
}

/**
 * [T-2.39] Qué representa el epicentro, además de dónde está.
 *
 * Con `source='local_quorum'` el punto es el CENTROIDE de los sitios que sintieron el
 * sismo (`incident/engine.py`), no una localización sísmica: está entre las estaciones,
 * no en la falla. Presentarlo sin decirlo invita a compararlo con el epicentro del SSN
 * y a concluir que la red "se equivocó" por 200 km.
 */
export function epicenterKindOf(event: SeismicEventOut | null): EpicenterView {
  const label = epicenterOf(event);
  if (!event || label === "—") {
    return { kind: "none", label: "—", note: "SIN EPICENTRO LOCALIZADO" };
  }
  if (event.source === "manual") {
    return { kind: "manual", label, note: "REUBICADO POR OPERADOR" };
  }
  if (event.source === CORROBORATED_SOURCE) {
    return {
      kind: "centroid",
      label,
      note: "CENTROIDE DE LA RED · NO ES UNA LOCALIZACIÓN SÍSMICA",
    };
  }
  return { kind: "external", label, note: "CATÁLOGO EXTERNO" };
}

/**
 * Duración del INCIDENTE (T-1.52): `closed_at − opened_at`, rotulada así — NO
 * es "duración del sismo" (no existe medición instrumental de sacudida;
 * derivarla de STA/LTA sin calibrar sería inventar física). Abierto ⇒ EN CURSO.
 */
export function durationOf(incident: { opened_at: string; closed_at: string | null }): string {
  if (incident.closed_at === null) {
    return "EN CURSO";
  }
  const seconds = Math.max(
    0,
    Math.round((Date.parse(incident.closed_at) - Date.parse(incident.opened_at)) / 1000),
  );
  if (seconds < 120) {
    return `${seconds} s`;
  }
  const minutes = Math.round(seconds / 60);
  return minutes < 120 ? `${minutes} min` : `${Math.round(minutes / 60)} h`;
}

/**
 * basis v2 del dictamen automático (T-1.48): sin medición NI corroboración el
 * veredicto se sostiene solo en la severidad de la alerta — la UI lo rotula en
 * vez de fingir evidencia instrumental. Claves ausentes (dictámenes previos a
 * basis v2) ⇒ false: no se acusa insuficiencia que el basis no declaró.
 */
export function insufficientData(dictamen: DictamenOut | null): boolean {
  if (dictamen === null) {
    return false;
  }
  const basis = dictamen.basis as Record<string, unknown> | null | undefined;
  const evidence =
    basis && typeof basis === "object" ? (basis["evidence"] as Record<string, unknown>) : null;
  return evidence !== null && evidence !== undefined && evidence["insufficient_data"] === true;
}

/**
 * Banda de sacudida MEDIDA a partir del PGA pico del incidente [T-2.39].
 *
 * Espejo de `api/src/takab_api/felt.py::felt_band` con sus umbrales por defecto. NO es
 * intensidad macrosísmica (MMI): TAKAB no la calcula (blueprint §14). Es la misma
 * tabla de verdad que decide si el gabinete actúa, expresada en palabras.
 *
 * Sin PGA devuelve "SIN MEDICIÓN" — jamás una banda tranquilizadora por defecto.
 */
export const PGA_WATCH_G = 0.04;
export const PGA_TRIP_G = 0.06;

export function feltLabelOf(maxPgaG: number | null | undefined): string {
  if (maxPgaG === null || maxPgaG === undefined) {
    return "SIN MEDICIÓN";
  }
  if (maxPgaG >= PGA_TRIP_G) {
    return "SACUDIDA FUERTE";
  }
  if (maxPgaG >= PGA_WATCH_G) {
    return "SACUDIDA MODERADA";
  }
  return "SACUDIDA LEVE";
}
