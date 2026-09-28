// Vigilante global de crisis: la push DESPIERTA (invalida la query) y la fase
// del servidor ENRUTA — al entrar alert_active, toma de pantalla inmediata.
// Vive dentro del QueryClientProvider en el layout raíz; no pinta nada.
import * as Notifications from "expo-notifications";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";

import { useSessionStore } from "@/auth/session.store";
import { adoptarSitioDelPush, useWatchedSiteId } from "@/services/mySite";

import { salioDeLaCrisis } from "./salidaTactica";
import { MOBILE_STATE_KEY, useAlertState } from "./useAlertState";

// En primer plano las notificaciones también se muestran (la app puede estar
// abierta en otra pantalla cuando llegue la CRISIS).
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/** Datos del push, vengan como vengan. Android los deja en `content.data`; en
 *  iOS la nube los pone junto a `aps` y, según la versión de expo, llegan en
 *  `content.data`, en `content.data.body` o solo en `trigger.payload`. */
function datosDelPush(notification: unknown): Record<string, unknown> {
  const n = notification as {
    request?: {
      content?: { data?: Record<string, unknown> | null };
      trigger?: { payload?: Record<string, unknown> | null } | null;
    };
  } | null;
  const data = n?.request?.content?.data ?? null;
  const candidatos = [data, data?.body, n?.request?.trigger?.payload];
  for (const c of candidatos) {
    if (c && typeof c === "object" && typeof (c as { site_id?: unknown }).site_id === "string") {
      return c as Record<string, unknown>;
    }
  }
  return (data as Record<string, unknown> | null) ?? {};
}

/** [T-9.33] Fases que se adueñan de la pantalla: mientras dure una, la
 *  confirmación del dictamen espera. */
const FASES_QUE_TOMAN_LA_PANTALLA: ReadonlySet<string> = new Set([
  "alert_active",
  "checkin_pending",
  "building_alarm",
  "building_movement",
]);

