// Resumen post-evento (T-2.40), calcado del "Post-ShakeAlert Message Summary" de USGS.
//
// Tras cada sismo relevante, USGS publica un post-mortem estandarizado: qué tan lejos
// quedó el epicentro estimado, qué tan lejos la magnitud, cuánto tiempo de aviso hubo
// y cuántas estaciones contribuyeron. Es el documento que convierte "el sistema
// funcionó" en una afirmación verificable — y el que una Protección Civil pide cuando
// evalúa si el servicio vale lo que cuesta.
//
// Los cuatro números salen de `/forensics`. Cuando alguno no se puede calcular se dice
// POR QUÉ: un "0 s de aviso" sin explicación se lee como un fallo del sistema, cuando
// casi siempre significa que ese incidente ni siquiera vino de SASMEX.

import Card from "../../components/Card";
import StateFrame from "../../components/StateFrame";
import type { ForensicsOut } from "@takab/sdk";
import type { ForensicsState } from "./useForensics";
import {
  citaDeProcedencia,
  esEstadoConocido,
  pintaCifra,
  rotuloProcedencia,
  significadoProcedencia,
} from "./procedencia";

const LEAD_REASON: Record<string, string> = {
  not_sasmex: "NO APLICA · el incidente no vino de SASMEX",
  no_peak: "SIN PICO MEDIDO EN LA VENTANA",
  peak_before_alert: "EL PICO PRECEDIÓ A LA ALERTA",
};

function Tile({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "ok" | "warn" | "idle";
}) {
  return (
    <div className={`postevent__tile${tone ? ` postevent__tile--${tone}` : ""}`}>
      <div className="postevent__lbl">{label}</div>
      <div className="postevent__val">{value}</div>
      {note && <div className="postevent__note">{note}</div>}
    </div>
  );
}

export function leadTimeView(f: ForensicsOut): {
  value: string;
  note?: string;
  tone: "ok" | "idle";
} {
  if (f.lead_time_s === null || f.lead_time_s === undefined) {
    return {
      value: "NO CALCULABLE",
      note: LEAD_REASON[f.lead_time_reason ?? ""] ?? f.lead_time_reason ?? undefined,
      tone: "idle",
    };
  }
  return { value: `${f.lead_time_s.toFixed(1)} s`, tone: "ok" };
}

type Correlacion = NonNullable<ForensicsOut["catalog_correlation"]>;

/**
 * [T-7.25 · consola] LO QUE HAY EN EL CATÁLOGO CUANDO NO HAY ACIERTO: cinco
 * hechos, y hasta esta ficha se pintaban todos como el más comprometido.
 *
 *     (a) no se preguntó              →  el estado del glosario, y punto
 *     (b) se preguntó, no contestaron →  con a quién y a qué hora
 *     (c) contestaron, ninguno casa   →  SIN CORRELACIÓN EN EL CATÁLOGO
 *     (d) correlacionó · preliminar   →  CORRELACIÓN EN DISPUTA
 *     (e) correlacionó · confirmado   →  CORRELACIÓN EN DISPUTA
 *
 * (c) es una afirmación **sobre el sismo**: exonera al catálogo de referencia.
 * Pintarla en (a) o en (b) es dar por concluido lo que nadie concluyó — y (a) es
 * el caso NORMAL, porque la consulta automática se despliega apagada, así que el
 * operador leía esa conclusión en todos los incidentes. Es el mismo defecto que
 * `dictamen/builder.py::_linea_sin_acierto` cerró en el papel; el papel dejó de
 * mentir en T-7.25 y la pantalla seguía mintiendo.
 *
 * (d) y (e) comparten frase y se separan por el rótulo del glosario, que va en
 * la nota: una solución que la propia fuente declara PRELIMINAR puede cambiar
 * mañana, y discrepar de ella no es lo mismo que discrepar de una ya revisada.
 *
 * **Las ramas se DERIVAN del glosario**, no se enumeran: el rótulo sale de
 * `rotuloProcedencia`, la explicación de `significadoProcedencia` y la disputa
 * de `pintaCifra` —los dos estados que autorizan una cifra externa son
 * exactamente los que pueden haber correlacionado—. Un sexto estado en
 * `shared/glossary/procedencia.json` no hereda la afirmación más cara del
 * bloque: sale por la rama de lo no interpretable, que DECLARA la ignorancia en
 * vez de exonerar.
 */
