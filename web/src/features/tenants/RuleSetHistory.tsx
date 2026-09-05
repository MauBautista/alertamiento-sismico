// Historial de versiones del rule_set, con vuelta atrás (T-5.16).
//
// LO QUE ESTA PANTALLA NO PUEDE INSINUAR: que volver atrás recorta el histórico.
// No lo recorta — crea una versión nueva que declara a cuál vuelve —, y la
// diferencia importa porque este historial es evidencia de compliance exenta de
// poda (regla de oro 11). Un botón rotulado «RESTAURAR» a secas dejaría a quien
// lo pulsa creyendo que deshace; lo dice en voz alta y hay test de que ninguna
// palabra de borrado aparece aquí.

import type { RuleSetOut } from "@takab/sdk";

import { utcStamp } from "../../lib/time";
import { useRuleSetRollback } from "./useRuleSetRollback";

export default function RuleSetHistory({
  versions,
  canEdit,
}: {
  versions: RuleSetOut[];
  canEdit: boolean;
}) {
  const rollback = useRuleSetRollback();
  const activa = versions.find((v) => v.is_active) ?? null;
  const anteriores = versions.filter((v) => !v.is_active);
  const porId = new Map(versions.map((v) => [v.rule_set_id, v.version]));

  return (
    <div className="soc-card rs-hist" data-testid="rule-set-history">
      <div className="soc-card__hd">
        <div>
          <div>Historial de umbrales</div>
          <div className="soc-card__sub">
            VOLVER ATRÁS CREA UNA VERSIÓN NUEVA QUE DECLARA A CUÁL VUELVE
          </div>
        </div>
        <span className="soc-bacnet">⬢ {versions.length} VERSIÓN(ES)</span>
      </div>

      {rollback.error !== null && (
        <p className="soc-user__error" role="alert">
          {rollback.conflict
            ? "EL RULE_SET CAMBIÓ EN EL SERVIDOR MIENTRAS MIRABAS · RECARGA Y REINTENTA"
            : rollback.error.toUpperCase()}
        </p>
      )}

      <ul className="rs-hist__list">
        {versions.map((v) => {
          const vuelveA = v.rolled_back_to != null ? porId.get(v.rolled_back_to) : undefined;
          return (
            <li key={v.rule_set_id} className="rs-hist__row" data-testid={`rs-row-${v.version}`}>
              <span className="soc-mono">v{v.version}</span>
              <span className="soc-mono rs-hist__ts">{utcStamp(Date.parse(v.created_at))} UTC</span>
              {v.is_active && <span className="rs-hist__pill">ACTIVA</span>}
              {vuelveA !== undefined && <span className="rs-hist__from">VUELVE A v{vuelveA}</span>}
              {/* La activa no ofrece volver a sí misma: el servidor lo rechaza
                  con 409, y un botón que solo puede fallar es una trampa. */}
              {canEdit && !v.is_active && activa !== null && (
                <button
                  type="button"
                  className="soc-btn soc-btn--ghost"
                  disabled={rollback.pendingId === v.rule_set_id}
                  onClick={() =>
                    rollback.volver({ ruleSetId: v.rule_set_id, baseVersion: activa.version })
                  }
                >
                  {rollback.pendingId === v.rule_set_id ? "VOLVIENDO…" : `VOLVER A v${v.version}`}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {anteriores.length === 0 && (
        <p className="soc-meta">SIN VERSIONES ANTERIORES · ESTA ES LA PRIMERA</p>
      )}
    </div>
  );
}
