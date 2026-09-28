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
  /** [D-49 · R1] 409: el edificio sigue en movimiento. SE reintenta, cuando
   *  vuelva la calma: no es terminal. */
  esperaCalma?: boolean;
  /** [D-49] 409: la cabeza no es un AMARILLO de la regla (fila histórica sin
   *  banda): la firma el inspector. Terminal. */
  loFirmaElInspector?: boolean;
  /** [D-49] La cabeza ya estaba firmada (al releerla o por el 409). Terminal. */
  yaFirmado?: boolean;
  /** [D-49] 404: el incidente no está al alcance de este perfil. Terminal. */
  fueraDeAlcance?: boolean;
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

/** El `detail` de un error del SDK, o `""`. */
function detalle(error: unknown): string {
  const d =
    error !== null && typeof error === "object" ? (error as { detail?: unknown }).detail : null;
  return typeof d === "string" ? d : "";
}

// [D-49] Cada 409 de `routers/dictamens.confirm_dictamen` se reconoce por su
// `detail` literal (el orden importa: el de banda también dice «lo firma el
// inspector» y el del VERDE «lo firma el sistema»).
const esRequiereInspector = (e: unknown) => detalle(e).includes("requiere inspector");
const esVerdeDelSistema = (e: unknown) => detalle(e).includes("lo firma el sistema");
const esEsperaCalma = (e: unknown) => detalle(e).includes("vuelva a calma");
const esLoFirmaElInspector = (e: unknown) => detalle(e).includes("lo firma el inspector");
const esYaFirmado = (e: unknown) => detalle(e).includes("ya está firmado");

const MENSAJE_VERDE_DEL_SISTEMA =
  "Un dictamen verde no lo confirma la brigada: lo emite el sistema cuando termina la espera sin daños reportados. Si ve daño, repórtelo o escálelo al inspector.";

const MENSAJE_CABEZA_CAMBIO =
  "El dictamen cambió mientras lo revisaba. Revise el vigente antes de confirmar.";

const MENSAJE_REQUIERE_INSPECTOR =
  "Hay un daño reportado que exige inspección: este dictamen no lo confirma la brigada. Escálelo al inspector.";

export const MENSAJE_ESPERE_CALMA =
  "El edificio sigue en movimiento: espere a que el edificio vuelva a calma para confirmar.";

const MENSAJE_LO_FIRMA_EL_INSPECTOR =
  "Este dictamen no salió de la regla automática: no lo confirma la brigada, lo firma el inspector. Escálelo.";

const MENSAJE_YA_FIRMADO =
  "El dictamen ya estaba firmado: no hay nada que confirmar. Revise el vigente.";

const MENSAJE_FUERA_DE_ALCANCE =
  "Este incidente no pertenece a su inmueble o su perfil ya no lo ve: no se puede confirmar desde aquí.";

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

/** [D-49] La respuesta de confirmar con causa CONOCIDA ⇒ su mensaje y su
 *  bandera. `null` ⇒ la genérica de `mensajeConfirmar`. */
function clasificar(
  status: number,
  error: unknown,
): Omit<Envio, "estado" | "dictamenId"> | null {
  if (status === 404) {
    return { mensaje: MENSAJE_FUERA_DE_ALCANCE, fueraDeAlcance: true };
  }
  if (status !== 409) {
    return null;
  }
  if (esEsperaCalma(error)) {
    return { mensaje: MENSAJE_ESPERE_CALMA, esperaCalma: true };
  }
  if (esRequiereInspector(error)) {
    return { mensaje: MENSAJE_REQUIERE_INSPECTOR, requiereInspector: true };
  }
  if (esVerdeDelSistema(error)) {
    return { mensaje: MENSAJE_VERDE_DEL_SISTEMA, loFirmaElSistema: true };
  }
  if (esLoFirmaElInspector(error)) {
    return { mensaje: MENSAJE_LO_FIRMA_EL_INSPECTOR, loFirmaElInspector: true };
  }
  if (esYaFirmado(error)) {
    return { mensaje: MENSAJE_YA_FIRMADO, yaFirmado: true };
  }
  return null;
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
        // [D-49] Ya firmado por otro: se DICE (antes volvía muda a `idle`).
        setConfirmacion({
          estado: "error",
          mensaje: MENSAJE_YA_FIRMADO,
          yaFirmado: true,
          dictamenId: vigente.dictamen_id,
        });
        return;
      }
      const dictamenId = vigente.dictamen_id;
      const res = await confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost({
        path: { incident_id: incidentId, dictamen_id: dictamenId },
      });
      if (res.error || !res.data) {
        const status = res.response?.status ?? 0;
        const conocida = clasificar(status, res.error);
        if (conocida !== null) {
          setConfirmacion({ estado: "error", ...conocida, dictamenId });
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
