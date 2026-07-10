import { describe, expect, it } from "vitest";

import type { DictamenOut, EvidenceObject, QuorumVoteOut, SeismicEventOut } from "@takab/sdk";

import {
  buildRows,
  chainHead,
  epicenterOf,
  isPreliminary,
  magnitudeOf,
  isCorroborated,
  minNodesFrom,
  miniseedOf,
  quorumView,
  verdictOf,
  durationOf,
  insufficientData,
} from "./model";
import { anEvent, anIncident, aSite } from "./fixtures";

function vote(over: Partial<QuorumVoteOut> = {}): QuorumVoteOut {
  return {
    event_id: "evt-1",
    sensor_id: "aaaaaaaa-0000-0000-0000-000000000001",
    detected_at: "2026-07-08T10:00:00Z",
    pga_g: 0.1,
    delta_s: 0,
    counted: true,
    ...over,
  };
}

function dictamen(over: Partial<DictamenOut> = {}): DictamenOut {
  return {
    dictamen_id: "d-1",
    tenant_id: "t-1",
    incident_id: "i-1",
    status: "inhabit_monitor",
    basis: {},
    signed_by: null,
    supersedes_dictamen_id: null,
    created_at: "2026-07-08T10:00:00Z",
    ...over,
  };
}

describe("verdictOf", () => {
  it("mapea los 4 status del DDL", () => {
    expect(verdictOf("normal_operation")).toEqual({ label: "OPERACIÓN NORMAL", kind: "ok" });
    expect(verdictOf("inhabit_monitor").kind).toBe("warn");
    expect(verdictOf("restricted").kind).toBe("warn");
    expect(verdictOf("no_inhabit_inspect")).toEqual({
      label: "NO HABITAR · INSPECCIÓN",
      kind: "crit",
    });
  });

  it("un status desconocido se muestra crudo en ámbar, nunca como normal", () => {
    const v = verdictOf("algo_nuevo");
    expect(v.kind).toBe("warn");
    expect(v.label).toBe("ALGO_NUEVO");
  });
});

describe("chainHead / isPreliminary", () => {
  it("la cabeza es la primera fila (el servidor ordena más-reciente-primero)", () => {
    const head = dictamen({ dictamen_id: "nuevo" });
    const old = dictamen({ dictamen_id: "viejo", created_at: "2026-07-01T00:00:00Z" });
    expect(chainHead([head, old])?.dictamen_id).toBe("nuevo");
  });

  it("cadena vacía o ausente ⇒ null", () => {
    expect(chainHead([])).toBeNull();
    expect(chainHead(undefined)).toBeNull();
  });

  it("signed_by null ⇒ preliminar; firmado ⇒ no", () => {
    expect(isPreliminary(dictamen({ signed_by: null }))).toBe(true);
    expect(isPreliminary(dictamen({ signed_by: "user-uuid" }))).toBe(false);
    expect(isPreliminary(null)).toBe(false);
  });
});

describe("buildRows", () => {
  it("une incidente + evento + sitio", () => {
    const rows = buildRows(
      [anIncident({ event_id: "evt-1", site_id: "s-1" })],
      [anEvent({ event_id: "evt-1", magnitude: 6.8 })],
      [aSite({ site_id: "s-1", name: "Planta Cholula" })],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].event?.magnitude).toBe(6.8);
    expect(rows[0].siteName).toBe("Planta Cholula");
  });

  it("nodeCount sale de event.meta.node_count", () => {
    const rows = buildRows(
      [anIncident({ event_id: "evt-1" })],
      [anEvent({ event_id: "evt-1", meta: { node_count: 4, sites: [] } })],
      [],
    );
    expect(rows[0].nodeCount).toBe(4);
  });

  it("meta sin node_count ⇒ null (no se inventa 0)", () => {
    const rows = buildRows(
      [anIncident({ event_id: "evt-1" })],
      [anEvent({ event_id: "evt-1" })],
      [],
    );
    expect(rows[0].nodeCount).toBeNull();
  });

  it("incidente sin evento asociado no rompe la fila", () => {
    const rows = buildRows([anIncident({ event_id: null })], [], []);
    expect(rows[0].event).toBeNull();
    expect(rows[0].nodeCount).toBeNull();
  });

  it("sitio desconocido degrada a un id corto, no a un nombre inventado", () => {
    const rows = buildRows([anIncident({ site_id: "abcdef12-3456-7890" })], [], []);
    expect(rows[0].siteName).toBe("SITIO abcdef12");
  });

  it("sin incidentes ⇒ sin filas", () => {
    expect(buildRows(undefined, [], [])).toEqual([]);
  });
});

describe("quorumView", () => {
  it("el ancla es el delta_s menor y los offsets se muestran verbatim", () => {
    const view = quorumView([
      vote({ sensor_id: "b0000000-1", delta_s: 1.4 }),
      vote({ sensor_id: "a0000000-1", delta_s: 0 }),
      vote({ sensor_id: "c0000000-1", delta_s: 3.1 }),
    ]);
    expect(view.nodes.find((n) => n.isAnchor)?.sensorId).toBe("a0000000-1");
    expect(view.nodes.map((n) => n.deltaS)).toEqual([1.4, 0, 3.1]);
  });

  it("delta_s negativo también puede ser el ancla (no se asume 0)", () => {
    const view = quorumView([
      vote({ sensor_id: "x", delta_s: 0 }),
      vote({ sensor_id: "y", delta_s: -0.5 }),
    ]);
    expect(view.nodes.find((n) => n.isAnchor)?.sensorId).toBe("y");
  });

  it("sin delta_s el ancla cae al detected_at más temprano", () => {
    const view = quorumView([
      vote({ sensor_id: "tarde", delta_s: null, detected_at: "2026-07-08T10:00:05Z" }),
      vote({ sensor_id: "pronto", delta_s: null, detected_at: "2026-07-08T10:00:01Z" }),
    ]);
    expect(view.nodes.find((n) => n.isAnchor)?.sensorId).toBe("pronto");
  });

  it("cuenta sólo los votos counted", () => {
    const view = quorumView([
      vote({ sensor_id: "a", counted: true }),
      vote({ sensor_id: "b", counted: true }),
      vote({ sensor_id: "c", counted: false }),
    ]);
    expect(view.countedNodes).toBe(2);
  });

  it("sin votos no hay ancla ni nodos", () => {
    const view = quorumView(undefined);
    expect(view.nodes).toEqual([]);
    expect(view.countedNodes).toBe(0);
  });
});

