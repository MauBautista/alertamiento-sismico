// 2.4 · Formulario de daños del táctico → alimenta el Triage de la consola.
// Las fotos forenses (2.3) se capturan en /camera y quedan ligadas por
// evidence_id. people_trapped ⇒ prioridad máxima (el backend notifica al SOC).
import { submitDamageReportIncidentsIncidentIdDamageReportsPost } from "@takab/sdk";
import { useRouter } from "expo-router";
import { useState } from "react";

import { useAlertState } from "@/features/alert/useAlertState";
import type { DamageKey, Severity } from "@/features/damage/categories";
import { DamageForm } from "@/features/damage/DamageForm";
import { useDamageDraft } from "@/features/damage/draft.store";
import { buildDamageReportBody } from "@/features/damage/payload";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

export default function Triage() {
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { data, loading, error, stale, dataUpdatedAt } = useAlertState(siteId);
  const incidentId = data?.incident?.incident_id ?? null;
  const evidenceIds = useDamageDraft((s) => s.evidenceIds);
  const resetDraft = useDamageDraft((s) => s.reset);

  const [selected, setSelected] = useState<Map<DamageKey, Severity>>(new Map());
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

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
    void (async () => {
      const body = buildDamageReportBody({
        categories: [...selected.entries()].map(([key, severity]) => ({ key, severity })),
        notes,
        zoneId: data?.my_zone?.zone_id ?? null,
        evidenceIds,
        tsDevice: new Date().toISOString(),
      });
      const res = await submitDamageReportIncidentsIncidentIdDamageReportsPost({
        path: { incident_id: incidentId },
        body,
      });
      setBusy(false);
      if (res.data) {
        resetDraft();
        setSelected(new Map());
        setNotes("");
        setSent(true);
      }
    })();
  };

  return (
    <StateFrame
      empty={incidentId === null}
      emptyText="Sin incidente activo en su sitio: no hay reporte de daños que levantar."
      error={data === null ? error : null}
      loading={loading}
      staleSinceMs={stale && data !== null ? dataUpdatedAt : null}
    >
      <DamageForm
        busy={busy}
        evidenceCount={evidenceIds.length}
        notes={sent ? "Reporte enviado. Puede levantar otro." : notes}
        onAddPhoto={() => router.push("/camera")}
        onNotes={(t) => {
          setSent(false);
          setNotes(t);
        }}
        onSeverity={setSeverity}
        onSubmit={submit}
        onToggle={toggle}
        selected={selected}
      />
    </StateFrame>
  );
}
