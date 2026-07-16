// Placeholder HONESTO de pantalla pendiente (regla §13.12 de la spec: sin
// stubs silenciosos — cada pantalla declara qué es y en qué tarea llega).
// Jamás muestra datos simulados como si fueran reales.
import { StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "./theme";

export function Pending({
  screen,
  title,
  task,
  note,
}: {
  screen: string;
  title: string;
  task: string;
  note?: string;
}) {
  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.eyebrow}>PANTALLA {screen}</Text>
        <Text style={styles.title}>{title}</Text>
        <View style={styles.pill}>
          <Text style={styles.pillText}>SE IMPLEMENTA EN {task}</Text>
        </View>
        {note ? <Text style={styles.note}>{note}</Text> : null}
        <Text style={styles.honesty}>
          Placeholder deliberado — sin datos simulados. La especificación de esta
          pantalla vive en takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md §7.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: space[5],
  },
  card: {
    width: "100%",
    backgroundColor: palette.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.borderStrong,
    padding: space[5],
    gap: space[3],
  },
  eyebrow: {
    color: palette.fg3,
    fontSize: fontSize.xs,
    letterSpacing: 2,
  },
  title: {
    color: palette.fg,
    fontSize: fontSize.xl,
    fontWeight: "600",
  },
  pill: {
    alignSelf: "flex-start",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: palette.warn,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  pillText: {
    color: palette.warn,
    fontSize: fontSize.xs,
    letterSpacing: 1,
  },
  note: {
    color: palette.fg2,
    fontSize: fontSize.sm,
    lineHeight: 20,
  },
  honesty: {
    color: palette.fg3,
    fontSize: fontSize.xs,
    lineHeight: 16,
  },
});
