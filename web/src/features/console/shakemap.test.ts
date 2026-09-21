// [T-7.24] Los builders del mapa de la sacudida: puros, sin MapLibre.
//
// Lo que se prueba aquí es lo que hace HONESTO al mapa, y cada `it` nombra el
// hecho que afirma. La regla que gobierna el fichero entero: **una cifra sin
// procedencia no se pinta** (`shared/glossary/procedencia.json`), y lo medido y
// lo modelado no pueden compartir codificación (`D-08` · `§A.3`).
import { cssVariables } from "@takab/design-tokens";
import { describe, expect, it } from "vitest";

import {
  ESTADO_COMPLETO,
  ESTADO_PENDIENTE,
  ESTADO_SIN_DATOS,
  ESTADO_SOLO_OBSERVADO,
  PGA_COLOR,
  PROC_MEDIDO,
  PROC_MODELADO,
  UMBRAL_TRIP,
  UMBRAL_WATCH,
  bandaDe,
  coberturaFeatureCollection,
  colorDeBanda,
  etiquetaDeAnillo,
  etiquetaDeMedida,
  modeladoFeatureCollection,
  nivelesDe,
  observadoFeatureCollection,
  sinProcedencia,
  vistaSacudida,
  type AnilloFeature,
  type PuntoFeature,
  type ShakemapOut,
} from "./shakemap";

/** Un punto MEDIDO tal como lo publica `shakemap/lectura.py::_observado`. */
function punto(over: Partial<PuntoFeature["properties"]> = {}): PuntoFeature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [-98.2404, 19.3139] },
    properties: {
      site_id: "s-1",
      site_code: "site-cholula-a",
      site_name: "Cholula A",
      procedencia: PROC_MEDIDO,
      voto_contado: null,
      pga_g: 0.083,
      pgv_cms: 2.1,
      dist_km: 120,
      hypo_km: 129,
      pga_g_modelada: 0.041,
      residuo_log10: 0.306,
      medido_en: "2026-09-14T10:00:35Z",
      ...over,
    },
  };
}

/** Un anillo MODELADO: polígono en GRADOS, ya materializado por el lector. */
function anillo(over: Partial<AnilloFeature["properties"]> = {}): AnilloFeature {
  return {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-99.1, 17.9],
          [-98.9, 17.9],
          [-98.9, 17.7],
          [-99.1, 17.7],
          [-99.1, 17.9],
        ],
      ],
    },
    properties: {
      procedencia: PROC_MODELADO,
      pga_g: 0.02,
      radio_km: 130,
      umbral: UMBRAL_WATCH,
      ...over,
    },
  };
}

function mapa(over: Partial<ShakemapOut> = {}): ShakemapOut {
  return {
    fuera_de_alcance: [],
    incident_id: "i-1",
    estado: ESTADO_COMPLETO,
    calculado_en: "2026-09-14T10:41:30Z",
    ley: "ATTEN-LAW v1",
    cobertura_km: 25,
    epicentro: {
      lat: 17.8,
      lon: -99.0,
      depth_km: 20,
      magnitud: 7.1,
      fuente: "SSN",
      procedencia: "confirmado",
      catalog_key: "SSN-2026-001",
    },
    observado: { type: "FeatureCollection", features: [punto()] },
    modelado: {
      type: "FeatureCollection",
      features: [
        anillo({ umbral: UMBRAL_WATCH, pga_g: 0.02, radio_km: 130 }),
        anillo({ umbral: UMBRAL_TRIP, pga_g: 0.08, radio_km: 66 }),
      ],
    },
    ...over,
  };
}

const NIVELES = [
  { umbral: UMBRAL_WATCH, pga_g: 0.02 },
  { umbral: UMBRAL_TRIP, pga_g: 0.08 },
];

