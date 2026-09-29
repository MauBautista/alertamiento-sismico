// [T-9.62 · D-46] La lista de SISMOS DE MÉXICO, vista desde el inmueble.
//
// Presentacional puro: los datos llegan por props y los estados (cargando,
// error, vacío, dato retenido) los resuelve el `StateFrame` de la ruta. Lo que
// esta vista SÍ decide es la franja del catálogo sin actualizar, porque es una
// edad distinta de la del dato en el teléfono (ver `frescura.ts`).
//
// Cifras EXTERNAS con procedencia, o no se pintan (`shared/glossary/procedencia.json`):
// la magnitud y el lugar son de USGS, y por eso el pie lleva SIEMPRE la
// `atribucion` que manda el servidor y la hora de la última sincronización. Lo de
// «en tu inmueble» es una ESTIMACIÓN nuestra y lo dice en cada fila. Sin cuenta
// regresiva y sin rótulo de «preliminar»: esto se publica después del sismo.
import type { SismoCercanoOut, SismosDelSitioOut } from "@takab/sdk";
import type { ReactNode } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";

import { Pulsable } from "@/ui/Pulsable";
import { fontSize, palette, radius, space, touch } from "@/ui/theme";

import { colorDeMmi, LEYENDA_ESCALA, radioDeMagnitud, romanoDeMmi, tintaSobre } from "./escala";
import { fechaLocal } from "./fecha";
import { catalogoSinActualizar } from "./frescura";

export const TITULO_SISMOS = "Sismos de México desde M 4.0 · últimos 90 días";

/** Diámetro del círculo: base legible para la cifra + el radio de la escala. */
function diametro(magnitud: number): number {
  return 40 + 2 * radioDeMagnitud(magnitud);
}

/** «En tu inmueble: IV (estimada) · 180 km» o «…: sin estimar · 612 km». */
export function lineaEnTuInmueble(s: SismoCercanoOut): string {
  const e = s.en_tu_inmueble;
  const romano = e.mmi_romano ?? romanoDeMmi(e.mmi_estimada);
  const grado = romano ? `${romano} (estimada)` : "sin estimar";
  return `En tu inmueble: ${grado} · ${Math.round(e.dist_km)} km`;
}

export function FilaSismo(props: { sismo: SismoCercanoOut }) {
  const s = props.sismo;
  const color = colorDeMmi(s.en_tu_inmueble.mmi_estimada);
  const d = diametro(s.magnitude);
  return (
    <View style={styles.fila} testID="sismo-fila">
      <View
        accessibilityLabel={`Magnitud ${s.magnitude.toFixed(1)}`}
        style={[
          styles.circulo,
          { width: d, height: d, borderRadius: d / 2 },
          color !== null ? { backgroundColor: color } : styles.circuloSinEstimar,
        ]}
        testID="sismo-circulo"
      >
        <Text style={[styles.magnitud, { color: color !== null ? tintaSobre(color) : palette.fg }]}>
          {s.magnitude.toFixed(1)}
        </Text>
      </View>
      <View style={styles.cuerpo}>
        <Text style={styles.lugar}>{s.place}</Text>
        <Text style={styles.fecha} testID="sismo-fecha">
          {fechaLocal(s.origin_time)}
        </Text>
        <Text style={styles.inmueble}>{lineaEnTuInmueble(s)}</Text>
      </View>
    </View>
  );
}

export function SismosList(props: {
  respuesta: SismosDelSitioOut;
  nowMs: number;
  refrescando: boolean;
  onRefrescar: () => void;
  /** Lo que va encima de la lista (el historial del inmueble). */
  cabecera?: ReactNode;
  /** [T-9.63] Abre el mapa (sismos + mapa de calor del inmueble). */
  onVerMapa?: () => void;
}) {
  const r = props.respuesta;
  const franja = catalogoSinActualizar(r, props.nowMs);
  return (
    <FlatList
      ListFooterComponent={
        <View style={styles.pie}>
          {r.atribucion ? <Text style={styles.pieTexto}>{r.atribucion}</Text> : null}
          <Text style={styles.pieTexto} testID="sismos-actualizado">
            Actualizado: {r.actualizado ? fechaLocal(r.actualizado) : "nunca"}
          </Text>
        </View>
      }
      ListHeaderComponent={
        <View style={styles.cabecera}>
          <Text style={styles.eyebrow}>{TITULO_SISMOS}</Text>
          <Text style={styles.leyenda}>{LEYENDA_ESCALA}</Text>
          {props.onVerMapa ? (
            <Pulsable
              accessibilityRole="button"
              onPress={props.onVerMapa}
              style={styles.verMapa}
              testID="sismos-ver-mapa"
            >
              <Text style={styles.verMapaTexto}>VER EN EL MAPA</Text>
              <Text style={styles.verMapaDetalle}>
                Los sismos y el mapa de calor del último que sintió su inmueble →
              </Text>
            </Pulsable>
          ) : null}
          {franja !== null ? (
            <View style={styles.franja} testID="catalogo-sin-actualizar">
              <Text style={styles.franjaTexto}>{franja}</Text>
            </View>
          ) : null}
          {props.cabecera}
          {r.items.length === 0 ? (
            // Sólo se llega aquí con el catálogo SIN actualizar: al día y sin
            // filas es el vacío honesto, y ése lo pinta el `StateFrame`.
            <Text style={styles.sinFilas} testID="sismos-sin-filas">
              El catálogo recibido no trae sismos, pero sin actualizar no se puede afirmar que no
              los hubo.
            </Text>
          ) : null}
        </View>
      }
      contentContainerStyle={styles.wrap}
      data={r.items}
      keyExtractor={(s) => `${s.origin_time}·${s.lat}·${s.lon}`}
      onRefresh={props.onRefrescar}
      refreshing={props.refrescando}
      renderItem={({ item }) => <FilaSismo sismo={item} />}
      style={styles.scroll}
    />
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  // 64 = TAB_SCREEN_TOP_RESERVE: la franja de avisos del sitio solapa esa banda.
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  cabecera: { gap: space[2] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  leyenda: { color: palette.fg3, fontSize: fontSize.xs },
  verMapa: {
    minHeight: touch.min,
    justifyContent: "center",
    backgroundColor: palette.card,
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[3],
    paddingHorizontal: space[3],
    gap: 2,
  },
  verMapaTexto: { color: palette.cyan, fontSize: fontSize.sm, fontWeight: "700", letterSpacing: 1 },
  verMapaDetalle: { color: palette.fg3, fontSize: fontSize.xs },
  franja: {
    backgroundColor: palette.card,
    borderColor: palette.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[2],
    paddingHorizontal: space[3],
  },
  franjaTexto: { color: palette.warn, fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
  sinFilas: { color: palette.fg3, fontSize: fontSize.sm },
  fila: {
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
  },
  circulo: { alignItems: "center", justifyContent: "center" },
  circuloSinEstimar: {
    backgroundColor: palette.raised,
    borderColor: palette.borderStrong,
    borderWidth: 1,
  },
  magnitud: { fontSize: fontSize.base, fontWeight: "700" },
  cuerpo: { flex: 1, gap: 2 },
  lugar: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  fecha: { color: palette.fg3, fontSize: fontSize.xs },
  inmueble: { color: palette.fg2, fontSize: fontSize.xs },
  pie: { gap: 2, paddingTop: space[2] },
  pieTexto: { color: palette.fg3, fontSize: fontSize.xs },
});
