import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@takab/sdk";

/*
 * [T-2.82] Etiquetas de cumplimiento del cliente.
 *
 * Se llama con el `client` de `@takab/sdk` en vez de con una función generada porque
 * el SDK se regenera en la integración, no aquí: los tipos de abajo son el contrato
 * de `api/src/takab_api/schemas/compliance.py` escrito a mano mientras tanto. Cuando
 * `shared/sdk-ts` se regenere, esto se sustituye por la función generada y los tipos
 * se importan de `@takab/sdk` — el resto del fichero no cambia.
 *
 * NADA de lo que se pinta se compone aquí: `notice`, `notes` y `title` los sirve el
 * servidor. Es deliberado. Las palabras con las que se presenta una afirmación
 * normativa las decide UN solo sitio (`takab_api.compliance.compliance_block`), el
 * mismo que las imprime en el dictamen PDF. Si la consola redactara las suyas,
 * pantalla y papel acabarían diciendo cosas distintas del mismo cliente — y el papel
 * lleva una firma debajo.
 */

/** Clases de afirmación admitidas. Espejo de `takab_api.compliance.CATALOG`. */
export const COMPLIANCE_CATALOG: Readonly<Record<string, string>> = {
  regulatory_framework: "Marco al que el cliente declara estar sujeto",
  internal_protocol: "Protocolo interno del cliente",
  third_party_certification: "Certificación emitida por un tercero",
  insurance_requirement: "Requisito de la aseguradora del cliente",
  contractual_obligation: "Obligación contractual del cliente",
};

export interface ComplianceClaim {
  key: string;
  title: string;
  claim: string;
  reference: string;
}

export interface ComplianceDoc {
  tenant_id: string;
  provenance: string;
  /** Deslinde PERMANENTE: acompaña al formulario mientras se teclea. */
  notice: string;
  items: ComplianceClaim[];
  /** Lo que hay que imprimir de ESTE documento, ya resuelto por el servidor. */
  notes: string[];
  unreadable: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface ComplianceClaimIn {
  key: string;
  claim: string;
  reference: string;
}

export interface ComplianceLabelsBody {
  items: ComplianceClaimIn[];
  base_updated_at: string | null;
}

/**
 * Sin relectura tras este umbral el documento pasa a DATOS RETENIDOS.
 *
 * No es un dato de campo, pero envejece igual: lo edita el dueño de la plataforma
 * desde otra sesión, y lo que aquí se muestra acaba impreso en un dictamen firmado.
 * Presentar como vigente una afirmación normativa retirada hace diez minutos es
 * exactamente lo que veta la regla de oro 7.
 */
export const COMPLIANCE_STALE_MS = 300_000;

const COMPLIANCE_FRESH_MS = 60_000;

export function complianceErrorMessage(status: number): string {
  switch (status) {
    case 403:
      return "SIN PERMISO · solo el dueño de la plataforma carga el marco declarado.";
    case 404:
      return "NO ENCONTRADO · el cliente no existe o no es visible para tu rol.";
    case 409:
      return "CAMBIÓ EN EL SERVIDOR · alguien editó el marco declarado. Recarga y reintenta.";
    case 422:
      return "AFIRMACIÓN INVÁLIDA · revisa la clase, el texto y la referencia citable.";
    default:
      return `/compliance-labels falló (HTTP ${status})`;
  }
}

function url(tenantId: string): string {
  return `/tenants/${tenantId}/compliance-labels`;
}

export interface ComplianceData {
  doc: ComplianceDoc | null;
  loading: boolean;
  error: string | null;
  /** Epoch ms del último dato fresco cuando YA es viejo; null = fresco. */
  staleSince: number | null;
  refetch: () => void;
}

export function useComplianceLabels(tenantId: string | null): ComplianceData {
  const query = useQuery({
    queryKey: ["compliance-labels", tenantId],
    queryFn: async (): Promise<ComplianceDoc> => {
      const { data, response } = await client.get<ComplianceDoc>({ url: url(tenantId as string) });
      if (data === undefined) {
        throw new Error(complianceErrorMessage(response.status));
      }
      return data;
    },
    enabled: tenantId !== null,
    staleTime: COMPLIANCE_FRESH_MS,
  });
  const age = Date.now() - query.dataUpdatedAt;
  return {
    doc: query.data ?? null,
    loading: tenantId !== null && query.isPending,
    error: query.error ? query.error.message : null,
    staleSince:
      query.dataUpdatedAt > 0 && age > COMPLIANCE_STALE_MS ? query.dataUpdatedAt : null,
    refetch: () => void query.refetch(),
  };
}

export interface ComplianceMutation {
  save: (body: ComplianceLabelsBody) => void;
  pending: boolean;
  error: string | null;
}

export function useSaveComplianceLabels(tenantId: string | null): ComplianceMutation {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (body: ComplianceLabelsBody): Promise<ComplianceDoc> => {
      const { data, response } = await client.put<ComplianceDoc>({
        url: url(tenantId as string),
        body,
      });
      if (data === undefined) {
        throw new Error(complianceErrorMessage(response.status));
      }
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["compliance-labels", tenantId] });
    },
  });
  return {
    save: (body) => mutation.mutate(body),
    pending: mutation.isPending,
    error: mutation.error ? mutation.error.message : null,
  };
}
