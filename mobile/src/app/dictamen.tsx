// 2.7 · Certificado de reingreso (táctico, dictamen_read). Lee el dictamen
// firmado (GET /incidents/{id}/dictamen) y descarga el MISMO PDF que genera la
// consola (presignado) a un archivo privado cacheado offline. No genera PDF.
import { readDictamenIncidentsIncidentIdDictamenGet } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { useEffect, useMemo, useState } from "react";

import { useAlertState } from "@/features/alert/useAlertState";
import { DictamenCertificate } from "@/features/dictamen/DictamenCertificate";
import { certificateView } from "@/features/dictamen/dictamenView";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";

export default function Dictamen() {
  const siteId = useWatchedSiteId();
  const { data: state } = useAlertState(siteId);
  const incidentId = state?.incident?.incident_id ?? null;

  const dictamen = useQuery({
    queryKey: ["dictamen", incidentId],
    enabled: incidentId != null,
    queryFn: async () => {
      const res = await readDictamenIncidentsIncidentIdDictamenGet({
        path: { incident_id: incidentId as string },
      });
      if (!res.data) {
        throw new Error("dictamen no disponible");
      }
      return res.data;
    },
  });

  const [downloading, setDownloading] = useState(false);
  const [cached, setCached] = useState(false);

  const localPdf = useMemo(
    () => (incidentId ? new File(Paths.document, `dictamen-${incidentId}.pdf`) : null),
    [incidentId],
  );

  useEffect(() => {
    if (localPdf === null) {
      return;
    }
    let alive = true;
    Promise.resolve(localPdf.exists).then((v) => {
      if (alive) {
        setCached(v);
      }
    });
    return () => {
      alive = false;
    };
  }, [localPdf]);

  const cert = dictamen.data ? certificateView(dictamen.data) : null;

  const download = () => {
    if (!dictamen.data?.pdf_url || localPdf === null) {
      return;
    }
    setDownloading(true);
    void (async () => {
      try {
        if (localPdf.exists) {
          localPdf.delete();
        }
        await File.downloadFileAsync(dictamen.data.pdf_url as string, localPdf);
        setCached(true);
      } finally {
        setDownloading(false);
      }
    })();
  };

  const open = () => {
    if (localPdf !== null) {
      void Sharing.shareAsync(localPdf.uri, { mimeType: "application/pdf" });
    }
  };

  return (
    <StateFrame
      empty={incidentId === null || (dictamen.data != null && cert === null)}
      emptyText={
        incidentId === null
          ? "Sin incidente activo: no hay dictamen que consultar."
          : "Aún no hay un dictamen firmado para este incidente."
      }
      error={dictamen.isError && !dictamen.data ? "No se pudo cargar el dictamen." : null}
      loading={dictamen.isLoading && incidentId !== null}
      staleSinceMs={null}
    >
      {cert ? (
        <DictamenCertificate
          cert={cert}
          downloading={downloading}
          onDownloadPdf={download}
          onOpenPdf={open}
          pdfCached={cached}
        />
      ) : null}
    </StateFrame>
  );
}
