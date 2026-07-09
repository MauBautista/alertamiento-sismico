import { ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import NotificationChannels from "./NotificationChannels";
import SyncFooter from "./SyncFooter";
import ThresholdSlider from "./ThresholdSlider";
import {
  REFERENCE_BANDS,
  THRESHOLD_KEYS,
  activeTenantRuleSet,
  channelErrors,
  draftsFrom,
  isDedicated,
  patchChannels,
  patchThresholds,
  readChannels,
  readThresholds,
  siteCountOf,
  syncStatusOf,
  syncedFingerprintOf,
  thresholdErrors,
  verticalOf,
} from "./model";
import type { ChannelDraft, ThresholdBand, ThresholdKey } from "./model";
import { useRuleSetPublish } from "./useRuleSetPublish";
import { TENANTS_STALE_MS, useTenantGateways, useTenantSync, useTenants } from "./useTenants";

const SLIDERS: {
  key: ThresholdKey;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
  dangerAt: number;
  hint: string;
}[] = [
  {
    key: "pga_watch_g",
    label: "PGA · banda de cautela",
    min: 0.01,
    max: 0.3,
    step: 0.005,
    unit: "g",
    dangerAt: 0.18,
    hint: `Entra en vigilancia. Referencia §4.5: ${REFERENCE_BANDS}`,
  },
  {
    key: "pga_trip_g",
    label: "PGA · banda de disparo",
    min: 0.01,
    max: 0.3,
    step: 0.005,
    unit: "g",
    dangerAt: 0.18,
    hint: "Dispara sirena y cierre de gas en el gabinete, sin nube ni internet.",
  },
  {
    key: "pgv_watch_cms",
    label: "PGV · banda de cautela",
    min: 0.5,
    max: 20,
    step: 0.5,
    unit: "cm/s",
    dangerAt: 12,
    hint: "Mejor indicador de daño estructural a medio/largo plazo.",
  },
  {
    key: "pgv_trip_cms",
    label: "PGV · banda de disparo",
    min: 0.5,
    max: 20,
    step: 0.5,
    unit: "cm/s",
    dangerAt: 12,
    hint: "Calibrar con la tipología y la altura del edificio.",
  },
];

/** Valores planos del `ThresholdBand` leído (default del edge incluido). */
function valuesOf(band: ThresholdBand): Record<ThresholdKey, number> {
  return Object.fromEntries(THRESHOLD_KEYS.map((k) => [k, band[k].value])) as Record<
    ThresholdKey,
    number
  >;
}

/**
 * T-1.30 · Matriz Multi-Tenant y Umbrales (mockup 4, MultiTenantMatrix.jsx).
 *
 * Desviaciones honestas ratificadas frente al mockup:
 * - Fuera el panel "AISLAMIENTO DE DATOS" (schema por tenant / AES-256 / llaves KMS
 *   por tenant): son afirmaciones de infra que ninguna API respalda. Queda el badge
 *   `isolation_mode`, que sí es una columna real con CHECK ('logical','dedicated').
 * - Fuera el botón "NUEVO": no existe `POST /tenants`.
 * - Fuera la cuenta de usuarios: no hay endpoint. Los sitios se cuentan de `/sites`.
 * - `tenants.vertical` (texto libre, nullable) ES el "tipo de instalación"; pero los
 *   umbrales se guardan por SCOPE de rule_set, no por vertical. Las bandas de
 *   referencia del blueprint §4.5 se pintan como pista estática, no como agrupación.
 * - Cuatro sliders, no dos: el `ThresholdBand` real del edge tiene banda de cautela
 *   y de disparo para PGA y PGV.
 */
export default function TenantsPage() {
  const me = useSessionStore((s) => s.me);
  const hasEditAction = me?.allowed_actions.edit_thresholds === true;

  const data = useTenants();
  const now = useNow(5000);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = data.tenants.find((t) => t.tenant_id === selectedId) ?? data.tenants[0] ?? null;
  const tenantId = selected?.tenant_id ?? null;

  /**
   * `PUT /rule-sets` inserta la fila con `tenant_id = claims.tenant_id` mientras el
   * alcance lo elige el cuerpo; el servidor ya rechaza (403) un alcance ajeno. Un
   * superadmin viendo OTRO tenant es, por tanto, sólo lectura: ofrecerle un botón
   * condenado al 403 violaría la regla de oro 7.
   */
  const ownTenant = tenantId !== null && tenantId === me?.tenant_id;
  const canEdit = hasEditAction && ownTenant;

  const ruleSet = useMemo(
    () => activeTenantRuleSet(data.ruleSets, tenantId),
    [data.ruleSets, tenantId],
  );

  const savedThresholds = useMemo(() => readThresholds(ruleSet?.config), [ruleSet]);
  const savedDrafts = useMemo(() => draftsFrom(readChannels(ruleSet?.config)), [ruleSet]);

  const [values, setValues] = useState<Record<ThresholdKey, number>>(() =>
    valuesOf(savedThresholds),
  );
  const [drafts, setDrafts] = useState<ChannelDraft[]>(savedDrafts);
  /** El rule_set cambió en el servidor mientras había edición sin guardar. */
  const [changedElsewhere, setChangedElsewhere] = useState(false);

  const gateways = useTenantGateways(tenantId);
  const sync = useTenantSync(gateways.gatewayIds);
  const publish = useRuleSetPublish();

  /**
   * Instantánea del servidor de la que se sembró el borrador. `dirty` se mide contra
   * ELLA, no contra lo último que llegó del servidor: si no, una publicación ajena
   * haría parecer "sucio" un borrador intacto y bloquearía la re-siembra.
   */
  const baselineRef = useRef({ values: valuesOf(savedThresholds), drafts: savedDrafts });
  const seededRef = useRef<string | null>(null);

  const dirty =
    THRESHOLD_KEYS.some((k) => values[k] !== baselineRef.current.values[k]) ||
    JSON.stringify(drafts) !== JSON.stringify(baselineRef.current.drafts);

  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  /**
   * Re-siembra el borrador desde el servidor. Dos reglas:
   * 1. Al cambiar de TENANT siempre se re-siembra y se olvida la publicación previa
   *    (si no, el pie seguía anunciando "vN publicada" de un tenant que nunca se tocó).
   * 2. Si sólo cambió el rule_set (otro admin publicó) y hay edición SIN GUARDAR, NO se
   *    pisa el trabajo del operador: se avisa y él decide.
   */
  useEffect(() => {
    const key = `${tenantId ?? "none"}|${ruleSet?.rule_set_id ?? "none"}`;
    if (seededRef.current === key) {
      return;
    }
    const tenantChanged = seededRef.current?.split("|")[0] !== (tenantId ?? "none");
    if (!tenantChanged && dirtyRef.current) {
      setChangedElsewhere(true);
      return;
    }
    seededRef.current = key;
    setChangedElsewhere(false);
    const next = valuesOf(savedThresholds);
    baselineRef.current = { values: next, drafts: savedDrafts };
    setValues(next);
    setDrafts(savedDrafts);
    if (tenantChanged) {
      publish.reset();
    }
    // `publish` se omite a propósito de las deps: cambia de identidad en cada render
    // y aquí sólo sirve para olvidar la publicación del tenant anterior.
  }, [tenantId, ruleSet?.rule_set_id, savedThresholds, savedDrafts]);

  const errors = [...thresholdErrors(values), ...channelErrors(drafts)];

  /**
   * Un poll de `config-state` que falla o sigue en vuelo NO autoriza un veredicto:
   * react-query conserva el último dato bueno, así que sin este corte el pie seguiría
   * anunciando "SINCRONIZADO" sobre una lectura muerta (regla de oro 7).
   */
  const syncStates = sync.error !== null || sync.loading ? undefined : sync.states;

  const staleSince =
    !data.loading &&
    !data.error &&
    data.dataUpdatedAt > 0 &&
    now - data.dataUpdatedAt > TENANTS_STALE_MS
      ? data.dataUpdatedAt
      : null;

  function apply(): void {
    if (!tenantId || !canEdit) {
      return;
    }
    const withThresholds = patchThresholds(ruleSet?.config, values);
    publish.apply({
      tenantId,
      config: patchChannels(withThresholds, drafts),
      baseVersion: ruleSet?.version ?? null,
    });
  }

  function reset(): void {
    seededRef.current = `${tenantId ?? "none"}|${ruleSet?.rule_set_id ?? "none"}`;
    setChangedElsewhere(false);
    const next = valuesOf(savedThresholds);
    baselineRef.current = { values: next, drafts: savedDrafts };
    setValues(next);
    setDrafts(savedDrafts);
    publish.reset();
  }

  return (
    <section className="mt" data-screen-label="04 Multi-Tenant">
      <header className="mt__hd">
        <div>
          <span className="soc-meta">PLATAFORMA · ADMINISTRACIÓN</span>
          <h1 className="mt__title">Matriz Multi-Tenant y Umbrales</h1>
          <p className="mt__sub">
            Aislamiento por tenant · umbrales de disparo local del gabinete · cascada de respaldo.
          </p>
        </div>
        <div className="mt__legend">
          <div>
            <span className="mt__leg-sw mt__leg-sw--ded" /> Tenant dedicado · DB aislada
          </div>
          <div>
            <span className="mt__leg-sw mt__leg-sw--log" /> Tenant lógico · row-level security
          </div>
        </div>
      </header>

      <StateFrame
        label="MULTI-TENANT"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={data.tenants.length === 0}
        emptyText="SIN TENANTS VISIBLES PARA ESTE ROL"
        staleSince={staleSince}
      >
        <div className="mt__grid">
          <nav className="mt__list" aria-label="Tenants">
            <div className="mt__list-hd">
              <span className="soc-meta">{data.tenants.length} TENANT(S) VISIBLES</span>
            </div>
            {data.tenants.map((t) => {
              const sites = siteCountOf(data.sites, t.tenant_id);
              return (
                <button
                  type="button"
                  key={t.tenant_id}
                  className={`mt-tenant${t.tenant_id === tenantId ? " is-selected" : ""}`}
                  aria-pressed={t.tenant_id === tenantId}
                  onClick={() => setSelectedId(t.tenant_id)}
                >
                  <span className="mt-tenant__swatch" />
                  <span className="mt-tenant__body">
                    <span className="mt-tenant__name">{t.name}</span>
                    <span className="mt-tenant__meta">
                      {verticalOf(t)} · {sites === null ? "S/D" : `${sites} sitios`} · {t.status}
                    </span>
                  </span>
                  <span
                    className={`mt-tenant__iso mt-tenant__iso--${isDedicated(t) ? "dedicated" : "logical"}`}
                  >
                    {isDedicated(t) ? "DEDICADO" : "LÓGICO"}
                  </span>
                </button>
              );
            })}
          </nav>

          {selected && (
            <div className="mt__detail">
              <header className="mt__detail-hd">
                <div>
                  <div className="mt__detail-id">{selected.code}</div>
                  <h2 className="mt__detail-name">{selected.name}</h2>
                  <div className="mt__detail-meta">
                    {verticalOf(selected)} · plan {selected.plan_code} · visibilidad{" "}
                    {selected.visibility}
                  </div>
                </div>
                <span
                  className={`soc-pill ${isDedicated(selected) ? "soc-pill--edge" : "soc-pill--ok"}`}
                >
                  <ShieldCheck size={11} aria-hidden />
                  {isDedicated(selected) ? "TENANT DEDICADO" : "TENANT LÓGICO"}
                </span>
              </header>

              <StateFrame
                label="UMBRALES"
                loading={data.ruleSets === undefined && data.ruleSetsError === null}
                error={data.ruleSetsError}
                onRetry={data.refetch}
                empty={data.ruleSets !== undefined && ruleSet === null}
                emptyText="ESTE TENANT NO TIENE RULE_SET ACTIVO · EL GABINETE APLICA SUS DEFAULTS"
                staleSince={null}
              >
                <div className="soc-card">
                  <div className="soc-card__hd">
                    <div>
                      <div>Umbrales de disparo local</div>
                      <div className="soc-card__sub">
                        EDGE GATEWAY · config.edge.thresholds · v{ruleSet?.version ?? "—"}
                      </div>
                    </div>
                    <span className="soc-bacnet">⬢ EDGE · REGLAS LOCALES</span>
                  </div>
                  <div className="mt-sliders">
                    {SLIDERS.map((s) => (
                      <ThresholdSlider
                        key={s.key}
                        label={s.label}
                        value={values[s.key]}
                        min={s.min}
                        max={s.max}
                        step={s.step}
                        unit={s.unit}
                        dangerAt={s.dangerAt}
                        hint={s.hint}
                        fromConfig={savedThresholds[s.key].fromConfig}
                        disabled={!canEdit}
                        onChange={(v) => setValues((prev) => ({ ...prev, [s.key]: v }))}
                      />
                    ))}
                  </div>
                </div>

                <NotificationChannels drafts={drafts} disabled={!canEdit} onChange={setDrafts} />

                {hasEditAction && !ownTenant && (
                  <p className="soc-meta">
                    SÓLO LECTURA · los umbrales de un tenant ajeno se editan con una sesión de ese
                    tenant (el servidor los escribe con el tenant del token)
                  </p>
                )}

                <SyncFooter
                  status={syncStatusOf(syncStates)}
                  syncedFingerprint={syncedFingerprintOf(syncStates)}
                  publishedVersion={publish.publishedVersion}
                  changedElsewhere={changedElsewhere}
                  dirty={dirty}
                  errors={errors}
                  applyError={publish.error ?? sync.error}
                  pending={publish.pending}
                  canEdit={canEdit}
                  onApply={apply}
                  onReset={reset}
                />
              </StateFrame>
            </div>
          )}
        </div>
      </StateFrame>
    </section>
  );
}
