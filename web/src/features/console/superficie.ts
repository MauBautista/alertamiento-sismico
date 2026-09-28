// [T-9.52 · D-44] LA SUPERFICIE ESTIMADA, en la consola.
//
// `D-44` enmienda a `D-08`/T-7.24: además de los puntos medidos y los anillos del
// modelo se pinta una SUPERFICIE continua —verde, amarillo, rojo— con la MMI
// estimada de Wald et al. (1999). La salida honesta no fue negarse a dibujarla
// sino rotularla como lo que es, en cada sitio donde aparece:
//
//  · «ESTIMADO a partir de N sensores (M calibrados)»: con tres o cuatro
//    estaciones la superficie es sobre todo MODELO, y eso lo dice el rótulo
//    porque el color no puede decirlo (`D-44 · El precio, declarado`);
//  · la MMI es ESTIMADA y NO OBSERVADA, siempre con esa palabra detrás. Nunca
//    «INTENSIDAD MMI» a secas: es la frase que mató a las dos capas de bandas
//    sin dato que vivían en `MapPanel` (guarda `DIF-shakemap.a`);
//  · la zona AJUSTADA a sensores calibrados se ve opaca y la solo MODELADA,
//    tenue. Es la mitad del rótulo que sí puede decir la imagen.
//
// Todo lo de este fichero es PURO. La imagen la pinta la nube
// (`shakemap/raster.py`, una celda = un píxel) y la consola sólo la pega sobre
// las cuatro esquinas de su bbox: si la recalculara, la consola y el PDF
// dibujarían cada uno su versión del mismo sismo.

import type { PuntoProps, ShakemapOut, SuperficieOut } from "@takab/sdk";

import { ESTADOS, ESTADO_PENDIENTE, etiquetaDeMedida } from "./shakemap";

/* =====================================================================
   LAS BANDAS — espejo de `shakemap/raster.py`, cruzado por
   `superficieCostura.test.ts`
   ===================================================================== */

/**
 * Los cortes POR DEFECTO del dictamen (`settings.py::dictamen_*_g`, `D-43`).
 *
 * El PNG se pinta con los del `rule_set` DEL SITIO, y desde `T-9.52` el JSON de la
 * superficie los publica (`verde_max_g`, `rojo_min_g`): la leyenda usa ÉSOS. Éstos
 * sólo se pintan cuando no llegan, rotulados «POR DEFECTO», en vez de presentarlos
 * como la verdad de ese edificio (el defecto que cerró `T-7.35`: un umbral de
 * fábrica presentado como el del inmueble).
 */
export const CORTE_VERDE_MAX_G = 0.04;
export const CORTE_ROJO_MIN_G = 0.1;

/** Opacidad (0–1) de cada zona, la misma que el PNG (`ALFA_* / 255`). */
export const ALFA_AJUSTADA = 150 / 255;
export const ALFA_MODELADA = 60 / 255;

export interface BandaSuperficie {
  banda: "rojo" | "amarillo" | "verde";
  /** El RGB EXACTO de la nube: la muestra de la leyenda es el color del píxel. */
  rgb: [number, number, number];
  rotulo: string;
}

const g = (v: number) => v.toFixed(2);

/**
 * De la más fuerte a la más débil, que es como se lee una leyenda de peligro.
 *
 * Los colores NO son tokens y es deliberado: son los del PNG, que la nube pinta
 * con RGB fijos. Una muestra repintada por tema dejaría de ser el color que se
 * ve en el mapa.
 */
export function bandasSuperficie(
  verdeMaxG: number | null = null,
  rojoMinG: number | null = null,
): readonly BandaSuperficie[] {
  const verde = verdeMaxG ?? CORTE_VERDE_MAX_G;
  const rojo = rojoMinG ?? CORTE_ROJO_MIN_G;
  return [
    { banda: "rojo", rgb: [208, 40, 40], rotulo: `≥ ${g(rojo)} g` },
    { banda: "amarillo", rgb: [232, 176, 0], rotulo: `${g(verde)}–${g(rojo)} g` },
    { banda: "verde", rgb: [46, 160, 67], rotulo: `< ${g(verde)} g` },
  ];
}

/** Las bandas con los cortes POR DEFECTO (lo que se pinta si el sitio no los publica). */
export const BANDAS_SUPERFICIE: readonly BandaSuperficie[] = bandasSuperficie();

/** ¿Llegaron los cortes del sitio con la superficie? (`T-9.52`) */
export function cortesDelSitio(sup: {
  verde_max_g: number | null;
  rojo_min_g: number | null;
}): boolean {
  return sup.verde_max_g !== null && sup.rojo_min_g !== null;
}

/** `rgba()` de una banda con la opacidad de una zona. */
export function tintaDeBanda(b: BandaSuperficie, alfa = 1): string {
  return `rgba(${b.rgb.join(",")},${alfa.toFixed(3)})`;
}

/* =====================================================================
   BUILDERS PUROS
   ===================================================================== */

export type Esquinas = [[number, number], [number, number], [number, number], [number, number]];

/**
 * Las cuatro esquinas de `[oeste, sur, este, norte]` en el orden que exige la
 * fuente `image` de MapLibre: arriba-izquierda, arriba-derecha, abajo-derecha,
 * abajo-izquierda. La fila 0 del PNG es el norte (`raster.py`), así que nada se
 * voltea.
 *
 * `null` = el bbox no es un rectángulo legible, y entonces NO se pinta: pegar
 * la imagen sobre esquinas invertidas la voltearía —el rojo de un lado acabaría
 * del otro— y nada en pantalla lo delataría.
 */
