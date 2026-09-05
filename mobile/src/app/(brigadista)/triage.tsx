// 2.4 · Formulario de daños del táctico → alimenta el Triage de la consola.
// Las fotos forenses (2.3) se capturan en /camera y quedan ligadas por su id
// LOCAL en la cola. people_trapped ⇒ prioridad máxima: el reporte salta al
// frente de la cola (§2.4) y el backend notifica al SOC.
//
// [T-2.108] Antes esto hacía POST directo. Dos fallos en uno: sin red el
// reporte se PERDÍA, y el cliente del SDK LANZA al morir `fetch`, así que el
// `catch` inexistente dejaba `busy` en true para siempre — el botón se
// quedaba en "ENVIANDO…" sin decir nada. Ahora se encola (escritura local, no
// red) y todos los desenlaces se declaran.
import { useRouter } from "expo-router";
import { useState } from "react";

import { useAlertState } from "@/features/alert/useAlertState";
import { queuePriority, type DamageKey, type Severity } from "@/features/damage/categories";
import { DamageForm } from "@/features/damage/DamageForm";
import { useDamageDraft } from "@/features/damage/draft.store";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

export default function Triage() {
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { data, loading, error, staleSinceMs } = useAlertState(siteId);
  const incidentId = data?.incident?.incident_id ?? null;
  const evidenceIds = useDamageDraft((s) => s.evidenceIds);
  const resetDraft = useDamageDraft((s) => s.reset);

  const [selected, setSelected] = useState<Map<DamageKey, Severity>>(new Map());
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);

  const toggle = (key: DamageKey) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.set(key, "medium");
      }
      return next;
    });
  };
  const setSeverity = (key: DamageKey, sev: Severity) => {
    setSelected((prev) => new Map(prev).set(key, sev));
  };

  const submit = () => {
    if (incidentId === null) {
      return;
    }
    setBusy(true);
    setStatus(null);
    void (async () => {
      try {
        const categories = [...selected.entries()].map(([key, severity]) => ({ key, severity }));
        await useQueueStore.getState().enqueueDamageReport(
          {
            incident_id: incidentId,
            categories,
            notes: notes.trim() || null,
            zone_id: data?.my_zone?.zone_id ?? null,
            // Ids LOCALES de las fotos de esta cola: el `evidence_id` del
            // servidor se resuelve al despachar (en avión aún no existe).
            evidence_refs: evidenceIds,
            ts_device: new Date().toISOString(),
          },
          queuePriority(categories),
        );
        resetDraft();
        setSelected(new Map());
        setNotes("");
        setStatus({
          ok: true,
          text: "Reporte guardado en este teléfono y en cola de envío. Se enviará solo al haber red — véalo en Sincronización.",
        });
        // Con red sale en el acto; sin red lo hará el listener al reconectar.
        void drainQueue();
      } catch {
        // Encolar es una escritura LOCAL: si falla, el dato no existe en
        // ninguna parte y callarlo sería lo peor que puede hacer esta pantalla.
        setStatus({
          ok: false,
          text: "No se pudo guardar el reporte en este teléfono. No se ha enviado nada: vuelva a intentarlo.",
        });
      } finally {
        setBusy(false);
      }
    })();
  };

  return (
    <StateFrame
      empty={incidentId === null}
      emptyText="Sin incidente activo en su sitio: no hay reporte de daños que levantar."
      error={data === null ? error : null}
      loading={loading}
      staleSinceMs={staleSinceMs}
    >
      <DamageForm
        busy={busy}
        evidenceCount={evidenceIds.length}
        notes={notes}
        onAddPhoto={() => router.push("/camera")}
        onNotes={(t) => {
          setStatus(null);
          setNotes(t);
        }}
        onSeverity={setSeverity}
        onSubmit={submit}
        onToggle={toggle}
        selected={selected}
        status={status}
      />
    </StateFrame>
  );
}
