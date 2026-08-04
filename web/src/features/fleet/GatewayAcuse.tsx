// Acuse de alta de gabinete (T-2.37).
//
// Antes, al pulsar AÑADIR GABINETE no cambiaba nada en pantalla: el formulario seguía
// abierto, con los mismos datos y sin confirmación. El operador volvía a pulsar. Como
// el `serial` es único global, el segundo intento daba 409… salvo que hubiera cambiado
// un dígito, en cuyo caso nacía un gabinete duplicado en el mismo sitio, con el mismo
// rótulo. Fue uno de los dos caminos por los que aparecían "estaciones repetidas".
//
// Este acuse cierra ese hueco y, de paso, entrega los tres UUID que el runbook de alta
// manda pegar en `/etc/takab/edge.env` del Pi — que hasta ahora había que ir a buscar
// a la base de datos.

import { useState } from "react";

import type { GatewayRowOut } from "@takab/sdk";

function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="acuse__row">
      <span className="acuse__label">{label}</span>
      <code className="acuse__value">{value}</code>
      <button
        type="button"
        className="soc-btn soc-btn--secondary"
        onClick={() => {
          // `clipboard` no existe en contextos no seguros (http://) ni en jsdom: el
          // acuse sigue siendo útil sin él, así que se degrada en silencio.
          void navigator.clipboard?.writeText(value).then(
            () => setCopied(true),
            () => setCopied(false),
          );
        }}
      >
        {copied ? "COPIADO" : "COPIAR"}
      </button>
    </div>
  );
}

export interface GatewayAcuseProps {
  gateway: GatewayRowOut;
  siteName: string;
  onDone: () => void;
}

export default function GatewayAcuse({ gateway, siteName, onDone }: GatewayAcuseProps) {
  const syncable = gateway.iot_thing !== null && gateway.iot_thing !== "";
  return (
    <div className="fleet__form acuse" data-testid="gateway-acuse">
      <h3 className="fleet__formtitle">GABINETE REGISTRADO · {siteName}</h3>
      <p className="fleet__hint">
        Alta en <strong>PROVISIONADO</strong>. Pega estos identificadores en{" "}
        <code>/etc/takab/edge.env</code> del Pi (runbook de alta de estación §5).
      </p>

      <Copyable label="TAKAB_EDGE_GATEWAY_ID" value={gateway.gateway_id} />
      <Copyable label="TAKAB_EDGE_SITE_ID" value={gateway.site_id} />
      <Copyable label="TAKAB_EDGE_TENANT_ID" value={gateway.tenant_id} />
      <Copyable label="SERIAL" value={gateway.serial} />

      {syncable ? (
        <Copyable label="TAKAB_EDGE_IOT_THING" value={gateway.iot_thing as string} />
      ) : (
        <p className="fleet__hint fleet__hint--warn" data-testid="acuse-unsyncable">
          NO SINCRONIZABLE · FALTA VINCULAR EL IOT THING. El gabinete no recibirá configuración
          firmada hasta que Terraform emita su certificado y su nombre se registre aquí (EDITAR
          GABINETE).
        </p>
      )}

      <div className="fleet__formactions">
        <button type="button" className="soc-btn" onClick={onDone}>
          CONTINUAR
        </button>
      </div>
    </div>
  );
}