export function esquinasDeBbox(bbox: readonly number[]): Esquinas | null {
  if (bbox.length !== 4 || !bbox.every(Number.isFinite)) return null;
  const [oeste, sur, este, norte] = bbox;
  if (!(oeste < este) || !(sur < norte)) return null;
  if (Math.abs(oeste) > 180 || Math.abs(este) > 180) return null;
  if (Math.abs(sur) > 90 || Math.abs(norte) > 90) return null;
  return [
    [oeste, norte],
    [este, norte],
    [este, sur],
    [oeste, sur],
  ];
}

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

/** El rótulo que la superficie lleva SIEMPRE que se enseña (`D-44`). */
export function rotuloEstimado(sup: SuperficieOut): string {
  return (
    `ESTIMADO a partir de ${plural(sup.n_sensores, "sensor", "sensores")} ` +
    `(${plural(sup.n_calibrados, "calibrado", "calibrados")}) · ` +
    "MMI estimada (Wald 1999), no observada"
  );
}

/**
 * El texto del popup de un punto MEDIDO: su nombre, su medida y su MMI
 * ESTIMADA. La palabra va pegada a la sigla, siempre: una MMI sin «ESTIMADA»
 * detrás se lee como una intensidad observada, que TAKAB no reporta.
 */
export function textoDelPunto(p: PuntoProps): string {
  const base = `${p.site_name} · ${etiquetaDeMedida(p)}`;
  if (p.mmi_estimada === null || p.mmi_romano === null) {
    return `${base} · MMI ESTIMADA: SIN VALOR`;
  }
  return `${base} · MMI ESTIMADA ${p.mmi_romano} (${p.mmi_estimada.toFixed(1)}) · Wald 1999 · NO OBSERVADA`;
}

/** El estado del PNG, tal como lo entrega `useSuperficiePng`. */
export interface PngSuperficie {
  url: string | null;
  cargando: boolean;
  error: boolean;
}

export interface VistaSuperficie {
  /** Se cuelga la imagen: hay superficie, esquinas legibles y un PNG listo. */
  pinta: boolean;
  url: string | null;
  esquinas: Esquinas | null;
  /** La superficie del snapshot (para rotularla), o `null`. */
  superficie: SuperficieOut | null;
  nota: string | null;
  notaTestId: string | null;
}

/**
 * Qué se pinta de la superficie y qué se DECLARA (regla de oro 7).
 *
 * El orden de las ramas no es libre, y es el de `vistaSacudida`: lo que
 * impide leer el snapshot sale ANTES que cualquier afirmación sobre la
 * superficie. Con el snapshot en error, pendiente o ilegible, la superficie
 * CALLA: esos estados ya los declara la nota del mapa de la sacudida, y una
 * segunda nota diciendo «sin superficie» atribuiría la ausencia a otra causa.
 */
export function vistaSuperficie(
  mapa: ShakemapOut | undefined,
  png: PngSuperficie,
  errorDelMapa: boolean,
): VistaSuperficie {
  const nada: VistaSuperficie = {
    pinta: false,
    url: null,
    esquinas: null,
    superficie: null,
    nota: null,
    notaTestId: null,
  };
  if (errorDelMapa || mapa === undefined) return nada;
  if (!(ESTADOS as readonly string[]).includes(mapa.estado)) return nada;
  if (mapa.estado === ESTADO_PENDIENTE) return nada;

  const sup = mapa.superficie;
  if (sup === null) {
    // La causa sale del DATO: la frase de la nube si la hay, y si no el código
    // tal cual. Un motivo que este lector no conoce no se traduce a otro.
    const nota =
      mapa.superficie_motivo_texto !== null
        ? `SIN SUPERFICIE ESTIMADA · ${mapa.superficie_motivo_texto}`
        : mapa.superficie_motivo !== null
          ? `SIN SUPERFICIE ESTIMADA · MOTIVO «${mapa.superficie_motivo}»`
          : "SIN SUPERFICIE ESTIMADA EN ESTE SNAPSHOT";
    return { ...nada, nota, notaTestId: "superficie-motivo" };
  }

  const conSup = { ...nada, superficie: sup };
  const esquinas = esquinasDeBbox(sup.bbox);
  if (esquinas === null) {
    return {
      ...conSup,
      nota: "SUPERFICIE CON UN BBOX NO INTERPRETABLE · NO SE PINTA",
      notaTestId: "superficie-bbox",
    };
  }
  // El fallo va antes que la espera: un PNG que falló no está «cargando».
  if (png.error) {
    return {
      ...conSup,
      nota: "SUPERFICIE ESTIMADA NO DISPONIBLE · LA IMAGEN NO SE PUDO CARGAR",
      notaTestId: "superficie-error",
    };
  }
  if (png.url === null) {
    // Mientras carga no se pinta NADA —tampoco la del incidente anterior—: una
    // superficie vieja bajo la leyenda nueva diría otro sismo.
    return {
      ...conSup,
      nota: "CARGANDO LA SUPERFICIE ESTIMADA",
      notaTestId: "superficie-cargando",
    };
  }
  return { ...conSup, pinta: true, url: png.url, esquinas };
}
