// [T-7.24] EL MAPA DE LA SACUDIDA, en la consola: lo MEDIDO, lo MODELADO y el
// residuo entre los dos.
//
// Todo lo de este fichero es PURO: recibe el snapshot que calculó el worker
// (`GET /incidents/{id}/shakemap`) y devuelve rasgos listos para MapLibre. No
// calcula sacudida ninguna — si lo hiciera, la consola y el PDF del dictamen
// dibujarían cada uno su versión del mismo sismo, que es el modo de fallo que
// este repositorio lleva una fase cerrando (`shakemap/lectura.py`).
//
// LAS TRES REGLAS QUE GOBIERNAN ESTE MÓDULO
// ─────────────────────────────────────────
// 1. **Con procedencia, o no se pinta** (`shared/glossary/procedencia.json`).
//    La procedencia viaja EN CADA RASGO y no en el nombre de la capa que lo
//    lleva: quien mezcle features no puede perderla por el camino. Un rasgo que
//    llegue sin ella no se dibuja, y se cuenta para poder declararlo.
// 2. **Jamás la misma codificación visual para lo medido y lo modelado**
//    (`D-08` · `design/BLOQUE-IV-ARQUITECTURA.md §A.3`). Medido = disco relleno
//    con su valor; modelado = anillo geográfico de trazo discontinuo.
// 3. **Nada con significado físico se dibuja en unidades de pantalla.** Es la
//    lección que costó la guarda `DIF-shakemap.a`: aquí vivían dos capas
//    `circle` con `circle-radius` de 55 y 100 PÍXELES rotuladas «INTENSIDAD
//    MMI», así que el mismo anillo afirmaba ~22 km a zoom 8.5 y ~1 km a zoom 13
//    — la banda cambiaba de significado físico con cada rueda del ratón. Los
//    anillos de este módulo son POLÍGONOS en grados, ya materializados por el
//    lector. El disco de un punto medido sí vive en píxeles y es constante:
//    un marcador no afirma extensión, afirma un valor EN ESE PUNTO.
//
// Y NO hay escala de intensidad. `dictamen/model.py::NO_MMI` está impreso en
// documentos FIRMADOS diciendo que TAKAB no reporta intensidad macrosísmica ni
// isosistas; derivar una MMI de la PGA de un sensor volvería falsa una frase ya
// firmada (la familia de defectos de `T-7.34`/`T-7.38`/`T-7.39`). Lo que se
// codifica es PGA en g, que es lo que se mide — y por eso los tokens se llaman
// `--tk-pga-*` y no `--tk-mmi-*`.

import { cssVariables } from "@takab/design-tokens";

import { kmToPixels } from "./wavefront";

/* =====================================================================
   EL CONTRATO — UNA sola verdad sobre el cable
   ===================================================================== */

// Estos tipos NO se escriben aquí: se re-exportan de `@takab/sdk`, que los
// genera del OpenAPI que publica `api/src/takab_api/schemas/shakemap.py`.
//
// ⚠️ Nacieron como espejo a mano —el endpoint no estaba en el contrato
// todavía— y el censo `web/src/sdkTypeParity.test.ts` (`T-2.82.b`) los cazó en
// cuanto `make drift` publicó los de verdad. Su mensaje es la regla: «no la
// corrijas copiando campos: importa el tipo generado para que haya UNA sola
// verdad sobre el cable». Y el espejo YA había divergido: al generado le había
// salido `fuera_de_alcance` —los niveles del modelo que quedan más allá del
// alcance acreditado de la ley— y la copia a mano no lo tenía, así que la
// consola no podía ni saber que existía.
//
// `PuntoFeature`/`AnilloFeature` se derivan del propio tipo generado en vez de
// re-escribir la forma del GeoJSON: así un cambio en el esquema llega aquí por
// el compilador y no por una lectura atenta.

import type {
  AnilloProps,
  AnillosOut,
  EpicentroOut,
  PuntoProps,
  PuntosOut,
  ShakemapOut,
} from "@takab/sdk";

export type { AnilloProps, AnillosOut, EpicentroOut, PuntoProps, PuntosOut, ShakemapOut };

export type Procedencia = "measured" | "modeled";

