// Derivación PURA del estado de alertabilidad del dispositivo (spec §6 · 0.2):
// un producto de seguridad de vida no puede "creer" que alertará — lo deriva
// de los permisos reales y lo declara. Sin heurísticas, sin optimismo.

export type PermissionSnapshot = {
  granted: boolean;
  canAskAgain: boolean;
  /** iOS: permiso de Critical Alerts concedido (exige entitlement GATE-STORE).
   * null = Android u origen desconocido (no aplica). */
  iosCriticalAllowed: boolean | null;
  /** [T-9.13] Android: el canal sísmico rompe «No molestar» (`bypassDnd`).
   * null/ausente = no aplica o no se pudo leer: no se inventa ni un sí ni un no. */
  androidDndBypass?: boolean | null;
};

export type AlertabilityLevel = "ok" | "degraded" | "blocked";

/** Lo que la persona puede hacer para arreglarlo, si hay algo que hacer. */
export type AlertabilityAccion = "permitir_no_molestar" | "abrir_ajustes";

export type Alertability = {
  level: AlertabilityLevel;
  /** Motivos legibles, en orden de gravedad. Vacío ⇔ level === "ok". */
  reasons: string[];
  accion?: AlertabilityAccion;
};

export function deriveAlertability(snapshot: PermissionSnapshot): Alertability {
  if (!snapshot.granted) {
    return {
      level: "blocked",
      reasons: [
        snapshot.canAskAgain
          ? "Las notificaciones no están concedidas."
          : "Las notificaciones están DENEGADAS en los ajustes del sistema.",
      ],
      // Denegadas del todo, ya sólo se arreglan en los ajustes del sistema.
      ...(snapshot.canAskAgain ? {} : { accion: "abrir_ajustes" as const }),
    };
  }
  if (snapshot.iosCriticalAllowed === false) {
    // Concedidas pero sin Critical Alerts: suena, pero NO rompe silencio/No
    // Molestar. Degradado honesto (el entitlement de Apple está en trámite).
    return {
      level: "degraded",
      reasons: [
        "Sin alerta crítica: la notificación no rompe el modo silencio (pendiente del permiso Critical Alerts).",
      ],
    };
  }
  if (snapshot.androidDndBypass === false) {
    // [T-9.13] Medido en un Pixel con Android 17 (2026-09-30): el uso ALARMA del
    // canal ya no basta, Android lo rebaja al publicar y la ALERTA SÍSMICA llegó
    // muda con «No molestar». Sólo la deja pasar el acceso a «No molestar».
    return {
      level: "degraded",
      reasons: [
        "Con «No molestar» activado, la alerta sísmica llegará en SILENCIO: permita a TAKAB el acceso a «No molestar».",
      ],
      accion: "permitir_no_molestar",
    };
  }
  return { level: "ok", reasons: [] };
}
