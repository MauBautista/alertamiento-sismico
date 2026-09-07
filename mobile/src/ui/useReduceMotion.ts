// [T-6.19] Preferencia de movimiento reducido del sistema, observable. Sin ella
// la app anima igual para la persona que pidió expresamente que no; con ella,
// la franja entra y sale sin transición. `false` hasta que el sistema conteste
// (la primera pintura no espera al puente nativo).
import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

export function useReduceMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((v) => {
        if (alive) {
          setReduce(v);
        }
      })
      .catch(() => {
        // Sin respuesta del sistema se anima; no es un dato de vida.
      });
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduce);
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return reduce;
}
