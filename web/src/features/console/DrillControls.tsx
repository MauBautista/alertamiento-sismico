// [T-6.01] La TIRA de acciones del simulacro, que se queda en /console.
//
// Hasta esta ficha vivía dentro de `DrillBanner` junto con el banner del
// simulacro en curso. El banner se fue al shell (`features/scene/DrillBanner`),
// donde la tabla de escena lo pinta en las seis rutas; los BOTONES no: en
// escena NORMAL no hay franja, sólo el control donde ya estaba (criterio 3).
//
// `drill-idle` lo mide el e2e de T-1.62 (la tira no puede pasar de 60 px) y por
// eso NO va dentro de un marco: dentro desaparecería en `loading`, dejando al
// operador sin el botón. `drill === null` y `loading` sólo gatean INICIAR —el
// dato (simulacro vivo, armado, retenido, fallo de lectura) lo declara el
// banner del shell con sus cuatro estados.

import { useState } from "react";

import { useSessionStore } from "../../auth/session.store";
import DrillHistory from "./DrillHistory";
import DrillModal from "./DrillModal";
import { useActiveDrill } from "./useActiveDrill";

export default function DrillControls() {
  const canStart = useSessionStore((s) => s.me?.allowed_actions.drill_start === true);
  const { drill, loading, start, pending, error } = useActiveDrill();
  const [modalOpen, setModalOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  return (
    <div className="soc-drill-bar">
      <div className="soc-drill soc-drill--idle soc-drill__actions" data-testid="drill-idle">
        {/* El fallo de INICIAR, junto al botón. Con un simulacro vivo el fallo
            de TERMINAR lo pinta el banner del shell, al lado de su botón. */}
        {error !== null && drill === null && (
          <span className="soc-user__error" role="alert">
            {error.toUpperCase()}
          </span>
        )}
        {/* Mientras no se sabe si hay uno en curso, no se ofrece arrancar otro. */}
        {canStart && !loading && drill === null && (
          <button
            type="button"
            className="soc-btn soc-btn--ghost"
            disabled={pending}
            onClick={() => setModalOpen(true)}
            title="Banner NO-real + voceo en los gabinetes elegidos; cero relés"
          >
            INICIAR SIMULACRO
          </button>
        )}
        <button
          type="button"
          className="soc-btn soc-btn--ghost"
          onClick={() => setHistoryOpen(true)}
        >
          HISTORIAL
        </button>
      </div>

      {modalOpen && (
        <DrillModal
          pending={pending}
          error={error}
          onSubmit={(input) => {
            start(input);
            setModalOpen(false);
          }}
          onClose={() => setModalOpen(false)}
        />
      )}
      {historyOpen && <DrillHistory onClose={() => setHistoryOpen(false)} />}
    </div>
  );
}
