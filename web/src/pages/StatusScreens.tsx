import logoTakab from "../assets/LogoTakab2.png";

export function SplashScreen() {
  return (
    <div className="soc-screen">
      <div className="soc-screen__panel">
        <img src={logoTakab} alt="TAKAB TECHNOLOGY" className="soc-screen__logo" />
        <p className="soc-screen__sub">INICIANDO CONSOLA SOC…</p>
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
