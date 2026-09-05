// [T-5.02 · D-27] Banner del MODO DEMOSTRACIÓN.
//
// Mientras está puesto, la nube **no avisa a nadie y no manda un solo comando de
// actuador**. Quien esté delante de esta pantalla tiene que saberlo sin
// preguntar — y sobre todo tiene que saberlo quien NO lo encendió, porque es
// quien se va a preguntar por qué no llegó un aviso.
//
// EL COLOR NO ES UN ADORNO. Va en cian y con borde discontinuo, y **no en
// ámbar**: en esta consola el ámbar ya significa «simulacro en curso» y «dato
// retenido», y un tercer significado en el mismo color vacía los tres. El
// discontinuo es el mismo idioma que T-5.01 le dio a los botones inertes del
// panel y T-5.05 al rótulo de los datos de demostración: «esto no es real».
//
// Los cuatro estados van por `StateFrame` como el resto (regla de oro 7). El
// caso que importa: si la lectura falla con el modo PUESTO, el banner **no
// desaparece en silencio** — se conserva el último dato conocido y se rotula.
// Un modo de supresión que deja de anunciarse es indistinguible de un sistema
// que sí está avisando.

import { EyeOff } from "lucide-react";

import StateFrame from "../../components/StateFrame";
import { useSessionStore } from "../../auth/session.store";
import { useNow } from "../../lib/useNow";
import { useDemoMode } from "./useDemoMode";

/** `7320` → `2 h 02 m`. Sin inventar precisión que no hace falta. */
export function restanteLegible(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h} h ${String(m).padStart(2, "0")} m` : `${m} m`;
}

export default function DemoModeBanner() {
  const puedeApagar = useSessionStore((s) => s.me?.allowed_actions.demo_mode_off === true);
  const now = useNow(1000);
  const { demo, loading, readError, updatedAt, refetch, apagar, pending } = useDemoMode();

  const activo = demo?.active === true;
  const restante =
    activo && demo?.expires_at != null ? (Date.parse(demo.expires_at) - now) / 1000 : 0;

  return (
    <StateFrame
      label="MODO DEMOSTRACIÓN"
      className="soc-demo-mode__frame"
      loading={loading}
      error={readError && demo === null ? "no se pudo leer el modo demostración" : null}
      onRetry={refetch}
      empty={!activo}
      emptyText=""
      staleSince={readError && demo !== null ? updatedAt : null}
    >
      {activo ? (
        <div className="soc-demo-mode" role="status" data-testid="demo-mode-banner">
          <EyeOff size={15} aria-hidden />
          <span className="soc-demo-mode__txt">
            MODO DEMOSTRACIÓN · NO SE AVISA A NADIE NI SE ACCIONA NADA
          </span>
          <span className="soc-demo-mode__meta">TERMINA SOLO EN {restanteLegible(restante)}</span>
          {/* La protección del edificio NO depende de esto, y decirlo aquí evita
              la lectura más peligrosa posible: que alguien crea que el gabinete
              está desarmado. No lo está: no sabe que este modo existe. */}
          <span className="soc-demo-mode__nota">La protección local del gabinete sigue armada</span>
          {puedeApagar && (
            <button
              type="button"
              className="soc-demo-mode__off"
              data-testid="demo-mode-off"
              onClick={apagar}
              disabled={pending}
            >
              SALIR DEL MODO
            </button>
          )}
        </div>
      ) : null}
    </StateFrame>
  );
}
