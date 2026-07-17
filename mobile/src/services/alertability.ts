// Derivación PURA del estado de alertabilidad del dispositivo (spec §6 · 0.2):
// un producto de seguridad de vida no puede "creer" que alertará — lo deriva
// de los permisos reales y lo declara. Sin heurísticas, sin optimismo.

export type PermissionSnapshot = {
  granted: boolean;
  canAskAgain: boolean;
  /** iOS: permiso de Critical Alerts concedido (exige entitlement GATE-STORE).
   * null = Android u origen desconocido (no aplica). */
  iosCriticalAllowed: boolean | null;
};

export type AlertabilityLevel = "ok" | "degraded" | "blocked";

export type Alertability = {
  level: AlertabilityLevel;
  /** Motivos legibles, en orden de gravedad. Vacío ⇔ level === "ok". */
  reasons: string[];
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
  return { level: "ok", reasons: [] };
}
