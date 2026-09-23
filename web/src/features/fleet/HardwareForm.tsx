// Alta de hardware de una estación (T-1.36): gabinete y sensor.
//
// El `tenant_id` no aparece en ningún formulario: lo hereda el servidor del sitio padre.
// Es lo que impide colgar el gabinete de un cliente en el edificio de otro (las claves
// foráneas de PostgreSQL no comparan `tenant_id`).
//
// El gabinete nace en `provisioned`. La API **no crea certificados X.509**, eso es
// Terraform; pero desde T-2.37 el `iot_thing` SÍ se puede capturar aquí si el operador
// ya lo provisionó, porque sin él el gabinete no sincroniza NUNCA y hasta ahora la
// consola no ofrecía forma alguna de vincularlo.

import { useState } from "react";

import type { EquipmentProfile, GatewayOut, SiteOut } from "@takab/sdk";

import Button, { ButtonLink } from "../../components/Button";
import { consoleSiteHref } from "./consoleSiteHref";
import { EQUIPMENT_ALL, EQUIPMENT_FIELDS } from "./equipment";
import { siteLabelText } from "./datosDeDemostracion";

/** Espejo de los CHECK de `sensors` (db/schema.sql). */
export const SENSOR_KINDS = ["structural", "ground"] as const;
export const SENSOR_MOUNTS = ["concrete_column", "steel", "floor", "buried"] as const;

export { EQUIPMENT_FIELDS };

export interface GatewayValues {
  serial: string;
  iot_thing: string;
  has_wr1: boolean;
  equipment: Required<EquipmentProfile>;
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
  /** Gabinetes YA registrados en este sitio: freno anti-duplicado ANTES de pulsar. */
  existing: GatewayOut[];
  submitting: boolean;
  error: string | null;
  onCreateGateway: (values: GatewayValues) => void;
  /**
   * [A-104] `onCreated` lo llama quien crea, SOLO cuando el servidor confirmó el
   * alta: entonces el formulario acusa y se limpia. Antes no pasaba nada visible
   * al pulsar, y el segundo clic creaba un sensor duplicado.
   */
  onCreateSensor: (values: SensorValues, onCreated: () => void) => void;
  onDone: () => void;
}

const SENSOR_VACIO: SensorValues = {
  kind: "structural",
  model: "RS4D",
  serial: "",
  mount: "",
  calibration_source: "",
};

