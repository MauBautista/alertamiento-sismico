// Alta de hardware de una estación (T-1.36): gabinete y sensor.
//
// El `tenant_id` no aparece en ningún formulario: lo hereda el servidor del sitio padre.
// Es lo que impide colgar el gabinete de un cliente en el edificio de otro (las claves
// foráneas de PostgreSQL no comparan `tenant_id`).
//
// El gabinete nace en `provisioned` y sin `iot_thing`: la API **no crea certificados
// X.509**, eso es Terraform. Hasta que el thing exista, el gabinete no es sincronizable
// y la Flota Edge lo dice. Prometer "OPERATIVO" al pulsar CREAR sería mentir.

import { useState } from "react";

import type { SiteOut } from "@takab/sdk";

/** Espejo de los CHECK de `sensors` (db/schema.sql). */
export const SENSOR_KINDS = ["structural", "ground"] as const;
export const SENSOR_MOUNTS = ["concrete_column", "steel", "floor", "buried"] as const;

export interface GatewayValues {
  serial: string;
  has_wr1: boolean;
}

export interface SensorValues {
  kind: (typeof SENSOR_KINDS)[number];
  model: string;
  serial: string;
  mount: (typeof SENSOR_MOUNTS)[number] | "";
  calibration_source: string;
}

export interface HardwareFormProps {
  site: SiteOut;
  submitting: boolean;
  error: string | null;
  onCreateGateway: (values: GatewayValues) => void;
  onCreateSensor: (values: SensorValues) => void;
  onDone: () => void;
}

export default function HardwareForm({
  site,
  submitting,
  error,
  onCreateGateway,
  onCreateSensor,
  onDone,
}: HardwareFormProps) {
  const [gw, setGw] = useState<GatewayValues>({ serial: "", has_wr1: true });
  const [sensor, setSensor] = useState<SensorValues>({
    kind: "structural",
    model: "RS4D",
    serial: "",
    mount: "",
    calibration_source: "",
  });

  return (
    <div className="fleet__form" data-testid="hardware-form">
      <h3 className="fleet__formtitle">HARDWARE · {site.code}</h3>

      <fieldset className="fleet__coords">
        <legend>GABINETE (RASPBERRY PI 5)</legend>
        <p className="fleet__hint">
          Nace en <strong>PROVISIONADO</strong>. Su certificado X.509 lo emite Terraform; hasta
          entonces no sincroniza y la flota lo muestra como pendiente.
        </p>
        <label>
          <span>SERIAL DEL GABINETE</span>
          <input
            value={gw.serial}
            onChange={(e) => setGw({ ...gw, serial: e.target.value })}
            maxLength={64}
          />
        </label>
        <label className="fleet__checkbox">
          <input
            type="checkbox"
            checked={gw.has_wr1}
            onChange={(e) => setGw({ ...gw, has_wr1: e.target.checked })}
          />
          <span>RECEPTOR WR-1 (SASMEX) INSTALADO</span>
        </label>
        <button
          type="button"
          className="soc-btn"
          disabled={submitting || gw.serial.trim() === ""}
          onClick={() => onCreateGateway({ ...gw, serial: gw.serial.trim() })}
        >
          AÑADIR GABINETE
        </button>
      </fieldset>

      <fieldset className="fleet__coords">
        <legend>SENSOR</legend>
        <label>
          <span>TIPO</span>
          <select
            value={sensor.kind}
            onChange={(e) => setSensor({ ...sensor, kind: e.target.value as SensorValues["kind"] })}
          >
            {SENSOR_KINDS.map((k) => (
              <option key={k} value={k}>
                {k === "structural" ? "ESTRUCTURAL" : "TERRENO"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>MODELO</span>
          <input
            value={sensor.model}
            onChange={(e) => setSensor({ ...sensor, model: e.target.value })}
            maxLength={64}
          />
        </label>
        <label>
          <span>SERIAL DEL SENSOR</span>
          <input
            value={sensor.serial}
            onChange={(e) => setSensor({ ...sensor, serial: e.target.value })}
            maxLength={64}
          />
        </label>
        <label>
          <span>MONTAJE</span>
          <select
            value={sensor.mount}
            onChange={(e) =>
              setSensor({ ...sensor, mount: e.target.value as SensorValues["mount"] })
            }
          >
            <option value="">SIN ESPECIFICAR</option>
            {SENSOR_MOUNTS.map((m) => (
              <option key={m} value={m}>
                {m.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>PROCEDENCIA DE LA CALIBRACIÓN</span>
          <input
            value={sensor.calibration_source}
            placeholder="stationxml:AM.R4F74 · vacío = SIN CALIBRAR"
            onChange={(e) => setSensor({ ...sensor, calibration_source: e.target.value })}
            maxLength={200}
          />
        </label>
        <p className="fleet__hint">
          Sin procedencia, el PGA/PGV del sitio se presenta en unidades relativas. No hay casilla de
          “calibrado”: hay que nombrar de dónde sale la respuesta instrumental.
        </p>
        <button
          type="button"
          className="soc-btn"
          disabled={submitting || sensor.model.trim() === ""}
          onClick={() =>
            onCreateSensor({
              ...sensor,
              model: sensor.model.trim(),
              serial: sensor.serial.trim(),
              calibration_source: sensor.calibration_source.trim(),
            })
          }
        >
          AÑADIR SENSOR
        </button>
      </fieldset>

      {error !== null && (
        <p className="soc-stateframe__error" role="alert" data-testid="hardware-form-error">
          {error}
        </p>
      )}

      <div className="fleet__formactions">
        <button type="button" className="soc-btn soc-btn--secondary" onClick={onDone}>
          VOLVER
        </button>
      </div>
    </div>
  );
}
