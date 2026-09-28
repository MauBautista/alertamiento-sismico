// [T-9.33 · D-43] Ruta de CONFIRMAR DICTAMEN. La abre el toque de la push
// DICTAMEN_CONFIRM (fase `dictamen_confirm`, ver `CrisisWatcher`) con el
// incidente en el parámetro `incident`; sin él, el del estado del sitio.
//
// · **Solo el TÁCTICO con `confirm_dictamen`.** La nube solo le manda la push a
//   esos roles, pero la app no se fía: el ocupante vuelve a INICIO sin pintar nada.
// · **No decide nada.** La banda y su porqué los fijó la regla determinista en la
//   nube; la pantalla los explica y manda la confirmación de ESA cabeza. La nube
//   responde 409 (cambió, ya firmada, VERDE, sin banda, requiere inspector o
//   el edificio sigue en movimiento), 403 (ROJO o sin permiso) o 404.
// · **Sólo en calma** (D-49 · R1): con la alerta viva o el tier fuera de
//   `normal` se explica «espere a que el edificio vuelva a calma», sin botón.
// · **Cuatro estados** (regla de oro 7): la cabeza puede cambiar bajo la brigada,
//   así que un dato viejo se marca como tal.
//
// Sin `@takab/sdk` en el cuerpo del módulo: expo-router barre `src/app` y el SDK
// se queda en los hooks y en las vistas.
import { Redirect, useLocalSearchParams } from "expo-router";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { ConfirmarDictamenView } from "@/features/dictamen/ConfirmarDictamenView";
import {
  confirmacionView,
  edificioEnCalma,
  incidenteDeConfirmacion,
} from "@/features/dictamen/confirmacion";
import {
  CADENA_POLL_MS,
  ErrorDeCadena,
  useConfirmarDictamen,
} from "@/features/dictamen/useConfirmarDictamen";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { useStaleSince } from "@/ui/useStaleSince";

const SIN_INCIDENTE = "Sin incidente: no hay dictamen que confirmar.";
const SIN_DICTAMEN = "Aún no hay dictamen para este incidente.";

function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorDeCadena && error.status === 403) {
    return "Su perfil no puede consultar la cadena de dictámenes. Avise a la administración del inmueble.";
  }
  return "No se pudo cargar el dictamen.";
}

export default function ConfirmarDictamen() {
  const status = useSessionStore((s) => s.status);
  const profile = useSessionStore((s) => s.profile);
  const puedeConfirmar = useSessionStore(
    (s) => s.me?.allowed_actions?.confirm_dictamen === true,
  );
  const puedeEscalar = useSessionStore((s) => s.me?.allowed_actions?.request_dictamen === true);
  const params = useLocalSearchParams<{ incident?: string }>();
  const siteId = useWatchedSiteId();
  const { data: estado } = useAlertState(siteId);

  const delParametro = typeof params.incident === "string" && params.incident !== "" ? params.incident : null;
  // [D-49 · R2] Sin parámetro, el que CITA el reingreso cuando espera confirmación
  // (puede ser un incidente ANTERIOR al abierto); si no, el abierto.
  const incidentId = delParametro ?? incidenteDeConfirmacion(estado);

  const { cadena, cabeza, confirmacion, escalado, confirmar, escalar } =
    useConfirmarDictamen(incidentId);
  const staleSinceMs = useStaleSince(cadena.dataUpdatedAt, CADENA_POLL_MS);

  if (status !== "authenticated") {
    return <Redirect href="/" />;
  }
  // Defensivo: el ocupante JAMÁS, y tampoco quien no puede confirmar.
  if (profile !== "tactical" || !puedeConfirmar) {
    return <Redirect href="/" />;
  }

  // [D-49 · R1] Con el edificio en movimiento (o sin saberlo) no se ofrece: la
  // nube respondería 409 «vuelva a calma». Se explica en su lugar.
  const vista = cadena.data ? confirmacionView(cabeza, edificioEnCalma(estado)) : null;

  return (
    <StateFrame
      empty={incidentId === null || vista?.tipo === "sin_dictamen"}
      emptyText={incidentId === null ? SIN_INCIDENTE : SIN_DICTAMEN}
      error={cadena.isError && !cadena.data ? mensajeDeError(cadena.error) : null}
      loading={cadena.isLoading && incidentId !== null}
      onRetry={() => void cadena.refetch()}
      staleSinceMs={staleSinceMs}
    >
      {vista !== null && vista.tipo !== "sin_dictamen" ? (
        <ConfirmarDictamenView
          confirmacion={confirmacion}
          escalado={escalado}
          onConfirmar={() => void confirmar()}
          onEscalar={puedeEscalar ? () => void escalar() : null}
          vista={vista}
        />
      ) : null}
    </StateFrame>
  );
}