export type PuntoFeature = PuntosOut["features"][number];
export type AnilloFeature = AnillosOut["features"][number];

/* =====================================================================
   VOCABULARIO CERRADO — espejo de `api/src/takab_api/shakemap/calculo.py`
   ===================================================================== */

/** Epicentro y magnitud citados, y al menos un inmueble midió: las tres capas. */
export const ESTADO_COMPLETO = "completo";
/** Hay medidas y no hay epicentro/magnitud: el mapa existe DEGRADADO y lo dice. */
export const ESTADO_SOLO_OBSERVADO = "solo_observado";
/** Ningún inmueble instrumentado midió en la ventana. */
export const ESTADO_SIN_DATOS = "sin_datos";
/** El worker aún no pasó. Lo pone el LECTOR, nunca el cálculo. */
export const ESTADO_PENDIENTE = "pendiente";

/** Los cuatro que esta consola sabe leer. Uno nuevo se DECLARA, no se adivina. */
export const ESTADOS = [
  ESTADO_COMPLETO,
  ESTADO_SOLO_OBSERVADO,
  ESTADO_SIN_DATOS,
  ESTADO_PENDIENTE,
] as const;

export const PROC_MEDIDO = "measured";
export const PROC_MODELADO = "modeled";

// Los niveles de los anillos son los umbrales con que ESTE sistema ya decide —la
// banda del inmueble—, no una escala inventada. Sus VALORES no se escriben aquí:
// llegan en cada anillo, sacados del `rule_set` que regía en la apertura del
// incidente.
export const UMBRAL_WATCH = "pga_watch_g";
export const UMBRAL_TRIP = "pga_trip_g";

/**
 * Los que la nube PUBLICA hoy — espejo del `UMBRALES` de `shakemap/calculo.py`,
 * que a su vez los deriva de los campos en `_g` de `felt.Thresholds`.
 *
 * No es azúcar: es lo único que una guarda puede CRUZAR contra el otro lado de
 * la costura. Estos nombres están escritos a mano aquí y otra vez en la nube, y
 * si la nube renombrara uno, `colorDeBanda` mandaría todos los anillos y todos
 * los puntos a `PGA_SIN_BANDA` —el mapa entero gris— mientras la leyenda sigue
 * rotulando tan tranquila el nombre nuevo, porque lo cita del propio rasgo.
 * Ninguna de las dos suites se enteraría: cada una fabrica sus propias cadenas.
 * Lo cruza `shakemapCostura.test.ts` leyendo los dos ficheros.
 */
export const UMBRALES = [UMBRAL_WATCH, UMBRAL_TRIP] as const;

// ⚠️ Y aquí NO hay lista de umbrales «heredados». La hubo: eximía a
// `correlacion_min_pga_g` —retirado del cálculo el 2026-09-21 porque como nivel
// de mapa producía anillos de miles de km— alegando que «los snapshots ya
// persistidos siguen trayendo ese anillo». No existen esos snapshots, medido:
// `git grep -n correlacion_min_pga_g HEAD` → vacío y `git grep -l -i shakemap
// HEAD -- api/migrations db/` → 0 ficheros, porque la tabla `incident_shakemap`
// nace en la migración `0069_mapa_de_sacudida.py`, de este mismo cambio. Era una
// herencia inventada, y su único efecto real era ensanchar el escape de la
// guarda de costura. El día que haya una herencia de verdad se declarará con su
// medición al lado; hasta entonces esto es default-deny sin excepciones.

/**
 * LA ESCALA DE PGA, en tokens.
 *
 * Vale HOY lo mismo que la escala de estado de la consola (`--tk-status-*`) y es
 * a propósito: lo medido y lo modelado se comparan a ojo con los puntos del
 * wall, y dos escalas de color para los MISMOS umbrales harían esa comparación
 * imposible. Lo que cambia entre medido y modelado es la FORMA, nunca el color
 * (`§A.3`). Tienen nombre propio porque significan otra cosa —PGA en g, no la
 * severidad de un incidente—, así que repintar una no repinta la otra; el mismo
 * argumento que separó `--tk-brand` de `--tk-cyan` en `T-6.15`.
 *
 * Se leen por TS y no con `var()` porque **MapLibre no resuelve variables CSS
 * dentro de un `paint`**: allí una `var(--tk-pga-trip)` es una cadena que el
 * motor rechaza (patrón de `SevTag.tsx`).
 */