export function sinAciertoView(corr: Correlacion | null | undefined): {
  value: string;
  note?: string;
} {
  // Los descartes son del catálogo YA CARGADO en la base, y eso no cierra la
  // pregunta a la fuente viva: se dicen siempre, pero DETRÁS del hecho que manda.
  const descartes = corr?.descartes ?? [];
  const cargado =
    descartes.length === 0
      ? ""
      : ` En el catálogo ya cargado había ${descartes.length} evento(s) en la ventana y ` +
        `ninguno es éste: ` +
        descartes
          .slice(0, 2)
          .map((d) => `${d.catalog_key} — ${d.detalle}`)
          .join(" · ");

  // Sin correlación PUBLICADA no se sabe siquiera si se preguntó. No es (c): es
  // que este incidente no trae la consulta, y decir otra cosa sería inventarla.
  if (!corr) {
    return {
      value: "SIN CONSULTA REGISTRADA",
      note: `Este incidente no publica correlación con el catálogo: no se afirma nada sobre él.${cargado}`,
    };
  }

  if (!esEstadoConocido(corr.estado)) {
    return {
      value: "ESTADO NO INTERPRETABLE",
      note: `Esta consola no sabe traducir el estado «${corr.estado}»: no se afirma nada sobre el catálogo.${cargado}`,
    };
  }

  const cita = citaDeProcedencia(corr.fuente, corr.consultado_en);
  const quien = cita === null ? "" : ` ${cita}.`;
  const significa = significadoProcedencia(corr.estado) ?? "";

  if (pintaCifra(corr.estado)) {
    // La consulta correlacionó y el criterio de identidad de T-5.11 —más
    // estricto que la ventana de la consulta— no reconoce el acierto. Que los
    // dos procedimientos discrepen no es un fallo de ninguno; lo que no puede
    // pasar es que la pantalla elija el desenlace más tranquilizador.
    return {
      value: "CORRELACIÓN EN DISPUTA",
      note:
        `La consulta correlacionó y el criterio de identidad no reconoce el acierto. ` +
        `${significa} La fuente la declara ${rotuloProcedencia(corr.estado)}.${quien}${cargado}`,
    };
  }

  return { value: rotuloProcedencia(corr.estado), note: `${significa}${quien}${cargado}` };
}

/**
 * La correlación con el catálogo de referencia.
 *
 * [T-5.11] Antes decía `SIN COINCIDENCIA · Ningún sismo del catálogo dentro de
 * ±120 s`, y ese ±120 s era **todo** el criterio: bastaba caer en la ventana
 * para que un sismo de otro continente se presentara como el nuestro. Ahora hay
 * un criterio de identidad (ventana consciente de la distancia, radio al sitio y
 * coherencia magnitud/distancia) y esta vista tiene que distinguir **tres cosas
 * que antes se pintaban igual**:
 *
 * 1. Casó y hay epicentro propio ⇒ es un CONTRASTE de verdad.
 * 2. Casó y no hay epicentro propio —la ruta del receptor, la normal⇒ la
 *    identidad se estableció pero **no hay nada nuestro que contrastar**, y
 *    llamarlo contraste prometería una verificación que no ocurrió.
 * 3. No casó **habiendo candidatos** ⇒ «hay un evento en el catálogo pero no es
 *    el nuestro», que es lo que el sistema no sabía decir. Un hueco aquí se lee
 *    como «no pasó nada», que es justo lo contrario.
 */
