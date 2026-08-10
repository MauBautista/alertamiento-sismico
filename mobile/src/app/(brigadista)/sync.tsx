// 2.5 · Sincronización asíncrona (offline-first). Muestra la cola que el
// teléfono PRODUJO (fotos, reportes, check-ins — jamás miniSEED): estado por
// elemento, tamaño pendiente, reintento manual y banner de modo offline. El
// badge de cifrado SOLO afirma AES-256 si SQLCipher se verificó (§4.2).
//
// [T-2.108] Esta pantalla existe para dar confianza sobre la cola y era la que
// mentía sobre su contenido: el banner prometía que "sus capturas y reportes"
// se guardaban localmente cuando la cola solo admitía check-ins. Ahora la
// promesa es cierta —fotos y reportes se encolan de verdad— y la pantalla usa
// el StateFrame como el resto (antes no tenía ni `error` ni `stale`: si abrir
// la base local fallaba, se quedaba en "Cargando…" para siempre).
import * as Network from "expo-network";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import {
  countByState,
  encryptionBadge,
  formatBytes,
  pendingBytes,
  pendingCount,
  syncItemView,
} from "@/features/sync/syncView";
import { retryFailed } from "@/offline/queue";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import { StateFrame } from "@/ui/StateFrame";
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
  const hydrated = useQueueStore((s) => s.hydrated);
  const hydrationError = useQueueStore((s) => s.hydrationError);
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
  const bytes = pendingBytes(items);
  const badge = encryptionBadge(encryption);

  // "Retenido desde": la edad de lo más viejo que sigue sin salir. Es el dato
  // honesto de esta pantalla — un contador de pendientes sin edad no distingue
  // "acabo de capturarlo" de "lleva dos horas aquí".
  const retenidoDesde = items
    .filter((i) => i.state !== "synced")
    .reduce<number | null>((min, i) => (min === null ? i.created_at : Math.min(min, i.created_at)), null);

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
      <Text style={styles.eyebrow}>
        {hydrated ? `SINCRONIZACIÓN · ${pending} PENDIENTE(S)` : "SINCRONIZACIÓN"}
        {hydrated && bytes > 0 ? ` · ${formatBytes(bytes)}` : ""}
      </Text>

      {!online ? (
        <View style={styles.offlineBanner} testID="offline-banner">
          <Text style={styles.offlineText}>
            MODO OFFLINE — sus fotos forenses, reportes de daños y check-ins se guardan en este
            teléfono y se enviarán automáticamente al recuperar la red. No cierre su sesión.
          </Text>
        </View>
      ) : null}

      {encryption !== null ? (
        <View style={[styles.badge, badge.secure ? styles.badgeOk : styles.badgeWarn]}>
          <Text style={[styles.badgeText, { color: badge.secure ? palette.ok : palette.warn }]}>
            {badge.label}
          </Text>
        </View>
      ) : null}

      <StateFrame
        empty={items.length === 0}
        emptyText="Nada por sincronizar. Todo lo que capture aparecerá aquí."
        error={
          hydrationError === null
            ? null
            : `No se pudo abrir su cola local (${hydrationError}). Lo que capture ahora puede no guardarse: no cierre la app.`
        }
        loading={!hydrated && hydrationError === null}
        staleSinceMs={!online && retenidoDesde !== null ? retenidoDesde : null}
      >
        <View style={styles.countsRow}>
          <Counter label="ENVIANDO" tone="warn" value={counts.uploading} />
          <Counter label="PENDIENTES" tone="muted" value={counts.pending} />
          <Counter label="OK" tone="ok" value={counts.synced} />
          <Counter label="FALLIDOS" tone="crit" value={counts.failed} />
        </View>

        {counts.failed > 0 ? (
          <Pressable
            accessibilityRole="button"
            onPress={retryAll}
            style={styles.retryAll}
            testID="retry-all"
          >
            <Text style={styles.retryAllText}>REINTENTAR FALLIDOS ({counts.failed})</Text>
          </Pressable>
        ) : null}

        {items
          .slice()
          .reverse()
          .map((item) => {
            const v = syncItemView(item, nowMs, items);
            return (
              <View key={v.id} style={styles.itemCard} testID={`sync-${v.id}`}>
                <View style={styles.itemHead}>
                  <Text style={styles.itemTitle}>{v.title}</Text>
                  <Text style={[styles.itemState, { color: TONE[v.tone] }]}>{v.stateLabel}</Text>
                </View>
                {v.urgent ? <Text style={styles.itemUrgent}>PRIORIDAD MÁXIMA</Text> : null}
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
          })}
      </StateFrame>
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
  countsRow: { flexDirection: "row", gap: space[2], marginBottom: space[3] },
  counter: { flex: 1, backgroundColor: palette.card, borderColor: palette.border, borderWidth: 1, borderRadius: radius.md, padding: space[2], alignItems: "center" },
  counterValue: { fontSize: fontSize.xl, fontWeight: "800" },
  counterLabel: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  retryAll: { backgroundColor: palette.crit, borderRadius: radius.md, paddingVertical: space[3], alignItems: "center", marginBottom: space[3] },
  retryAllText: { color: palette.fg, fontWeight: "800", letterSpacing: 1 },
  itemCard: { backgroundColor: palette.card, borderColor: palette.border, borderWidth: 1, borderRadius: radius.lg, padding: space[3], gap: space[1], marginBottom: space[3] },
  itemHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  itemTitle: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  itemState: { fontSize: fontSize.xs, fontWeight: "800", letterSpacing: 1 },
  itemUrgent: { color: palette.crit, fontSize: fontSize.xs, fontWeight: "800", letterSpacing: 1 },
  itemDetail: { color: palette.fg3, fontSize: fontSize.xs },
  retryBtn: { alignSelf: "flex-start", borderColor: palette.cyan, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: space[2], paddingVertical: 2, marginTop: space[1] },
  retryText: { color: palette.cyan, fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
});
