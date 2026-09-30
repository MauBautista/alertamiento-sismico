// [T-9.13] ¿Sonará este teléfono como debe? Se lee al abrir y se RE-lee al volver a
// primer plano: es justo cuando la persona viene de los ajustes del sistema de
// conceder (o quitar) el acceso a «No molestar» o las notificaciones.
import { useEffect, useState } from "react";
import { AppState, Linking } from "react-native";

import {
  deriveAlertability,
  type Alertability,
  type AlertabilityAccion,
} from "@/services/alertability";
import { abrirAccesoNoMolestar, getAlertabilitySnapshot } from "@/services/push";

export function useAlertabilidad(): Alertability | null {
  const [alertabilidad, setAlertabilidad] = useState<Alertability | null>(null);
  useEffect(() => {
    let vivo = true;
    const cargar = () => {
      // Si la lectura falla no se inventa un «todo bien»: se queda el último dato.
      getAlertabilitySnapshot()
        .then((s) => {
          if (vivo) {
            setAlertabilidad(deriveAlertability(s));
          }
        })
        .catch(() => {});
    };
    cargar();
    const sub = AppState.addEventListener("change", (estado) => {
      if (estado === "active") {
        cargar();
      }
    });
    return () => {
      vivo = false;
      sub.remove();
    };
  }, []);
  return alertabilidad;
}

/** Lo que hace el botón del aviso. Si el ajuste de «No molestar» no se puede abrir
 *  en este Android, se abren los de la app: mejor un paso más que ninguna salida. */
export function ejecutarAccionDelTelefono(accion: AlertabilityAccion): void {
  if (accion === "permitir_no_molestar") {
    abrirAccesoNoMolestar().catch(() => {
      void Linking.openSettings();
    });
    return;
  }
  void Linking.openSettings();
}
