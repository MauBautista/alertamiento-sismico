// [T-7.17] LA RED DE ESTACIONES: lo que midió cada una junto a lo que le tocaba.
//
// Un pico suelto no dice nada —¿mucho o poco para esta distancia?— y un valor
// teórico suelto es una simulación. Las dos columnas juntas hacen que la fila se
// lea sola: la estación midió lo que le tocaba, o no, y entonces hay algo que
// mirar.
//
// **En orden de arribo**, que es el orden del servidor y el orden en que ocurrió.
// Esta tabla no reordena: si lo hiciera, dos superficies contarían la misma
// secuencia en distinto orden.
//
// Lo que NO se inventa, y por eso hay tantos `S/D`:
//
// · Sin epicentro no hay distancia ni arribo teórico. Rellenarlos con una
//   estimación sería presentar una simulación como si fuera la medición.
// · `tier` vacío NO es `normal`: un gabinete que no publicó transición no dijo
//   que estuviera en calma, no dijo nada (regla de oro 7).
// · El umbral va con su PROCEDENCIA. Un umbral de fábrica presentado como del
//   edificio es el defecto que cerró T-7.35.

import Card from "../../components/Card";
import SiteLabel from "../../components/SiteLabel";
import StateFrame from "../../components/StateFrame";
import Table from "../../components/Table";
import type { EstacionesData } from "./useEstaciones";

function segundos(v: number | null | undefined): string {
  return v === null || v === undefined ? "S/D" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}s`;
}

function pga(v: number | null | undefined): string {
  return v === null || v === undefined ? "S/D" : `${v.toFixed(3)} g`;
}

function km(v: number | null | undefined): string {
  return v === null || v === undefined ? "S/D" : `${Math.round(v)} km`;
}

/** Cuánto se desvió lo medido de lo esperado. `S/D` si falta cualquiera de los dos. */
export function desfase(
  teorico: number | null | undefined,
  medido: number | null | undefined,
): string {
  if (teorico === null || teorico === undefined) return "S/D";
  if (medido === null || medido === undefined) return "S/D";
  const d = medido - teorico;
  return `${d >= 0 ? "+" : ""}${d.toFixed(1)}s`;
}

export interface EstacionesTableProps {
  estaciones: EstacionesData;
  /** Epoch ms de la última respuesta buena cuando ya es vieja; `null` = fresca. */
  staleSince?: number | null;
}

export default function EstacionesTable({ estaciones, staleSince = null }: EstacionesTableProps) {
  const d = estaciones.data;
  const ancla =
    d === null
      ? ""
      : d.ancla === "event"
        ? "ARRIBOS DESDE EL ORIGEN DEL SISMO"
        : "ARRIBOS DESDE LA APERTURA DEL INCIDENTE";
  return (
    <Card
      title="Red de estaciones · Lo medido y lo esperado"
      sub={
        <>
          {ancla}
          {d?.reproduccion === true && " · REPRODUCCIÓN"}
        </>
      }
    >
      <StateFrame
        label="ESTACIONES"
        loading={estaciones.loading}
        error={estaciones.error ? "no se pudo leer la red de estaciones" : null}
        onRetry={estaciones.refetch}
        empty={d !== null && d.items.length === 0}
        emptyText="ESTE CLIENTE NO TIENE ESTACIONES CON GABINETE ACTIVO"
        staleSince={staleSince}
      >
        {d !== null && d.items.length > 0 && (
          <Table densa grid>
            <thead>
              <tr>
                <th scope="col">Estación</th>
                <th scope="col">Distancia</th>
                <th scope="col">Arribo esperado</th>
                <th scope="col">Arribo medido</th>
                <th scope="col">Desfase</th>
                <th scope="col">Pico</th>
                <th scope="col">Tier</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((e) => (
                <tr key={e.site_id} data-testid={`estacion-${e.site_code}`}>
                  <td>
                    <SiteLabel name={e.site_name} code={e.site_code} serial={e.sensor_code} />
                    {e.sensor_code !== null && (
                      <span className="soc-estaciones__sensor"> · {e.sensor_code}</span>
                    )}
                  </td>
                  <td>{km(e.dist_km)}</td>
                  <td>{segundos(e.t_arribo_teorico_s)}</td>
                  <td>{segundos(e.t_arribo_medido_s)}</td>
                  <td>{desfase(e.t_arribo_teorico_s, e.t_arribo_medido_s)}</td>
                  <td title={`umbral ${pga(e.umbral_pga_g)} · ${e.umbral_origen}`}>
                    {pga(e.peak_pga_g)}
                  </td>
                  {/* Vacío y `normal` son cosas distintas y se escriben distinto. */}
                  <td>{e.tier ?? "S/D"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </StateFrame>
    </Card>
  );
}
