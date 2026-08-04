import { useEffect, useState } from "react";

import type { SiteOut } from "@takab/sdk";

import StateFrame from "../../components/StateFrame";
import { utcStamp } from "../../lib/time";
import { useNow } from "../../lib/useNow";
import {
  CODES_STALE_MS,
  generateEnrollmentCode,
  useCreateEnrollmentCode,
  useEnrollmentCodes,
  useRevokeEnrollmentCode,
} from "./useEnrollmentCodes";

/** Ventanas de vigencia ofrecidas. Sin caducidad NO es una opción por defecto:
 * un código eterno pegado en un tablón enrola a cualquiera que pase. */
const WINDOWS: { label: string; hours: number | null }[] = [
  { label: "24 horas", hours: 24 },
  { label: "7 días", hours: 24 * 7 },
  { label: "30 días", hours: 24 * 30 },
  { label: "Sin caducidad", hours: null },
];

/** Cuánto se queda el código nuevo en pantalla antes de borrarse del DOM. */
export const REVEAL_MS = 120_000;

function expiryLabel(iso: string | null | undefined, nowMs: number): string {
  if (!iso) {
    return "SIN CADUCIDAD";
  }
  const at = Date.parse(iso);
  return at <= nowMs ? `VENCIDO · ${utcStamp(at)} UTC` : `VENCE ${utcStamp(at)} UTC`;
}

function usesLabel(uses: number, maxUses: number | null | undefined): string {
  return maxUses == null ? `${uses} USO(S) · SIN TOPE` : `${uses}/${maxUses} USOS`;
}

export interface EnrollmentCodesProps {
  site: SiteOut;
  onClose: () => void;
}

/**
 * [T-2.53] Códigos de alta de ocupantes por estación.
 *
 * `POST/GET/DELETE /sites/{id}/enrollment-codes` existían desde T-2.03 y NADIE los
 * llamaba — ni la web ni la app. Sin esta tarjeta no hay forma de enrolar un
 * teléfono real, que es lo que `GATE-HW` está esperando.
 *
 * El código se trata como secreto operativo:
 * - Se genera con `crypto.getRandomValues`, no con `Math.random()`.
 * - El recién creado se muestra UNA vez, con un temporizador que lo saca del DOM
 *   (`REVEAL_MS`), y con un botón para ocultarlo antes.
 * - Los ya existentes salen **enmascarados**; revelarlos es un acto explícito.
 * - **Nada se guarda en `localStorage`/`sessionStorage`** (`CLAUDE.md §8`).
 *
 * Honestidad sobre el alcance de esa protección: `GET .../enrollment-codes`
 * devuelve el código en claro, así que el enmascarado evita la mirada por encima
 * del hombro y la captura de pantalla, no a quien puede llamar al endpoint. El
 * control real es `enrollment_manage` + la RLS por tenant. Revocar es la única
 * respuesta a un código filtrado, y por eso está a un clic.
 */
