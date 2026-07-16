// 2.1 · Dashboard táctico — presentacional puro. MISMO payload que la consola
// (site_health de mobile-state + frames del /ws + groupActions COMPARTIDA de
// @takab/sdk — cero transformaciones divergentes). Features de 1 s: pga/pgv/
// rms/stalta — JAMÁS forma de onda (regla de oro 9).
import type { ActuatorGroup, FeatureRow, MobileSiteHealthOut } from "@takab/sdk";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { timeAgoLabel } from "@/ui/timeAgo";
import { fontSize, palette, radius, space } from "@/ui/theme";

import { fmtMetric, upsLabel } from "./health";

export type LivePill = "ready" | "connecting" | "closed";

const PILL_COLOR: Record<LivePill, string> = {
  ready: palette.ok,
  connecting: palette.warn,
  closed: palette.crit,
};
const PILL_LABEL: Record<LivePill, string> = {
  ready: "LIVE",
  connecting: "RECONECTANDO…",
  closed: "SIN CANAL LIVE",
};

const GROUP_COLOR = { critical: palette.crit, warning: palette.warn, ok: palette.ok } as const;

function Metric(props: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{props.label}</Text>
      <Text style={styles.metricValue}>{props.value}</Text>
    </View>
  );
}

export function PanelView(props: {
  siteName: string;
  tier: string | null;
  health: MobileSiteHealthOut;
  live: LivePill;
  latestByChannel: FeatureRow[];
  /** null = jamás llegó un frame de features (se declara, no se finge). */
  featuresAtMs: number | null;
  groups: ActuatorGroup[];
  incidentOpen: boolean;
  nowMs: number;
}) {
  const h = props.health;
  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <View style={styles.headerRow}>
        <Text style={styles.eyebrow}>{props.siteName.toUpperCase()} · DASHBOARD</Text>
        <View style={[styles.pill, { borderColor: PILL_COLOR[props.live] }]}>
          <Text style={[styles.pillText, { color: PILL_COLOR[props.live] }]} testID="live-pill">
            {PILL_LABEL[props.live]}
          </Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>SALUD DEL GABINETE · {h.status}</Text>
        <View style={styles.metricGrid}>
          <Metric label="RTT MQTT" value={fmtMetric(h.mqtt_rtt_ms, " ms")} />
          <Metric label="LAG SEEDLINK" value={fmtMetric(h.seedlink_lag_s, " s", 1)} />
          <Metric label="OFFSET NTP" value={fmtMetric(h.ntp_offset_ms, " ms", 1)} />
          <Metric label="CPU" value={fmtMetric(h.cpu_temp_c, " °C", 1)} />
          <Metric label="UPS" value={upsLabel(h.power_status, h.battery_pct)} />
          <Metric
            label="CERT mTLS"
            value={h.cert_days_remaining == null ? "S/D" : `${h.cert_days_remaining} d`}
          />
        </View>
        <Text style={styles.muted}>
          Último heartbeat:{" "}
          {h.heartbeat_at ? timeAgoLabel(Date.parse(h.heartbeat_at), props.nowMs) : "S/D"}
          {props.tier ? ` · tier ${props.tier.toUpperCase()}` : ""}
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>MOVIMIENTO · FEATURES 1 s</Text>
        {props.latestByChannel.length === 0 ? (
          <Text style={styles.muted} testID="features-waiting">
            ESPERANDO DATOS DEL SITIO… (sin frames aún)
          </Text>
        ) : (
          <>
            {props.latestByChannel.map((row) => (
              <View key={row.channel} style={styles.featRow} testID={`feat-${row.channel}`}>
                <Text style={styles.featChannel}>{row.channel}</Text>
                <Text style={styles.featValue}>PGA {fmtMetric(row.pga_g, " g", 3)}</Text>
                <Text style={styles.featValue}>PGV {fmtMetric(row.pgv_cms, "", 2)}</Text>
                <Text style={styles.featValue}>RMS {fmtMetric(row.rms, "", 3)}</Text>
                <Text style={styles.featValue}>STA/LTA {fmtMetric(row.stalta, "", 2)}</Text>
              </View>
            ))}
            <Text style={styles.muted}>
              {props.featuresAtMs
                ? `Frame recibido ${timeAgoLabel(props.featuresAtMs, props.nowMs)}`
                : "S/D"}
              {" · features 1 s, sin forma de onda"}
            </Text>
          </>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>ACTUADORES BMS · ARBITRAJE</Text>
        {!props.incidentOpen ? (
          <Text style={styles.muted} testID="bms-idle">
            SIN INCIDENTE ABIERTO — la traza aparece al activarse el sitio.
          </Text>
        ) : props.groups.length === 0 ? (
          <Text style={styles.muted}>SIN ACCIONES REGISTRADAS TODAVÍA.</Text>
        ) : (
          props.groups.map((g) => (
            <View key={g.kind} style={styles.bmsRow} testID={`bms-${g.kind}`}>
              <Text style={styles.bmsLabel}>{g.label}</Text>
              <View style={styles.bmsRight}>
                <Text style={[styles.bmsState, { color: GROUP_COLOR[g.view.kind] }]}>
                  {g.view.state}
                </Text>
                {g.count > 1 ? <Text style={styles.bmsCount}>×{g.count}</Text> : null}
              </View>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2, flexShrink: 1 },
  pill: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space[2],
    paddingVertical: 2,
  },
  pillText: { fontSize: fontSize.xs, letterSpacing: 1, fontWeight: "700" },
  card: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  cardTitle: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: space[3] },
  metric: { minWidth: "28%", gap: 2 },
  metricLabel: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  metricValue: { color: palette.fg, fontSize: fontSize.md, fontWeight: "700" },
  muted: { color: palette.fg3, fontSize: fontSize.xs },
  featRow: { flexDirection: "row", gap: space[2], alignItems: "baseline", flexWrap: "wrap" },
  featChannel: { color: palette.cyan, fontSize: fontSize.sm, fontWeight: "700", minWidth: 44 },
  featValue: { color: palette.fg2, fontSize: fontSize.xs },
  bmsRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  bmsLabel: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  bmsRight: { flexDirection: "row", alignItems: "center", gap: space[1] },
  bmsState: { fontSize: fontSize.sm, fontWeight: "800", letterSpacing: 1 },
  bmsCount: { color: palette.fg3, fontSize: fontSize.xs },
});