describe("bandaDe · la banda de una medida sale de los umbrales CITADOS, no de una escala inventada", () => {
  it("toma el umbral MÁS ALTO que la medida alcanza", () => {
    expect(bandaDe(0.083, NIVELES)).toBe(UMBRAL_TRIP);
    expect(bandaDe(0.03, NIVELES)).toBe(UMBRAL_WATCH);
  });

  it("por debajo del umbral MÁS BAJO citado no hay banda que afirmar", () => {
    // Y no es lo mismo que no haber medido: el número sigue viajando en el
    // rótulo. Lo que no se afirma es una banda.
    expect(bandaDe(0.0004, NIVELES)).toBeNull();
    // Y tampoco se inventa una banda por debajo del `watch` del edificio: lo
    // que la nube publica son los umbrales con los que ESTE sistema decide.
    expect(bandaDe(0.005, NIVELES)).toBeNull();
  });

  it("sin medida no hay banda: un silencio no es un cero (regla de oro 7)", () => {
    expect(bandaDe(null, NIVELES)).toBeNull();
  });

  it("SIN UMBRALES CITADOS tampoco: no se bandea con números de fábrica", () => {
    // Es el caso `solo_observado`: sin epicentro no hay anillos, y los anillos
    // son lo único que trae los umbrales del `rule_set` que regía el incidente.
    // Inventar aquí un 0.02 g de fábrica es el defecto que cerró `T-7.35`.
    expect(bandaDe(0.083, [])).toBeNull();
  });
});

describe("colorDeBanda · un umbral que esta consola no conoce NO hereda el color de otro", () => {
  it("las DOS bandas que la nube publica resuelven a su token `--tk-pga-*`", () => {
    expect(colorDeBanda(UMBRAL_WATCH)).toBe(cssVariables["--tk-pga-watch"]);
    expect(colorDeBanda(UMBRAL_TRIP)).toBe(cssVariables["--tk-pga-trip"]);
  });

  it("un umbral nuevo del servidor cae en SIN BANDA, jamás en el rojo del disparo", () => {
    // Un fallback no puede ser `ok`, y aquí el «ok» más caro sería el peor: que
    // un nivel que esta consola no sabe leer se pintara como el de disparo.
    const nuevo = colorDeBanda("pga_evacuate_g");
    expect(nuevo).toBe(cssVariables["--tk-pga-sin-banda"]);
    expect(nuevo).not.toBe(cssVariables["--tk-pga-trip"]);
  });

  it("sin banda que afirmar, la tinta neutra", () => {
    expect(colorDeBanda(null)).toBe(cssVariables["--tk-pga-sin-banda"]);
  });

  it("no queda ningún token de BANDA huérfano en el paquete", () => {
    // ⚠️ `--tk-pga-perceptible` (#00E676) existía para pintar
    // `correlacion_min_pga_g`, un nivel que la nube no publica y que ningún
    // snapshot persistido trae (lo mide `shakemapCostura.test.ts`). Un token de
    // banda que nadie consume es una escala que promete un nivel más de los que
    // el mapa puede recibir: la leyenda huérfana otra vez, esta vez en los
    // tokens. Los `--tk-pga-sin-*` quedan fuera a propósito — no son bandas,
    // son las dos ausencias, y las consume el `paint` y la hoja.
    const bandas = (Object.entries(cssVariables) as Array<[string, string]>).filter(
      ([n]) => n.startsWith("--tk-pga-") && !n.startsWith("--tk-pga-sin-"),
    );
    expect(
      bandas.map(([, valor]) => valor).sort(),
      "un token `--tk-pga-*` de banda que `PGA_COLOR` no consume",
    ).toEqual(Object.values(PGA_COLOR).sort());
  });
});