export const PGA_COLOR: Record<string, string> = {
  [UMBRAL_WATCH]: cssVariables["--tk-pga-watch"],
  [UMBRAL_TRIP]: cssVariables["--tk-pga-trip"],
};

/** Tinta de lo que NO tiene banda que afirmar (sin medida, o umbral desconocido). */
export const PGA_SIN_BANDA = cssVariables["--tk-pga-sin-banda"];

/**
 * Tinta de `SIN COBERTURA`, que **no es un estado del mapa sino del ESPACIO**:
 * fuera del radio de representatividad de todo inmueble instrumentado. Lo
 * declara quien pinta, y no se extrapola color hacia allí.
 */
export const PGA_SIN_COBERTURA = cssVariables["--tk-pga-sin-cobertura"];

/* =====================================================================
   BUILDERS PUROS
   ===================================================================== */

export interface Nivel {
  umbral: string;
  pga_g: number;
}

/** Los umbrales citados por ESTE incidente, derivados de sus propios anillos. */
export function nivelesDe(mapa: ShakemapOut | undefined): Nivel[] {
  return (mapa?.modelado?.features ?? [])
    .filter((f) => f.properties.procedencia === PROC_MODELADO)
    .map((f) => ({ umbral: f.properties.umbral, pga_g: f.properties.pga_g }))
    .sort((a, b) => a.pga_g - b.pga_g);
}

/**
 * La banda de una medida: el umbral MÁS ALTO que alcanza, o `null`.
 *
 * `null` cubre tres cosas distintas que comparten tinta y **jamás rótulo**: sin
 * medida (el gabinete no publicó), por debajo del umbral más bajo citado, y sin
 * umbrales citados —el caso `solo_observado`, donde no hay anillos porque no hay
 * epicentro—. Bandear ahí con números de fábrica es el defecto que cerró
 * `T-7.35`: un umbral de fábrica presentado como el del edificio.
 */
export function bandaDe(pga_g: number | null, niveles: Nivel[]): string | null {
  if (pga_g === null || niveles.length === 0) return null;
  let banda: string | null = null;
  for (const nivel of niveles) {
    if (pga_g >= nivel.pga_g) banda = nivel.umbral;
  }
  return banda;
}

/** El color de una banda. Un umbral desconocido NO hereda el color de otro. */
export function colorDeBanda(umbral: string | null): string {
  if (umbral === null) return PGA_SIN_BANDA;
  return PGA_COLOR[umbral] ?? PGA_SIN_BANDA;
}

/**
 * El rótulo de un punto MEDIDO: su valor y, si se pudo comparar, su residuo.
 *
 * El residuo se escribe en VECES y no en logaritmos (`×2.0`, no `+0.31 log10`):
 * quien mira este mapa decide si evacúa un edificio, no publica un paper. El
 * logaritmo sigue viajando en el dato para quien lo quiera.
 */
export function etiquetaDeMedida(p: PuntoProps): string {
  if (p.pga_g === null) return "SIN MEDIDA EN LA VENTANA";
  const valor = `${p.pga_g.toFixed(3)} g`;
  if (p.residuo_log10 === null) return valor;
  return `${valor} · ×${Math.pow(10, p.residuo_log10).toFixed(1)}`;
}

/** El rótulo de un anillo. Dice MODELO en el mapa, no solo en la leyenda. */
export function etiquetaDeAnillo(a: AnilloProps): string {
  return `MODELO · ${a.pga_g.toFixed(3)} g`;
}

interface FeatureCollection<G, P> {
  type: "FeatureCollection";
  features: Array<{ type: "Feature"; geometry: G; properties: P }>;
}

export type PuntoPintado = PuntoProps & {
  /** `false` = no hay valor: el disco se pinta HUECO y el rótulo lo dice. */
  medido: boolean;
  banda: string | null;
  color: string;
  label: string;
};

export type AnilloPintado = AnilloProps & { color: string; label: string };

