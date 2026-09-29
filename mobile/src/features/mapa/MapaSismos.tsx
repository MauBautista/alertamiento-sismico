// [T-9.63 · T-9.65 · D-46 · D-44] EL MAPA DE LA APP: los sismos de México vistos
// desde el inmueble y, si lo hay, el mapa de calor ESTIMADO del último que se
// sintió en él.
//
// Motor NATIVO (`@maplibre/maplibre-react-native`) sobre `TextureView`, elegido
// midiendo en el Pixel 8 Pro (spike T-9.63, 6 vueltas intercaladas): pinta en
// ~340 ms frente a ~980 del WebView con MapLibre GL JS, ocupa ~430 MB frente a
// ~630 (app + render de Chromium) y arrastra sin fotogramas lentos (0 % frente a
// 0,7 %). Cuesta +10,6 MB de APK. `texture` y no `surface`: midió igual o mejor y
// es la única de las dos que `gfxinfo` puede vigilar.
//
// Lo que NO hace el nativo por sí solo y aquí se pone a mano: el crédito de
// OpenStreetMap a la vista (el SDK lo esconde tras un botón) y el rótulo de
// ESTIMADO de la superficie, que va siempre con ella.
import type { MapaDeCalorMovilOut, SismosDelSitioOut } from "@takab/sdk";
import { Camera, GeoJSONSource, ImageSource, Layer, Map } from "@maplibre/maplibre-react-native";
import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { fechaLocal } from "@/features/sismos/fecha";
import { LEYENDA_ESCALA } from "@/features/sismos/escala";
import { fontSize, palette, space } from "@/ui/theme";

import { ESTILO_BASE, esquinasDeBbox, pieDelMapa, rotuloEstimado, sismosGeoJSON } from "./capas";
import { pngEnDisco } from "./pngEnDisco";

/** Zoom inicial: el inmueble y la costa del Pacífico caben a la vez. */
export const ZOOM_INICIAL = 5;

export const SIN_MAPA_DE_CALOR =
  "Sin mapa de calor: ningún sismo sentido en su inmueble lo tiene todavía.";

export function MapaSismos(props: { sismos: SismosDelSitioOut; mapa: MapaDeCalorMovilOut }) {
  const { sismos, mapa } = props;
  const puntos = useMemo(() => sismosGeoJSON(sismos.items), [sismos.items]);
  const inc = mapa.incidente;
  const bbox = inc?.superficie.bbox ?? null;
  const esquinas = useMemo(() => (bbox ? esquinasDeBbox(bbox) : null), [bbox]);
  // El fichero es el del incidente: sólo se reescribe si cambia el incidente o
  // su imagen, no en cada render (el sondeo trae un objeto nuevo cada 5 min).
  const incidentId = inc?.incident_id ?? null;
  const png = inc?.superficie.png_base64 ?? null;
  const uri = useMemo(
    () => (incidentId !== null && png !== null ? pngEnDisco(incidentId, png) : null),
    [incidentId, png],
  );
  const pinta = uri !== null && esquinas !== null;
  const sitio: [number, number] = [mapa.sitio.lon, mapa.sitio.lat];

  return (
    <View style={styles.pantalla}>
      <Map
        androidView="texture"
        attribution={false}
        compass={false}
        logo={false}
        mapStyle={ESTILO_BASE}
        style={styles.mapa}
        testID="mapa-sismos"
      >
        <Camera initialViewState={{ center: sitio, zoom: ZOOM_INICIAL }} />
        {uri !== null && esquinas !== null ? (
          <ImageSource coordinates={esquinas} id="superficie" url={uri}>
            <Layer id="superficie" paint={{ "raster-opacity": 0.6 }} type="raster" />
          </ImageSource>
        ) : null}
        <GeoJSONSource data={puntos} id="sismos">
          <Layer
            id="sismos"
            paint={{
              "circle-radius": ["get", "radio"],
              "circle-color": ["get", "color"],
              "circle-stroke-width": 1,
              "circle-stroke-color": palette.bg,
            }}
            type="circle"
          />
        </GeoJSONSource>
        <GeoJSONSource data={{ type: "Point", coordinates: sitio }} id="inmueble">
          <Layer
            id="inmueble"
            paint={{
              "circle-radius": 7,
              "circle-color": palette.fg,
              "circle-stroke-width": 3,
              "circle-stroke-color": palette.cyan,
            }}
            type="circle"
          />
        </GeoJSONSource>
      </Map>

      <View pointerEvents="none" style={styles.leyenda} testID="mapa-leyenda">
        <Text style={styles.eyebrow}>SISMOS DE MÉXICO · ◉ SU INMUEBLE</Text>
        <Text style={styles.texto}>{LEYENDA_ESCALA}</Text>
        {inc ? (
          <>
            <Text style={styles.eyebrow} testID="mapa-calor-titulo">
              MAPA DE CALOR · {fechaLocal(inc.opened_at)}
            </Text>
            <Text style={styles.texto} testID="mapa-calor-rotulo">
              {rotuloEstimado(inc.superficie)}
            </Text>
            {pinta ? null : (
              <Text style={styles.aviso} testID="mapa-calor-sin-pintar">
                No se pudo dibujar la superficie de este evento.
              </Text>
            )}
          </>
        ) : (
          <Text style={styles.texto} testID="mapa-calor-sin-evento">
            {SIN_MAPA_DE_CALOR}
          </Text>
        )}
      </View>

      <View pointerEvents="none" style={styles.pie} testID="mapa-atribucion">
        {pieDelMapa(sismos.atribucion).map((linea) => (
          <Text key={linea} style={styles.pieTexto}>
            {linea}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pantalla: { flex: 1, backgroundColor: palette.bg },
  mapa: { flex: 1 },
  leyenda: {
    position: "absolute",
    // 64 = TAB_SCREEN_TOP_RESERVE: la franja de avisos del sitio solapa esa banda.
    top: 64,
    left: space[3],
    right: space[3],
    padding: space[3],
    gap: space[1],
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: 8,
  },
  eyebrow: { color: palette.fg2, fontSize: fontSize.xs, letterSpacing: 1.5 },
  texto: { color: palette.fg3, fontSize: fontSize.xs },
  aviso: { color: palette.warn, fontSize: fontSize.xs },
  pie: {
    position: "absolute",
    bottom: space[2],
    left: space[3],
    right: space[3],
    padding: space[1],
    backgroundColor: palette.card,
    borderRadius: 4,
  },
  pieTexto: { color: palette.fg3, fontSize: fontSize.xs },
});
