import { GitCommitVertical, RotateCcw, UploadCloud } from "lucide-react";

import ConfirmButton from "../../components/ConfirmButton";
import type { SyncStatus } from "./model";

const STATUS_COPY: Record<SyncStatus, { text: string; color: string }> = {
  // Sólo `config-state` autoriza a decir SINCRONIZADO: `publish` responde 202
  // `pending_sync` y su docstring dice literalmente "NO sincroniza al edge".
  synced: {
    text: "CONFIG FIRMADA APLICADA EN TODOS LOS GABINETES",
    color: "var(--tk-status-normal)",
  },
  partial: {
    text: "SYNC PARCIAL · algún gabinete sigue con la config anterior",
    color: "var(--tk-status-warning)",
  },
  pending: {
    text: "PENDIENTE DE SYNC · intención registrada, aún no llega al edge",
    color: "var(--tk-status-warning)",
  },
  "no-gateways": { text: "SIN GABINETES SINCRONIZABLES EN ESTE TENANT", color: "var(--tk-fg-3)" },
  unknown: { text: "ESTADO DE SYNC DESCONOCIDO", color: "var(--tk-fg-3)" },
};

export interface SyncFooterProps {
  status: SyncStatus;
  /** Huella de la config firmada que corre en los gabinetes (si todos traen la misma). */
  syncedFingerprint: string | null;
  /** Versión de `rule_sets` creada por el último PUT de esta sesión. */
  publishedVersion: number | null;
  /** Otro admin publicó mientras había edición sin guardar. */
  changedElsewhere: boolean;
  dirty: boolean;
  errors: string[];
  applyError: string | null;
  pending: boolean;
  canEdit: boolean;
  onApply: () => void;
  onReset: () => void;
}

/**
 * Pie de la matriz: aplicar + estado REAL del sync firmado.
 *
 * El mockup prometía "Cambios pendientes de sync al edge · ≤60s · firmado JWT" como
 * si el botón lo garantizara. La verdad del contrato: `PUT /rule-sets` crea la
 * versión y `POST publish` registra la INTENCIÓN (202 `pending_sync`); quien firma
 * (HMAC, no JWT) y entrega es el worker de T-1.23. Por eso el estado se lee de
 * `GET /fleet/gateways/{id}/config-state` y jamás se afirma sin él.
 *
 * `PUT` no escribe `audit_log` (sólo `publish` audita): no se promete auditoría
 * por guardado.
 */
export default function SyncFooter({
  status,
  syncedFingerprint,
  publishedVersion,
  changedElsewhere,
  dirty,
  errors,
  applyError,
  pending,
  canEdit,
  onApply,
  onReset,
}: SyncFooterProps) {
  const copy = STATUS_COPY[status];
  const blocked = !canEdit || !dirty || errors.length > 0 || pending;

  return (
    <footer className="mt__detail-ft">
      <span className="mt__detail-chain">
        <GitCommitVertical size={11} aria-hidden />
        <span style={{ color: copy.color }}>{copy.text}</span>
        {/* Huella, no versión: `gateway_config_state.version` cuenta ENTREGAS por
            gateway y no es comparable con `rule_sets.version`. */}
        {syncedFingerprint !== null && ` · firma ${syncedFingerprint}`}
        {publishedVersion !== null && ` · rule_set v${publishedVersion} publicada`}
        {dirty && " · CAMBIOS SIN APLICAR"}
      </span>

      {changedElsewhere && (
        <p role="alert" className="soc-meta">
          OTRO ADMIN PUBLICÓ UNA VERSIÓN NUEVA · tus cambios siguen sin aplicar; RESTAURAR los
          descarta y trae la del servidor
        </p>
      )}

      {errors.length > 0 && (
        <ul role="alert" className="soc-meta">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {applyError && (
        <p role="alert" className="soc-meta">
          {applyError}
        </p>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="button"
          className="soc-btn soc-btn--secondary"
          disabled={!dirty || pending}
          onClick={onReset}
        >
          <RotateCcw size={12} aria-hidden /> RESTAURAR
        </button>
        <ConfirmButton
          label="APLICAR Y SINCRONIZAR"
          icon={<UploadCloud size={12} aria-hidden />}
          disabled={blocked}
          onConfirm={onApply}
        />
      </div>
    </footer>
  );
}
