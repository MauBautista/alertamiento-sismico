// Alta de simulacro (T-2.48): a quién, cuánto, cuándo y por qué.
//
// Hasta T-2.47 la consola solo sabía lanzar "5 minutos a TODOS los gabinetes
// del tenant": `POST /drills` aceptaba `site_ids`, `duration_s`, `note` y
// `scheduled_at` desde T-1.60/T-2.03 y nadie los mandaba. Un simulacro real se
// hace por edificio y con aviso previo, no de golpe en todo el corporativo.
//
// AHORA vs PROGRAMAR son dos cosas distintas y el modal no las mezcla:
// programar NO emite nada — deja una agenda que después alguien ejecuta con un
// clic (regla de oro 8).

import { useMemo, useState } from "react";

import { listSitesSitesGet } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import Modal from "../../components/Modal";
import StateFrame from "../../components/StateFrame";
import type { StartDrillInput } from "./useActiveDrill";

/** Ventanas ofrecidas; el CHECK de DB acota a 30 s..1 h. */
const DURATIONS: readonly { value: number; label: string }[] = [
  { value: 60, label: "1 MIN" },
  { value: 180, label: "3 MIN" },
  { value: 300, label: "5 MIN" },
  { value: 600, label: "10 MIN" },
  { value: 900, label: "15 MIN" },
  { value: 1800, label: "30 MIN" },
];

export interface DrillModalProps {
  pending: boolean;
  error: string | null;
  onSubmit: (input: StartDrillInput) => void;
  onClose: () => void;
}

/** `datetime-local` → ISO UTC. Devuelve null si el navegador no dio nada útil. */
function localToUtcIso(value: string): string | null {
  if (value.trim() === "") return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}

export default function DrillModal({ pending, error, onSubmit, onClose }: DrillModalProps) {
  const sites = useQuery({
    queryKey: ["sites"],
    queryFn: async () => {
      const { data, response } = await listSitesSitesGet();
      if (data === undefined) throw new Error(`GET /sites falló (${response.status})`);
      return data;
    },
    staleTime: 300_000,
  });

  const [selected, setSelected] = useState<string[]>([]);
  const [durationS, setDurationS] = useState(300);
  const [note, setNote] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [when, setWhen] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);

  const live = useMemo(
    () => (sites.data ?? []).filter((s) => s.status !== "retired"),
    [sites.data],
  );

  const toggle = (siteId: string) =>
    setSelected((prev) =>
      prev.includes(siteId) ? prev.filter((s) => s !== siteId) : [...prev, siteId],
    );

  const submit = () => {
    let scheduledAt: string | null = null;
    if (scheduling) {
      scheduledAt = localToUtcIso(when);
      if (scheduledAt === null) {
        setInvalid("INDICA LA FECHA Y HORA DEL SIMULACRO");
        return;
      }
      if (Date.parse(scheduledAt) <= Date.now()) {
        setInvalid("LA HORA PROGRAMADA DEBE ESTAR EN EL FUTURO");
        return;
      }
    }
    setInvalid(null);
    onSubmit({
      // Lista vacía = "todos los comandables": el servidor decide quién lo es,
      // el navegador no tiene forma honesta de saberlo (`/sites` no trae
      // gabinetes) y adivinarlo sería inventar la lista de destinatarios.
      siteIds: selected.length === 0 ? null : selected,
      durationS,
      note: note.trim() === "" ? null : note.trim(),
      scheduledAt,
    });
  };

  return (
    <Modal title="SIMULACRO INSTITUCIONAL" onClose={onClose}>
      <div className="soc-drillform" data-testid="drill-modal">
        <p className="soc-drillform__notice" role="note">
          UN SIMULACRO PINTA EL BANNER NO-REAL Y VOCEA EL AVISO EN LOS GABINETES ELEGIDOS ·{" "}
          <strong>CERO RELÉS</strong> · NO CREA INCIDENTES · UNA ALERTA REAL LO ABORTA
        </p>

        <fieldset className="soc-drillform__group">
          <legend>SITIOS</legend>
          <StateFrame
            label="SITIOS"
            loading={sites.isPending}
            error={sites.error ? sites.error.message : null}
            onRetry={() => void sites.refetch()}
            empty={!sites.isPending && sites.error === null && live.length === 0}
            emptyText="SIN SITIOS VISIBLES"
          >
            <ul className="soc-drillform__sites">
              {live.map((s) => (
                <li key={s.site_id}>
                  <label>
                    <input
                      type="checkbox"
                      aria-label={s.name}
                      checked={selected.includes(s.site_id)}
                      onChange={() => toggle(s.site_id)}
                    />
                    <span>{s.name}</span>
                    <span className="soc-meta soc-mono">{s.code}</span>
                  </label>
                </li>
              ))}
            </ul>
          </StateFrame>
          <p className="soc-meta">
            {selected.length === 0
              ? "SIN SELECCIÓN ⇒ TODOS LOS SITIOS CON GABINETE COMANDABLE DEL TENANT"
              : `${selected.length} SITIO(S) SELECCIONADO(S)`}
          </p>
        </fieldset>

        <label className="soc-meta" htmlFor="drill-duration">
          DURACIÓN DE LA VENTANA
        </label>
        <select
          id="drill-duration"
          className="soc-user__input"
          value={durationS}
          onChange={(e) => setDurationS(Number(e.target.value))}
        >
          {DURATIONS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>

        <fieldset className="soc-drillform__group">
          <legend>CUÁNDO</legend>
          <label>
            <input
              type="radio"
              name="drill-when"
              checked={!scheduling}
              onChange={() => setScheduling(false)}
            />
            <span>AHORA</span>
          </label>
          <label>
            <input
              type="radio"
              name="drill-when"
              checked={scheduling}
              onChange={() => setScheduling(true)}
            />
            <span>PROGRAMAR</span>
          </label>
          {scheduling && (
            <>
              <label className="soc-meta" htmlFor="drill-when-at">
                FECHA Y HORA (LOCAL)
              </label>
              <input
                id="drill-when-at"
                className="soc-user__input soc-mono"
                type="datetime-local"
                value={when}
                onChange={(e) => setWhen(e.target.value)}
              />
              <p className="soc-meta">
                PROGRAMAR NO EMITE NADA: DEJA EL SIMULACRO ARMADO Y ALGUIEN LO EJECUTA CON UN CLIC A
                LA HORA PREVISTA
              </p>
            </>
          )}
        </fieldset>

        <label className="soc-meta" htmlFor="drill-note">
          NOTA (OPCIONAL — P.EJ. SIMULACRO TRIMESTRAL)
        </label>
        <input
          id="drill-note"
          className="soc-user__input"
          value={note}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
        />

        {(invalid !== null || error !== null) && (
          <p className="soc-user__error" role="alert">
            {invalid ?? error?.toUpperCase()}
          </p>
        )}

        <div className="soc-drillform__actions">
          <button type="button" className="soc-btn soc-btn--secondary" onClick={onClose}>
            VOLVER
          </button>
          <button
            type="button"
            className="soc-btn soc-btn--primary"
            disabled={pending}
            onClick={submit}
          >
            {scheduling ? "PROGRAMAR SIMULACRO" : "INICIAR AHORA"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
