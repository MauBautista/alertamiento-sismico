// Evacuación observada por CCTV (T-3.12.c).
//
// LA ÚNICA SUPERFICIE DE CCTV DE LA CONSOLA, y es ésta. El card de `DetailPanel` es
// *verificación visual en vivo* y sigue con su empty-state honesto: son cosas distintas y
// tener dos a medias sería peor que tener una.
//
// Pinta el MISMO objeto que consume la sección del dictamen PDF. Si la pantalla y el papel
// lo leyeran cada uno a su manera acabarían discrepando, y aquí el que discrepa lleva una
// firma debajo.

import StateFrame from "../../components/StateFrame";
import type { CctvState } from "./useCctv";

/** Los cuatro papeles, en el orden en que el reporte los cuenta. */
const ROTULOS: Record<string, string> = {
  pre: "ANTES DE LA SEÑAL",
  egress: "SALIENDO",
  peak: "AFORO MÁXIMO",
  reentry: "REINGRESANDO",
};

function segundos(v: number | null | undefined): string {
  // `null` es «no medido» y NO se degrada a 0: un t90 de cero diría que la gente salió
  // instantáneamente. Es la misma regla que el contrato del backend.
  return v === null || v === undefined ? "SIN MEDIR" : `${Math.round(v)} s`;
}

export default function CctvPanel({
  cctv,
  canDownloadClip,
  onDownloadClip,
}: {
  cctv: CctvState;
  canDownloadClip: boolean;
  onDownloadClip?: (clipId: string) => void;
}) {
  const d = cctv.data;
  const evac = d?.evacuacion ?? null;

  return (
    <div className="soc-card cctv" data-testid="cctv-panel">
      <div className="soc-card__hd">
        <div>
          <div>Evacuación observada</div>
          <div className="soc-card__sub">CCTV · AFORO EN EL PUNTO DE REUNIÓN</div>
        </div>
      </div>
      <StateFrame
        label="EVACUACIÓN OBSERVADA"
        loading={cctv.loading}
        error={cctv.error}
        onRetry={cctv.refetch}
        // `empty` es «no hay cámara en este sitio», que es un hecho sobre el mundo y no
        // un fallo. Con cámara y sin análisis el panel SÍ pinta: tiene algo que decir.
        empty={d !== undefined && !d.con_camara}
        emptyText={d?.estado ?? "SIN COBERTURA CCTV DECLARADA"}
        staleSince={cctv.staleSince}
      >
        {d && (
          <div className="cctv__cuerpo">
            {evac === null ? (
              // Con clip y sin conteo el panel lo DICE. Un cero aquí sería una mentira
              // sobre una evacuación que quizá fue perfecta.
              <p className="cctv__estado" data-testid="cctv-estado">
                {d.estado}
              </p>
            ) : (
              <>
                <dl className="cctv__cifras">
                  <div>
                    <dt>AFORO MÁXIMO</dt>
                    <dd>{evac.peak_n ?? "SIN MEDIR"}</dd>
                  </div>
                  <div>
                    <dt>MITAD FUERA</dt>
                    <dd>{segundos(evac.t50_s)}</dd>
                  </div>
                  <div>
                    <dt>LA MAYOR PARTE FUERA</dt>
                    <dd>{segundos(evac.t90_s)}</dd>
                  </div>
                </dl>
                <p className="cctv__correlacion">{evac.correlacion}</p>
                {/* Un reingreso ANTES del dictamen no es una celda más: el edificio se
                    reocupó sin certificación de habitabilidad. Va con su propio rótulo
                    para que no se lea de pasada. */}
                <p
                  className={
                    evac.reingreso_antes_del_dictamen
                      ? "cctv__veredicto cctv__veredicto--hallazgo"
                      : "cctv__veredicto"
                  }
                  data-testid="cctv-reingreso"
                  data-hallazgo={evac.reingreso_antes_del_dictamen ? "si" : "no"}
                >
                  {evac.veredicto_reingreso}
                </p>
                {d.discrepancia && (
                  // Se muestra como DISCREPANCIA y nunca promediada: la diferencia entre
                  // el aforo por cámara y el pase de lista ES la información.
                  <p className="cctv__discrepancia" data-testid="cctv-discrepancia">
                    <span>
                      cámara {d.discrepancia.aforo_camara ?? "—"} · pase de lista{" "}
                      {d.discrepancia.checkins ?? "—"}
                    </span>
                    <span>{d.discrepancia.lectura}</span>
                  </p>
                )}
              </>
            )}

            <ul className="cctv__capturas" data-testid="cctv-capturas">
              {(d.capturas ?? []).map((c) => (
                <li key={c.papel} data-papel={c.papel} data-disponible={c.disponible ? "si" : "no"}>
                  <span className="cctv__papel">{ROTULOS[c.papel] ?? c.papel}</span>
                  <span className="cctv__estado-captura">
                    {c.disponible
                      ? new Date(c.captured_at as string).toLocaleTimeString()
                      : c.purged_at
                        ? "PURGADO (retención de vídeo)"
                        : (c.razon ?? "SIN CAPTURA")}
                  </span>
                </li>
              ))}
            </ul>

            {(d.clips ?? []).map((c) => (
              <div key={c.clip_id} className="cctv__clip" data-testid="cctv-clip">
                <span>
                  {new Date(c.started_at).toLocaleTimeString()} —{" "}
                  {new Date(c.ended_at).toLocaleTimeString()}
                </span>
                {c.disponible ? (
                  // El botón sólo existe si el token trae `cctv_video`. Ocultarlo no es la
                  // defensa —la API rechaza igual— pero ofrecer un botón que va a dar 403
                  // enseña a desconfiar de la consola.
                  canDownloadClip && (
                    <button type="button" onClick={() => onDownloadClip?.(c.clip_id)}>
                      DESCARGAR CLIP
                    </button>
                  )
                ) : (
                  // El hecho sobrevive, la imagen no: la huella sigue siendo verificable.
                  <span className="cctv__purgado">PURGADO (retención de vídeo)</span>
                )}
              </div>
            ))}
          </div>
        )}
      </StateFrame>
    </div>
  );
}
