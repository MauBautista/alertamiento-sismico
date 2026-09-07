// [T-6.19] LA FRANJA DE AVISOS DEL SITIO — presentacional pura.
//
// Dos avisos, en este orden: MODO DEMOSTRACIÓN (D-27: la nube no está
// avisando a nadie; borde discontinuo + glifo de ojo tachado) y el SIMULACRO
// (regla lateral gruesa + glifo; NUNCA relleno sólido). La franja de reingreso
// de INICIO es la única con relleno sólido y lleva su propio glifo: las tres se
// distinguen por la FORMA, no por el matiz — una persona daltónica las lee.
//
// Vive en el layout de las dos pestañeras (U-32): el ocupante la ve en las
// cuatro pestañas y el brigadista encima de su panel (U-02). Antes sólo INICIO
// la pintaba, y el brigadista —la persona que manda en el edificio— era el
// único sin la etiqueta que dice que es un ensayo.
//
// Movimiento: UNA entrada y UNA salida (fundido), ninguna con `reduceMotion`.
// Sin bucles: el simulacro ya suena; parpadear en el teléfono no protege a nadie.
import { Feather } from "@expo/vector-icons";
import type { MobileStateOut } from "@takab/sdk";
import { useEffect, useMemo, useState } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

import { drillNotice, stripOverlap, type DrillNotice } from "./drillNotice";

export const FADE_MS = 180;

const DRILL_RULE: Record<DrillNotice["kind"], string> = {
  executing: palette.warn,
  pending: palette.fg3,
  not_executing: palette.fg3,
  aborted: palette.crit,
};

interface Notices {
  demo: boolean;
  drill: DrillNotice | null;
}

function sameNotices(a: Notices, b: Notices): boolean {
  return (
    a.demo === b.demo &&
    a.drill?.kind === b.drill?.kind &&
    a.drill?.title === b.drill?.title &&
    a.drill?.detail === b.drill?.detail
  );
}

export function SiteNoticeStrip(props: {
  data: MobileStateOut | null;
  /** Inset superior del aparato (la franja absorbe la barra de estado). */
  topInset: number;
  reduceMotion: boolean;
}) {
  const { data, topInset, reduceMotion } = props;
  // Memo sobre los CAMPOS, no sobre `data`: cada sondeo trae un objeto nuevo y
  // los avisos no deben re-animarse porque el reloj del servidor avanzó.
  const demo = data?.demo_mode === true;
  const drill = data?.drill ?? null;
  const hasDrill = drill !== null;
  const execution = drill?.execution;
  const active = drill?.active ?? false;
  const total = drill?.sites_total;
  const ejecutando = drill?.sites_executing;
  const notices = useMemo<Notices>(
    () => ({
      demo,
      drill: hasDrill
        ? drillNotice({
            active,
            execution,
            sites_total: total,
            sites_executing: ejecutando,
            // La agenda no pinta en la franja.
            next_scheduled_at: null,
            last_started_at: null,
            last_note: null,
          })
        : null,
    }),
    [demo, hasDrill, execution, active, total, ejecutando],
  );
  const visible = notices.demo || notices.drill !== null;

  // Lo que se PINTA mientras la franja se va: el último aviso visible. Estado
  // derivado durante el render (no en un efecto): sólo cambia con un aviso
  // nuevo, y el sondeo con el mismo aviso no lo toca.
  const [shown, setShown] = useState<Notices>(notices);
  if (visible && !sameNotices(shown, notices)) {
    setShown(notices);
  }
  const [mounted, setMounted] = useState(visible);
  if (visible && !mounted) {
    setMounted(true);
  }
  if (!visible && mounted && reduceMotion) {
    setMounted(false);
  }

  const [opacity] = useState(() => new Animated.Value(visible ? 1 : 0));
  useEffect(() => {
    if (reduceMotion) {
      opacity.setValue(visible ? 1 : 0);
      return;
    }
    const anim = Animated.timing(opacity, {
      toValue: visible ? 1 : 0,
      duration: FADE_MS,
      useNativeDriver: true,
    });
    anim.start(({ finished }) => {
      if (finished && !visible) {
        setMounted(false);
      }
    });
    return () => anim.stop();
  }, [visible, reduceMotion, opacity]);

  if (!mounted) {
    return null;
  }
  const aviso = shown.drill;
  return (
    <Animated.View
      pointerEvents="box-none"
      style={[
        styles.strip,
        { paddingTop: topInset, marginBottom: -stripOverlap(topInset), opacity },
      ]}
      testID="site-notices"
    >
      {shown.demo ? (
        <View style={styles.demo} testID="demo-mode-banner">
          <Feather color={palette.fg2} name="eye-off" size={fontSize.md} testID="demo-glyph" />
          <View style={styles.textos}>
            <Text style={styles.demoText}>
              MODO DEMOSTRACIÓN — LA NUBE NO ESTÁ ENVIANDO AVISOS
            </Text>
            <Text style={styles.nota}>
              La protección del gabinete de su edificio sigue armada
            </Text>
          </View>
        </View>
      ) : null}
      {aviso ? (
        <View
          accessibilityRole="alert"
          style={[styles.drill, { borderLeftColor: DRILL_RULE[aviso.kind] }]}
          testID="drill-banner"
        >
          <Feather
            color={DRILL_RULE[aviso.kind]}
            name={aviso.glyph}
            size={fontSize.md}
            testID={`drill-glyph-${aviso.glyph}`}
          />
          <View style={styles.textos}>
            <Text style={styles.drillText} testID={`drill-notice-${aviso.kind}`}>
              {aviso.title}
            </Text>
            <Text style={styles.nota}>{aviso.detail}</Text>
          </View>
        </View>
      ) : null}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  strip: {
    backgroundColor: palette.bg,
    paddingHorizontal: space[4],
    paddingBottom: space[2],
    gap: space[2],
    zIndex: 1,
    elevation: 1,
  },
  demo: {
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: palette.fg3,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
  },
  drill: {
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    backgroundColor: palette.card,
    borderRadius: radius.md,
    borderLeftWidth: 6,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
  },
  textos: { flex: 1, gap: 2 },
  demoText: {
    color: palette.fg2,
    fontSize: fontSize.sm,
    fontWeight: "800",
    letterSpacing: 1,
  },
  drillText: {
    color: palette.fg,
    fontSize: fontSize.sm,
    fontWeight: "800",
    letterSpacing: 1,
  },
  nota: { color: palette.fg3, fontSize: fontSize.xs },
});