describe("las etiquetas dicen el valor Y de dónde sale", () => {
  it("lo medido es el número, y el residuo dice cuánto se aparta del modelo", () => {
    // `residuo_log10 = log10(medida/modelada)`; 0.306 es ×2.0. Se escribe en
    // veces y no en logaritmos porque quien mira el mapa decide evacuar, no
    // publica un paper.
    expect(etiquetaDeMedida(punto().properties)).toBe("0.083 g · ×2.0");
  });

  it("sin residuo se queda en el número: no se inventa la comparación", () => {
    expect(etiquetaDeMedida(punto({ residuo_log10: null }).properties)).toBe("0.083 g");
  });

  it("sin medida lo DICE, y no escribe 0.000 g", () => {
    const label = etiquetaDeMedida(punto({ pga_g: null, residuo_log10: null }).properties);
    expect(label).toMatch(/SIN MEDIDA/);
    expect(label).not.toMatch(/0\.000 g/);
  });

  it("el anillo se rotula como MODELO en el propio mapa, no solo en la leyenda", () => {
    // Un anillo suelto en pantalla tiene que poder leerse sin la leyenda: es la
    // diferencia entre una estimación y una medición.
    expect(etiquetaDeAnillo(anillo().properties)).toMatch(/^MODELO · 0\.020 g/);
  });
});

describe("las colecciones: con procedencia, o no se pinta", () => {
  it("cada punto observado sale con su procedencia MEDIDA y su valor", () => {
    const fc = observadoFeatureCollection(mapa());
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].properties).toMatchObject({
      procedencia: PROC_MEDIDO,
      pga_g: 0.083,
      medido: true,
      banda: UMBRAL_TRIP,
      color: cssVariables["--tk-pga-trip"],
      label: "0.083 g · ×2.0",
    });
  });

  it("cada anillo sale con su procedencia MODELADA y su geometría en GRADOS", () => {
    const fc = modeladoFeatureCollection(mapa());
    expect(fc.features).toHaveLength(2);
    for (const f of fc.features) {
      expect(f.properties.procedencia).toBe(PROC_MODELADO);
      expect(f.geometry.type).toBe("Polygon");
      // Grados geográficos: lon en [-180,180], lat en [-90,90]. Un radio en
      // píxeles no cabría en este rango y por eso el rango es la guarda.
      for (const [lon, lat] of f.geometry.coordinates[0]) {
        expect(Math.abs(lon)).toBeLessThanOrEqual(180);
        expect(Math.abs(lat)).toBeLessThanOrEqual(90);
      }
    }
  });

  it("un rasgo SIN la procedencia de su capa NO se pinta, y se puede contar", () => {
    // Default-deny. Si un día el servidor publica un punto sin `procedencia`,
    // el mapa no lo dibuja como medido «porque venía en la lista de medidos»:
    // la lista no es la procedencia, la procedencia viaja en el dato.
    const sucio = mapa({
      observado: {
        type: "FeatureCollection",
        features: [punto(), punto({ site_id: "s-2", procedencia: "" as typeof PROC_MEDIDO })],
      },
    });
    expect(observadoFeatureCollection(sucio).features).toHaveLength(1);
    expect(sinProcedencia(sucio)).toBe(1);
  });

  it("un anillo que dijera venir MEDIDO tampoco se cuela en la capa del modelo", () => {
    const sucio = mapa({
      modelado: {
        type: "FeatureCollection",
        features: [anillo(), anillo({ procedencia: PROC_MEDIDO as typeof PROC_MODELADO })],
      },
    });
    expect(modeladoFeatureCollection(sucio).features).toHaveLength(1);
    expect(sinProcedencia(sucio)).toBe(1);
  });

  it("sin mapa las dos colecciones quedan VACÍAS: nada que borrar a mano", () => {
    expect(observadoFeatureCollection(undefined).features).toEqual([]);
    expect(modeladoFeatureCollection(undefined).features).toEqual([]);
  });

  it("nivelesDe deriva los umbrales de los propios anillos, ordenados", () => {
    expect(nivelesDe(mapa())).toEqual(NIVELES);
    expect(nivelesDe(mapa({ modelado: null }))).toEqual([]);
  });
});

