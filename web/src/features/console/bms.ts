// [T-2.08] La agrupación BMS vive en @takab/sdk (compartida con el dashboard
// táctico móvil — criterio 2.1: cero transformaciones divergentes). Re-export
// para que los consumidores de la consola no cambien de import.
//
// [T-2.119] `channelEvidence` y `ACTUATOR_CHANNELS` salen por aquí por el mismo
// motivo: el estado de gas, ascensores y puertas se deriva UNA vez, con la
// polaridad fail-safe de cada canal, y las dos superficies leen esa.
export {
  ACTION_STATE,
  ACTUATOR_CHANNELS,
  CHANNEL_LABEL,
  channelEvidence,
  groupActions,
  sirenEvidence,
  type ActionStateView,
  type ActuatorChannelSpec,
  type ActuatorGroup,
  type ChannelEvidence,
} from "@takab/sdk";
