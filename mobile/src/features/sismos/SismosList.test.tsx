// [T-9.62 · D-46] LA PESTAÑA SISMOS: qué lee la persona en cada fila y cuándo se
// le avisa de que el catálogo no está al día.
import type { SismoCercanoOut, SismosDelSitioOut } from "@takab/sdk";
import { act, render, within } from "@testing-library/react-native";

import { colorDeMmi, LEYENDA_ESCALA } from "./escala";
import { catalogoSinActualizar, MAX_EDAD_CATALOGO_MS } from "./frescura";
import { FilaSismo, SismosList } from "./SismosList";

const AHORA = Date.now();
const hace = (ms: number) => new Date(AHORA - ms).toISOString();

function sismo(over: Partial<SismoCercanoOut> = {}): SismoCercanoOut {
  return {
    depth_km: 20,
    lat: 16.2,
    lon: -98.1,
    magnitude: 5.4,
    origin_time: "2026-09-20T14:05:00Z",
    place: "12 km al S de Pinotepa Nacional, Oax.",
    review_status: "reviewed",
    usgs_url: "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd",
    en_tu_inmueble: {
      dist_km: 180.4,
      metodo: "Estimada con la distancia y la magnitud",
      mmi_estimada: 4.2,
      mmi_romano: "IV",
      pga_estimada_g: 0.012,
    },
    ...over,
  };
}

function respuesta(over: Partial<SismosDelSitioOut> = {}): SismosDelSitioOut {
  return {
    actualizado: hace(5 * 60_000),
    atribucion: "Datos: USGS Earthquake Hazards Program",
    items: [sismo()],
    sync_estado: "ok",
    ...over,
  };
}

async function montar(el: React.ReactElement) {
  const v = await render(el);
  await act(async () => {});
  return v;
}

function colorDeFondo(nodo: { props: { style?: unknown } }): unknown {
  const estilos = [nodo.props.style].flat(Infinity) as Record<string, unknown>[];
  return estilos.reduce<unknown>((c, s) => (s?.backgroundColor ?? c), undefined);
}

describe("[T-9.62] la fila de un sismo", () => {
  it("pinta magnitud, lugar, fecha y lo que habría pasado EN el inmueble", async () => {
    const v = await montar(<FilaSismo sismo={sismo()} />);
    const fila = v.getByTestId("sismo-fila");
    expect(within(fila).getByText("5.4")).toBeTruthy();
    expect(within(fila).getByText("12 km al S de Pinotepa Nacional, Oax.")).toBeTruthy();
    expect(within(fila).getByText("En tu inmueble: IV (estimada) · 180 km")).toBeTruthy();
    // La fecha sale de `Intl` en español de México: el año y el mes abreviado.
    expect(within(fila).getByTestId("sismo-fecha")).toHaveTextContent(/2026/);
    expect(within(fila).getByTestId("sismo-fecha")).toHaveTextContent(/sept?/i);
  });

  it("sin MMI estimada dice «sin estimar» y no le inventa color", async () => {
    const v = await montar(
      <FilaSismo
        sismo={sismo({
          en_tu_inmueble: {
            dist_km: 612,
            metodo: "fuera de alcance",
            mmi_estimada: null,
            mmi_romano: null,
            pga_estimada_g: 0,
          },
        })}
      />,
    );
    expect(v.getByText("En tu inmueble: sin estimar · 612 km")).toBeTruthy();
    const circulo = v.getByTestId("sismo-circulo");
    for (let g = 1; g <= 10; g++) {
      expect(colorDeFondo(circulo)).not.toBe(colorDeMmi(g));
    }
  });

  it.each([
    [2.1, "II"],
    [4.2, "IV"],
    [6.6, "VII"],
    [9.4, "IX"],
  ])("el círculo de una MMI de %s lleva el color de %s", async (mmi, romano) => {
    const v = await montar(
      <FilaSismo
        sismo={sismo({
          en_tu_inmueble: {
            dist_km: 50,
            metodo: "estimada",
            mmi_estimada: mmi,
            mmi_romano: romano,
            pga_estimada_g: 0.1,
          },
        })}
      />,
    );
    expect(colorDeFondo(v.getByTestId("sismo-circulo"))).toBe(colorDeMmi(mmi));
  });

  it("no dice «preliminar» ni pinta cuenta regresiva alguna", async () => {
    const v = await montar(<FilaSismo sismo={sismo({ review_status: "automatic" })} />);
    expect(v.queryByText(/preliminar/i)).toBeNull();
    expect(v.queryByText(/T[-−]\s*\d|segundos para/i)).toBeNull();
  });
});