describe("vistaSacudida · los CUATRO estados se declaran, y ninguno se pinta como otro", () => {
  it("completo pinta las dos capas y no tiene nada que declarar", () => {
    const v = vistaSacudida(mapa(), false);
    expect(v).toMatchObject({ pintaObservado: true, pintaModelado: true, nota: null });
  });

  it("PENDIENTE no es un error ni un vacío: el worker todavía no pasó", () => {
    const v = vistaSacudida(
      mapa({
        estado: ESTADO_PENDIENTE,
        calculado_en: null,
        modelado: null,
        observado: { type: "FeatureCollection", features: [] },
      }),
      false,
    );
    expect(v.notaTestId).toBe("shakemap-pendiente");
    expect(v.nota).toMatch(/AÚN NO/i);
    expect(v.pintaObservado).toBe(false);
  });

  it("SIN DATOS y SIN un solo inmueble instrumentado lo dice con ESA causa", () => {
    // Colección vacía: el snapshot no trae ni un inmueble que pudiera medir. No
    // es lo mismo que el caso de abajo —los hay y ninguno publicó—, y el
    // operador hace cosas distintas con cada uno: aquí no hay gabinete que
    // revisar, allí hay dos.
    const v = vistaSacudida(
      mapa({ estado: ESTADO_SIN_DATOS, observado: { type: "FeatureCollection", features: [] } }),
      false,
    );
    expect(v.notaTestId).toBe("shakemap-sin-datos");
    expect(v.nota).toMatch(/SIN INMUEBLES INSTRUMENTADOS/i);
    expect(v.nota, "sin inmuebles no se puede afirmar que «ninguno midió»").not.toMatch(
      /MIDIÓ EN LA VENTANA/i,
    );
    expect(v.pintaObservado).toBe(false);
  });

  it("SIN DATOS con puntos MUDOS es el ÚNICO `sin_datos` que la nube sabe emitir, y NO es una contradicción", () => {
    // ⚠️ EL DEFECTO, medido contra el código real de la nube: `sin_datos` sale
    // de `calculo.py::calcula` cuando `hubo_medida` es falso, y los PUNTOS de
    // ese mismo snapshot salen de `tuple(_punto(m, …) for m in medidas)` —uno
    // por inmueble instrumentado con coordenadas, midiera o no, porque
    // `servicio.py::_medidas_de` no filtra por `peak_pga_g`—. O sea: el
    // snapshot `sin_datos` que la nube publica de verdad viaja con un punto
    // MUDO por inmueble, y con `puntos.length > 0` como predicado la consola
    // le gritaba al operador que el snapshot se contradice, imprimía «TRAE 2
    // MEDIDA(S) · SE PINTA LO MEDIDO» con cero medidas y **tapaba la nota que
    // sí importa**. Una falsa alarma en la pantalla del SOC.
    //
    // Un punto NO es una medida: lo que gatea la discrepancia es `medido`.
    const mudo = { pga_g: null, pgv_cms: null, residuo_log10: null, pga_g_modelada: null };
    const v = vistaSacudida(
      mapa({
        estado: ESTADO_SIN_DATOS,
        observado: {
          type: "FeatureCollection",
          features: [punto(mudo), punto({ site_id: "s-2", site_code: "site-b", ...mudo })],
        },
      }),
      false,
    );
    expect(v.notaTestId, "el caso normal de la nube no se acusa de contradicción").toBe(
      "shakemap-sin-datos",
    );
    expect(v.nota).toMatch(/NINGUNO DE LOS 2 INMUEBLES INSTRUMENTADOS MIDIÓ EN LA VENTANA/);
    expect(v.nota, "cero medidas no son «2 MEDIDA(S)»").not.toMatch(/MEDIDA\(S\)/);
    // Y no se pinta la capa de lo MEDIDO: dos discos sin valor bajo una leyenda
    // que promete «DISCO CON SU VALOR» y un halo de cobertura que nadie dibuja
    // es el defecto de la leyenda huérfana otra vez.
    expect(v.pintaObservado).toBe(false);
  });

  it("SIN DATOS con una medida DENTRO no borra la medida ni afirma que nadie midió", () => {
    // El defecto: el rótulo decía `sin_datos`, la colección traía 0.31 g, y la
    // consola borraba el punto de la pantalla y escribía «NINGÚN INMUEBLE
    // INSTRUMENTADO MIDIÓ EN LA VENTANA» encima. Eso no declara una ausencia:
    // la fabrica. El rótulo lo escribió un worker; la medida, un acelerómetro.
    //
    // El punto MUDO va al lado a propósito: es lo que la nube mete en todo
    // snapshot `sin_datos` (un punto por inmueble instrumentado), así que
    // contar puntos en vez de medidas anunciaría «2 MEDIDA(S)» habiendo una.
    const v = vistaSacudida(
      mapa({
        estado: ESTADO_SIN_DATOS,
        observado: {
          type: "FeatureCollection",
          features: [
            punto({ pga_g: 0.31 }),
            punto({ site_id: "s-2", site_code: "site-b", pga_g: null, residuo_log10: null }),
          ],
        },
      }),
      false,
    );
    expect(v.pintaObservado, "una medida de 0.31 g no puede desaparecer por un rótulo").toBe(true);
    expect(v.nota).not.toMatch(/NINGÚN INMUEBLE/i);
    expect(v.notaTestId).toBe("shakemap-sin-datos-discrepa");
    // Y la discrepancia se DECLARA con su cuenta: callarla dejaría al operador
    // sin saber que el snapshot se contradice. La cuenta es de MEDIDAS.
    expect(v.nota).toMatch(/SIN DATOS/);
    expect(v.nota, "la cuenta que se anuncia es la de medidas, no la de puntos").toMatch(
      /\b1 MEDIDA\(S\)/,
    );
  });

  it("SIN EPICENTRO NI MAGNITUD el mapa existe DEGRADADO y lo declara", () => {
    // `§A.5`: la capa 1 sola es un mapa honesto; inventarle un modelo, no.
    const v = vistaSacudida(
      mapa({ estado: ESTADO_SOLO_OBSERVADO, modelado: null, epicentro: null }),
      false,
    );
    expect(v.pintaObservado).toBe(true);
    expect(v.pintaModelado).toBe(false);
    expect(v.notaTestId).toBe("shakemap-sin-modelo");
    expect(v.nota).toMatch(/NO SE MODELA/i);
  });

  it("lo que manda es EL DATO, no el rótulo: `completo` sin anillos también se declara", () => {
    // El estado lo escribió el worker; los anillos son lo que hay. Si alguna vez
    // discrepan, se cree al dato y se dice — creerle al rótulo dejaría la
    // leyenda prometiendo un modelo que no está en pantalla.
    const v = vistaSacudida(mapa({ modelado: null }), false);
    expect(v.pintaModelado).toBe(false);
    expect(v.nota).toMatch(/NO SE MODELA LA SACUDIDA/);
  });

  it("y la CAUSA también sale del dato: con epicentro M7.1 no se afirma que no lo hay", () => {
    // ⚠️ La prueba de arriba comprobaba el `data-testid` y NUNCA el texto, así
    // que bendecía esto: un snapshot con epicentro SSN CONFIRMADO y magnitud 7.1
    // rotulado «SIN EPICENTRO NI MAGNITUD CITADOS». El hecho (no se modela) era
    // cierto y la causa, inventada — la familia de T-7.34/T-7.38/T-7.39, el
    // papel que se desmiente a sí mismo, trasladada a la pantalla.
    const conEpicentro = mapa({ modelado: null });
    expect(conEpicentro.epicentro?.magnitud, "la fixture tiene que traer magnitud").toBe(7.1);
    const v = vistaSacudida(conEpicentro, false);
    expect(v.nota).not.toMatch(/SIN EPICENTRO/);
    expect(v.notaTestId).toBe("shakemap-sin-anillos");
    // Lo que sí dice: el hecho, y que hay epicentro y magnitud citados.
    expect(v.nota).toMatch(/NO SE MODELA LA SACUDIDA/);
    expect(v.nota).toMatch(/EPICENTRO Y MAGNITUD CITADOS/);

    // Y la rama que sí puede afirmar la causa la afirma: sin epicentro.
    const sin = vistaSacudida(mapa({ modelado: null, epicentro: null }), false);
    expect(sin.notaTestId).toBe("shakemap-sin-modelo");
    expect(sin.nota).toMatch(/SIN EPICENTRO NI MAGNITUD CITADOS/);
    // Y con epicentro pero SIN magnitud citable tampoco hay con qué modelar.
    const sinM = vistaSacudida(
      mapa({ modelado: null, epicentro: { ...mapa().epicentro!, magnitud: null } }),
      false,
    );
    expect(sinM.notaTestId).toBe("shakemap-sin-modelo");
  });

  it("un estado que esta consola no sabe leer NO se pinta como completo", () => {
    const v = vistaSacudida(mapa({ estado: "recalculando" }), false);
    expect(v.notaTestId).toBe("shakemap-no-interpretable");
    expect(v.nota).toMatch(/recalculando/);
    expect(v.pintaObservado).toBe(false);
    expect(v.pintaModelado).toBe(false);
  });

  it("el error de la consulta se declara y NO se disfraza de «sin datos»", () => {
    const v = vistaSacudida(undefined, true);
    expect(v.notaTestId).toBe("shakemap-error");
    expect(v.nota).toMatch(/NO DISPONIBLE/i);
  });

  it("CONSULTANDO no es «no hay»: la espera es un estado propio (regla de oro 7)", () => {
    const v = vistaSacudida(undefined, false, true);
    expect(v.notaTestId).toBe("shakemap-cargando");
    expect(v.nota).toMatch(/CONSULTANDO/i);
    // Y un error en vuelo sigue siendo un error: la espera no lo tapa.
    expect(vistaSacudida(undefined, true, true).notaTestId).toBe("shakemap-error");
  });

  it("`legible` separa «se pudo leer el snapshot» de «hay algo que pintar»", () => {
    // De `legible` cuelga todo lo que AFIRMA algo sobre el snapshot entero (su
    // hora de cálculo, p. ej.). Un mapa sin datos SÍ es legible —se leyó, y dice
    // que nadie midió—; uno cuyo estado no se sabe interpretar, NO.
    expect(vistaSacudida(mapa(), false).legible).toBe(true);
    expect(
      vistaSacudida(
        mapa({ estado: ESTADO_SIN_DATOS, observado: { type: "FeatureCollection", features: [] } }),
        false,
      ).legible,
    ).toBe(true);
    expect(vistaSacudida(mapa({ estado: ESTADO_PENDIENTE }), false).legible).toBe(true);
    expect(vistaSacudida(mapa({ estado: "recalculando" }), false).legible).toBe(false);
    expect(vistaSacudida(undefined, true).legible).toBe(false);
    expect(vistaSacudida(undefined, false, true).legible).toBe(false);
  });
});

