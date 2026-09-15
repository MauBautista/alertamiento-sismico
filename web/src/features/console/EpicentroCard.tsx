// [T-7.20] EL EPICENTRO DE LA REPRODUCCIÓN, con su procedencia en la misma línea.
//
// «EPICENTRO · REPRODUCCIÓN 19-09-2017 · M7.1 · CONFIRMADO POR LA FUENTE · USGS».
//
// Las cinco piezas van juntas y en ese orden por una razón cada una:
//
// · **EPICENTRO** — es dónde se originó el sismo, no un edificio. La confusión
//   entre las dos cosas es la que el mapa lleva tres fichas evitando.
// · **REPRODUCCIÓN + la fecha del sismo real** — un epicentro de 2017 pintado
//   sin decirlo es la mentira más cara que puede contar esta pantalla, y la
//   fecha es lo que impide leerlo como un sismo de hoy.
// · **La magnitud SOLO si la procedencia autoriza** (`T-5.10`): una cifra sin
//   procedencia se lee como propia, y TAKAB no calcula magnitudes.
// · **El estado de la fuente y la fuente**, del glosario compartido — el mismo
//   vocabulario que el panel del gabinete y la app, que no pueden importarse
//   entre sí y por eso se encuentran en un JSON.
//
// Se revela con `soc-row-in`: la tarjeta APARECE cuando la reproducción existe,
// y aparecer es información. No respira ni parpadea — eso es de la alerta
// (`T-7.19`), y esto es lo que se lee cuando la sacudida ya terminó.

import Card from "../../components/Card";
import { pintaCifra, rotuloProcedencia } from "../triage/procedencia";
import type { ReproduccionData } from "./useReproduccion";

/** `2017-09-19T18:14:38Z` → `19-09-2017`. Sin hora: la hora del sismo real no es
 *  la de hoy, y ponerla al lado de la de la demostración las mezcla. */
export function fechaDelSismo(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "FECHA NO LEGIBLE";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCDate())}-${p(d.getUTCMonth() + 1)}-${d.getUTCFullYear()}`;
}

/** La línea entera, como función pura: es lo que se puede fijar en una prueba. */
export function lineaDelEpicentro(r: {
  t0_real: string;
  magnitude: number | null;
  review_status: string | null | undefined;
  catalog_source: string | null | undefined;
}): string {
  const partes = ["EPICENTRO", `REPRODUCCIÓN ${fechaDelSismo(r.t0_real)}`];
  const estado = r.review_status ?? "sin_dato_externo";
  // La cifra va solo si la fuente la sostiene. Si no, se dice por qué no la hay
  // — nunca un hueco: un hueco se lee como «no pasó nada».
  if (r.magnitude !== null && pintaCifra(estado)) partes.push(`M${r.magnitude.toFixed(1)}`);
  partes.push(rotuloProcedencia(estado));
  if (r.catalog_source) partes.push(r.catalog_source);
  return partes.join(" · ");
}

export default function EpicentroCard({ reproduccion }: { reproduccion: ReproduccionData }) {
  const r = reproduccion.data;
  // Sin reproducción no hay tarjeta. Y NO es un marco vacío: la inmensa mayoría
  // de los incidentes no son reproducciones, y un «SIN REPRODUCCIÓN» permanente
  // en el muro enseña al operador a no leer esa esquina.
  if (r === null) return null;
  return (
    <div className="soc-reveal" data-testid="epicentro-card">
      <Card
        title={lineaDelEpicentro({
          t0_real: r.t0_real,
          magnitude: r.magnitude,
          review_status: r.review_status,
          catalog_source: r.catalog_source,
        })}
        sub={
          <>
            {r.place ?? "SIN LUGAR EN EL CATÁLOGO"} · {r.lat?.toFixed(2)} / {r.lon?.toFixed(2)}
            {r.depth_km !== null && ` · ${r.depth_km.toFixed(0)} km`}
          </>
        }
      >
        {null}
      </Card>
    </div>
  );
}
