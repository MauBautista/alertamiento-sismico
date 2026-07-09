// Mutaciones de la flota (T-1.36): alta, edición y retiro de estaciones.
//
// Dos errores del servidor NO son "algo salió mal" y deben llegar literales al operador:
//  - 409 al editar  → alguien más guardó; recargar antes de pisar su cambio. La API usa
//    `base_row_version` (xmin) precisamente para no revertir en silencio la ubicación de
//    una estación, que reencuadra la ventana del quórum.
//  - 409 al crear   → `code` repetido en el tenant, o `serial` repetido en TODA la
//    plataforma (los seriales son únicos globales).

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createGatewayFleetGatewaysPost,
  createSensorSensorsPost,
  createSiteSitesPost,
  retireSiteSitesSiteIdDelete,
  updateSiteSitesSiteIdPut,
} from "@takab/sdk";
import type { GatewayCreate, SensorCreate, SiteCreate, SiteUpdate } from "@takab/sdk";

/** Traduce el status HTTP a algo que un operador pueda accionar. */
export function messageFor(status: number, fallback: string): string {
  switch (status) {
    case 409:
      return "CONFLICTO · el registro cambió en el servidor o el identificador ya existe. Recarga y reintenta.";
    case 403:
      return "SIN PERMISO · tu rol no administra la flota, o el recurso es de otro tenant.";
    case 404:
      return "NO ENCONTRADO · el recurso no existe o no es visible para tu tenant.";
    case 422:
      return "DATOS INVÁLIDOS · revisa las coordenadas y los campos obligatorios.";
    default:
      return fallback;
  }
}

async function unwrap<T>(
  call: Promise<{ data?: T; response: Response }>,
  what: string,
): Promise<T> {
  const { data, response } = await call;
  if (data === undefined) {
    throw new Error(messageFor(response.status, `${what} falló (HTTP ${response.status})`));
  }
  return data;
}

/** Invalida TODO lo que depende del catálogo: mapa, flota, sitios. */
function useInvalidateFleet() {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["sites"] }),
      queryClient.invalidateQueries({ queryKey: ["fleet"] }),
      queryClient.invalidateQueries({ queryKey: ["mapState"] }),
    ]);
  };
}

export function useCreateSite() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: (body: SiteCreate) => unwrap(createSiteSitesPost({ body }), "El alta del sitio"),
    onSuccess: invalidate,
  });
}

export function useUpdateSite() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: ({ siteId, body }: { siteId: string; body: SiteUpdate }) =>
      unwrap(updateSiteSitesSiteIdPut({ path: { site_id: siteId }, body }), "La edición del sitio"),
    onSuccess: invalidate,
  });
}

export function useRetireSite() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    // Retiro LÓGICO: la fila se conserva porque la evidencia de sus incidentes la
    // referencia y no se poda nunca (regla de oro 11).
    mutationFn: (siteId: string) =>
      unwrap(retireSiteSitesSiteIdDelete({ path: { site_id: siteId } }), "El retiro del sitio"),
    onSuccess: invalidate,
  });
}

export function useCreateGateway() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: (body: GatewayCreate) =>
      unwrap(createGatewayFleetGatewaysPost({ body }), "El alta del gabinete"),
    onSuccess: invalidate,
  });
}

export function useCreateSensor() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: (body: SensorCreate) =>
      unwrap(createSensorSensorsPost({ body }), "El alta del sensor"),
    onSuccess: invalidate,
  });
}