describe("coberturaFeatureCollection · el borde de lo que una medida puede decir", () => {
  const ZOOM = 8.5;

  it("un halo por inmueble que MIDIÓ, con el radio del propio snapshot", () => {
    const fc = coberturaFeatureCollection(mapa({ cobertura_km: 25 }), ZOOM);
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].properties.cobertura_km).toBe(25);
    expect(fc.features[0].geometry.type).toBe("Point");
  });

  it("el que NO publicó nada no da cobertura: rodearlo diría que sí midió", () => {
    const fc = coberturaFeatureCollection(
      mapa({ observado: { type: "FeatureCollection", features: [punto({ pga_g: null })] } }),
      ZOOM,
    );
    expect(fc.features).toEqual([]);
  });

  it("el radio es FÍSICO: los mismos km dan MÁS píxeles cuanto más cerca se mira", () => {
    // ⚠️ Es la lección de `DIF-shakemap.a`. Un `circle-radius` constante haría
    // que el mismo halo afirmara 25 km a un zoom y un par de manzanas a otro.
    const cerca = coberturaFeatureCollection(mapa(), 13);
    const lejos = coberturaFeatureCollection(mapa(), 8.5);
    expect(cerca.features[0].properties.radius_px).toBeGreaterThan(
      lejos.features[0].properties.radius_px * 10,
    );
  });

  it("sin mapa no hay halo que pintar", () => {
    expect(coberturaFeatureCollection(undefined, ZOOM).features).toEqual([]);
  });
});
