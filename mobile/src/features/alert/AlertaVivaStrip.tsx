// [T-7.29] LA FRANJA QUE NO DEJA OLVIDAR QUE HAY UNA ALERTA VIVA.
//
// Es la contraparte obligatoria del botón de salir de la toma de crisis: en el
// momento en que un táctico puede trabajar en la app durante una alerta, la app
// tiene que seguir diciéndole que la alerta sigue. Sin esto, salir de la toma
// sería indistinguible de que el sismo terminó — la regla de oro 7 en su forma
// más cara, porque quien la lee mal es la persona que manda en el edificio.
//
// Presentacional pura (el contenedor de abajo pone el dato y el router), y
// deliberadamente distinta de la franja de avisos del sitio: RELLENO SÓLIDO y
// glifo de alerta. Las franjas del producto se distinguen por la FORMA, no por
// el matiz, para que una persona daltónica las lea igual.
import { Feather } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { emergency, fontSize, palette, space } from "@/ui/theme";

export function AlertaVivaStrip(props: {
  visible: boolean;
  onVolver: () => void;
  topInset?: number;
}) {
  const { visible, onVolver, topInset = 0 } = props;
  if (!visible) {
    return null;
  }
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onVolver}
      style={[styles.strip, { paddingTop: topInset + space[2] }]}
      testID="alerta-viva"
    >
      <Feather
        color={emergency.red.ink}
        name="alert-triangle"
        size={fontSize.md}
      />
      <View style={styles.textos}>
        <Text style={styles.titulo}>ALERTA SÍSMICA ACTIVA</Text>
        <Text style={styles.nota}>Toque para volver a la instrucción</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  strip: {
    backgroundColor: emergency.red.bg,
    borderBottomColor: palette.crit,
    borderBottomWidth: 2,
    flexDirection: "row",
    alignItems: "center",
    gap: space[2],
    paddingHorizontal: space[4],
    paddingBottom: space[2],
    // El objetivo táctil no baja del mínimo de T-6.20: la franja ENTERA es el
    // control, no un enlace de 14 px dentro de ella.
    minHeight: 48,
  },
  textos: { flex: 1, minWidth: 0 },
  titulo: {
    color: emergency.red.ink,
    fontSize: fontSize.sm,
    fontWeight: "700",
    letterSpacing: 1,
  },
  nota: { color: emergency.red.ink2, fontSize: fontSize.xs, marginTop: 2 },
});
