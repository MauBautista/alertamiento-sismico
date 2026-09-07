// [T-6.04] EL NOMBRE DE UN SITIO, CON SU CINTA SI ES DE DEMOSTRACIÓN.
//
// T-5.05 enseñó a la consola qué sitio es simulado (`esDeDemostracion`, derivado
// del prefijo del seed) y lo pintó en DOS superficies: el mapa y la tarjeta de
// flota. La cola de incidentes, el triage, el detalle y los KPI seguían pintando
// esos mismos sitios sin marca (U-07). Un marcado a medias enseña una regla
// falsa —«sin cinta ⇒ real»— justo al prospecto que mira la fila debajo del pin
// rotulado.
//
// Por eso hay UN componente para pintar un nombre de sitio, y un censo
// (`src/siteDemoCensus.test.ts`) que obliga a que toda superficie que pinte un
// sitio pase por aquí (o por `siteLabelText`, para los contextos de texto plano:
// `<option>`, `<title>`, SVG).
//
// La cinta es gris y discontinua a propósito, la misma que la tarjeta de flota y
// la capa `site-demo` del mapa: el ámbar de esta consola ya significa simulacro
// y dato retenido, y un tercer significado en el mismo color deja de significar
// nada. Cero tokens nuevos.

import { esDeDemostracion, ROTULO_DEMO, TITULO_DEMO } from "../features/fleet/datosDeDemostracion";

export interface SiteLabelProps {
  /** Nombre a pintar (o el `SITIO xxxxxxxx` de respaldo que ya use la pantalla). */
  name: string;
  /** Código del sitio (`sites.code`); la marca se deriva de él. */
  code: string | null | undefined;
  /** Serial del gabinete, si la superficie habla de uno: también marca. */
  serial?: string | null;
  className?: string;
}

export default function SiteLabel({ name, code, serial = null, className }: SiteLabelProps) {
  const demo = esDeDemostracion(code) || esDeDemostracion(serial);
  return (
    <span className={className ? `site-label ${className}` : "site-label"}>
      {name}
      {demo && (
        <span className="site-demo" data-testid="site-demo" title={TITULO_DEMO}>
          {ROTULO_DEMO}
        </span>
      )}
    </span>
  );
}
