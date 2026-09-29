// [T-9.62] EL RÓTULO DE UNA PESTAÑA QUE CABE EN SU HUECO.
//
// Con SISMOS el táctico tiene OCHO pestañas. En un Samsung A53 (1080 px, ~411 dp)
// cada hueco mide ~51 dp y «DIRECTORIO» se pintaba «DIREC…» aunque el rótulo ya
// iba en el cuerpo 2xs (T-6.22). El rótulo de serie de la barra corta con puntos
// suspensivos; éste se ENCOGE hasta caber, con un piso para que siga legible, y
// ocupa el ancho del hueco (`alignSelf: stretch`), que es lo que le deja medirse.
//
// Se encoge el TEXTO; el objetivo táctil de la pestaña no cambia.
import type { ReactNode } from "react";
import { type ColorValue, Text, type TextStyle } from "react-native";

/** Hasta dónde se encoge: por debajo, un rótulo deja de leerse en la mano. */
export const MIN_ESCALA_ROTULO = 0.7;

type PropsRotulo = {
  focused: boolean;
  color: ColorValue;
  position: "beside-icon" | "below-icon";
  children: string;
};

export function rotuloQueCabe(estilo: TextStyle): (props: PropsRotulo) => ReactNode {
  function Rotulo({ color, children }: PropsRotulo) {
    return (
      <Text
        adjustsFontSizeToFit
        minimumFontScale={MIN_ESCALA_ROTULO}
        numberOfLines={1}
        style={[estilo, { color, alignSelf: "stretch", textAlign: "center" }]}
      >
        {children}
      </Text>
    );
  }
  return Rotulo;
}
