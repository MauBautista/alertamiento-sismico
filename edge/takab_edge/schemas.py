"""Contratos versionados: genera JSON Schema de los modelos Pydantic del edge.

Contracts-first ([ANALISIS-00], blueprint §0.1): la nube y los simuladores validan
contra estos schemas versionados (`shared/schemas/`), generados de los modelos Pydantic
del edge — que son la fuente de verdad. Como los payloads se construyen SIEMPRE como
esos modelos (validados por Pydantic al instanciar), la conformidad es por construcción;
`tests/test_schemas.py` falla si un modelo cambia sin regenerar el schema (anti-drift).

Regenerar: `uv run --directory edge python -m takab_edge.schemas`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from takab_edge.contracts import (
    ActuatorAck,
    BackfillRequest,
    CommandAck,
    EvidenceObject,
    Feature1s,
    FeatureBatch,
    HealthSnapshot,
    LocalEvent,
    SecondaryCabinetState,
    WaveformPacket,
)

#: Versión de los contratos publicados (semver). Súbela ante cambios incompatibles.
#: 1.1.0 (T-1.40): health_snapshot honesto — ntp_offset_s/battery_pct/
#: cert_days_remaining nullable («sin dato»), + mqtt_rtt_ms, ups_status default
#: unknown. Aditivo/relajante: un payload 1.0.0 sigue validando contra 1.1.0.
#: 1.2.0 (T-1.53): health_snapshot + disk_used_pct nullable (panel LAN). ADITIVO:
#: el ingest de la nube ignora la clave (sin columna destino) y un payload 1.1.0
#: sigue validando contra 1.2.0.
#: 1.3.0 (T-1.56): + feature_batch (batcheo escalonado por tier, topic
#: takab/features/batch). ADITIVO: familia nueva; todo payload 1.2.0 sigue
#: validando y la nube acepta feature_1s suelto indefinidamente.
#: 1.4.0 (T-1.59): ActuatorChannel + `system`, ActuatorAction + `self_test`,
#: CommandAck + `results` nullable (autodiagnóstico del gabinete). ADITIVO:
#: enums ampliados y clave opcional — payloads 1.3.0 siguen validando.
#: 1.5.0 (T-1.60): ActuatorAction + `drill_start`/`drill_stop` (simulacro
#: institucional por canal `system`). ADITIVO.
#: 1.6.0 (T-1.74): HealthSnapshot + `fw_version` — el gabinete DECLARA qué código
#: corre en vez de que alguien lo anote en `gateways.fw_version`. ADITIVO: clave
#: opcional, un payload 1.5.0 sigue validando y la nube trata su ausencia como
#: «sin dato» (no pisa lo que ya tenga).
#: 1.7.0 (T-2.22): HealthSnapshot + `ups_runtime_s` — la autonomía del UPS que
#: `UpsReading` ya medía deja de perderse. ADITIVO: clave opcional nullable; un
#: payload 1.6.0 sigue validando y la nube persiste su ausencia como NULL
#: (`battery_min_left` deja de ser siempre NULL).
#: 1.8.0 (T-2.33): + lora_secondary_state (estado por gabinete secundario LoRa,
#: sección ``lora`` del panel; ancla del firmware ESP32). ADITIVO: familia nueva.
#: 1.9.0 (T-2.70): HealthSnapshot + `fw_running` — el SHA que el PROCESO cargó al
#: arrancar, junto al `fw_version` del DISCO que ya viajaba. Las dos juntas son lo
#: único que responde «¿se aplicó la actualización?»: el disco cambia con el
#: `rsync`, el proceso solo con el reinicio. ADITIVO: clave opcional nullable; un
#: payload 1.8.0 sigue validando y la nube trata su ausencia como «sin dato».
#: 1.10.0 (T-2.70.a·B1): HealthSnapshot · `relays` pasa a ser NULLABLE. `null` =
#: «no pude preguntar al dueño de los pines»; `[]` sigue siendo «pregunté y no
#: hay filas» (módulo detenido). Hasta D3 la distinción no hacía falta porque el
#: dueño vivía en el mismo proceso; desde que `takab-gpio` es un proceso aparte,
#: `gpio_owner=gpio` con ese proceso caído deja al edificio sin sirena, sin
#: cierre de gas, sin retorno de ascensores y sin retenedores mientras
#: `takab-edge` late como si nada — y fundido con `[]` la nube lo leía como
#: «módulo detenido», que es benigno. RELAJANTE, no rompedor: todo payload 1.9.0
#: (`[]` o lista con filas) sigue validando contra 1.10.0. Lo que un gabinete
#: ≤1.9.0 NO puede emitir es el `null`, así que la nube nunca le atribuye el
#: rótulo grave por error — su `[]` aterriza como el hecho neutro de siempre.
#: 1.11.0 (T-2.116): ActuatorAck y CommandAck + `channel_state` — el ESTADO DEL
#: CANAL tras el arbitraje de demandas, que la spec móvil §2.2 exige desde el
#: día uno («el resultado real llega en el `command_ack` con el estado
#: recalculado del relé») y que no existía en ningún contrato. Los acks decían
#: `success=true` + `detail="relay"`, o sea «la orden se ejecutó», y eso NO es
#: «el relé cambió»: un `deactivate` de sirena con la alerta vigente retira la
#: demanda manual con éxito y la sirena sigue sonando. ADITIVO y nullable: clave
#: opcional, un payload 1.10.0 sigue validando, y `null` significa «no pude
#: preguntar al dueño de los pines» (BACnet, costura caída, ack de rechazo sin
#: ejecución) — nunca «el relé está en reposo». Un gabinete ≤1.10.0 no lo emite,
#: así que la nube nunca le atribuye un estado que no declaró.
SCHEMA_VERSION = "1.11.0"

#: Familias de payload que cruzan edge→nube (features, eventos, health, ACK).
MODELS: dict[str, type[BaseModel]] = {
    "waveform_packet": WaveformPacket,
    "feature_1s": Feature1s,
    "feature_batch": FeatureBatch,  # T-1.56: lote de tier normal (takab/features/batch)
    "local_event": LocalEvent,
    "health_snapshot": HealthSnapshot,
    "actuator_ack": ActuatorAck,
    "command_ack": CommandAck,  # T-1.23: ack de comando remoto (takab/acks)
    "backfill_request": BackfillRequest,  # T-1.25: solicitud de URL pre-firmada
    "evidence_object": EvidenceObject,
    "lora_secondary_state": SecondaryCabinetState,  # T-2.33: gabinete secundario LoRa
}


def schema_for(name: str, model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://takab.mx/schemas/{name}/v{SCHEMA_VERSION}"
    schema["version"] = SCHEMA_VERSION
    return schema


def output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "shared" / "schemas"


def generate() -> None:
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        text = json.dumps(schema_for(name, model), indent=2, ensure_ascii=False) + "\n"
        (out / f"{name}.schema.json").write_text(text)
    print(f"generados {len(MODELS)} schemas v{SCHEMA_VERSION} en {out}")


if __name__ == "__main__":
    generate()