/** Capa 1+3: un disco por inmueble instrumentado, con su valor y su residuo. */
export function observadoFeatureCollection(
  mapa: ShakemapOut | undefined,
): FeatureCollection<PuntoFeature["geometry"], PuntoPintado> {
  const niveles = nivelesDe(mapa);
  return {
    type: "FeatureCollection",
    features: (mapa?.observado.features ?? [])
      // Default-deny: la lista no es la procedencia. Un punto sin ella no se
      // pinta como medido sólo porque venía en la colección de medidos.
      .filter((f) => f.properties.procedencia === PROC_MEDIDO)
      .map((f) => {
        const banda = bandaDe(f.properties.pga_g, niveles);
        return {
          type: "Feature" as const,
          geometry: f.geometry,
          properties: {
            ...f.properties,
            medido: f.properties.pga_g !== null,
            banda,
            color: colorDeBanda(banda),
            label: etiquetaDeMedida(f.properties),
          },
        };
      }),
  };
}

/** Capa 2: anillos de PGA constante, en GRADOS. Nunca en píxeles. */
export function modeladoFeatureCollection(
  mapa: ShakemapOut | undefined,
): FeatureCollection<AnilloFeature["geometry"], AnilloPintado> {
  return {
    type: "FeatureCollection",
    features: (mapa?.modelado?.features ?? [])
      .filter((f) => f.properties.procedencia === PROC_MODELADO)
      .map((f) => ({
        type: "Feature" as const,
        geometry: f.geometry,
        properties: {
          ...f.properties,
          color: colorDeBanda(f.properties.umbral),
          label: etiquetaDeAnillo(f.properties),
        },
      })),
  };
}

export type CoberturaProps = {
  site_id: string;
  site_code: string;
  cobertura_km: number;
  /** Radio de PANTALLA de un radio FÍSICO, al zoom actual. Se rehace en `zoomend`. */
  radius_px: number;
};

/**
 * Capa 4: hasta dónde llega lo MEDIDO. El borde de la cobertura, no su relleno.
 *
 * Existe porque la leyenda declaraba una tinta de `SIN COBERTURA` que NINGUNA
 * capa usaba: una clave de color prometía que el mapa distingue «fuera del
 * radio de representatividad» y el mapa no lo distinguía en ninguna parte —
 * estructuralmente, el mismo defecto de la leyenda MMI que `T-7.24` vino a
 * cerrar. O se pinta o no se promete; aquí se pinta.
 *
 * Qué afirma: dentro de este círculo hay una medida real que habla del suelo;
 * fuera, sólo hay modelo y NO se extrapola color. Por eso el círculo se dibuja
 * alrededor de los inmuebles que **midieron de verdad** (`medido`): uno que no
 * publicó nada no da cobertura ninguna, y rodearlo de un halo diría que sí.
 *
 * ⚠️ El radio es FÍSICO (`cobertura_km` del propio snapshot) y por eso se
 * convierte a píxeles con el zoom y se rehace en `zoomend`, igual que los
 * anillos quietos de `T-2.47`. Un `circle-radius` constante aquí sería otra vez
 * el pecado de `DIF-shakemap.a`: el mismo halo afirmando 25 km a un zoom y 1 km
 * a otro.
 */
export function coberturaFeatureCollection(
  mapa: ShakemapOut | undefined,
  zoom: number,
): FeatureCollection<PuntoFeature["geometry"], CoberturaProps> {
  return {
    type: "FeatureCollection",
    features: observadoFeatureCollection(mapa)
      .features.filter((f) => f.properties.medido)
      .map((f) => ({
        type: "Feature" as const,
        geometry: f.geometry,
        properties: {
          site_id: f.properties.site_id,
          site_code: f.properties.site_code,
          cobertura_km: mapa?.cobertura_km ?? 0,
          radius_px: kmToPixels(mapa?.cobertura_km ?? 0, f.geometry.coordinates[1], zoom),
        },
      })),
  };
}

/**
 * Cuántos rasgos se descartaron por no traer la procedencia de su capa.
 *
 * Descartar en silencio sería cambiar un dato sospechoso por una pantalla
 * tranquila. Se cuenta para que la leyenda pueda decir cuántos y por qué.
 */
