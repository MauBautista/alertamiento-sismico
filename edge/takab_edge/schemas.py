"""Contratos versionados: genera JSON Schema de los modelos Pydantic del edge.

Contracts-first ([ANALISIS-00], blueprint §0.1): la nube y los simuladores validan
contra estos schemas versionados (`shared/schemas/`), generados de los modelos Pydantic
del edge — que son la fuente de verdad. Como los payloads se construyen SIEMPRE como
esos modelos (validados por Pydantic al instanciar), la conformidad es por construcción;
`tests/test_schemas.py` falla si un modelo cambia sin regenerar el schema (anti-drift).

Regenerar: `uv run --directory edge python -m takab_edge.schemas`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from takab_edge.contracts import (  # noqa: I001
    ActuationRecord,
    ActuatorAck,
    BackfillRequest,
    CommandAck,
    EvidenceObject,
    Feature1s,
    FeatureBatch,
    HealthSnapshot,
    LocalEvent,
    SecondaryCabinetState,
    TierTransition,
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
#: 1.12.0 (T-2.70): ActuatorAction + `update_activate`/`update_rollback` (canal
#: `system`). Ninguna de las dos lleva código: el artefacto viaja por `deploy.sh`
#: y queda INERTE en `releases/<id>/`; lo que la nube ordena es ESTRENARLO, que
#: es lo único que un canary por cohortes necesita gobernar. ADITIVO: enum
#: ampliado, un payload 1.11.0 sigue validando, y un gabinete viejo que reciba
#: uno de los dos lo rechaza con ack —`ActuatorAction(payload["action"])` truena
#: y el dispatcher descarta— en vez de hacer algo a medias.
#: 1.13.0 (T-2.86.a): + actuation_record (bitácora de actuación del gabinete,
#: topic takab/audit). ADITIVO: familia NUEVA, ningún contrato existente cambia y
#: todo payload 1.12.0 sigue validando. Un gabinete ≤1.12.0 simplemente no publica
#: en ese topic — su bitácora se queda en disco, que es donde estaba antes de esta
#: ficha, y la nube no le atribuye un vacío que no declaró.
#: 1.14.0 (T-3.11.b): `backfill_request.mode` gana `cctv_clip` y `cctv_still`. ADITIVO:
#: enum ampliado, un payload 1.13.0 sigue validando, y un gabinete viejo no emite ninguno
#: de los dos. Va por el contrato y el topic que YA existen a propósito: un topic MQTT
#: nuevo obliga a tocar la política fleet de AWS IoT, y un topic no autorizado desconecta
#: al gabinete en cada publish (medido el 2026-07-12). Ampliar un enum no toca terraform.
#: Ojo al lado de la nube: `canonical_key` DEBE crecer con el enum — un `mode` que el
#: esquema acepta y la nube no sabe convertir en key devuelve «payload inválido» y el
#: gabinete se queda esperando un grant que no llega.
#: 1.15.0 (T-7.05·H-1): sube por TRES cambios de contrato que ya estaban en el árbol
#: y que viajaron bajo el número anterior. Eso último es el defecto que esta versión
#: cierra, y merece nombre propio: el 2026-09-10 un latido de arranque de `gw-dev-0001`
#: acabó en `takab-dev-dlq-telemetry` porque el gabinete corría el esquema relajado y la
#: nube seguía sirviendo la imagen con el estrecho — y **los dos ficheros decían
#: `1.14.0`**, así que el desfase era indetectable por construcción. Lo que cambió:
#:   · `health_snapshot.packet_loss_pct` admite `null` (`d67d079`, T-5.24, 2026-09-03).
#:     RELAJACIÓN: un payload 1.14.0 sigue validando contra 1.15.0, pero **al revés no**
#:     — una nube ≤1.14.0 rechaza el `null`, que es exactamente lo que pasó. Un consumidor
#:     viejo con un emisor nuevo es el sentido peligroso de este cambio.
#:   · `actuation_record.ActuationCause` gana `lan_drill_voice` (`a3413eb`, T-5.17).
#:     ADITIVO: enum ampliado.
#:   · `lora_secondary_state` gana `pending` (`ce1db6d`, T-5.25). ADITIVO: clave opcional.
#: La guarda que impide repetirlo está abajo: `HUELLA_POR_VERSION`.
#:
#: 1.16.0 — ADITIVO: nace `tier_transition` (`T-7.30`). Es el hecho que le faltaba
#: a la nube para saber que la sacudida TERMINÓ: hasta ahora el gabinete no
#: publicaba nada al volver a `normal` y `rule_evaluations` no la escribía nadie,
#: así que un sismo real no podía producir jamás la fase `shaking_concluded` — el
#: teléfono se quedaba en la pantalla de crisis contando (medido con el WR-1 el
#: 2026-09-12). Viaja por `takab/events`, discriminado por `kind`, para NO abrir
#: topic: uno nuevo obliga a tocar la política de fleet y un topic no autorizado
#: desconecta al gabinete en cada publish. Un consumidor 1.15.0 ignora el mensaje
#: nuevo (no lo entiende, no lo rompe); el sentido peligroso sería el contrario.
SCHEMA_VERSION = "1.16.0"

#: Familias de payload que cruzan edge→nube (features, eventos, health, ACK).
MODELS: dict[str, type[BaseModel]] = {
    "waveform_packet": WaveformPacket,
    "feature_1s": Feature1s,
    "feature_batch": FeatureBatch,  # T-1.56: lote de tier normal (takab/features/batch)
    "local_event": LocalEvent,
    "tier_transition": TierTransition,  # T-7.30: la sacudida terminó (takab/events)
    "health_snapshot": HealthSnapshot,
    "actuator_ack": ActuatorAck,
    "command_ack": CommandAck,  # T-1.23: ack de comando remoto (takab/acks)
    "backfill_request": BackfillRequest,  # T-1.25: solicitud de URL pre-firmada
    "evidence_object": EvidenceObject,
    "lora_secondary_state": SecondaryCabinetState,  # T-2.33: gabinete secundario LoRa
    "actuation_record": ActuationRecord,  # T-2.86.a: bitácora del gabinete (takab/audit)
}


def schema_for(name: str, model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://takab.mx/schemas/{name}/v{SCHEMA_VERSION}"
    schema["version"] = SCHEMA_VERSION
    return schema


def huella_del_contenido() -> str:
    """SHA-256 de lo que los esquemas DICEN, ignorando `$id` y `version`.

    Es la guarda contra el defecto que costó el incidente del 2026-09-10: entre
    `1.14.0` y `1.15.0` tres contratos cambiaron sin que el número se moviera, así
    que gabinete y nube podían servir esquemas distintos declarando el mismo. La
    versión no se defiende sola —es un literal que nadie está obligado a tocar—;
    esto la ata al contenido.

    Se excluyen `$id` y `version` a propósito: si entraran, la huella cambiaría al
    subir la versión y la comprobación sería circular (cualquier bump la
    «arreglaría»). Lo que se quiere es lo contrario: **tocar un contrato sin subir
    la versión rompe**, y la única salida cómoda es subirla y anotar el porqué en
    el registro de arriba.
    """
    h = hashlib.sha256()
    for name in sorted(MODELS):
        cuerpo = schema_for(name, MODELS[name])
        cuerpo.pop("$id", None)
        cuerpo.pop("version", None)
        h.update(name.encode())
        h.update(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()


#: Huella del contenido por versión declarada. Añadir una entrada es el gesto que
#: `edge/tests/test_schemas.py` obliga a hacer cuando un contrato cambia: pisar la
#: huella de una versión ya publicada en vez de añadir la nueva es posible, pero es
#: un acto explícito y revisable, con el registro de cambios dos pantallas arriba.
#: Se guardan también las anteriores: son el registro de qué se publicó bajo cada
#: número, que es justo lo que no existía cuando el desfase pasó desapercibido.
HUELLA_POR_VERSION: dict[str, str] = {
    "1.15.0": "11d28237b98491a9eaaf1fb600ed88c74a38d31ae3d5c36bc9bb07c0f66a57b0",
    "1.16.0": "1c0bcb6f44a608b2f923f6b195b5bbd8e1f546bb9f8be611bc82c239db71bf17",
}


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
