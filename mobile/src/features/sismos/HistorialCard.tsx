// [T-9.66 · D-46] HISTORIAL SÍSMICO DEL INMUEBLE, la mitad de la app: los últimos
// cinco eventos de `GET /sites/{id}/historial-sismico`, mezclados por fecha.
//
// DÓNDE VIVE, y por qué en SISMOS y no en INICIO: INICIO es del ocupante y el
// táctico no la tiene; SISMOS la tienen los dos perfiles. Además INICIO es la
// pantalla del ESTADO DE AHORA («¿tengo que hacer algo?»), y un historial de un
// año ahí compite con esa pregunta; en SISMOS es la continuación natural de la
// lista («y de todo esto, ¿qué le llegó a mi edificio?»).
//
// Dos cosas distintas, y la fila lo dice: un INCIDENTE es lo que MIDIÓ el
// gabinete (PGA medida); un SISMO del catálogo es lo que ahí se habría sentido
// (MMI ESTIMADA). Confundirlas es pintar una estimación como medición.
//
// Estados propios (regla de oro 7) y no un `StateFrame`: la tarjeta vive DENTRO
// del marco de la pestaña, y un segundo marco anidado pintaría un segundo
// «SIN CONEXIÓN» a pantalla completa en medio de la lista.
import type { HistorialSismicoOut } from "@takab/sdk";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { Pulsable } from "@/ui/Pulsable";
import { fontSize, palette, radius, space, touch } from "@/ui/theme";
import { timeAgoLabel } from "@/ui/timeAgo";

import { fechaLocal } from "./fecha";
import type { LecturaSismica } from "./useSismos";

export const HISTORIAL_MAX_FILAS = 5;

type Evento = HistorialSismicoOut["eventos"][number];

const SEVERIDAD: Record<string, string> = {
  info: "INFORMATIVO",
  watch: "VIGILANCIA",
  warning: "ADVERTENCIA",
  critical: "CRÍTICO",
};

const ESTADO: Record<string, string> = {
  open: "Abierto",
  acked: "Atendido",
  in_review: "En revisión",
  closed: "Cerrado",
};

const CLASIFICACION: Record<string, string> = {
  real: "Sismo real",
  falso_positivo: "Falso positivo",
  prueba: "Prueba",
  indeterminado: "Indeterminado",
  reproduccion: "Reproducción",
};

function FilaEvento({ evento }: { evento: Evento }) {
  if ("incident_id" in evento) {
    const pga =
      evento.pga_medida_g != null ? `${evento.pga_medida_g.toFixed(3)} g` : "sin dato";
    return (
      <View style={styles.fila} testID="historial-fila">
        <Text style={styles.titulo}>
          INCIDENTE · {SEVERIDAD[evento.severity] ?? evento.severity.toUpperCase()}
        </Text>
        <Text style={styles.detalle}>
          {ESTADO[evento.estado] ?? evento.estado} ·{" "}
          {evento.clasificacion
            ? (CLASIFICACION[evento.clasificacion] ?? evento.clasificacion)
            : "sin clasificar"}
        </Text>
        <Text style={styles.detalle}>PGA medida: {pga}</Text>
        <Text style={styles.fecha}>{fechaLocal(evento.opened_at)}</Text>
      </View>
    );
  }
  return (
    <View style={styles.fila} testID="historial-fila">
      <Text style={styles.titulo}>
        {`M ${evento.magnitude.toFixed(1)} · ${evento.place}`}
      </Text>
      <Text style={styles.detalle}>
        {`MMI estimada: ${evento.mmi_romano} · ${Math.round(evento.dist_km)} km`}
      </Text>
      <Text style={styles.fecha}>{fechaLocal(evento.origin_time)}</Text>
    </View>
  );
}

export function HistorialCard(props: {
  lectura: LecturaSismica<HistorialSismicoOut>;
  nowMs: number;
}) {
  const { data, loading, error, staleSinceMs, refetch } = props.lectura;
  const eventos = (data?.eventos ?? []).slice(0, HISTORIAL_MAX_FILAS);

  let cuerpo: React.ReactNode;
  if (loading) {
    cuerpo = (
      <View style={styles.centro} testID="historial-loading">
        <ActivityIndicator color={palette.cyan} />
      </View>
    );
  } else if (error !== null) {
    cuerpo = (
      <View style={styles.centro} testID="historial-error">
        <Text style={styles.error}>{error}</Text>
        <Pulsable
          accessibilityRole="button"
          onPress={refetch}
          style={styles.reintentar}
          testID="historial-retry"
        >
          <Text style={styles.reintentarTexto}>REINTENTAR</Text>
        </Pulsable>
      </View>
    );
  } else if (eventos.length === 0) {
    cuerpo = (
      <Text style={styles.vacio} testID="historial-empty">
        Este inmueble no registra incidentes ni sismos sentidos en el último año.
      </Text>
    );
  } else {
    const haySismo = eventos.some((e) => !("incident_id" in e));
    cuerpo = (
      <>
        {staleSinceMs !== null ? (
          <Text style={styles.retenido} testID="historial-stale">
            DATOS RETENIDOS · {timeAgoLabel(staleSinceMs, props.nowMs)} · sin conexión
          </Text>
        ) : null}
        {eventos.map((e) => (
          <FilaEvento
            evento={e}
            key={"incident_id" in e ? e.incident_id : `${e.origin_time}·${e.place}`}
          />
        ))}
        {haySismo && data?.atribucion ? (
          <Text style={styles.fecha}>{data.atribucion}</Text>
        ) : null}
      </>
    );
  }

  return (
    <View style={styles.tarjeta} testID="historial-sismico">
      <Text style={styles.eyebrow}>HISTORIAL SÍSMICO DEL INMUEBLE</Text>
      <Text style={styles.sub}>Últimos {HISTORIAL_MAX_FILAS} eventos</Text>
      {cuerpo}
    </View>
  );
}

const styles = StyleSheet.create({
  tarjeta: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
    gap: space[2],
  },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  sub: { color: palette.fg3, fontSize: fontSize.xs },
  fila: {
    borderTopColor: palette.border,
    borderTopWidth: 1,
    paddingTop: space[2],
    gap: 2,
  },
  titulo: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  detalle: { color: palette.fg2, fontSize: fontSize.xs },
  fecha: { color: palette.fg3, fontSize: fontSize.xs },
  centro: { alignItems: "center", gap: space[2], paddingVertical: space[2] },
  error: { color: palette.warn, fontSize: fontSize.sm, textAlign: "center" },
  reintentar: {
    minHeight: touch.min,
    justifyContent: "center",
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space[4],
  },
  reintentarTexto: { color: palette.cyan, fontSize: fontSize.sm, fontWeight: "700" },
  vacio: { color: palette.fg3, fontSize: fontSize.sm },
  retenido: { color: palette.warn, fontSize: fontSize.xs, letterSpacing: 1 },
});