describe("[T-9.62] la lista: encabezado, pie y procedencia", () => {
  it("encabezado, leyenda, atribución del servidor y «Actualizado»", async () => {
    const v = await montar(
      <SismosList nowMs={AHORA} onRefrescar={jest.fn()} refrescando={false} respuesta={respuesta()} />,
    );
    expect(v.getByText("Sismos de México desde M 4.0 · últimos 90 días")).toBeTruthy();
    expect(v.getByText(LEYENDA_ESCALA)).toBeTruthy();
    expect(v.getByText("Datos: USGS Earthquake Hazards Program")).toBeTruthy();
    expect(v.getByTestId("sismos-actualizado")).toHaveTextContent(/^Actualizado: /);
    expect(v.queryByTestId("catalogo-sin-actualizar")).toBeNull();
    expect(v.getAllByTestId("sismo-fila")).toHaveLength(1);
  });

  it("el catálogo que NO se ha sincronizado lo dice con una franja", async () => {
    const v = await montar(
      <SismosList
        nowMs={AHORA}
        onRefrescar={jest.fn()}
        refrescando={false}
        respuesta={respuesta({ sync_estado: "fallido", actualizado: hace(10 * 60_000) })}
      />,
    );
    expect(v.getByTestId("catalogo-sin-actualizar")).toHaveTextContent(
      /^CATÁLOGO SIN ACTUALIZAR DESDE /,
    );
  });

  it("…y también el que dice `ok` pero es de hace más de media hora", async () => {
    const v = await montar(
      <SismosList
        nowMs={AHORA}
        onRefrescar={jest.fn()}
        refrescando={false}
        respuesta={respuesta({ actualizado: hace(MAX_EDAD_CATALOGO_MS + 60_000) })}
      />,
    );
    expect(v.getByTestId("catalogo-sin-actualizar")).toBeTruthy();
  });

  it("con catálogo viejo y sin filas NO afirma «no hubo sismos»: lo dice con la franja", async () => {
    const v = await montar(
      <SismosList
        nowMs={AHORA}
        onRefrescar={jest.fn()}
        refrescando={false}
        respuesta={respuesta({ items: [], sync_estado: "nunca", actualizado: null })}
      />,
    );
    expect(v.getByTestId("catalogo-sin-actualizar")).toHaveTextContent(/NUNCA SINCRONIZADO/);
    expect(v.getByTestId("sismos-sin-filas")).toHaveTextContent(/no se puede afirmar/);
  });

  it("el hueco del historial se monta encima de la lista", async () => {
    const { Text } = jest.requireActual("react-native");
    const v = await montar(
      <SismosList
        cabecera={<Text>HISTORIAL AQUÍ</Text>}
        nowMs={AHORA}
        onRefrescar={jest.fn()}
        refrescando={false}
        respuesta={respuesta()}
      />,
    );
    expect(v.getByText("HISTORIAL AQUÍ")).toBeTruthy();
  });
});

describe("[T-9.62] cuándo el catálogo está sin actualizar (regla de oro 7)", () => {
  it("`ok` y reciente: al día", () => {
    expect(catalogoSinActualizar(respuesta(), AHORA)).toBeNull();
  });

  it.each(["fallido", "apagado", "nunca"] as const)("`%s` nunca está al día", (estado) => {
    expect(catalogoSinActualizar(respuesta({ sync_estado: estado }), AHORA)).not.toBeNull();
  });

  it("`ok` sin fecha de actualización tampoco: no se afirma frescura sin reloj", () => {
    expect(catalogoSinActualizar(respuesta({ actualizado: null }), AHORA)).not.toBeNull();
  });

  it("la frontera es media hora exacta", () => {
    expect(
      catalogoSinActualizar(respuesta({ actualizado: hace(MAX_EDAD_CATALOGO_MS) }), AHORA),
    ).toBeNull();
    expect(
      catalogoSinActualizar(respuesta({ actualizado: hace(MAX_EDAD_CATALOGO_MS + 1) }), AHORA),
    ).not.toBeNull();
    expect(MAX_EDAD_CATALOGO_MS).toBe(30 * 60_000);
  });
});
