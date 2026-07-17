// 1.7 · Directorio — presentacional puro: contactos agrupados por zona con
// llamada de un toque. Sin teléfono publicado NO hay botón (honesto, no un
// tel: que truena).
import type { DirectoryEntryOut } from "@takab/sdk";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

const ROLE_LABEL: Record<string, string> = {
  brigadista: "BRIGADISTA",
  security_guard: "SEGURIDAD",
  building_admin: "ADMINISTRACIÓN",
};

export function groupByZone(entries: DirectoryEntryOut[]): [string, DirectoryEntryOut[]][] {
  const groups = new Map<string, DirectoryEntryOut[]>();
  for (const e of entries) {
    const key = e.zone_name ?? "SIN ZONA";
    const list = groups.get(key) ?? [];
    list.push(e);
    groups.set(key, list);
  }
  return [...groups.entries()];
}

export function DirectoryList(props: { entries: DirectoryEntryOut[] }) {
  return (
    <View style={styles.wrap}>
      {groupByZone(props.entries).map(([zone, list]) => (
        <View key={zone} style={styles.group}>
          <Text style={styles.zone}>{zone.toUpperCase()}</Text>
          {list.map((e) => (
            <View key={e.user_id} style={styles.row} testID={`dir-${e.user_id}`}>
              <View style={styles.info}>
                <Text style={styles.name}>{e.display_name}</Text>
                <Text style={styles.role}>{ROLE_LABEL[e.role] ?? e.role.toUpperCase()}</Text>
              </View>
              {e.phone ? (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => void Linking.openURL(`tel:${e.phone}`)}
                  style={styles.callBtn}
                  testID={`dir-call-${e.user_id}`}
                >
                  <Text style={styles.callText}>LLAMAR</Text>
                </Pressable>
              ) : (
                <Text style={styles.noPhone}>sin teléfono</Text>
              )}
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space[3] },
  group: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  zone: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  info: { gap: 2 },
  name: { color: palette.fg, fontSize: fontSize.md, fontWeight: "600" },
  role: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  callBtn: {
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  callText: { color: palette.bg, fontWeight: "700", fontSize: fontSize.xs, letterSpacing: 1 },
  noPhone: { color: palette.fg3, fontSize: fontSize.xs },
});
