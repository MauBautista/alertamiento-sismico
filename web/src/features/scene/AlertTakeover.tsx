// [T-9.73 · D-47, que enmienda D-30] LA TOMA DE PANTALLA de una alerta
// confirmada: un borde rojo interior que pulsa alrededor de la consola entera y
// una viñeta muy tenue en las orillas.
//
// NO es un modal. La capa es `position: fixed` con `pointer-events: none`: el
// operador sigue trabajando debajo, y el borde (≤ 6 px) no le quita contraste a
// nada. Es decorativa (`aria-hidden`): el titular lo dicen la franja y la
// tarjeta, que ya son `role="alert"`; repetirlo aquí sería gritarlo dos veces a
// un lector de pantalla.
//
// Cuándo se monta NO lo decide este componente: lo decide `SceneStrip` con la
// tabla de escena (`alertKind === "alert"`: SASMEX, cuórum o aviso que la red
// corroboró) y `alertaViva` (`open`/`acked`). En revisión, cerrada, con un aviso
// de un solo inmueble o en un simulacro no existe — se apaga por el ESTADO DEL
// SERVIDOR, no por un cronómetro del cliente (condición 3 de D-30).
//
// `stale`: con la lectura vieja o en error, el borde se QUEDA (la alerta sigue
// abierta hasta que el servidor diga otra cosa) pero deja de latir. Un latido
// afirma «llega ahora», y un dato congelado no llega (regla de oro 7).
//
// Va por portal a `document.body` para no ser hijo de `.soc-main`: la reja del
// shell clava a todo hijo que no sea la franja ni el banner en la fila elástica
// (privacy.css, [D3]), y la franja no puede ganar hijos que animen
// (`layoutInvariants`, [T-6.01]).

import { createPortal } from "react-dom";

export interface AlertTakeoverProps {
  /** La lectura de incidentes es vieja o falló: borde fijo, sin latido. */
  stale: boolean;
}

export default function AlertTakeover({ stale }: AlertTakeoverProps) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <div
      className="soc-takeover"
      data-testid="soc-takeover"
      data-stale={String(stale)}
      aria-hidden="true"
    />,
    document.body,
  );
}
