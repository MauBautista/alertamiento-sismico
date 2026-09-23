// [T-8.11 · A-062] El control pulsable de la app: un `Pressable` que SE VE
// responder al dedo.
//
// `Pressable` no trae respuesta visual de serie, y la app tenía 57 sin ninguna:
// cada toque parecía ignorado hasta que llegaba la respuesta del servidor, y en
// ese hueco la persona vuelve a pulsar. Este componente es la ÚNICA forma de
// poner un control bajo el dedo (lo exige `tests/censo-respuesta-al-toque`):
//
//   · OPACIDAD al pulsar + onda de Android del color del tema. Es instantáneo
//     —no hay transición que reducir—, así que se da siempre.
//   · ESCALA sutil solo si el sistema NO pide reducir el movimiento: cambiar el
//     tamaño de algo SÍ es movimiento, aunque no se anime.
//
// Lo que el llamador declara se respeta: su `style` viaja tal cual (el censo
// táctil lo sigue leyendo en la etiqueta `<Pulsable`), un botón atenuado se
// atenúa MÁS al pulsar —no se aclara— y su `transform` no se pisa.
//
// No es para los controles que ya tienen su propio portador de respuesta: el
// botón de pánico (mantener pulsado, con su barra que se llena) y el deslizador
// de confirmación del panel de control. Duplicarles la señal la ensucia.
import { useSyncExternalStore } from "react";
import {
  AccessibilityInfo,
  Pressable,
  StyleSheet,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { tokens } from "@takab/design-tokens";

/**
 * Los tres números de la respuesta al toque. La onda sale del paquete de
 * tokens (el cian de la marca al 15 %, el mismo que usa la consola para su
 * resalte); opacidad y escala no son colores ni espaciados, son la regla.
 */
export const toque = {
  ripple: tokens.color.cyan.a15,
  /** Multiplica la opacidad que el control YA tenía. */
  opacidad: 0.8,
  /** Más de un 5 % deja de leerse como «lo toqué» y se lee como animación. */
  escala: 0.97,
} as const;

const RIPPLE = { color: toque.ripple } as const;

/* =====================================================================
   PREFERENCIA DE MOVIMIENTO, compartida
   ===================================================================== */

// Una sola suscripción para toda la app, no una por botón: un pase de lista de
// 200 personas monta 400 controles, y `useReduceMotion` por cada uno serían 400
// consultas al puente nativo al abrir la pantalla. Hasta que el sistema
// conteste vale `false` (como `useReduceMotion`): la primera pintura no espera.
let reducir = false;
let vigilando = false;
const oyentes = new Set<() => void>();

function fijar(v: boolean): void {
  if (v !== reducir) {
    reducir = v;
    oyentes.forEach((f) => f());
  }
}

function vigilar(): void {
  if (vigilando) {
    return;
  }
  vigilando = true;
  try {
    Promise.resolve(AccessibilityInfo.isReduceMotionEnabled())
      .then((v) => fijar(v === true))
      .catch(() => {
        // Sin respuesta del sistema se queda en `false`: no es un dato de vida.
      });
    // Vive lo que vive la app: no se da de baja.
    AccessibilityInfo.addEventListener("reduceMotionChanged", (v) => fijar(v === true));
  } catch {
    // Un entorno sin el módulo nativo no puede dejar un botón sin pintar.
  }
}

function suscribir(f: () => void): () => void {
  vigilar();
  oyentes.add(f);
  return () => {
    oyentes.delete(f);
  };
}

const leer = (): boolean => reducir;

/** Solo para pruebas: cada `it` empieza sin preferencia leída. */
export function reiniciarMovimientoParaTests(): void {
  reducir = false;
  vigilando = false;
  oyentes.clear();
}

/* =====================================================================
   LA REGLA (pura)
   ===================================================================== */

/**
 * El estilo que pinta el control. Sin pulsar, el del llamador y nada más; al
 * pulsar, su opacidad por `toque.opacidad` y —si hay movimiento— la escala
 * añadida a su `transform`.
 */
export function estiloAlPulsar(
  style: StyleProp<ViewStyle>,
  pressed: boolean,
  movimientoReducido: boolean,
): StyleProp<ViewStyle> {
  if (!pressed) {
    return [style, null];
  }
  const base = StyleSheet.flatten(style) ?? {};
  const opacidad = (typeof base.opacity === "number" ? base.opacity : 1) * toque.opacidad;
  if (movimientoReducido) {
    return [style, { opacity: opacidad }];
  }
  const previo = Array.isArray(base.transform) ? base.transform : [];
  return [style, { opacity: opacidad, transform: [...previo, { scale: toque.escala }] }];
}

/* =====================================================================
   EL COMPONENTE
   ===================================================================== */

export type PulsableProps = Omit<PressableProps, "style" | "android_ripple"> & {
  style?: StyleProp<ViewStyle>;
};

export function Pulsable({ style, ...resto }: PulsableProps) {
  const movimientoReducido = useSyncExternalStore(suscribir, leer, leer);
  return (
    <Pressable
      {...resto}
      android_ripple={RIPPLE}
      style={({ pressed }) => estiloAlPulsar(style, pressed, movimientoReducido)}
    />
  );
}
