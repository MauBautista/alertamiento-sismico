// Mutaciones de la flota (T-1.36): alta, edición y retiro de estaciones.
//
// Dos errores del servidor NO son "algo salió mal" y deben llegar literales al operador:
//  - 409 al editar  → alguien más guardó; recargar antes de pisar su cambio. La API usa
//    `base_row_version` (xmin) precisamente para no revertir en silencio la ubicación de
//    una estación, que reencuadra la ventana del quórum.
//  - 409 al crear   → `code` repetido en el tenant, o `serial` repetido en TODA la
//    plataforma (los seriales son únicos globales).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createGatewayFleetGatewaysPost,
  createSensorSensorsPost,
  createSiteSitesPost,
  getRetireCodeStateTenantsTenantIdRetireCodeGet,
  fleetHealthHistoryFleetHealthHistoryGet,
  listGatewayConfigStatesFleetConfigStateGet,
  restoreGatewayFleetGatewaysGatewayIdRestorePost,
  retireGatewayFleetGatewaysGatewayIdRetirePost,
  retireSiteSitesSiteIdRetirePost,
  updateGatewayFleetGatewaysGatewayIdPut,
  updateSiteSitesSiteIdPut,
} from "@takab/sdk";
import type {
  GatewayConfigStateOut,
  GatewayCreate,
  GatewayHealthOut,
  GatewayRetire,
  GatewayUpdate,
  SensorCreate,
  SiteCreate,
  SiteRetire,
  SiteUpdate,
} from "@takab/sdk";

/** Traduce el status HTTP a algo que un operador pueda accionar. */
export function messageFor(status: number, fallback: string): string {
  switch (status) {
    case 400:
      // [T-2.36] Primer factor: el identificador tecleado no coincide.
      return "NO COINCIDE · el identificador que escribiste no es el de esta estación.";
    case 409:
      return "CONFLICTO · el registro cambió en el servidor o el identificador ya existe. Recarga y reintenta.";
    case 403:
      return "SIN PERMISO · tu rol no administra la flota, o el recurso es de otro tenant.";
    case 404:
      return "NO ENCONTRADO · el recurso no existe o no es visible para tu tenant.";
    case 422:
      return "DATOS INVÁLIDOS · revisa las coordenadas y los campos obligatorios.";
    case 429:
      // [T-2.36] El bloqueo se cuenta por CLIENTE, no por usuario: decirlo evita que
      // el operador siga probando creyendo que es un problema de su sesión.
      return "DEMASIADOS INTENTOS · el retiro queda bloqueado 15 min para este cliente.";
    default:
      return fallback;
  }
}

/** El 403 del retiro es del CÓDIGO, no del rol: el rol ya se validó al pintar el botón. */
function retireMessageFor(status: number, fallback: string): string {
  if (status === 403) {
    return "CÓDIGO INCORRECTO · verifica el código de retiro con TAKAB.";
  }
  if (status === 409) {
    return "SIN CÓDIGO CONFIGURADO · este cliente no tiene código de retiro; solicítalo a TAKAB.";
  }
  return messageFor(status, fallback);
}

async function unwrap<T>(
  call: Promise<{ data?: T; response: Response }>,
  what: string,
  translate: (status: number, fallback: string) => string = messageFor,
): Promise<T> {
  const { data, response } = await call;
  if (data === undefined) {
    throw new Error(translate(response.status, `${what} falló (HTTP ${response.status})`));
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
    // [T-2.36] Con doble fricción: identificador tecleado + código del cliente.
    mutationFn: ({ siteId, body }: { siteId: string; body: SiteRetire }) =>
      unwrap(
        retireSiteSitesSiteIdRetirePost({ path: { site_id: siteId }, body }),
        "El retiro de la estación",
        retireMessageFor,
      ),
    onSuccess: invalidate,
  });
}

export function useRetireGateway() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: ({ gatewayId, body }: { gatewayId: string; body: GatewayRetire }) =>
      unwrap(
        retireGatewayFleetGatewaysGatewayIdRetirePost({
          path: { gateway_id: gatewayId },
          body,
        }),
        "El retiro del gabinete",
        retireMessageFor,
      ),
    onSuccess: invalidate,
  });
}