describe("isCorroborated · el veredicto de quórum es un HECHO del servidor", () => {
  it("source=local_quorum ⇒ el motor formó el evento por quórum", () => {
    expect(isCorroborated({ source: "local_quorum" })).toBe(true);
  });

  it("otras fuentes NO son quórum (sasmex, manual, external)", () => {
    expect(isCorroborated({ source: "sasmex" })).toBe(false);
    expect(isCorroborated({ source: "manual" })).toBe(false);
    expect(isCorroborated({ source: "external" })).toBe(false);
  });

  it("sin evento no se afirma nada", () => {
    expect(isCorroborated(null)).toBe(false);
    expect(isCorroborated(undefined)).toBe(false);
  });
});

describe("minNodesFrom", () => {
  it("lee config.quorum.min_nodes", () => {
    expect(minNodesFrom({ quorum: { min_nodes: 3 } })).toBe(3);
  });

  it("config ausente o sin quorum ⇒ null", () => {
    expect(minNodesFrom(undefined)).toBeNull();
    expect(minNodesFrom({})).toBeNull();
    expect(minNodesFrom({ quorum: [] })).toBeNull();
    expect(minNodesFrom({ quorum: { min_nodes: "3" } })).toBeNull();
  });
});

describe("miniseedOf", () => {
  const ev = (kind: string): EvidenceObject => ({
    evidence_id: `e-${kind}`,
    kind,
    s3_key: `k/${kind}`,
    created_at: "2026-07-08T10:00:00Z",
  });

  it("encuentra la evidencia miniSEED archivada", () => {
    expect(miniseedOf([ev("report_pdf"), ev("miniseed")])?.evidence_id).toBe("e-miniseed");
  });

  it("sin miniSEED archivado ⇒ null (no hay generación bajo demanda)", () => {
    expect(miniseedOf([ev("report_pdf")])).toBeNull();
    expect(miniseedOf(undefined)).toBeNull();
  });
});

describe("epicenterOf / magnitudeOf", () => {
  it("muestra coordenadas: no hay geocodificación inversa", () => {
    expect(epicenterOf(anEvent({ epicenter_lat: 19.06, epicenter_lon: -98.3 }))).toBe(
      "19.06, -98.30",
    );
  });

  it("epicentro nulo ⇒ guion, jamás una ciudad inventada", () => {
    expect(epicenterOf(anEvent({ epicenter_lat: null, epicenter_lon: null }))).toBe("—");
    expect(epicenterOf(null)).toBe("—");
  });

  it("magnitud nula ⇒ guion (el catálogo la llena post-hoc; §14 prohíbe la preliminar)", () => {
    expect(magnitudeOf(anEvent({ magnitude: null }))).toBe("—");
    expect(magnitudeOf(null)).toBe("—");
    expect(magnitudeOf(anEvent({ magnitude: 5 }))).toBe("M 5.0");
  });
});

describe("SeismicEventOut.meta contract", () => {
  it("meta es un dict opaco: un node_count no numérico no se cuela", () => {
    const evt: SeismicEventOut = anEvent({ meta: { node_count: "tres" } });
    expect(buildRows([anIncident({ event_id: evt.event_id })], [evt], [])[0].nodeCount).toBeNull();
  });
});

describe("durationOf (T-1.52)", () => {
  it("cerrado: humaniza s/min/h; abierto: EN CURSO (jamás inventa un fin)", () => {
    expect(
      durationOf({ opened_at: "2026-07-10T03:14:00Z", closed_at: "2026-07-10T03:14:48Z" }),
    ).toBe("48 s");
    expect(
      durationOf({ opened_at: "2026-07-10T03:14:00Z", closed_at: "2026-07-10T03:26:00Z" }),
    ).toBe("12 min");
    expect(
      durationOf({ opened_at: "2026-07-10T03:00:00Z", closed_at: "2026-07-10T06:00:00Z" }),
    ).toBe("3 h");
    expect(durationOf({ opened_at: "2026-07-10T03:14:00Z", closed_at: null })).toBe("EN CURSO");
  });
});

describe("insufficientData (T-1.52 · basis v2)", () => {
  it("true SOLO si el basis lo declara; claves ausentes (pre-v2) ⇒ false", () => {
    const base = {
      dictamen_id: "d",
      tenant_id: "t",
      incident_id: "i",
      status: "no_inhabit_inspect",
      signed_by: null,
      supersedes_dictamen_id: null,
      created_at: "2026-07-10T03:15:00Z",
    };
    expect(
      insufficientData({ ...base, basis: { evidence: { insufficient_data: true } } } as never),
    ).toBe(true);
    expect(
      insufficientData({ ...base, basis: { evidence: { insufficient_data: false } } } as never),
    ).toBe(false);
    expect(insufficientData({ ...base, basis: {} } as never)).toBe(false);
    expect(insufficientData(null)).toBe(false);
  });
});
