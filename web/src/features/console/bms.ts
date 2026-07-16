// [T-2.08] La agrupación BMS vive en @takab/sdk (compartida con el dashboard
// táctico móvil — criterio 2.1: cero transformaciones divergentes). Re-export
// para que los consumidores de la consola no cambien de import.
export {
  ACTION_STATE,
  CHANNEL_LABEL,
  groupActions,
  type ActionStateView,
  type ActuatorGroup,
} from "@takab/sdk";