export function CrisisWatcher() {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const siteId = useWatchedSiteId();
  const { state, data } = useAlertState(siteId);
  // [T-2.106] Instante de la alarma del inmueble YA anunciada. La toma sísmica
  // se re-impone en cada render porque de una evacuación no se sale con el dedo;
  // la alarma del inmueble se anuncia UNA VEZ por activación, porque la pantalla
  // le pide al ocupante que atienda a su brigada y devolverlo a la fuerza le
  // impediría abrir el directorio para llamarla. Una activación NUEVA (otro
  // `since`) vuelve a anunciarse.
  const alarmaAnunciada = useRef<string | null>(null);
  // [T-9.11 · D-39] Incidente cuyo MOVIMIENTO ya se anunció. Igual que la alarma
  // del inmueble: una vez por episodio, porque la brigada tiene que poder ir a
  // REPORTAR DAÑOS sin que la devuelvan a la fuerza. Solo el perfil TÁCTICO: la
  // nube no le sirve la fase al ocupante, y la app tampoco se fía.
  const movimientoAnunciado = useRef<string | null>(null);
  const [toqueMovimiento, setToqueMovimiento] = useState(0);
  const profile = useSessionStore((s) => s.profile);
  const me = useSessionStore((s) => s.me);
  // [D-42] `site_id` del último push recibido o tocado. Se guarda aparte porque
  // en arranque en FRÍO el push llega antes que `/me`: la adopción espera a
  // saber quién es la sesión (y solo ocurre si es de todo el cliente).
  const [sitioDelPush, setSitioDelPush] = useState<string | null>(null);
  const frioLeido = useRef(false);
  // [T-9.33 · D-43] Incidente de la push DICTAMEN_CONFIRM que se TOCÓ. No es una
  // alarma (canal `ops`): al recibirla no se enruta; al tocarla se abre la
  // pantalla de CONFIRMAR DICTAMEN, que es la que pregunta al REST por la cabeza
  // vigente. Se guarda aparte porque en arranque en FRÍO el toque llega antes
  // que `/me`, y quién puede confirmar lo dice `/me`.
  // Es un ref (y un contador que despierta al efecto) para no escribir estado
  // DENTRO del efecto que lo consume.
  const confirmarDictamenDe = useRef<string | null>(null);
  const [toqueDictamen, setToqueDictamen] = useState(0);

  // Push recibida (primer plano o tap): invalidar mobile-state — el REST es la
  // verdad; el contenido de la push jamás enruta por sí solo.
  useEffect(() => {
    const invalidate = () => {
      void queryClient.invalidateQueries({ queryKey: [MOBILE_STATE_KEY] });
    };
    const recordarSitio = (notification: unknown) => {
      const site = datosDelPush(notification).site_id;
      if (typeof site === "string" && site !== "") {
        setSitioDelPush(site);
      }
    };
    const received = Notifications.addNotificationReceivedListener((n) => {
      recordarSitio(n);
      invalidate();
    });
    // [T-9.11] Tocar la push de MOVIMIENTO vuelve a abrir /movimiento aunque ya
    // se hubiera anunciado. La push no enruta sola: solo olvida el anuncio, y el
    // efecto de abajo enruta ÚNICAMENTE si el REST sigue diciendo
    // `building_movement` y el perfil es táctico.
    const alTocar = (r: unknown) => {
      const notification = (r as { notification?: unknown } | null)?.notification;
      recordarSitio(notification);
      invalidate();
      const datos = datosDelPush(notification);
      const phase = datos.phase;
      if (phase === "dictamen_confirm") {
        const incidente = datos.incident_id;
        if (typeof incidente === "string" && incidente !== "") {
          confirmarDictamenDe.current = incidente;
          setToqueDictamen((n) => n + 1);
        }
      }
      if (phase === "building_movement") {
        movimientoAnunciado.current = null;
        setToqueMovimiento((n) => n + 1);
      }
    };
    const responded = Notifications.addNotificationResponseReceivedListener(alTocar);
    // [D-42] Arranque en FRÍO: el toque que ABRIÓ la app no pasa por el listener.
    // Una sola vez por montaje: esa respuesta no cambia, y re-leerla en cada
    // re-suscripción re-anunciaría un movimiento ya visto.
    if (!frioLeido.current && typeof Notifications.getLastNotificationResponseAsync === "function") {
      frioLeido.current = true;
      void Notifications.getLastNotificationResponseAsync()
        .then((r) => {
          // Sin guarda de «montado»: si el efecto se re-suscribió entretanto,
          // descartarla perdería el toque que abrió la app, y la bandera de
          // arriba ya impide leerla dos veces.
          if (r) {
            alTocar(r);
          }
        })
        .catch(() => undefined);
    }
    return () => {
      received.remove();
      responded.remove();
    };
  }, [queryClient]);

  // [D-42] Adoptar el sitio del push SOLO si la sesión es de todo el cliente
  // (`adoptarSitioDelPush` lo comprueba). Ocupantes y tácticos por inmueble
  // conservan el suyo.
  useEffect(() => {
    if (sitioDelPush !== null && me != null) {
      adoptarSitioDelPush(sitioDelPush);
    }
  }, [sitioDelPush, me]);

  // [T-9.33 · D-43] Abrir CONFIRMAR DICTAMEN tras tocar su push. Solo el
  // TÁCTICO con `confirm_dictamen` (el ocupante JAMÁS, aunque la push le llegara)
  // y solo en calma: una fase de vida (sismo, check-in, movimiento, alarma) manda
  // y la petición espera a que termine.
  const puedeConfirmar = me?.allowed_actions?.confirm_dictamen === true;
  useEffect(() => {
    const incidente = confirmarDictamenDe.current;
    if (incidente === null || me == null) {
      return;
    }
    if (profile !== "tactical" || !puedeConfirmar) {
      confirmarDictamenDe.current = null;
      return;
    }
    if (state !== null && FASES_QUE_TOMAN_LA_PANTALLA.has(state)) {
      return;
    }
    confirmarDictamenDe.current = null;
    if (pathname !== "/confirmar-dictamen") {
      router.push({ pathname: "/confirmar-dictamen", params: { incident: incidente } });
    }
  }, [toqueDictamen, me, profile, puedeConfirmar, state, pathname, router]);

  const alarmaDesde = data?.building_alarm?.since ?? null;
  useEffect(() => {
    // [T-7.29] La toma se re-impone SIEMPRE… salvo que este táctico ya haya
    // salido de ESTE episodio. Sin esa excepción, el botón de salir no serviría
    // de nada: el efecto lo devolvería a /crisis en el render siguiente. La
    // excepción es por incidente, así que una alerta NUEVA vuelve a tomar la
    // pantalla aunque hubiera salido de la anterior.
    if (state === "alert_active" && pathname !== "/crisis") {
      if (!salioDeLaCrisis(data?.incident?.incident_id ?? null)) {
        router.push("/crisis");
      }
      return;
    }
    // [T-2.06] Sacudida concluida sin check-in propio ⇒ toma de pantalla 1.4.
    if (state === "checkin_pending" && pathname !== "/checkin") {
      router.push("/checkin");
      return;
    }
    // [T-2.106] Alarma del inmueble: se anuncia al ENTRAR en ella (y de nuevo
    // si es otra activación), jamás en bucle. El servidor ya resolvió la
    // precedencia, así que llegar aquí significa que NO hay sismo en curso.
    if (state === "building_alarm" && alarmaDesde !== null) {
      if (alarmaAnunciada.current !== alarmaDesde) {
        alarmaAnunciada.current = alarmaDesde;
        if (pathname !== "/alarma-inmueble") {
          router.push("/alarma-inmueble");
        }
      }
      return;
    }
    // [T-9.11 · D-39] Movimiento en el inmueble: solo el TÁCTICO, una vez por
    // incidente (o de nuevo al tocar su push). Al ocupante NUNCA — defensivo.
    if (state === "building_movement") {
      // La nube manda `building_alarm` TAMBIÉN durante el movimiento (solo a la
      // brigada), y /movimiento la pinta en un bloque propio. Si la brigada NO
      // la está mirando, se olvida el anuncio: cuando el movimiento termine y la
      // fase vuelva a `building_alarm`, /movimiento la suelta a INICIO y la
      // alarma —que sigue sonando— tiene que volver a anunciarse. Si la está
      // mirando (la abrió desde el bloque), cuenta como anunciada.
      if (alarmaDesde !== null) {
        alarmaAnunciada.current = pathname === "/alarma-inmueble" ? alarmaDesde : null;
      }
      const episodio = data?.incident?.incident_id ?? "sin-incidente";
      if (profile === "tactical" && movimientoAnunciado.current !== episodio) {
        movimientoAnunciado.current = episodio;
        if (pathname !== "/movimiento") {
          router.push("/movimiento");
        }
      }
      return;
    }
    if (state !== null) {
      movimientoAnunciado.current = null;
    }
    if (state !== null && state !== "building_alarm") {
      alarmaAnunciada.current = null; // la próxima activación vuelve a anunciarse
    }
  }, [
    state,
    alarmaDesde,
    pathname,
    router,
    data?.incident?.incident_id,
    profile,
    toqueMovimiento,
  ]);

  return null;
}
