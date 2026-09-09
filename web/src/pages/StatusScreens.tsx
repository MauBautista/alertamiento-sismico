import { tokens, toNumber } from "@takab/design-tokens";
import { useState } from "react";

import logoTakab from "../assets/imagotipo-takab-ailert.png";
import { useNow } from "../lib/useNow";

/**
 * [T-6.07] A partir de aquí, una espera que sigue esperando tiene que DECIR qué
 * espera. El umbral es un token semántico (`--tk-wait-declare`), no un número
 * escrito aquí: la misma pregunta se la hacen otras pantallas.
 */
const UMBRAL_MS = toNumber(tokens.wait.declare);

/**
 * Pantalla de arranque. Era estática y muda: el mismo «INICIANDO CONSOLA SOC…»
 * a los 0.3 s que a los 30, así que no distinguía «va lento» de «se colgó» — y
 * quien mira una consola de operación resuelve esa duda recargando a ciegas.
 *
 * Dos cosas la arreglan y las dos importan: `role="status"` (un lector de
 * pantalla anuncia que algo pasa, en vez de leer un rótulo y callarse) y, a
 * partir del umbral, decir QUÉ se está esperando y DESDE CUÁNDO. El qué se lo
 * pasa quien la monta: no es lo mismo esperar el arranque de la sesión que la
 * vuelta de Cognito, y confundirlos manda a mirar el sitio equivocado.
 */
export function SplashScreen({
  espera = "la sesión del operador (/me)",
}: { espera?: string } = {}) {
  // El instante en que ESTA espera empezó, no el del proceso: si se reusara el
  // arranque del navegador, una segunda espera nacería ya «tardando».
  const [desde] = useState(() => Date.now());
  const ahora = useNow(1000);
  const transcurrido = Math.max(0, Math.round((ahora - desde) / 1000));
  const tardando = ahora - desde >= UMBRAL_MS;

  return (
    <div className="soc-screen">
      <div className="soc-screen__panel" role="status" aria-live="polite">
        <img src={logoTakab} alt="TAKAB Ailert" className="soc-screen__logo" />
        <p className="soc-screen__sub">INICIANDO CONSOLA SOC…</p>
        {tardando && (
          <p className="soc-screen__sub" data-testid="splash-tardando">
            ESTO ESTÁ TARDANDO · esperando {espera} desde hace {transcurrido} s
          </p>
        )}
      </div>
    </div>
  );
}

/*
 * [T-2.134] AQUÍ VIVÍA `ErrorScreen` («ERROR DE SESIÓN» + REINTENTAR), y se
 * retiró con el `status: "error"` que la producía.
 *
 * `T-2.123` decidió qué debe declarar la consola cuando `/me` no contesta —que
 * no puede establecer el alcance del operador, que no va a pintar ni un dato de
 * tenant, y que el alertamiento no depende de esta pantalla— y lo escribió en
 * `app/DegradedSessionScreen.tsx`. Esta pantalla decía «ERROR DE SESIÓN», que
 * para el mismo hecho es a la vez más alarmante y menos informativo: sugiere que
 * la sesión se perdió, cuando el token sigue siendo válido.
 *
 * No se conserva «por si acaso»: un modo de fallo, una pantalla. Dos pantallas
 * para el mismo hecho es cómo se acaba enseñando la que nadie decidió.
 */
