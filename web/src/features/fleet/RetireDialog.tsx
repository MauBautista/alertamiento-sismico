// Diálogo de retiro con doble fricción (T-2.36).
//
// [B3 · T-2.65] La cabecera de este archivo decía que retirar "apaga la protección
// sísmica de un edificio". Es lo contrario de la decisión (A), ratificada el
// 2026-08-05: el retiro es ADMINISTRATIVO. El gabinete sigue leyendo el sensor y el
// reflejo SASMEX→sirena sigue actuando, porque ese camino no depende de la nube ni
// puede hacerlo (reglas de oro 1 y 2). Que un clic de inventario desprotegiera un
// edificio con gente dentro sería el fallo, no la función.
//
// Lo que el retiro apaga es la GESTIÓN EN LA NUBE: config firmada y comandos de
// actuación. Y desde T-2.65 el gabinete recibe un último sobre que se lo dice, para
// declararlo en su panel local en vez de quedar latiendo invisible (lo que le pasó a
// `gw-dev-0001` el 2026-08-04).
//
// Eso tiene que estar EN EL COPY, no solo aquí: este es el último texto que alguien
// lee antes de pulsar. Quien creyera que apaga la sirena no retiraría nunca; quien
// creyera que desmonta el equipo dejaría un edificio contando con una protección que
// ya no gestiona nadie. Las dos lecturas equivocadas salían del mismo silencio.
//
// La fricción sigue siendo doble, porque la consecuencia sigue siendo seria:
//
//   1. Teclear el identificador EXACTO del objeto (serial del gabinete, código del
//      sitio). Está en pantalla: no es un secreto, es un freno contra el clic
//      equivocado en la fila de al lado.
//   2. El código de retiro del cliente, que entrega TAKAB y solo el superadmin rota.
//
// La validación local únicamente HABILITA el botón. Quien decide es el servidor: si
// esta comprobación se pudiera saltar (devtools), el 400/403 sigue esperando allá.

import { useEffect, useId, useRef, useState } from "react";

import Modal from "../../components/Modal";

export interface RetireDialogProps {
  /** Qué se retira: cambia el copy, no la mecánica. */
  kind: "gateway" | "site";
  /** Rótulo humano (nombre del sitio) para que el operador sepa qué está apagando. */
  label: string;
  /** Identificador que hay que teclear: `serial` del gabinete, `code` del sitio. */
  confirmValue: string;
  /** ¿El cliente tiene código configurado? `null` = aún no se sabe. */
  codeConfigured: boolean | null;
  pending: boolean;
  /** Mensaje del servidor tras un intento fallido (429/409/403). */
  error: string | null;
  onCancel: () => void;
  onConfirm: (input: { confirmValue: string; retireCode: string }) => void;
}

const COPY = {
  gateway: {
    title: "RETIRAR GABINETE",
    what: "gabinete",
    field: "serial",
    keeps:
      "El gabinete SIGUE PROTEGIENDO el edificio: el reflejo SASMEX→sirena es local y no " +
      "se apaga desde esta pantalla.",
    consequence:
      "Lo que se apaga es su gestión en la nube — dejará de recibir configuración firmada y " +
      "de ser destinatario de comandos de actuación — y el propio gabinete lo declarará en " +
      "su panel local. Para dejar el edificio sin protección hay que ir a desmontarlo. " +
      "Se deshace desde la consola con RESTAURAR.",
  },
  site: {
    title: "RETIRAR ESTACIÓN",
    what: "estación",
    field: "código",
    keeps:
      "Sus gabinetes SIGUEN PROTEGIENDO los edificios: el reflejo SASMEX→sirena es local y " +
      "no se apaga desde esta pantalla.",
    consequence:
      "Se retirarán también TODOS sus gabinetes: dejarán de recibir configuración firmada y " +
      "de ser destinatarios de comandos de actuación, y cada uno lo declarará en su panel " +
      "local. Restaurar la estación NO los devuelve, y para dejar los edificios sin " +
      "protección hay que ir a desmontar el hardware.",
  },
} as const;

export default function RetireDialog({
  kind,
  label,
  confirmValue,
  codeConfigured,
  pending,
  error,
  onCancel,
  onConfirm,
}: RetireDialogProps) {
  const [typed, setTyped] = useState("");
  const [code, setCode] = useState("");
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const typedId = useId();
  const codeId = useId();
  const copy = COPY[kind];

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  const matches = typed.trim() === confirmValue;
  // Sin código configurado el intento sería un 409 seguro: se dice ANTES, no se
  // ofrece un botón que siempre falla (regla de oro 7).
  const blocked = codeConfigured === false;
  const ready = matches && code.length > 0 && !pending && !blocked;

  return (
    <Modal title={copy.title} onClose={onCancel}>
      <div className="retire" data-testid="retire-dialog">
        <p className="retire__target">
          {label} · <span className="retire__id">{confirmValue}</span>
        </p>
        {/* Lo que NO se apaga va PRIMERO y aparte: es la pregunta que el operador
            trae en la cabeza, y enterrarla al final de un párrafo de consecuencias
            equivale a no contestarla. */}
        <p className="retire__keeps" data-testid="retire-keeps">
          {copy.keeps}
        </p>
        <p className="retire__warn">
          Esta acción es un retiro lógico: cambia el inventario, no el hardware. {copy.consequence}
        </p>

        {blocked && (
          <p className="retire__blocked" role="alert" data-testid="retire-no-code">
            ESTE CLIENTE NO TIENE CÓDIGO DE RETIRO CONFIGURADO · solicítalo a TAKAB antes de retirar
            hardware.
          </p>
        )}

        <label className="retire__field" htmlFor={typedId}>
          <span>
            Escribe el {copy.field} <strong>{confirmValue}</strong> para confirmar
          </span>
          <input
            id={typedId}
            ref={firstFieldRef}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            disabled={blocked}
            onChange={(e) => setTyped(e.target.value)}
          />
        </label>

        <label className="retire__field" htmlFor={codeId}>
          <span>Código de retiro del cliente</span>
          <input
            id={codeId}
            // type=password: el código es una credencial compartida y la consola SOC
            // vive en un muro de video con gente delante.
            type="password"
            autoComplete="off"
            value={code}
            disabled={blocked}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>

        {error && (
          <p className="retire__error" role="alert" data-testid="retire-error">
            {error}
          </p>
        )}

        <div className="retire__actions">
          <button type="button" className="soc-btn" onClick={onCancel} disabled={pending}>
            CANCELAR
          </button>
          <button
            type="button"
            className="soc-btn soc-btn--danger"
            disabled={!ready}
            onClick={() => onConfirm({ confirmValue: typed.trim(), retireCode: code })}
          >
            {pending ? "RETIRANDO…" : `RETIRAR ${copy.what.toUpperCase()}`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
