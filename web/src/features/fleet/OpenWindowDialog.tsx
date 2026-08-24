// [T-2.71] Abrir una ventana de mantenimiento desde la consola.
//
// **Por qué esto faltaba y por qué importa.** La API existía y estaba probada; la web
// solo LEÍA y CERRABA, así que abrir una ventana había que hacerlo por `curl`. Un
// silencio que se pide desde fuera de la consola deja al operador sin la pantalla en
// la que después tiene que verlo — y sin el motivo obligatorio delante.
//
// **El motivo es obligatorio, y no es burocracia.** Una ventana APAGA AVISOS de un
// edificio durante minutos u horas. Lo único que separa «silencio con dueño» de
// «silencio que nadie recuerda haber pedido» es que quede escrito quién y por qué —
// y esa es la fila que alguien va a leer cuando pregunte por qué no sonó la alarma.
//
// **Y el copy tiene que decir lo que la ventana NO hace.** Silencia alarmas de
// OPERACIÓN; jamás la actuación. El reflejo SASMEX→sirena es local y no depende de
// esto (reglas de oro 1 y 2). Un operador que creyera que esto desarma el edificio no
// abriría una ventana nunca; uno que creyera lo contrario dejaría un edificio
// pensando que está callado cuando sigue protegido. Las dos lecturas salen del mismo
// silencio, que es la lección de `RetireDialog`.

import { useId, useState } from "react";

import Modal from "../../components/Modal";

/** Duraciones ofrecidas. Se eligen de una lista y no se teclean: un campo libre de
 *  segundos invita a un cero de más, y aquí un cero de más son horas de alarmas
 *  apagadas. El servidor tiene la última palabra sobre el tope. */
export const DURACIONES: ReadonlyArray<{ label: string; s: number }> = [
  { label: "30 minutos", s: 1800 },
  { label: "1 hora", s: 3600 },
  { label: "2 horas", s: 7200 },
  { label: "4 horas", s: 14400 },
];

export interface OpenWindowDialogProps {
  /** Rótulo humano del gabinete, para que se vea QUÉ se va a silenciar. */
  label: string;
  gatewayId: string;
  pending: boolean;
  /** Mensaje del servidor tras un intento fallido. */
  error: string | null;
  onCancel: () => void;
  onConfirm: (input: { gateway_id: string; reason: string; duration_s: number }) => void;
}

export default function OpenWindowDialog({
  label,
  gatewayId,
  pending,
  error,
  onCancel,
  onConfirm,
}: OpenWindowDialogProps) {
  const [reason, setReason] = useState("");
  const [durationS, setDurationS] = useState(DURACIONES[0].s);
  const reasonId = useId();
  const durationId = useId();

  const motivo = reason.trim();
  // La validación local solo HABILITA el botón; quien decide es el servidor.
  const listo = motivo.length > 0 && !pending;

  return (
    <Modal onClose={onCancel} title="ABRIR VENTANA DE MANTENIMIENTO">
      <p data-testid="open-window-target">
        Se van a silenciar los avisos de <strong>{label}</strong> mientras dure la ventana.
      </p>
      <p data-testid="open-window-keeps">
        La protección del edificio NO se toca: el reflejo SASMEX→sirena es local y esta pantalla no
        puede apagarlo. Lo que se silencia son las alarmas de OPERACIÓN.
      </p>

      <label htmlFor={reasonId}>Motivo (obligatorio)</label>
      <input
        aria-describedby="open-window-keeps"
        data-testid="open-window-reason"
        id={reasonId}
        maxLength={500}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Por qué se silencia, y quién lo pidió"
        value={reason}
      />

      <label htmlFor={durationId}>Duración</label>
      <select
        data-testid="open-window-duration"
        id={durationId}
        onChange={(e) => setDurationS(Number(e.target.value))}
        value={durationS}
      >
        {DURACIONES.map((d) => (
          <option key={d.s} value={d.s}>
            {d.label}
          </option>
        ))}
      </select>

      {error !== null ? (
        <p data-testid="open-window-error" role="alert">
          {error}
        </p>
      ) : null}

      <div>
        <button data-testid="open-window-cancel" onClick={onCancel} type="button">
          CANCELAR
        </button>
        <button
          data-testid="open-window-confirm"
          disabled={!listo}
          onClick={() =>
            onConfirm({ gateway_id: gatewayId, reason: motivo, duration_s: durationS })
          }
          type="button"
        >
          {pending ? "ABRIENDO…" : "ABRIR VENTANA"}
        </button>
      </div>
    </Modal>
  );
}