/**
 * ¿El cliente tiene código de retiro configurado? [T-2.36]
 *
 * Se consulta ANTES de ofrecer el retiro: sin código el intento sería un 409 seguro,
 * y prometer un botón que siempre falla es exactamente lo que veta la regla de oro 7.
 * `null` mientras se resuelve o si la consulta falla — la UI dice "no se sabe", no
 * asume que sí.
 */
export function useRetireCodeConfigured(tenantId: string | null): boolean | null {
  const query = useQuery({
    queryKey: ["retire-code", tenantId],
    queryFn: async () => {
      const { data } = await getRetireCodeStateTenantsTenantIdRetireCodeGet({
        path: { tenant_id: tenantId as string },
      });
      return data ?? null;
    },
    enabled: tenantId !== null,
    staleTime: 300_000,
  });
  return query.data?.configured ?? null;
}

export function useCreateGateway() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: (body: GatewayCreate) =>
      unwrap(createGatewayFleetGatewaysPost({ body }), "El alta del gabinete"),
    onSuccess: invalidate,
  });
}

export function useUpdateGateway() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: ({ gatewayId, body }: { gatewayId: string; body: GatewayUpdate }) =>
      unwrap(
        updateGatewayFleetGatewaysGatewayIdPut({ path: { gateway_id: gatewayId }, body }),
        "La edición del gabinete",
      ),
    onSuccess: invalidate,
  });
}

export function useRestoreGateway() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    // Vuelve a `provisioned`, NO a `online`: el estado vivo lo demuestra el siguiente
    // heartbeat. Restaurar no lleva código de retiro — encender protección de más no
    // es el riesgo que la fricción vigila.
    mutationFn: (gatewayId: string) =>
      unwrap(
        restoreGatewayFleetGatewaysGatewayIdRestorePost({ path: { gateway_id: gatewayId } }),
        "La restauración del gabinete",
      ),
    onSuccess: invalidate,
  });
}

/**
 * Estado del config firmado de TODA la flota, en UNA consulta [T-2.37].
 *
 * Antes se abría una query por gabinete con `refetchInterval` de 10 s. La cadencia se
 * mantiene holgada porque el worker publica en menos de un minuto: refrescar más
 * rápido no adelanta nada y multiplica el tráfico.
 */
export function useFleetSyncStates(enabled: boolean): Map<string, GatewayConfigStateOut> {
  const query = useQuery({
    queryKey: ["fleet", "config-state"],
    queryFn: async () => {
      const { data, response } = await listGatewayConfigStatesFleetConfigStateGet();
      if (data === undefined) {
        throw new Error(`GET /fleet/config-state falló (${response.status})`);
      }
      return data;
    },
    enabled,
    refetchInterval: 30_000,
  });
  return new Map((query.data ?? []).map((s) => [s.gateway_id, s]));
}

export function useCreateSensor() {
  const invalidate = useInvalidateFleet();
  return useMutation({
    mutationFn: (body: SensorCreate) =>
      unwrap(createSensorSensorsPost({ body }), "El alta del sensor"),
    onSuccess: invalidate,
  });
}

/**
 * Historia de salud de 24 h por gabinete [T-2.38].
 *
 * Cadencia larga a propósito: es una tendencia, no un indicador vivo. El estado
 * instantáneo ya lo trae `/fleet/gateways` cada 30 s.
 */
export function useFleetHealth(enabled: boolean): Map<string, GatewayHealthOut> {
  const query = useQuery({
    queryKey: ["fleet", "health-history"],
    queryFn: async () => {
      const { data } = await fleetHealthHistoryFleetHealthHistoryGet({
        query: { hours: 24, bucket_min: 60 },
      });
      return data ?? [];
    },
    enabled,
    staleTime: 300_000,
    refetchInterval: 300_000,
  });
  return new Map((query.data ?? []).map((h) => [h.gateway_id, h]));
}
