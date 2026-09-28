// [T-9.33 · D-43] CONFIRMAR DICTAMEN / ESCALAR AL INSPECTOR, del lado del cliente.
//
// · La CABEZA vigente es la primera de la cadena (`GET /incidents/{id}/dictamens`,
//   más reciente primero: `created_at DESC, dictamen_id DESC`, la misma cabeza
//   que usa la nube para validar).
// · CONFIRMAR manda el `dictamen_id` de ESA cabeza. La nube decide (409 si ya no
//   es la vigente o ya está firmada; 403 si es ROJA o el rol no confirma). Un 409
//   recarga la cadena, porque lo que la brigada estaba leyendo ya no es lo que
//   rige; un 403 se dice y deja la otra salida: escalar.
// · ESCALAR es la solicitud de dictamen que ya existe
//   (`POST /incidents/{id}/dictamen-request`). Un 409 ahí significa que YA había
//   una solicitud pendiente: el inspector ya está avisado, que es lo que se pedía.
// · Best-effort DECLARADO, como el acuse táctico: un fallo se ve y se reintenta.
import {
  confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost,
  listDictamensIncidentsIncidentIdDictamensGet,
  requestDictamenIncidentsIncidentIdDictamenRequestPost,
  type DictamenOut,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";

export const CADENA_DICTAMEN_KEY = "cadena-dictamen";

/** Cada cuánto se vuelve a preguntar por la cabeza: puede cambiar bajo la
 *  brigada (la regla sube la banda con un daño tardío, otro la confirma). De
 *  aquí sale también la vejez del dato (`useStaleSince`). */
export const CADENA_POLL_MS = 30_000;

export type Envio = {
  estado: "idle" | "enviando" | "hecho" | "error";
  mensaje: string | null;
  /** [F3·r3] La nube respondió 409 «requiere inspector»: hay un daño ROJO
   *  reportado. No se reintenta: se escala. */
  requiereInspector?: boolean;
  /** [F3·r3] La nube respondió 409 al confirmar un VERDE: lo firma el sistema
   *  tras la gracia. Tampoco se reintenta. */
  loFirmaElSistema?: boolean;
  /** [F3·r3] El `dictamen_id` al que se refiere este resultado. «Confirmado» (o
   *  «requiere inspector») vale para ESA cabeza: si aparece otra, el resultado
   *  deja de aplicar y se vuelve a ofrecer. `null`/ausente ⇒ vale para cualquiera. */
  dictamenId?: string | null;
};

/** ¿El resultado de un envío aplica a la cabeza que se está viendo? */
export function envioVigente(e: Envio, dictamenId: string | null | undefined): Envio {
  if (e.estado === "enviando" || e.dictamenId == null || e.dictamenId === dictamenId) {
    return e;
  }
  return IDLE;
}

const IDLE: Envio = { estado: "idle", mensaje: null };

/** El 409 de un daño ROJO reportado (la regla aún no subió la banda) lleva
 *  «requiere inspector» en el `detail`; los otros 409 son de cabeza cambiada. */
function esRequiereInspector(error: unknown): boolean {
  const detail =
    error !== null && typeof error === "object" ? (error as { detail?: unknown }).detail : null;
  return typeof detail === "string" && detail.includes("requiere inspector");
}

/** El 409 de confirmar un VERDE: lo firma el sistema al terminar la gracia. */
function esVerdeDelSistema(error: unknown): boolean {
  const detail =
    error !== null && typeof error === "object" ? (error as { detail?: unknown }).detail : null;
  return typeof detail === "string" && detail.includes("lo firma el sistema");
}

const MENSAJE_VERDE_DEL_SISTEMA =
  "Un dictamen verde no lo confirma la brigada: lo emite el sistema cuando termina la espera sin daños reportados. Si ve daño, repórtelo o escálelo al inspector.";

const MENSAJE_CABEZA_CAMBIO =
  "El dictamen cambió mientras lo revisaba. Revise el vigente antes de confirmar.";

const MENSAJE_REQUIERE_INSPECTOR =
  "Hay un daño reportado que exige inspección: este dictamen no lo confirma la brigada. Escálelo al inspector.";

/** Error con el código HTTP, para que la vista pueda distinguir un 403 (no le
 *  corresponde leer la cadena) de una red caída. */
export class ErrorDeCadena extends Error {
  constructor(readonly status: number) {
    super(`cadena de dictámenes no disponible (${status})`);
  }
}

function mensajeConfirmar(status: number): string {
  if (status === 409) {
    return "El dictamen cambió o ya fue firmado mientras lo revisaba. Revise el vigente.";
  }
  if (status === 403) {
    return "Este dictamen no lo puede confirmar usted: escálelo al inspector.";
  }
  return "No se pudo confirmar. Compruebe la conexión y vuelva a intentarlo.";
}

export function useConfirmarDictamen(incidentId: string | null) {
  const cadena = useQuery({
    queryKey: [CADENA_DICTAMEN_KEY, incidentId],
    enabled: incidentId != null,
    refetchInterval: CADENA_POLL_MS,
    queryFn: async (): Promise<DictamenOut[]> => {
      const res = await listDictamensIncidentsIncidentIdDictamensGet({
        path: { incident_id: incidentId as string },
      });
      if (!res.data) {
        throw new ErrorDeCadena(res.response?.status ?? 0);
      }
      return res.data.items;
    },
  });
  const cabeza: DictamenOut | undefined = cadena.data?.[0];
  const refetch = cadena.refetch;

  const [confirmacion, setConfirmacion] = useState<Envio>(IDLE);
  const [escalado, setEscalado] = useState<Envio>(IDLE);

  const confirmar = useCallback(async () => {
    if (incidentId === null || cabeza === undefined || confirmacion.estado === "enviando") {
      return;
    }
    setConfirmacion({ estado: "enviando", mensaje: null });
    try {
      // [F3·r3] Se relee la cabeza JUSTO antes de enviar: la regla pudo subir la
      // banda (daño tardío) u otro pudo firmar mientras la brigada leía. Se
      // confirma lo que rige AHORA o nada; jamás la versión que ya no rige.
      const fresca = await refetch();
      const vigente = fresca.data?.[0];
      if (vigente === undefined || vigente.dictamen_id !== cabeza.dictamen_id) {
        setConfirmacion({ estado: "error", mensaje: MENSAJE_CABEZA_CAMBIO });
        return;
      }
      if (vigente.signed_by != null) {
        setConfirmacion({ estado: "idle", mensaje: null });
        return;
      }
      const dictamenId = vigente.dictamen_id;
      const res = await confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost({
        path: { incident_id: incidentId, dictamen_id: dictamenId },
      });
      if (res.error || !res.data) {
        const status = res.response?.status ?? 0;
        if (status === 409 && esRequiereInspector(res.error)) {
          setConfirmacion({
            estado: "error",
            mensaje: MENSAJE_REQUIERE_INSPECTOR,
            requiereInspector: true,
            dictamenId,
          });
          void refetch();
          return;
        }
        if (status === 409 && esVerdeDelSistema(res.error)) {
          setConfirmacion({
            estado: "error",
            mensaje: MENSAJE_VERDE_DEL_SISTEMA,
            loFirmaElSistema: true,
            dictamenId,
          });
          void refetch();
          return;
        }
        setConfirmacion({ estado: "error", mensaje: mensajeConfirmar(status) });
        if (status === 409) {
          void refetch();
        }
        return;
      }
      setConfirmacion({ estado: "hecho", mensaje: "Dictamen confirmado.", dictamenId });
      void refetch();
    } catch {
      setConfirmacion({ estado: "error", mensaje: mensajeConfirmar(0) });
    }
  }, [incidentId, cabeza, confirmacion.estado, refetch]);

  const escalar = useCallback(async () => {
    if (incidentId === null || escalado.estado === "enviando" || escalado.estado === "hecho") {
      return;
    }
    setEscalado({ estado: "enviando", mensaje: null });
    try {
      const res = await requestDictamenIncidentsIncidentIdDictamenRequestPost({
        path: { incident_id: incidentId },
        body: { note: "Escalado desde la app al confirmar el dictamen." },
      });
      const status = res.response?.status ?? 0;
      if (res.error || !res.data) {
        if (status === 409) {
          setEscalado({
            estado: "hecho",
            mensaje: "La solicitud al inspector ya estaba pendiente.",
          });
          return;
        }
        setEscalado({
          estado: "error",
          mensaje:
            status === 403
              ? "Su perfil no puede solicitar al inspector: avise a la administración del inmueble."
              : "No se pudo escalar. Compruebe la conexión y vuelva a intentarlo.",
        });
        return;
      }
      setEscalado({ estado: "hecho", mensaje: "Solicitud enviada al inspector." });
    } catch {
      setEscalado({
        estado: "error",
        mensaje: "No se pudo escalar. Compruebe la conexión y vuelva a intentarlo.",
      });
    }
  }, [incidentId, escalado.estado]);

  // [F3·r3] Lo que se enseña es el resultado de ESTA cabeza, no el de otra.
  return {
    cadena,
    cabeza,
    confirmacion: envioVigente(confirmacion, cabeza?.dictamen_id),
    escalado,
    confirmar,
    escalar,
  };
}
