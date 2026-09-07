// Formulario de estación (T-1.36): alta y edición, con selector de punto en el mapa.
//
// Los desplegables se derivan del DDL (`db/schema.sql` CHECK de `criticality`), no de
// una lista inventada aquí: un valor fuera del dominio sería un 400 del servidor.
//
// Al EDITAR se envía `base_row_version`: si otro operador guardó entre medias, la API
// responde 409 y el formulario lo dice, en vez de revertir su cambio en silencio.
//
// [T-6.03] EN QUÉ CLIENTE SE ESCRIBE. El formulario no tenía campo de cliente y la
// API resuelve el tenant así (`routers/_common.resolve_write_tenant`): un rol de
// cliente escribe SIEMPRE en el suyo; un rol interno TAKAB debe NOMBRARLO, o recibe
// un 400. La consola nunca lo nombraba, así que el superadmin no podía dar de alta
// una estación (y el 400 llegaba traducido como el mensaje del retiro). Ahora el
// formulario declara SIEMPRE en qué cliente escribe —rótulo permanente, no un
// tooltip— y sólo ofrece el selector a quien de verdad puede elegir. Un rol de
// cliente no puede elegir otro: no se le pinta un control que el servidor negaría.

import { useState } from "react";

import type { SiteOut } from "@takab/sdk";

import MapPointPicker from "./MapPointPicker";
import BuildingTypeField from "./BuildingTypeField";
import { DEFAULT_PICK, isValidPoint, parseLatLonPair } from "./geo";
import type { LonLat } from "./geo";

/** Espejo del CHECK de `sites.criticality`. */
export const CRITICALITY = ["low", "medium", "high", "critical"] as const;
export type Criticality = (typeof CRITICALITY)[number];

/** Lo mínimo de un cliente para elegirlo y rotularlo. */
export interface TenantOption {
  tenant_id: string;
  name: string;
  code: string;
}

/**
 * En qué cliente escribe este formulario.
 *
 * - `own`: rol de cliente (o edición de un sitio, que no se muda de tenant). El
 *   servidor decide; aquí sólo se ROTULA. `tenantName` puede faltar si el catálogo
 *   de clientes no cargó — entonces se rotula con el identificador, no con nada.
 * - `choose`: rol interno TAKAB. Debe nombrar el cliente; sin elección el alta no
 *   se puede enviar (la API la rechazaría con 400).
 */
export type WriteTarget =
  | { kind: "own"; tenantId: string; tenantName: string | null }
  | {
      kind: "choose";
      tenants: TenantOption[];
      loading: boolean;
      error: string | null;
      /** Preselección (p. ej. `?tenant=` al venir de la ficha del cliente). */
      initialTenantId: string | null;
    };

export interface SiteFormValues {
  code: string;
  name: string;
  criticality: Criticality;
  address: string;
  building_type: string;
  point: LonLat;
  /** Cliente elegido (`choose`) o propio (`own`); `null` = aún sin elegir. */
  tenant_id: string | null;
}

export interface SiteFormProps {
  /** `undefined` = alta; una fila = edición. */
  site?: SiteOut;
  writeTarget: WriteTarget;
  submitting: boolean;
  error: string | null;
  onSubmit: (values: SiteFormValues) => void;
  onCancel: () => void;
}

function initialTenantId(target: WriteTarget): string | null {
  return target.kind === "own" ? target.tenantId : target.initialTenantId;
}

function initialValues(site: SiteOut | undefined, target: WriteTarget): SiteFormValues {
  if (site === undefined) {
    return {
      code: "",
      name: "",
      criticality: "medium",
      address: "",
      building_type: "",
      point: DEFAULT_PICK,
      tenant_id: initialTenantId(target),
    };
  }
  return {
    code: site.code,
    name: site.name,
    criticality: (CRITICALITY as readonly string[]).includes(site.criticality)
      ? (site.criticality as Criticality)
      : "medium",
    address: site.address ?? "",
    building_type: site.building_type ?? "",
    point: { lon: site.lon, lat: site.lat },
    // Un sitio no se muda de tenant (`SiteUpdate` no lleva `tenant_id`).
    tenant_id: site.tenant_id,
  };
}

/** Texto del rótulo permanente: qué cliente, o por qué aún no se sabe. */
export function writeTargetLabel(target: WriteTarget, tenantId: string | null): string {
  if (target.kind === "own") {
    return target.tenantName ?? `CLIENTE ${target.tenantId}`;
  }
  const chosen =
    tenantId === null ? undefined : target.tenants.find((t) => t.tenant_id === tenantId);
  if (chosen !== undefined) return chosen.name;
  if (target.loading) return "CARGANDO CLIENTES…";
  if (target.error !== null) return "SIN LISTA DE CLIENTES";
  return "ELIGE UN CLIENTE";
}

