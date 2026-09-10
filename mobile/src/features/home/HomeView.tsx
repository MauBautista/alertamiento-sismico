// 1.1 Modo reposo — presentacional puro. Todo lo que pinta viene del servidor
// (mobile-state + directorio); el teléfono no calcula estados. Un drill JAMÁS
// dispara pantallas de crisis (no crea incidente — garantía server-side).
// [T-6.19] Las franjas de SIMULACRO y de MODO DEMOSTRACIÓN ya no viven aquí:
// las pinta `features/notices/SiteNoticeStrip` desde el layout de las
// pestañas, para que se vean igual en INICIO, RUTAS, DIRECTORIO y CUENTA.
import { Feather } from "@expo/vector-icons";
import type { DirectoryEntryOut, MobileStateOut } from "@takab/sdk";
import {
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { fontSize, palette, radius, slopHasta, space, touch } from "@/ui/theme";

import { healthBanner, wr1Chip, type HealthTone } from "./health";

/**
 * [T-6.20] Alto VISIBLE del chip que vive DENTRO de una fila. Crecerlo hasta el
 * mínimo táctil empujaría la lista fuera de pantalla, así que el que crece es
 * el área que recibe el dedo: `slopHasta(CHIP_ALTO)` la lleva a `touch.min`.
 * El número sale de aquí y no de una estimación a ojo, para que la cuenta siga
 * siendo cierta si alguien cambia el chip.
 */
const CHIP_ALTO = 24;

const TONE_COLOR: Record<HealthTone, string> = {
  ok: palette.ok,
  warn: palette.warn,
  crit: palette.crit,
};

/** `HH:MM` local — la hora en que se supo por última vez. */
function fmtHora(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

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
  /**
   * [T-6.24 · U-33] Epoch ms del dato cuando YA ES VIEJO, o `null` si es fresco.
   *
   * La tarjeta de estado se pintaba SIEMPRE con el tono de `site_health`, que
   * describe el gabinete y no sabe nada de si esta lectura llegó hace un
   * segundo o hace diez minutos. Medido con la red cortada 105 s: «SEGURO»
   * seguía en verde vivo e intacto, y la única señal era una franja fina
   * dibujada encima de la barra de estado de Android. El umbral estaba bien; la
   * jerarquía no — que es exactamente lo que persigue la regla de oro 7.
   */
  staleSinceMs?: number | null;
  onOpenRutas: () => void;
  onOpenDirectorio: () => void;
  onOpenPanic?: () => void;
}) {
  const { data } = props;
  const banner = healthBanner(data.site_health, props.nowMs);
  const chip = wr1Chip(data.site_health);
  // Retenido MANDA sobre el tono del gabinete: un verde vivo afirma «esto es de
  // ahora», y con el dato viejo eso es falso aunque el edificio esté bien. El
  // texto sigue siendo el portador —el tono solo acompaña—, así que el rótulo
  // no cambia y debajo se dice desde cuándo.
  const retenido = props.staleSinceMs ?? null;
  const tono = retenido !== null ? "warn" : banner.tone;
  return (
    <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
      <Text style={styles.eyebrow}>{data.site_name.toUpperCase()}</Text>

      {/* [T-6.19] Relleno SÓLIDO + glifo de visto: es la única franja con
          relleno, y así se distingue de la de simulacro (regla lateral) sin
          depender del verde. */}
      {data.phase === "reentry_approved" ? (
        <View style={styles.reentryBanner} testID="reentry-banner">
          <Feather
            color={palette.bg}
            name="check-circle"
            size={fontSize.md}
            testID="reentry-glyph"
          />
          <Text style={styles.reentryText}>
            REINGRESO AUTORIZADO — el dictamen técnico del inspector aprobó el
            reingreso al inmueble.
          </Text>
        </View>
      ) : null}

      <View style={[styles.statusCard, { borderColor: TONE_COLOR[tono] }]}>
        <Text style={[styles.statusLabel, { color: TONE_COLOR[tono] }]} testID="estado">
          {banner.label}
        </Text>
        <Text style={styles.statusDetail}>{banner.detail}</Text>
        {retenido !== null ? (
          <Text style={styles.statusRetenido} testID="estado-retenido">
            {/* DESDE CUÁNDO, no cuánto hace. `props.nowMs` es el instante de la
                CONSULTA —ya viejo cuando el dato lo está—, así que una edad
                calculada con él dice «hace segundos» mientras la franja de
                arriba dice «hace 1 min»: dos edades del mismo hecho, y la de la
                tarjeta siempre la más corta. Medido en el Pixel. Una hora fija
                no puede envejecer mal. */}
            DATO RETENIDO · desde {fmtHora(retenido)} · sin conexión
          </Text>
        ) : null}
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
              {POLICY_LABEL[data.my_zone.evac_policy] ??
                data.my_zone.evac_policy}
            </Text>
          ) : (
            <Text style={styles.muted}>Sin política de zona definida.</Text>
          )}
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>SU ZONA</Text>
          <Text style={styles.muted}>
            Sin zona asignada — vincúlese con su administrador.
          </Text>
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>SIMULACROS</Text>
        <Text style={styles.rowText}>
          Próximo:{" "}
          {data.drill.next_scheduled_at ? (
            <Text style={styles.rowStrong}>
              {fmtFecha(data.drill.next_scheduled_at)}
            </Text>
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
          <Text style={styles.muted}>
            Sin brigadistas publicados para su zona.
          </Text>
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
                  hitSlop={slopHasta(CHIP_ALTO)}
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
        <Pressable
          accessibilityRole="button"
          onPress={props.onOpenDirectorio}
          style={styles.linkBtn}
        >
          <Text style={styles.link}>Ver directorio completo →</Text>
        </Pressable>
      </View>

      <Pressable
        accessibilityRole="button"
        onPress={props.onOpenRutas}
        style={styles.routesBtn}
      >
        <Text style={styles.routesText}>
          RUTAS DE EVACUACIÓN Y PUNTO DE REUNIÓN →
        </Text>
      </Pressable>

      {props.onOpenPanic ? (
        <Pressable
          accessibilityRole="button"
          onPress={props.onOpenPanic}
          style={styles.panicBtn}
          testID="open-panic"
        >
          <Text style={styles.panicText}>
            ALARMA DEL INMUEBLE (NO SÍSMICA) →
          </Text>
        </Pressable>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  reentryBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    backgroundColor: palette.ok,
    borderRadius: radius.md,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
  },
  reentryText: {
    flex: 1,
    color: palette.bg,
    fontSize: fontSize.sm,
    fontWeight: "800",
    lineHeight: 18,
  },
  statusCard: {
    backgroundColor: palette.card,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[1],
  },
  statusLabel: { fontSize: fontSize.xl, fontWeight: "800", letterSpacing: 2 },
  statusDetail: { color: palette.fg2, fontSize: fontSize.sm },
  statusRetenido: {
    color: palette.warn,
    fontSize: fontSize.xs,
    fontWeight: "700",
    letterSpacing: 1,
    marginTop: space[1],
  },
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
  dirRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  dirInfo: { gap: 2 },
  callBtn: {
    minHeight: CHIP_ALTO,
    justifyContent: "center",
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingHorizontal: space[3],
    paddingVertical: space[1],
  },
  callText: {
    color: palette.bg,
    fontWeight: "700",
    fontSize: fontSize.xs,
    letterSpacing: 1,
  },
  link: { color: palette.cyan, fontSize: fontSize.sm, marginTop: space[1] },
  routesBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    backgroundColor: palette.card,
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
  },
  routesText: {
    color: palette.cyan,
    fontWeight: "700",
    fontSize: fontSize.sm,
    letterSpacing: 1,
  },
  panicBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    borderColor: palette.crit,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
  },
  /* [T-6.20] Medido en el Pixel: 382×19 dp. Es el camino a los teléfonos de
     la brigada; ahora el control mide lo que mide el mínimo. */
  linkBtn: { minHeight: touch.min, justifyContent: "center" },
  panicText: {
    color: palette.crit,
    fontWeight: "700",
    fontSize: fontSize.sm,
    letterSpacing: 1,
  },
});