export default function EnrollmentCodes({ site, onClose }: EnrollmentCodesProps) {
  const data = useEnrollmentCodes(site.site_id);
  const create = useCreateEnrollmentCode();
  const revoke = useRevokeEnrollmentCode();

  const [windowIdx, setWindowIdx] = useState(0);
  const [maxUses, setMaxUses] = useState("25");
  const [fresh, setFresh] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<string | null>(null);

  // El código nuevo no se queda en el DOM indefinidamente: una consola SOC vive en
  // un videowall y esta pantalla puede quedarse abierta toda la guardia.
  useEffect(() => {
    if (fresh === null) {
      return;
    }
    const timer = setTimeout(() => setFresh(null), REVEAL_MS);
    return () => clearTimeout(timer);
  }, [fresh]);

  // Cambiar de estación no arrastra el secreto de la anterior.
  useEffect(() => {
    setFresh(null);
    setRevealed(null);
  }, [site.site_id]);

  const nowMs = useNow(5000);
  const staleSince =
    !data.loading &&
    data.error === null &&
    data.dataUpdatedAt > 0 &&
    nowMs - data.dataUpdatedAt > CODES_STALE_MS
      ? data.dataUpdatedAt
      : null;
  const parsedUses = maxUses.trim() === "" ? null : Number.parseInt(maxUses, 10);
  const usesInvalid = parsedUses !== null && (!Number.isFinite(parsedUses) || parsedUses < 1);

  function submit(e: React.FormEvent): void {
    e.preventDefault();
    if (usesInvalid) {
      return;
    }
    const code = generateEnrollmentCode();
    const hours = WINDOWS[windowIdx].hours;
    create.mutate(
      {
        siteId: site.site_id,
        code,
        expiresAt: hours === null ? null : new Date(nowMs + hours * 3_600_000).toISOString(),
        maxUses: parsedUses,
      },
      { onSuccess: () => setFresh(code) },
    );
  }

  return (
    <section className="enroll" data-testid="enrollment-codes">
      <header className="enroll__hd">
        <div>
          <h3 className="enroll__title">Códigos de alta · {site.name}</h3>
          <p className="enroll__sub">
            Quien teclee uno de estos códigos en la app queda enrolado como OCUPANTE de esta
            estación. Nunca concede otro rol (lo fija la base de datos).
          </p>
        </div>
        <button type="button" className="soc-btn soc-btn--secondary" onClick={onClose}>
          VOLVER
        </button>
      </header>

      <form className="enroll__form" data-testid="enrollment-form" onSubmit={submit}>
        <label className="enroll__field">
          <span>Vigencia</span>
          <select value={windowIdx} onChange={(e) => setWindowIdx(Number(e.target.value))}>
            {WINDOWS.map((w, i) => (
              <option key={w.label} value={i}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
        <label className="enroll__field">
          <span>Usos máximos (vacío = sin tope)</span>
          <input
            type="number"
            min={1}
            value={maxUses}
            onChange={(e) => setMaxUses(e.target.value)}
          />
        </label>
        <button type="submit" className="soc-btn" disabled={create.isPending || usesInvalid}>
          {create.isPending ? "GENERANDO…" : "GENERAR CÓDIGO"}
        </button>
      </form>

      {WINDOWS[windowIdx].hours === null && (
        <p className="enroll__warn" role="note" data-testid="no-expiry-warning">
          SIN CADUCIDAD · un código que no vence enrola a cualquiera que lo lea, para siempre.
          Revócalo en cuanto termine el alta del personal.
        </p>
      )}

      {create.error !== null && (
        <p className="enroll__error" role="alert" data-testid="enrollment-error">
          {create.error.message}
        </p>
      )}

      {fresh !== null && (
        <div className="enroll__fresh" data-testid="fresh-code">
          <span className="soc-meta">ENTRÉGALO AHORA · NO SE VOLVERÁ A DESTACAR</span>
          <code className="enroll__code">{fresh}</code>
          <div className="enroll__freshactions">
            <button
              type="button"
              className="soc-btn soc-btn--secondary"
              onClick={() => void navigator.clipboard?.writeText(fresh)}
            >
              COPIAR
            </button>
            <button
              type="button"
              className="soc-btn soc-btn--secondary"
              onClick={() => setFresh(null)}
            >
              OCULTAR
            </button>
          </div>
        </div>
      )}

      <StateFrame
        label="CÓDIGOS"
        loading={data.loading}
        error={data.error}
        onRetry={data.refetch}
        empty={data.codes.length === 0}
        emptyText="SIN CÓDIGOS EN ESTA ESTACIÓN"
        staleSince={staleSince}
      >
        <ul className="enroll__list">
          {data.codes.map((c) => (
            <li
              key={c.code}
              className={`enroll__row${c.active ? "" : " enroll__row--revoked"}`}
              data-testid="enrollment-row"
            >
              <code className="enroll__code enroll__code--masked">
                {revealed === c.code ? c.code : "•".repeat(c.code.length)}
              </code>
              <span className="soc-meta">
                {c.grants_role.toUpperCase()} · {expiryLabel(c.expires_at, nowMs)} ·{" "}
                {usesLabel(c.uses, c.max_uses)}
                {!c.active && " · REVOCADO"}
              </span>
              <div className="enroll__rowactions">
                <button
                  type="button"
                  className="soc-btn soc-btn--secondary"
                  onClick={() => setRevealed(revealed === c.code ? null : c.code)}
                >
                  {revealed === c.code ? "OCULTAR" : "VER"}
                </button>
                {c.active && (
                  <button
                    type="button"
                    className="soc-btn soc-btn--secondary"
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate({ siteId: site.site_id, code: c.code })}
                  >
                    REVOCAR
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </StateFrame>

      {revoke.error !== null && (
        <p className="enroll__error" role="alert">
          {revoke.error.message}
        </p>
      )}
      <p className="soc-meta">
        Revocar desactiva el código y conserva su historial de usos: la evidencia de quién se enroló
        con él no se borra (regla de oro 11).
      </p>
    </section>
  );
}