export default function HardwareForm({
  site,
  existing,
  submitting,
  error,
  onCreateGateway,
  onCreateSensor,
  onDone,
}: HardwareFormProps) {
  const [gw, setGw] = useState<GatewayValues>({
    serial: "",
    iot_thing: "",
    has_wr1: true,
    equipment: { ...EQUIPMENT_ALL },
  });
  const [sensor, setSensor] = useState<SensorValues>(SENSOR_VACIO);
  // [A-104] Lo último que el servidor CONFIRMÓ haber dado de alta. Se enseña
  // hasta la siguiente alta: es el acuse, no un toast que se escapa.
  const [sensorAck, setSensorAck] = useState<string | null>(null);

  return (
    <div className="fleet__form" data-testid="hardware-form">
      <h3 className="fleet__formtitle">HARDWARE · {siteLabelText(site.code, site.code)}</h3>

      <fieldset className="fleet__coords">
        <legend>GABINETE (RASPBERRY PI 4)</legend>
        <p className="fleet__hint">
          Nace en <strong>PROVISIONADO</strong>. Su certificado X.509 lo emite Terraform; hasta
          entonces no sincroniza y la flota lo muestra como pendiente.
        </p>
        {existing.length > 0 && (
          <p className="fleet__hint fleet__hint--warn" data-testid="hardware-existing">
            ESTE SITIO YA TIENE {existing.length} GABINETE(S):{" "}
            {existing.map((g) => g.serial).join(" · ")}. Añade otro solo si el edificio tiene un
            segundo gabinete físico.
          </p>
        )}
        <label>
          <span>SERIAL DEL GABINETE</span>
          <input
            value={gw.serial}
            onChange={(e) => setGw({ ...gw, serial: e.target.value })}
            maxLength={64}
          />
        </label>
        <label>
          <span>IOT THING (AWS · OPCIONAL)</span>
          <input
            value={gw.iot_thing}
            placeholder="gw-dev-0001 · vacío = NO SINCRONIZABLE"
            onChange={(e) => setGw({ ...gw, iot_thing: e.target.value })}
            maxLength={128}
          />
        </label>
        {gw.iot_thing.trim() === "" && (
          <p className="fleet__hint fleet__hint--warn">
            SIN IOT THING EL GABINETE QUEDA <strong>PENDIENTE DE APROVISIONAR</strong> y no recibirá
            configuración firmada hasta vincularlo (EDITAR GABINETE).
          </p>
        )}
        <label className="fleet__checkbox">
          <input
            type="checkbox"
            checked={gw.has_wr1}
            onChange={(e) => setGw({ ...gw, has_wr1: e.target.checked })}
          />
          <span>RECEPTOR WR-1 (SASMEX) INSTALADO</span>
        </label>
        <p className="fleet__hint">
          ACTUADORES INSTALADOS EN EL SITIO — no toda estación tiene gas, ascensores o retenedores.
          Lo aquí declarado viaja firmado al gabinete: un canal ausente no se comanda ni se pinta.
        </p>
        {EQUIPMENT_FIELDS.map(({ key, label }) => (
          <label className="fleet__checkbox" key={key}>
            <input
              type="checkbox"
              checked={gw.equipment[key]}
              onChange={(e) =>
                setGw({ ...gw, equipment: { ...gw.equipment, [key]: e.target.checked } })
              }
            />
            <span>{label}</span>
          </label>
        ))}
        <Button
          disabled={submitting || gw.serial.trim() === ""}
          onClick={() =>
            onCreateGateway({
              ...gw,
              serial: gw.serial.trim(),
              iot_thing: gw.iot_thing.trim(),
            })
          }
        >
          AÑADIR GABINETE
        </Button>
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
        <Button
          disabled={submitting || sensor.model.trim() === ""}
          onClick={() => {
            const enviado: SensorValues = {
              ...sensor,
              model: sensor.model.trim(),
              serial: sensor.serial.trim(),
              calibration_source: sensor.calibration_source.trim(),
            };
            setSensorAck(null);
            onCreateSensor(enviado, () => {
              setSensorAck(
                `${enviado.model}${enviado.serial === "" ? " · SIN SERIAL" : ` · ${enviado.serial}`}`,
              );
              setSensor(SENSOR_VACIO);
            });
          }}
        >
          AÑADIR SENSOR
        </Button>
        {sensorAck !== null && (
          <p className="fleet__hint" role="status" data-testid="sensor-ack">
            SENSOR AÑADIDO · {sensorAck}. El formulario queda limpio para el siguiente.
          </p>
        )}
      </fieldset>

      {error !== null && (
        <p className="soc-stateframe__error" role="alert" data-testid="hardware-form-error">
          {error}
        </p>
      )}

      <div className="fleet__formactions" data-testid="hardware-formactions">
        <Button variant="secondary" onClick={onDone}>
          VOLVER
        </Button>
        {/* [T-7.05 · C-4] EL CAMINO A MONITOREO, EN EL PUNTO DONDE EL ALTA TERMINA.
            El censo de flujos de `T-7.04` midió el alta completa en 8 clics desde el
            wall, y el octavo —la pestaña Monitoreo— aterrizaba en una consola sin nada
            seleccionado: la estación recién nacida había que buscarla entre N pins, un
            clic más y con el cliente delante. El mecanismo ya existía (`?sitio=`,
            T-6.14) y aquí se enlaza.
            Esta fila, y no el acuse del gabinete: allí el enlace era una salida de un
            solo sentido en mitad del alta, que se llevaba por delante los únicos tres
            UUID que el runbook necesita y el paso del sensor (ver `GatewayAcuse.tsx`).
            Aquí no queda nada detrás que perder.
            El rótulo dice MONITOREO y no «el mapa» a propósito: `?sitio=` abre la
            FICHA lateral de la estación; el mapa no centra ni resalta su pin —
            `MapPanel` no recibe hoy sitio seleccionado alguno (`MapPanelProps`,
            `features/console/MapPanel.tsx`)—. Prometer foco en el mapa sería una
            promesa que la pantalla de destino no cumple. */}
        <ButtonLink
          variant="secondary"
          to={consoleSiteHref(site.site_id)}
          data-testid="hardware-ver-en-monitoreo"
        >
          VER LA ESTACIÓN EN MONITOREO
        </ButtonLink>
      </div>
    </div>
  );
}
