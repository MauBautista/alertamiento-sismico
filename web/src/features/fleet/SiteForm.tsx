// Formulario de estación (T-1.36): alta y edición, con selector de punto en el mapa.
//
// Los desplegables se derivan del DDL (`db/schema.sql` CHECK de `criticality`), no de
// una lista inventada aquí: un valor fuera del dominio sería un 400 del servidor.
//
// Al EDITAR se envía `base_row_version`: si otro operador guardó entre medias, la API
// responde 409 y el formulario lo dice, en vez de revertir su cambio en silencio.

import { useState } from "react";

import type { SiteOut } from "@takab/sdk";

import MapPointPicker from "./MapPointPicker";
import { DEFAULT_PICK, isValidPoint, parseLatLonPair } from "./geo";
import type { LonLat } from "./geo";

/** Espejo del CHECK de `sites.criticality`. */
export const CRITICALITY = ["low", "medium", "high", "critical"] as const;
export type Criticality = (typeof CRITICALITY)[number];

export interface SiteFormValues {
  code: string;
  name: string;
  criticality: Criticality;
  address: string;
  building_type: string;
  point: LonLat;
}

export interface SiteFormProps {
  /** `undefined` = alta; una fila = edición. */
  site?: SiteOut;
  submitting: boolean;
  error: string | null;
  onSubmit: (values: SiteFormValues) => void;
  onCancel: () => void;
}

function initialValues(site: SiteOut | undefined): SiteFormValues {
  if (site === undefined) {
    return {
      code: "",
      name: "",
      criticality: "medium",
      address: "",
      building_type: "",
      point: DEFAULT_PICK,
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
  };
}

export default function SiteForm({ site, submitting, error, onSubmit, onCancel }: SiteFormProps) {
  const [values, setValues] = useState<SiteFormValues>(() => initialValues(site));
  const editing = site !== undefined;
  const complete = values.code.trim() !== "" && values.name.trim() !== "";
  const canSubmit = complete && isValidPoint(values.point) && !submitting;

  function set<K extends keyof SiteFormValues>(key: K, value: SiteFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  /** Pegar "19.0633, -98.3014" (formato Google Maps / GPS) coloca el marcador. */
  function onPasteCoords(text: string) {
    const parsed = parseLatLonPair(text);
    if (parsed !== null) set("point", parsed);
  }

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

      <label>
        <span>TIPO DE INMUEBLE</span>
        <input
          value={values.building_type}
          onChange={(e) => set("building_type", e.target.value)}
        />
      </label>

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
        <button type="submit" className="soc-btn" disabled={!canSubmit}>
          {submitting ? "GUARDANDO…" : editing ? "GUARDAR CAMBIOS" : "CREAR ESTACIÓN"}
        </button>
        <button type="button" className="soc-btn soc-btn--secondary" onClick={onCancel}>
          CANCELAR
        </button>
      </div>
    </form>
  );
}