export function catalogView(f: ForensicsOut): { value: string; note?: string } {
  const corr = f.catalog_correlation;
  // Sin acierto no hay UN caso sino CINCO, y los separa `sinAciertoView`.
  if (!f.catalog || !f.catalog_delta) return sinAciertoView(corr);
  const d = f.catalog_delta;
  // [T-5.10] La cifra externa solo se pinta con procedencia. Casar no la concede.
  const mag =
    f.catalog.magnitude !== null &&
    f.catalog.magnitude !== undefined &&
    corr !== null &&
    corr !== undefined &&
    pintaCifra(corr.estado)
      ? ` · M ${f.catalog.magnitude.toFixed(1)}`
      : "";
  const cita = `${f.catalog.source} ${f.catalog.catalog_key}${mag} · Δt ${d.dt_s.toFixed(0)} s`;

  if (d.km === null || d.km === undefined) {
    const alSitio =
      f.catalog.km_al_sitio !== null && f.catalog.km_al_sitio !== undefined
        ? `${Math.round(f.catalog.km_al_sitio)} km del sitio`
        : "distancia al sitio no calculable";
    return {
      value: "NO VERIFICABLE",
      note: `${cita} · ${alSitio} · sin epicentro propio que contrastar.`,
    };
  }
  return { value: `${Math.round(d.km)} km ${d.bearing ?? ""}`.trim(), note: cita };
}

export default function PostEventSummary({ forensics }: { forensics: ForensicsState }) {
  const f = forensics.data;
  return (
    <Card
      title="Resumen post-evento"
      sub="DESEMPEÑO DE LA RED · CORRELACIÓN CON EL CATÁLOGO DE REFERENCIA"
      className="postevent"
      testId="post-event-summary"
    >
      <StateFrame
        label="RESUMEN POST-EVENTO"
        loading={forensics.loading}
        error={forensics.error}
        onRetry={forensics.refetch}
        empty={f !== undefined && (f.channels ?? []).length === 0 && (f.station_count ?? 0) === 0}
        emptyText="SIN MEDICIONES NI VOTOS PARA ESTE INCIDENTE"
        // [T-2.82.a] El tiempo de aviso ganado y las estaciones que
        // contribuyeron son los números que se citan como desempeño de la red
        // ante una Protección Civil — y congelados se citan exactamente igual.
        // La edad la resuelve `useForensics` con el reloj de toda la pantalla;
        // aquí sólo se declara.
        staleSince={forensics.staleSince}
      >
        {f && (
          <div className="postevent__grid">
            <Tile
              label="TIEMPO DE AVISO GANADO"
              value={leadTimeView(f).value}
              note={leadTimeView(f).note}
              tone={leadTimeView(f).tone}
            />
            <Tile
              label="ESTACIONES QUE CONTRIBUYERON"
              value={String(f.station_count ?? 0)}
              note={(f.station_count ?? 0) === 0 ? "Sin corroboración multi-estación" : undefined}
              tone={(f.station_count ?? 0) >= 3 ? "ok" : "idle"}
            />
            <Tile
              label="CORRELACIÓN CON CATÁLOGO"
              value={catalogView(f).value}
              note={catalogView(f).note}
            />
            <Tile
              label="PICO MEDIDO"
              value={
                f.peak_pga_g === null || f.peak_pga_g === undefined
                  ? "SIN MEDICIÓN"
                  : `${f.peak_pga_g.toFixed(3)} g`
              }
              // Sin procedencia de calibración el número NO está en gravedades: es un
              // valor relativo, y presentarlo como física sería inventarla.
              note={f.calibrated ? undefined : "UNIDADES RELATIVAS · SENSOR SIN CALIBRAR"}
              tone={f.calibrated ? undefined : "warn"}
            />
          </div>
        )}
      </StateFrame>
    </Card>
  );
}
