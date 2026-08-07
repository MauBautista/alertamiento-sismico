// Edición de un gabinete ya registrado (T-2.37).
//
// El endpoint `PUT /fleet/gateways/{id}` existía desde T-1.32 y la consola nunca lo
// llamaba: un gabinete dado de alta desde la web quedaba congelado para siempre — sin
// forma de vincular su `iot_thing` (⇒ jamás sincronizaba) ni de corregir qué
// actuadores tiene instalados.
//
// `status` NO se edita a propósito: `online`/`degraded`/`offline` los deriva el
// heartbeat y `retired` se alcanza por el diálogo de retiro con doble fricción. Un
// desplegable que dijera "online" haría que la Flota Edge mintiera sobre un gabinete
// muerto.
//
// [T-2.69] `fw_version` salió por la misma razón, y era el caso más grave. Este PUT
// es de reemplazo TOTAL y el formulario reenviaba el valor prellenado con CADA
// edición: un operador podía anotar —o borrar, dejándolo vacío— una versión que el
// gabinete nunca corrió. En un gabinete vivo el siguiente latido lo corregía en
// ≤60 s; en uno SIN ENLACE la mentira era PERMANENTE, y es justo ese sobre el que
// más importa saber la verdad. El propio placeholder ya decía "la reporta el propio
// gabinete": ahora es la única forma. El servidor lo rechaza con 422.

import { useState } from "react";

import type { EquipmentProfile, GatewayOut } from "@takab/sdk";

import { EQUIPMENT_FIELDS, equipmentOf } from "./equipment";

export interface GatewayEditValues {
  serial: string;
  iot_thing: string;
  has_wr1: boolean;
  equipment: Required<EquipmentProfile>;
}

export interface GatewayFormProps {
  gateway: GatewayOut;
  siteName: string;
  submitting: boolean;
  error: string | null;
  onSubmit: (values: GatewayEditValues) => void;
  onCancel: () => void;
}

export default function GatewayForm({
  gateway,
  siteName,
  submitting,
  error,
  onSubmit,
  onCancel,
}: GatewayFormProps) {
  const [values, setValues] = useState<GatewayEditValues>({
    serial: gateway.serial,
    iot_thing: gateway.iot_thing ?? "",
    has_wr1: gateway.has_wr1,
    equipment: equipmentOf(gateway.equipment),
  });

  const syncable = values.iot_thing.trim() !== "";

  return (
    <div className="fleet__form" data-testid="gateway-form">
      <h3 className="fleet__formtitle">
        EDITAR GABINETE · {siteName} · {gateway.serial}
      </h3>

      <label>
        <span>SERIAL DEL GABINETE</span>
        <input
          value={values.serial}
          onChange={(e) => setValues({ ...values, serial: e.target.value })}
          maxLength={64}
        />
      </label>

      <label>
        <span>IOT THING (AWS · LO CREA TERRAFORM)</span>
        <input
          value={values.iot_thing}
          placeholder="gw-dev-0001 · vacío = NO SINCRONIZABLE"
          onChange={(e) => setValues({ ...values, iot_thing: e.target.value })}
          maxLength={128}
        />
      </label>
      {!syncable && (
        <p className="fleet__hint fleet__hint--warn" data-testid="gateway-form-unsyncable">
          SIN IOT THING EL GABINETE NO RECIBE CONFIGURACIÓN FIRMADA. Provisiona el thing con
          Terraform (<code>infra/scripts/provision_gateway.sh</code>) y pega aquí su nombre.
        </p>
      )}

      <label className="fleet__checkbox">
        <input
          type="checkbox"
          checked={values.has_wr1}
          onChange={(e) => setValues({ ...values, has_wr1: e.target.checked })}
        />
        <span>RECEPTOR WR-1 (SASMEX) INSTALADO</span>
      </label>

      <p className="fleet__hint">
        ACTUADORES INSTALADOS EN EL SITIO. Al guardar, el cambio se re-publica FIRMADO al gabinete:
        un canal que se desmarque deja de comandarse y desaparece del panel local. La tarjeta
        muestra cuándo llegó.
      </p>
      {EQUIPMENT_FIELDS.map(({ key, label }) => (
        <label className="fleet__checkbox" key={key}>
          <input
            type="checkbox"
            checked={values.equipment[key]}
            onChange={(e) =>
              setValues({
                ...values,
                equipment: { ...values.equipment, [key]: e.target.checked },
              })
            }
          />
          <span>{label}</span>
        </label>
      ))}

      {error !== null && (
        <p className="soc-stateframe__error" role="alert" data-testid="gateway-form-error">
          {error}
        </p>
      )}

      <div className="fleet__formactions">
        <button type="button" className="soc-btn soc-btn--secondary" onClick={onCancel}>
          CANCELAR
        </button>
        <button
          type="button"
          className="soc-btn"
          disabled={submitting || values.serial.trim() === ""}
          onClick={() =>
            onSubmit({
              ...values,
              serial: values.serial.trim(),
              iot_thing: values.iot_thing.trim(),
            })
          }
        >
          {submitting ? "GUARDANDO…" : "GUARDAR GABINETE"}
        </button>
      </div>
    </div>
  );
}