export default function SiteForm({
  site,
  writeTarget,
  submitting,
  error,
  onSubmit,
  onCancel,
}: SiteFormProps) {
  const [values, setValues] = useState<SiteFormValues>(() => initialValues(site, writeTarget));

  const editing = site !== undefined;
  const complete = values.code.trim() !== "" && values.name.trim() !== "";
  // El cliente elegido tiene que estar EN LA LISTA: un id que no esté (una URL
  // vieja, un cliente retirado) daría un 404 del servidor, no un alta.
  const tenantOk =
    editing ||
    writeTarget.kind === "own" ||
    writeTarget.tenants.some((t) => t.tenant_id === values.tenant_id);
  const canSubmit = complete && isValidPoint(values.point) && tenantOk && !submitting;
  // [T-6.02] Un botón apagado dice por qué.
  const submitTitle = submitting
    ? "Guardando…"
    : !tenantOk
      ? "Elige el cliente en el que se escribe la estación"
      : !complete
        ? "Escribe el código y el nombre de la estación"
        : !isValidPoint(values.point)
          ? "Coloca el marcador en el mapa o escribe latitud y longitud válidas"
          : undefined;

  function set<K extends keyof SiteFormValues>(key: K, value: SiteFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  /** Pegar "19.0633, -98.3014" (formato Google Maps / GPS) coloca el marcador. */
  function onPasteCoords(text: string) {
    const parsed = parseLatLonPair(text);
    if (parsed !== null) set("point", parsed);
  }

  const chooser = !editing && writeTarget.kind === "choose" ? writeTarget : null;

  return (
    <form
      className="fleet__form"
      data-testid="site-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit(values);
      }}
    >
      <h3 className="fleet__formtitle">{editing ? "EDITAR ESTACIÓN" : "NUEVA ESTACIÓN"}</h3>

      {/* Rótulo PERMANENTE: siempre se lee en qué cliente escribe este formulario,
          también cuando el rol no puede elegir. Un dato que decide dónde aterriza
          un edificio no puede vivir sólo en un tooltip. */}
      <p className="fleet__target" data-testid="site-form-target">
        {editing ? "ESTACIÓN DE" : "ESCRIBIENDO EN"} ·{" "}
        <strong>{writeTargetLabel(writeTarget, values.tenant_id)}</strong>
      </p>

      {chooser !== null && (
        <label>
          <span>CLIENTE</span>
          <select
            value={values.tenant_id ?? ""}
            onChange={(e) => set("tenant_id", e.target.value === "" ? null : e.target.value)}
            disabled={chooser.loading || chooser.tenants.length === 0}
            required
            data-testid="site-form-tenant"
          >
            <option value="">
              {chooser.loading
                ? "CARGANDO CLIENTES…"
                : chooser.tenants.length === 0
                  ? "SIN CLIENTES"
                  : "— ELIGE UN CLIENTE —"}
            </option>
            {chooser.tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.name} · {t.code}
              </option>
            ))}
          </select>
        </label>
      )}
      {chooser !== null && chooser.error !== null && (
        <p
          className="fleet__hint fleet__hint--warn"
          role="alert"
          data-testid="site-form-tenants-error"
        >
          SIN LISTA DE CLIENTES · {chooser.error}
        </p>
      )}

      <label>
        <span>CÓDIGO</span>
        <input
          value={values.code}
          onChange={(e) => set("code", e.target.value)}
          maxLength={32}
          required
        />
      </label>

      <label>
        <span>NOMBRE</span>
        <input
          value={values.name}
          onChange={(e) => set("name", e.target.value)}
          maxLength={200}
          required
        />
      </label>

      <label>
        <span>CRITICIDAD</span>
        <select
          value={values.criticality}
          onChange={(e) => set("criticality", e.target.value as Criticality)}
        >
          {CRITICALITY.map((c) => (
            <option key={c} value={c}>
              {c.toUpperCase()}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>DIRECCIÓN</span>
        <input value={values.address} onChange={(e) => set("address", e.target.value)} />
      </label>

      <BuildingTypeField value={values.building_type} onChange={(v) => set("building_type", v)} />

      <fieldset className="fleet__coords">
        <legend>UBICACIÓN FÍSICA</legend>
        <p className="fleet__hint">
          Arrastra el marcador o haz clic en el mapa. También puedes pegar “lat, lon”.
        </p>
        <label>
          <span>LATITUD</span>
          <input
            type="number"
            step="0.000001"
            value={values.point.lat}
            onChange={(e) => set("point", { ...values.point, lat: Number(e.target.value) })}
            onPaste={(e) => onPasteCoords(e.clipboardData.getData("text"))}
          />
        </label>
        <label>
          <span>LONGITUD</span>
          <input
            type="number"
            step="0.000001"
            value={values.point.lon}
            onChange={(e) => set("point", { ...values.point, lon: Number(e.target.value) })}
            onPaste={(e) => onPasteCoords(e.clipboardData.getData("text"))}
          />
        </label>
        <MapPointPicker value={values.point} onChange={(point) => set("point", point)} />
      </fieldset>

      {error !== null && (
        <p className="soc-stateframe__error" role="alert" data-testid="site-form-error">
          {error}
        </p>
      )}

      <div className="fleet__formactions">
        <button type="submit" className="soc-btn" disabled={!canSubmit} title={submitTitle}>
          {submitting ? "GUARDANDO…" : editing ? "GUARDAR CAMBIOS" : "CREAR ESTACIÓN"}
        </button>
        <button type="button" className="soc-btn soc-btn--secondary" onClick={onCancel}>
          CANCELAR
        </button>
      </div>
    </form>
  );
}
