// 2.6 · Headcount — presentacional. Contadores del servidor, filtro "no
// reportados" por defecto, llamada de un toque y marcación "verificado en
// persona" (check-in delegado). "Notificar a no reportados" = push OPS;
// "Cerrar headcount" habilitado solo si todos están contabilizados.
import type { RosterOut } from "@takab/sdk";
import { Linking, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import { allAccounted, rosterRows, type PersonState } from "./rosterView";

const STATE_COLOR: Record<PersonState, string> = {
  safe: palette.ok,
  need_help: palette.crit,
  unreported: palette.warn,
};
const STATE_LABEL: Record<PersonState, string> = {
  safe: "A SALVO",
  need_help: "AYUDA",
  unreported: "SIN REPORTE",
};

function Counter(props: { label: string; value: number; color: string }) {
  return (
    <View style={styles.counter}>
      <Text style={[styles.counterValue, { color: props.color }]}>{props.value}</Text>
      <Text style={styles.counterLabel}>{props.label}</Text>
    </View>
  );
}

export function HeadcountView(props: {
  roster: RosterOut;
  onlyUnreported: boolean;
  live: boolean;
  markingId: string | null;
  onToggleFilter: (v: boolean) => void;
  onMarkVerified: (userId: string) => void;
  onNotifyUnreported: () => void;
  onCloseHeadcount: () => void;
  busy: boolean;
}) {
  const rows = rosterRows(props.roster, props.onlyUnreported);
  const canClose = allAccounted(props.roster);

  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <View style={styles.headRow}>
        <Text style={styles.eyebrow}>PASE DE LISTA</Text>
        <View style={[styles.livePill, { borderColor: props.live ? palette.ok : palette.fg3 }]}>
          <Text style={[styles.liveText, { color: props.live ? palette.ok : palette.fg3 }]}>
            {props.live ? "EN VIVO" : "SIN CANAL"}
          </Text>
        </View>
      </View>

      <View style={styles.countsRow}>
        <Counter label="A SALVO" value={props.roster.safe} color={palette.ok} />
        <Counter label="AYUDA" value={props.roster.need_help} color={palette.crit} />
        <Counter label="SIN REPORTE" value={props.roster.unreported} color={palette.warn} />
      </View>

      <View style={styles.filterRow}>
        <Text style={styles.filterLabel}>Solo no reportados</Text>
        <Switch
          onValueChange={props.onToggleFilter}
          testID="filter-unreported"
          value={props.onlyUnreported}
        />
      </View>

      {rows.length === 0 ? (
        <Text style={styles.empty}>
          {props.onlyUnreported ? "Todos reportaron." : "Sin personas asignadas."}
        </Text>
      ) : (
        rows.map((r) => (
          <View key={r.userId} style={styles.personRow} testID={`person-${r.userId}`}>
            <View style={styles.personInfo}>
              <Text style={styles.personName}>{r.name}</Text>
              <Text style={styles.personZone}>
                {r.zone ?? "sin zona"}
                {r.delegated ? " · verificado en persona" : ""}
              </Text>
            </View>
            <View style={styles.personRight}>
              <Text style={[styles.personState, { color: STATE_COLOR[r.state] }]}>
                {STATE_LABEL[r.state]}
              </Text>
              {r.state === "unreported" ? (
                <View style={styles.actions}>
                  {r.phone ? (
                    <Pressable
                      accessibilityRole="button"
                      onPress={() => void Linking.openURL(`tel:${r.phone}`)}
                      style={styles.callBtn}
                      testID={`call-${r.userId}`}
                    >
                      <Text style={styles.callText}>LLAMAR</Text>
                    </Pressable>
                  ) : null}
                  <Pressable
                    accessibilityRole="button"
                    disabled={props.markingId === r.userId}
                    onPress={() => props.onMarkVerified(r.userId)}
                    style={styles.verifyBtn}
                    testID={`verify-${r.userId}`}
                  >
                    <Text style={styles.verifyText}>
                      {props.markingId === r.userId ? "…" : "VERIFICAR"}
                    </Text>
                  </Pressable>
                </View>
              ) : null}
            </View>
          </View>
        ))
      )}

      <Pressable
        accessibilityRole="button"
        disabled={props.roster.unreported === 0 || props.busy}
        onPress={props.onNotifyUnreported}
        style={[styles.notifyBtn, props.roster.unreported === 0 && styles.dim]}
        testID="notify-unreported"
      >
        <Text style={styles.notifyText}>NOTIFICAR A NO REPORTADOS ({props.roster.unreported})</Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        disabled={!canClose || props.busy}
        onPress={props.onCloseHeadcount}
        style={[styles.closeBtn, !canClose && styles.dim]}
        testID="close-headcount"
      >
        <Text style={styles.closeText}>
          {canClose ? "CERRAR HEADCOUNT (FIRMADO)" : "FALTAN POR CONTABILIZAR"}
        </Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  headRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  livePill: { borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: space[2], paddingVertical: 2 },
  liveText: { fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
  countsRow: { flexDirection: "row", gap: space[2] },
  counter: { flex: 1, backgroundColor: palette.card, borderColor: palette.border, borderWidth: 1, borderRadius: radius.md, padding: space[2], alignItems: "center" },
  counterValue: { fontSize: fontSize.xl, fontWeight: "800" },
  counterLabel: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  filterRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  filterLabel: { color: palette.fg2, fontSize: fontSize.sm },
  empty: { color: palette.fg3, fontSize: fontSize.sm, textAlign: "center", marginVertical: space[3] },
  personRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: palette.card, borderColor: palette.border, borderWidth: 1, borderRadius: radius.md, padding: space[3] },
  personInfo: { flex: 1, gap: 2 },
  personName: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  personZone: { color: palette.fg3, fontSize: fontSize.xs },
  personRight: { alignItems: "flex-end", gap: space[1] },
  personState: { fontSize: fontSize.xs, fontWeight: "800", letterSpacing: 1 },
  actions: { flexDirection: "row", gap: space[1] },
  callBtn: { backgroundColor: palette.cyan, borderRadius: radius.sm, paddingHorizontal: space[2], paddingVertical: 2 },
  callText: { color: palette.bg, fontSize: fontSize.xs, fontWeight: "700" },
  verifyBtn: { borderColor: palette.ok, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: space[2], paddingVertical: 2 },
  verifyText: { color: palette.ok, fontSize: fontSize.xs, fontWeight: "700" },
  notifyBtn: { borderColor: palette.warn, borderWidth: 1, borderRadius: radius.md, paddingVertical: space[3], alignItems: "center", marginTop: space[2] },
  notifyText: { color: palette.warn, fontWeight: "700", fontSize: fontSize.sm, letterSpacing: 1 },
  closeBtn: { backgroundColor: palette.cyan, borderRadius: radius.lg, paddingVertical: space[3], alignItems: "center" },
  closeText: { color: palette.bg, fontWeight: "800", letterSpacing: 1 },
  dim: { opacity: 0.4 },
});
