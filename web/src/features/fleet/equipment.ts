// Catálogo de actuadores declarables por gabinete (T-2.31, extraído en T-2.37).
//
// Vive aparte porque lo comparten DOS formularios: el alta (`HardwareForm`) y la
// edición (`GatewayForm`). Duplicarlo dejaría a uno de los dos desincronizado el día
// que cambie el contrato.
//
// El conjunto NO es libre: es exactamente el de `ActuatorChannel` del edge. Un canal
// nuevo aquí, sin su pin GPIO, su modo fail-safe y su lugar en la secuencia de tier
// del Pi, aparecería como "instalado" en la consola sin que el gabinete pueda
// accionarlo jamás — dato falso, regla de oro 7.

import type { EquipmentProfile } from "@takab/sdk";

export const EQUIPMENT_FIELDS = [
  { key: "siren", label: "SIRENA" },
  { key: "strobe", label: "ESTROBO" },
  { key: "gas_valve", label: "VÁLVULA DE GAS" },
  { key: "elevator", label: "ASCENSORES" },
  { key: "door_retainer", label: "RETENEDORES DE PUERTA" },
] as const;

/** Todo instalado: el default del DDL (compat con la flota anterior a T-2.31). */
export const EQUIPMENT_ALL: Required<EquipmentProfile> = {
  siren: true,
  strobe: true,
  gas_valve: true,
  elevator: true,
  door_retainer: true,
};

/** Normaliza lo que venga del servidor al contrato completo de 5 booleanos. */
export function equipmentOf(
  value: EquipmentProfile | null | undefined,
): Required<EquipmentProfile> {
  return { ...EQUIPMENT_ALL, ...(value ?? {}) };
}
