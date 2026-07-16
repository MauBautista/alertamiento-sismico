// Contrato de estados obligatorio (regla de oro 7, espejo del StateFrame de
// consola): loading > error > empty > contenido (+ banner DATOS RETENIDOS si
// lo que se muestra es viejo). Mostrar un dato congelado como "live" es peor
// que mostrar "sin datos".
import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import { timeAgoLabel } from "./timeAgo";

/** Tic de reloj para la edad del banner stale (30 s es suficiente para
 *  "hace X min"); el initializer corre una vez, el resto va por interval. */
function useNowMs(override?: number): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  return override ?? nowMs;
}

export function StateFrame(props: {
  /** Cargando SIN datos que mostrar (con datos viejos habla el stale). */
  loading: boolean;
  /** Error SIN datos que mostrar (texto honesto, no un spinner infinito). */
  error: string | null;
  empty: boolean;
  emptyText: string;
  /** Epoch ms del dato mostrado cuando NO es fresco; null = fresco. */
  staleSinceMs: number | null;
  /** Override SOLO para tests deterministas. */
  nowMs?: number;
  children: React.ReactNode;
}) {
  const nowMs = useNowMs(props.nowMs);
  if (props.loading) {
    return (
      <View style={styles.center} testID="state-loading">
        <ActivityIndicator color={palette.cyan} />
      </View>
    );
  }
  if (props.error !== null) {
    return (
      <View style={styles.center} testID="state-error">
        <Text style={styles.errorTitle}>SIN CONEXIÓN CON EL SERVIDOR</Text>
        <Text style={styles.errorBody}>{props.error}</Text>
      </View>
    );
  }
  if (props.empty) {
    return (
      <View style={styles.center} testID="state-empty">
        <Text style={styles.emptyText}>{props.emptyText}</Text>
      </View>
    );
  }
  return (
    <View style={styles.wrap}>
      {props.staleSinceMs !== null ? (
        <View style={styles.staleBanner} testID="state-stale">
          <Text style={styles.staleText}>
            DATOS RETENIDOS · {timeAgoLabel(props.staleSinceMs, nowMs)} · sin conexión
          </Text>
        </View>
      ) : null}
      {props.children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1 },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: space[2],
    padding: space[5],
  },
  errorTitle: { color: palette.warn, fontSize: fontSize.sm, fontWeight: "700", letterSpacing: 1 },
  errorBody: { color: palette.fg3, fontSize: fontSize.sm, textAlign: "center" },
  emptyText: { color: palette.fg3, fontSize: fontSize.sm, textAlign: "center" },
  staleBanner: {
    backgroundColor: palette.card,
    borderColor: palette.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[1],
    paddingHorizontal: space[3],
    marginBottom: space[2],
  },
  staleText: { color: palette.warn, fontSize: fontSize.xs, letterSpacing: 1 },
});
