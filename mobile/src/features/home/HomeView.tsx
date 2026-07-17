// 1.1 Modo reposo — presentacional puro. Todo lo que pinta viene del servidor
// (mobile-state + directorio); el teléfono no calcula estados. La variante
// SIMULACRO es una franja ámbar sobre el contenido normal: un drill JAMÁS
// dispara pantallas de crisis (no crea incidente — garantía server-side).
import type { DirectoryEntryOut, MobileStateOut } from "@takab/sdk";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import { healthBanner, wr1Chip, type HealthTone } from "./health";

const TONE_COLOR: Record<HealthTone, string> = {
  ok: palette.ok,
  warn: palette.warn,
  crit: palette.crit,
};

function fmtFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-MX", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const POLICY_LABEL: Record<string, string> = {
  evacuate: "ZONA DE EVACUACIÓN",
  shelter: "ZONA DE REPLIEGUE",
};

export function HomeView(props: {
  data: MobileStateOut;
  brigadistas: DirectoryEntryOut[];
  nowMs: number;
  onOpenRutas: () => void;
  onOpenDirectorio: () => void;
  onOpenPanic?: () => void;
}) {
  const { data } = props;
  const banner = healthBanner(data.site_health, props.nowMs);
  const chip = wr1Chip(data.site_health);
  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <Text style={styles.eyebrow}>{data.site_name.toUpperCase()}</Text>

      {data.phase === "reentry_approved" ? (
        <View style={styles.reentryBanner} testID="reentry-banner">
          <Text style={styles.reentryText}>
            REINGRESO AUTORIZADO — el dictamen técnico del inspector aprobó el reingreso al
            inmueble.
          </Text>
        </View>
      ) : null}

      {data.drill.active ? (
        <View style={styles.drillBanner} testID="drill-banner">
          <Text style={styles.drillText}>SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL</Text>
        </View>
      ) : null}

      <View style={[styles.statusCard, { borderColor: TONE_COLOR[banner.tone] }]}>
        <Text style={[styles.statusLabel, { color: TONE_COLOR[banner.tone] }]} testID="estado">
          {banner.label}
        </Text>
        <Text style={styles.statusDetail}>{banner.detail}</Text>
        {chip ? (
          <View style={styles.chip} testID="wr1-chip">
            <Text style={styles.chipText}>{chip}</Text>
          </View>
        ) : null}
      </View>

      {data.my_zone ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>SU ZONA</Text>
          <Text style={styles.zoneName}>{data.my_zone.name}</Text>
          {data.my_zone.evac_policy ? (
            <Text style={styles.zonePolicy}>
              {POLICY_LABEL[data.my_zone.evac_policy] ?? data.my_zone.evac_policy}
            </Text>
          ) : (
            <Text style={styles.muted}>Sin política de zona definida.</Text>
          )}
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>SU ZONA</Text>
          <Text style={styles.muted}>Sin zona asignada — vincúlese con su administrador.</Text>
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>SIMULACROS</Text>
        <Text style={styles.rowText}>
          Próximo:{" "}
          {data.drill.next_scheduled_at ? (
            <Text style={styles.rowStrong}>{fmtFecha(data.drill.next_scheduled_at)}</Text>
          ) : (
            <Text style={styles.muted}>sin programar</Text>
          )}
        </Text>
        <Text style={styles.rowText}>
          Último:{" "}
          {data.drill.last_started_at ? (
            <Text style={styles.rowStrong}>
              {fmtFecha(data.drill.last_started_at)}
              {data.drill.last_note ? ` · ${data.drill.last_note}` : ""}
            </Text>
          ) : (
            <Text style={styles.muted}>sin registro</Text>
          )}
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>BRIGADISTAS DE SU ZONA</Text>
        {props.brigadistas.length === 0 ? (
          <Text style={styles.muted}>Sin brigadistas publicados para su zona.</Text>
        ) : (
          props.brigadistas.map((b) => (
            <View key={b.user_id} style={styles.dirRow}>
              <View style={styles.dirInfo}>
                <Text style={styles.rowStrong}>{b.display_name}</Text>
                <Text style={styles.muted}>{b.role.toUpperCase()}</Text>
              </View>
              {b.phone ? (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => void Linking.openURL(`tel:${b.phone}`)}
                  style={styles.callBtn}
                  testID={`call-${b.user_id}`}
                >
                  <Text style={styles.callText}>LLAMAR</Text>
                </Pressable>
              ) : null}
            </View>
          ))
        )}
        <Pressable accessibilityRole="button" onPress={props.onOpenDirectorio}>
          <Text style={styles.link}>Ver directorio completo →</Text>
        </Pressable>
      </View>

      <Pressable accessibilityRole="button" onPress={props.onOpenRutas} style={styles.routesBtn}>
        <Text style={styles.routesText}>RUTAS DE EVACUACIÓN Y PUNTO DE REUNIÓN →</Text>
      </Pressable>

      {props.onOpenPanic ? (
        <Pressable
          accessibilityRole="button"
          onPress={props.onOpenPanic}
          style={styles.panicBtn}
          testID="open-panic"
        >
          <Text style={styles.panicText}>ALARMA DEL INMUEBLE (NO SÍSMICA) →</Text>
        </Pressable>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  drillBanner: {
    backgroundColor: palette.warn,
    borderRadius: radius.md,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
  },
  drillText: { color: palette.bg, fontSize: fontSize.sm, fontWeight: "800", letterSpacing: 1 },
  reentryBanner: {
    backgroundColor: palette.ok,
    borderRadius: radius.md,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
  },
  reentryText: { color: palette.bg, fontSize: fontSize.sm, fontWeight: "800", lineHeight: 18 },
  statusCard: {
    backgroundColor: palette.card,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[1],
  },
  statusLabel: { fontSize: fontSize.xl, fontWeight: "800", letterSpacing: 2 },
  statusDetail: { color: palette.fg2, fontSize: fontSize.sm },
  chip: {
    alignSelf: "flex-start",
    borderColor: palette.borderStrong,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space[2],
    paddingVertical: 2,
    marginTop: space[1],
  },
  chipText: { color: palette.fg2, fontSize: fontSize.xs, letterSpacing: 1 },
  card: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  cardTitle: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  zoneName: { color: palette.fg, fontSize: fontSize.lg, fontWeight: "700" },
  zonePolicy: { color: palette.cyan, fontSize: fontSize.sm, letterSpacing: 1 },
  rowText: { color: palette.fg2, fontSize: fontSize.sm },
  rowStrong: { color: palette.fg, fontWeight: "600" },
  muted: { color: palette.fg3, fontSize: fontSize.sm },
  dirRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  dirInfo: { gap: 2 },
  callBtn: {
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  callText: { color: palette.bg, fontWeight: "700", fontSize: fontSize.xs, letterSpacing: 1 },
  link: { color: palette.cyan, fontSize: fontSize.sm, marginTop: space[1] },
  routesBtn: {
    backgroundColor: palette.card,
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
  },
  routesText: { color: palette.cyan, fontWeight: "700", fontSize: fontSize.sm, letterSpacing: 1 },
  panicBtn: {
    borderColor: palette.crit,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
  },
  panicText: { color: palette.crit, fontWeight: "700", fontSize: fontSize.sm, letterSpacing: 1 },
});
