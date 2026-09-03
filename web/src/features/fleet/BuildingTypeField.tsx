// Tipo de inmueble y su banda de REFERENCIA (T-5.16 · D-28).
//
// Componente propio, y no unas líneas dentro de `SiteForm`, por una razón que
// midió `serverDataCensus`: el catálogo es dato de SERVIDOR, y pintarlo suelto
// dentro de un formulario lo dejaba sin los cuatro estados obligatorios. Si la
// consulta falla, un desplegable con solo «SIN CLASIFICAR» se lee como «no hay
// tipos», que es lo contrario de «no se pudieron leer».
//
// LO QUE ESTE CAMPO NO HACE: aplicar la banda. La enseña y lo dice. Si el tipo
// resolviera el umbral, guardar este formulario —el mismo acto con el que se
// corrige una dirección— re-armaría el edificio a otra sensibilidad sin publicar
// y sin firmar (`D-28`).

import StateFrame from "../../components/StateFrame";
import { useNow } from "../../lib/useNow";
import { BUILDING_TYPES_STALE_MS, useBuildingTypes } from "./useBuildingTypes";

export default function BuildingTypeField({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const tipos = useBuildingTypes();
  const nowMs = useNow(30_000);
  // El catálogo cambia con un despliegue, no con un latido — pero cambia. Una
  // pestaña abierta desde ayer no ofrecería la tipología que se añadió esta
  // mañana, y quien la busque concluiría que no existe.
  const staleSince =
    tipos.dataUpdatedAt > 0 && nowMs - tipos.dataUpdatedAt > BUILDING_TYPES_STALE_MS
      ? tipos.dataUpdatedAt
      : null;
  const items = tipos.catalog?.items ?? [];
  const elegido = items.find((t) => t.value === value);
  /** `undefined` = sin tipo elegido · `null` = el tipo no tiene banda publicada. */
  const banda = elegido === undefined ? undefined : (elegido.banda ?? null);

  return (
    <StateFrame
      label="TIPO DE INMUEBLE"
      loading={tipos.loading}
      error={tipos.readError ? "no se pudo leer el catálogo de tipologías" : null}
      empty={!tipos.loading && !tipos.readError && items.length === 0}
      emptyText="EL CATÁLOGO DE TIPOLOGÍAS LLEGÓ VACÍO"
      staleSince={staleSince}
    >
      <label>
        <span>TIPO DE INMUEBLE</span>
        <select
          value={value}
          data-testid="site-building-type"
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">SIN CLASIFICAR</option>
          {items.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <p className="fleet__hint" data-testid="site-banda-referencia">
        {banda === undefined
          ? "Sin tipo elegido: no hay banda de referencia que enseñar."
          : banda === null
            ? (elegido?.sin_banda_por_que ?? "")
            : `Banda de referencia: cautela ${banda.pga_watch_g.toFixed(3)} g · ` +
              `disparo ${banda.pga_trip_g.toFixed(3)} g. ` +
              "NO se aplica al guardar: los umbrales se publican y se firman aparte."}
      </p>
    </StateFrame>
  );
}