export function sinProcedencia(mapa: ShakemapOut | undefined): number {
  if (mapa === undefined) return 0;
  const puntos = mapa.observado.features.filter((f) => f.properties.procedencia !== PROC_MEDIDO);
  const anillos = (mapa.modelado?.features ?? []).filter(
    (f) => f.properties.procedencia !== PROC_MODELADO,
  );
  return puntos.length + anillos.length;
}

export interface VistaSacudida {
  /** El estado tal como lo declaró el lector (`""` si no hay mapa). */
  estado: string;
  /**
   * El snapshot se pudo LEER: llegó, y su estado es uno de los cuatro que esta
   * consola sabe interpretar.
   *
   * De aquí cuelga todo lo que AFIRMA algo sobre el snapshot como conjunto —la
   * hora del cálculo, por ejemplo—. Fechar un mapa que se acaba de declarar
   * ilegible lo presenta como un mapa válido y reciente, que es exactamente la
   * mentira que la nota de arriba acaba de desmentir.
   */
  legible: boolean;
  /** Qué se puede pintar. Se DERIVA del dato, no del rótulo del estado. */
  pintaObservado: boolean;
  pintaModelado: boolean;
  /** Lo que la leyenda tiene que declarar, y con qué `data-testid`. */
  nota: string | null;
  notaTestId: string | null;
}

/**
 * Qué se pinta y qué se DECLARA (regla de oro 7).
 *
 * El orden de las ramas no es libre, y es el mismo razonamiento de
 * `dictamen/builder.py::_linea_sin_acierto`: lo que no se sabe leer sale por su
 * propia rama ANTES de que un `else` acogedor lo convierta en el caso más
 * tranquilizador. Aquí el caso tranquilizador sería «completo», o sea un mapa
 * que se presenta como bueno.
 */
