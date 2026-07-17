// 2.5 · Sincronización asíncrona (offline-first). Muestra la cola que el
// teléfono PRODUJO (check-ins/reportes/evidencia — jamás miniSEED): estado por
// elemento, tamaño pendiente, reintento manual y banner de modo offline. El
// badge de cifrado SOLO afirma AES-256 si SQLCipher se verificó (§4.2).
import * as Network from "expo-network";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { retryFailed } from "@/offline/queue";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import {
  countByState,
  encryptionBadge,
  pendingCount,
  syncItemView,
} from "@/features/sync/syncView";
import { fontSize, palette, radius, space } from "@/ui/theme";

const TONE: Record<string, string> = {
  ok: palette.ok,
  warn: palette.warn,
  crit: palette.crit,
  muted: palette.fg3,
};

export default function Sync() {
  const items = useQueueStore((s) => s.items);
  const encryption = useQueueStore((s) => s.encryption);
  const apply = useQueueStore((s) => s.apply);
  const [online, setOnline] = useState(true);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    let alive = true;
    Network.getNetworkStateAsync().then((s) => {
      if (alive) {
        setOnline(s.isConnected ?? true);
      }
    });
    const sub = Network.addNetworkStateListener((s) => setOnline(s.isConnected ?? true));
    const tick = setInterval(() => setNowMs(Date.now()), 5_000);
    return () => {
      alive = false;
      sub.remove();
      clearInterval(tick);
    };
  }, []);

  const counts = countByState(items);
  const pending = pendingCount(items);
  const badge = encryptionBadge(encryption);

  const retryAll = () => {
    void (async () => {
      for (const item of items.filter((i) => i.state === "failed")) {
        await apply(retryFailed(item));
      }
      void drainQueue();
    })();
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <Text style={styles.eyebrow}>SINCRONIZACIÓN · {pending} PENDIENTE(S)</Text>

      {!online ? (
        <View style={styles.offlineBanner} testID="offline-banner">
          <Text style={styles.offlineText}>
            MODO OFFLINE — sus capturas y reportes se guardan localmente y se enviarán
            automáticamente al recuperar la red. No cierre su sesión.
          </Text>
        </View>
      ) : null}

      <View style={[styles.badge, badge.secure ? styles.badgeOk : styles.badgeWarn]}>
        <Text style={[styles.badgeText, { color: badge.secure ? palette.ok : palette.warn }]}>
          {badge.label}
        </Text>
      </View>

      <View style={styles.countsRow}>
        <Counter label="ENVIANDO" value={counts.uploading} tone="warn" />
        <Counter label="PENDIENTES" value={counts.pending} tone="muted" />
        <Counter label="OK" value={counts.synced} tone="ok" />
        <Counter label="FALLIDOS" value={counts.failed} tone="crit" />
      </View>

      {counts.failed > 0 ? (
        <Pressable accessibilityRole="button" onPress={retryAll} style={styles.retryAll} testID="retry-all">
          <Text style={styles.retryAllText}>REINTENTAR FALLIDOS ({counts.failed})</Text>
        </Pressable>
      ) : null}

      {items.length === 0 ? (
        <Text style={styles.empty}>Nada por sincronizar. Todo lo que capture aparecerá aquí.</Text>
      ) : (
        items
          .slice()
          .reverse()
          .map((item) => {
            const v = syncItemView(item, nowMs);
            return (
              <View key={v.id} style={styles.itemCard} testID={`sync-${v.id}`}>
                <View style={styles.itemHead}>
                  <Text style={styles.itemTitle}>{v.title}</Text>
                  <Text style={[styles.itemState, { color: TONE[v.tone] }]}>{v.stateLabel}</Text>
                </View>
                {v.detail ? <Text style={styles.itemDetail}>{v.detail}</Text> : null}
                {v.retriable ? (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => {
                      void apply(retryFailed(item)).then(() => drainQueue());
                    }}
                    style={styles.retryBtn}
                    testID={`retry-${v.id}`}
                  >
                    <Text style={styles.retryText}>REINTENTAR</Text>
                  </Pressable>
                ) : null}
              </View>
            );
          })
      )}
    </ScrollView>
  );
}

function Counter(props: { label: string; value: number; tone: keyof typeof TONE }) {
  return (
    <View style={styles.counter}>
      <Text style={[styles.counterValue, { color: TONE[props.tone] }]}>{props.value}</Text>
      <Text style={styles.counterLabel}>{props.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  offlineBanner: { backgroundColor: palette.card, borderColor: palette.warn, borderWidth: 1, borderRadius: radius.md, padding: space[3] },
  offlineText: { color: palette.warn, fontSize: fontSize.sm, lineHeight: 20 },
  badge: { alignSelf: "flex-start", borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: space[3], paddingVertical: 3 },
  badgeOk: { borderColor: palette.ok },
  badgeWarn: { borderColor: palette.warn },
  badgeText: { fontSize: fontSize.xs, letterSpacing: 1, fontWeight: "700" },
  countsRow: { flexDirection: "row", gap: space[2] },
  counter: { flex: 1, backgroundColor: palette.card, borderColor: palette.border, borderWidth: 1, borderRadius: radius.md, padding: space[2], alignItems: "center" },
  counterValue: { fontSize: fontSize.xl, fontWeight: "800" },
  counterLabel: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  retryAll: { backgroundColor: palette.crit, borderRadius: radius.md, paddingVertical: space[3], alignItems: "center" },
  retryAllText: { color: palette.fg, fontWeight: "800", letterSpacing: 1 },
  empty: { color: palette.fg3, fontSize: fontSize.sm, textAlign: "center", marginTop: space[4] },
  itemCard: { backgroundColor: palette.card, borderColor: palette.border, borderWidth: 1, borderRadius: radius.lg, padding: space[3], gap: space[1] },
  itemHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  itemTitle: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  itemState: { fontSize: fontSize.xs, fontWeight: "800", letterSpacing: 1 },
  itemDetail: { color: palette.fg3, fontSize: fontSize.xs },
  retryBtn: { alignSelf: "flex-start", borderColor: palette.cyan, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: space[2], paddingVertical: 2, marginTop: space[1] },
  retryText: { color: palette.cyan, fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
});
