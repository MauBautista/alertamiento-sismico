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
import { huellaDelReingreso } from "@/features/dictamen/confirmacion";
import {
  antiguedadDelCertificado,
  bloqueoDelInmueble,
  certificateView,
} from "@/features/dictamen/dictamenView";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { useStaleSince } from "@/ui/useStaleSince";

/** Cuánto se sigue afirmando que este dictamen es el vigente. Sin poll del que
 *  derivarlo: la cadena puede recibir una versión nueva en cualquier momento. */
const DICTAMEN_STALE_MS = 60_000;

export default function Dictamen() {
  const siteId = useWatchedSiteId();
  const { data: state, staleSinceMs: estadoStaleSinceMs } = useAlertState(siteId);
  // [T-8.11 · A-022] Desde D-33 el motor cierra el incidente segundos después de
  // la firma: `incident` vuelve a null y el dictamen sigue vigente. Su incidente
  // viaja en `reentry.incident_id`; sin él, esta pantalla decía «Sin incidente
  // activo» justo cuando el certificado existe.
  const incidentId = state?.incident?.incident_id ?? state?.reentry?.incident_id ?? null;

  const dictamen = useQuery({
    // [T-9.33] Con la HUELLA del reingreso, como INICIO (F3·r4): una firma nueva
    // sobre este incidente cambia el estado, y el dictamen se vuelve a pedir en vez
    // de pintar el veredicto sustituido junto al bloqueo que lo sustituyó.
    queryKey: ["dictamen", incidentId, huellaDelReingreso(state)],
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
  // [T-5.21] Del RELOJ, y no de `failureCount`. Esta pantalla NO hace poll —
  // un dictamen firmado no cambia—, pero **puede ser sustituido**: la cadena
  // admite una versión nueva en cualquier momento, y este documento es el que
  // dice si el edificio se ocupa. Pasado el minuto se deja de afirmar que es
  // el vigente. El umbral va escrito porque aquí no hay intervalo del que
  // derivarlo, y un umbral inventado sin decirlo es lo que esta ficha corrige.
  const dictamenStaleSinceMs = useStaleSince(dictamen.dataUpdatedAt, DICTAMEN_STALE_MS / 3);

  const [downloading, setDownloading] = useState(false);
  // [D-43 · F3] «Descargado» es de UN folio: se guarda para cuál, y con otra
  // firma deja de valer sin tener que borrarlo en un efecto.
  const [cachedFolio, setCachedFolio] = useState<string | null>(null);
  // [T-8.11] Una descarga que falla (sin red, URL firmada caducada) se DICE: antes
  // el `finally` sin `catch` la dejaba en silencio y el botón volvía a su sitio
  // como si nada.
  const [downloadErr, setDownloadErr] = useState<{ folio: string; msg: string } | null>(null);

  // [D-43 · F3] El PDF local se nombra por el FOLIO de la firma (su
  // `dictamen_id`), no por el incidente: la cadena admite firmas nuevas del mismo
  // incidente (el sistema, una confirmación, el inspector) y un nombre por
  // incidente abría el papel VIEJO de otra firma como si fuera el vigente. Sin
  // folio (sin firma) no hay papel local que abrir.
  const folio = dictamen.data?.signed ? (dictamen.data.folio ?? null) : null;
  const localPdf = useMemo(
    () => (folio ? new File(Paths.document, `dictamen-${folio}.pdf`) : null),
    [folio],
  );

  const cached = folio !== null && cachedFolio === folio;
  const downloadError = downloadErr !== null && downloadErr.folio === folio ? downloadErr.msg : null;

  useEffect(() => {
    if (localPdf === null || folio === null) {
      return;
    }
    let alive = true;
    Promise.resolve(localPdf.exists).then((v) => {
      if (alive) {
        setCachedFolio((prev) => (v ? folio : prev === folio ? null : prev));
      }
    });
    return () => {
      alive = false;
    };
  }, [localPdf, folio]);

  const cert = dictamen.data ? certificateView(dictamen.data) : null;
  // [T-9.33 · D-49] El MISMO estado del inmueble que pinta el panel: si allí está
  // bloqueado, el certificado no puede decir «aprobado» en grande.
  const bloqueo = dictamen.data ? bloqueoDelInmueble(dictamen.data, state) : null;

  const download = () => {
    if (!dictamen.data?.pdf_url || localPdf === null || folio === null) {
      return;
    }
    const deEste = folio;
    setDownloading(true);
    setDownloadErr(null);
    void (async () => {
      try {
        if (localPdf.exists) {
          localPdf.delete();
        }
        await File.downloadFileAsync(dictamen.data.pdf_url as string, localPdf);
        setCachedFolio(deEste);
      } catch {
        setDownloadErr({
          folio: deEste,
          msg: "No se pudo descargar el certificado. Compruebe la conexión y vuelva a intentarlo.",
        });
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
      staleSinceMs={antiguedadDelCertificado(dictamenStaleSinceMs, estadoStaleSinceMs)}
    >
      {cert ? (
        <DictamenCertificate
          bloqueo={bloqueo}
          cert={cert}
          downloading={downloading}
          downloadError={downloadError}
          onDownloadPdf={download}
          onOpenPdf={open}
          pdfCached={cached}
        />
      ) : null}
    </StateFrame>
  );
}