export function vistaSacudida(
  mapa: ShakemapOut | undefined,
  error: boolean,
  cargando = false,
): VistaSacudida {
  const vacia: VistaSacudida = {
    estado: mapa?.estado ?? "",
    legible: false,
    pintaObservado: false,
    pintaModelado: false,
    nota: null,
    notaTestId: null,
  };

  // El error va primero: un fallo de la consulta NO puede leerse como «no hay
  // datos», que es la confusión que este repositorio nombra en cada superficie.
  if (error) {
    return { ...vacia, nota: "MAPA DE SACUDIDA NO DISPONIBLE", notaTestId: "shakemap-error" };
  }
  // CONSULTANDO no es «no hay»: son los dos estados que la regla de oro 7
  // obliga a separar. Sin esta rama, el hueco entre la petición y la respuesta
  // se ve exactamente igual que un incidente sin mapa.
  if (cargando && mapa === undefined) {
    return {
      ...vacia,
      nota: "CONSULTANDO EL MAPA DE LA SACUDIDA",
      notaTestId: "shakemap-cargando",
    };
  }
  if (mapa === undefined) return vacia;

  if (!(ESTADOS as readonly string[]).includes(mapa.estado)) {
    return {
      ...vacia,
      nota: `ESTADO DEL MAPA NO INTERPRETABLE · «${mapa.estado}»`,
      notaTestId: "shakemap-no-interpretable",
    };
  }

  const legible: VistaSacudida = { ...vacia, legible: true };

  if (mapa.estado === ESTADO_PENDIENTE) {
    return {
      ...legible,
      nota: "MAPA EN CÁLCULO · ESTE INCIDENTE AÚN NO TIENE SNAPSHOT",
      notaTestId: "shakemap-pendiente",
    };
  }

  const puntos = observadoFeatureCollection(mapa).features;
  const hayPuntos = puntos.length > 0;
  // ⚠️ UN PUNTO NO ES UNA MEDIDA, y confundirlos costó una falsa alarma en la
  // pantalla del SOC. La nube emite un `Punto` por cada inmueble instrumentado
  // con coordenadas, midiera o no: `servicio.py::_medidas_de` no filtra por
  // `peak_pga_g` y `calculo.py::calcula` hace `tuple(_punto(m, …) for m in
  // medidas)`. Lo que dice si alguien midió es `medido` (`pga_g !== null`), y
  // es lo único con lo que se puede contar medidas o afirmar que las hay.
  const medidas = puntos.filter((p) => p.properties.medido).length;
  const hayAnillos = modeladoFeatureCollection(mapa).features.length > 0;

  if (mapa.estado === ESTADO_SIN_DATOS) {
    // El modelo sí se pinta si lo hay —está rotulado como modelo en cada
    // anillo—, pero lo que manda es que NADIE MIDIÓ: un mapa de puro modelo no
    // es un mapa de la sacudida, y callarlo lo haría pasar por uno.
    //
    // ⚠️ «Nadie midió» es una afirmación sobre el DATO, así que se comprueba
    // contra el dato. El rótulo decía `sin_datos` y la colección traía una
    // medida de 0.31 g: se borraba el punto de la pantalla y se escribía
    // «NINGÚN INMUEBLE INSTRUMENTADO MIDIÓ EN LA VENTANA» encima. Eso no es
    // declarar una ausencia, es fabricarla. Cuando el rótulo y la colección
    // discrepan se pinta lo que HAY y se declara la discrepancia: el rótulo lo
    // escribió un worker, la medida la escribió un acelerómetro.
    //
    // ⚠️⚠️ Pero la discrepancia se gatea con las MEDIDAS y no con los puntos.
    // Gateada con `puntos.length` acusaba de contradecirse al único `sin_datos`
    // que esta nube sabe emitir —el que viaja con un punto mudo por inmueble—:
    // imprimía «TRAE 2 MEDIDA(S) · SE PINTA LO MEDIDO» con cero medidas, dos
    // discos sin valor bajo una leyenda que promete «DISCO CON SU VALOR», una
    // fila de `SIN COBERTURA` sin un solo halo… y **tapaba la nota correcta**,
    // que es justo la que el operador necesita leer. Una defensa contra un
    // snapshot corrupto que dispara siempre no es una defensa: es una alarma
    // falsa, y ésta es la ficha que lleva dos vueltas cazándolas en el papel.
    // Lo cruza contra la nube `shakemapCostura.test.ts`.
    if (medidas > 0) {
      return {
        ...legible,
        pintaObservado: true,
        pintaModelado: hayAnillos,
        nota: `EL SNAPSHOT SE DECLARA «SIN DATOS» Y TRAE ${medidas} MEDIDA(S) · SE PINTA LO MEDIDO`,
        notaTestId: "shakemap-sin-datos-discrepa",
      };
    }
    return {
      ...legible,
      pintaModelado: hayAnillos,
      // Y la CAUSA sale del dato, como en la rama de abajo: «los hay y ninguno
      // publicó» manda a revisar dos gabinetes; «no hay ninguno» no manda a
      // revisar nada. Colapsarlas en una frase le da al operador la tarea
      // equivocada.
      nota: hayPuntos
        ? `NINGUNO DE LOS ${puntos.length} INMUEBLES INSTRUMENTADOS MIDIÓ EN LA VENTANA`
        : "SIN INMUEBLES INSTRUMENTADOS EN ESTE SNAPSHOT",
      notaTestId: "shakemap-sin-datos",
    };
  }

  if (!hayAnillos) {
    // El HECHO (no se modela) sale del dato; la CAUSA también tiene que salir
    // del dato. Esta rama afirmaba «SIN EPICENTRO NI MAGNITUD CITADOS» sobre un
    // snapshot con epicentro SSN confirmado y M7.1 — una causa inventada para
    // un hecho cierto, que es la familia de `T-7.34`/`T-7.38`/`T-7.39` (el papel
    // que se desmiente a sí mismo) trasladada a la pantalla.
    const sinEpicentro = mapa.epicentro === null || mapa.epicentro.magnitud === null;
    if (sinEpicentro) {
      return {
        ...legible,
        pintaObservado: hayPuntos,
        nota: "SIN EPICENTRO NI MAGNITUD CITADOS · NO SE MODELA LA SACUDIDA",
        notaTestId: "shakemap-sin-modelo",
      };
    }
    return {
      ...legible,
      pintaObservado: hayPuntos,
      nota: "NO SE MODELA LA SACUDIDA · HAY EPICENTRO Y MAGNITUD CITADOS Y EL SNAPSHOT NO TRAE ANILLOS",
      notaTestId: "shakemap-sin-anillos",
    };
  }

  return { ...legible, pintaObservado: hayPuntos, pintaModelado: true };
}
