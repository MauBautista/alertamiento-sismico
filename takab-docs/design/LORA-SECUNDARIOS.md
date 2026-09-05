# LORA-SECUNDARIOS — Contrato v1 del enlace a gabinetes secundarios (T-2.33)

> Documento canónico del protocolo entre el gabinete principal (Raspberry Pi 4,
> módulo `edge/takab_edge/lora/`) y los gabinetes secundarios (ESP32 + LoRa +
> estrobos + sirena/bocina). El firmware ESP32 futuro se ancla a los VECTORES
> DORADOS de este documento (espejo de `edge/tests/test_lora_frame.py`).
> Cambiar el layout de la trama exige `ver=0x02` y romper esos tests a propósito.

## 1. Qué es un gabinete secundario

Un espejo de sirena/estrobo instalado LEJOS del gabinete principal (otra nave,
azotea, patio) donde no llega LAN/WiFi. Se comunica por **LoRa 915 MHz (ISM
México)** — largo alcance, baja tasa. **Jamás gatea nada**: recibe la orden de
alarma cuando el principal ACTÚA (SASMEX o comando firmado de quórum — la
detección instrumental local es solo aviso desde T-2.32), reporta su salud por
heartbeat, y su ausencia se hace VISIBLE en el panel (regla de oro 7) sin
afectar la protección del edificio principal.

Hardware previsto por secundario: placa ESP32+LoRa (Heltec/TTGO o similar,
915 MHz), relé de estrobo, relé de sirena/bocina, alimentación con batería
respaldada (el heartbeat reporta mV). El principal usa OTRA placa ESP32+LoRa
como **módem** colgado del USB del Pi (`/dev/ttyUSB0`).

## 2. Trama v1 (fija, 29 bytes)

| off | len | campo        | notas |
|-----|-----|--------------|-------|
| 0   | 1   | `ver`        | `0x01` |
| 1   | 1   | `msg_type`   | 1=HEARTBEAT · 2=ALARM_ACT · 3=ALARM_CLEAR · 4=ACK · 5=TEST · 6=SILENCE |
| 2   | 2   | `cabinet_id` | u16 BE — emisor (uplink) / destino (downlink); sin broadcast: unicast por clave |
| 4   | 4   | `session`    | u32 BE — aleatoria al boot del EMISOR |
| 8   | 4   | `seq`        | u32 BE — contador monótono dentro de la sesión |
| 12  | 1   | `flags`      | bit0=siren · bit1=strobe · bit2=alarm_active · bit3=test |
| 13  | 2   | `battery_mv` | u16 BE — 0 = sin dato (solo uplink) |
| 15  | 4   | `arg`        | u32 BE — ACK: `seq` confirmado; resto 0 |
| 19  | 10  | `hmac`       | `HMAC-SHA256(k_cab, b"lora-v1" + trama[0:19])[:10]` |

- **Claves**: una clave de sitio (`TAKAB_EDGE_LORA_KEY` en el Pi; grabada en el
  ESP32 en aprovisionamiento) de la que se DERIVA la clave por gabinete:
  `k_i = HMAC-SHA256(site_key, b"lora-cab" + id_be16)` (32 B). Un ESP32
  comprometido no expone la clave de sitio ni las de sus hermanos.
- **Anti-replay SIN RTC**: el receptor guarda `(session, max_seq)` por gabinete.
  Misma sesión ⇒ `seq` estrictamente creciente; sesión nueva (boot) resetea el
  contador. Nada se persiste. El replay cruzado cae porque la sesión va firmada.
- **Semántica**: `ALARM_ACT` (flags siren/estrobo) **enciende** —suma, no pisa— y
  `alarm_active` queda hasta `ALARM_CLEAR`; `TEST` destella el estrobo SIN sirena
  y no cambia `alarm_active` ni los relés enclavados; `SILENCE` **corta los
  audibles y solo eso** (deja el estrobo, no toca `alarm_active`); todo downlink
  se responde con `ACK` (`arg` = seq recibido); `HEARTBEAT` cada 90 s ± 10 s de
  jitter (ALOHA) con `battery_mv` y el bit `alarm_active` real del secundario.
- **`SILENCE` es un tipo propio y no un `ALARM_ACT` sin el bit de sirena** (T-5.25).
  Las dos razones apuntan al mismo sitio, el peor: (1) este documento dice que
  `ALARM_ACT` *enciende*, así que un firmware escrito contra esa frase engancha la
  sirena y no la suelta con otro `ALARM_ACT`; (2) en el emisor del Pi, dos
  `ALARM_ACT` seguidos SUMAN flags a propósito —los comandos de red llegan por
  canal separado—, de modo que un silencio disfrazado de activación se lo tragaría
  la fusión. La ambigüedad caía del lado de «la sirena sigue sonando».
  Es **aditivo sobre v1**: el layout no cambia y `ver` sigue en `0x01`. Un firmware
  que no conozca el tipo 6 lo rechaza y **no ackea** ⇒ el panel del principal
  declara `SIGUE SONANDO · SILENCIO SIN CONFIRMAR`, que es la verdad y no un
  silencio fingido.

## 3. Vectores dorados (paridad byte-exacta con el firmware)

Con `site_key = b"clave-lora-de-sitio-0123456789ab"` y `cabinet_id = 258`:

```
k_258 = d6d04c86c73040548bb923c24d63251cd04892bb4499069f4fd8ba36faee71ea

HEARTBEAT  (session=0xDEADBEEF, seq=7, flags=alarm_active, battery=3870 mV):
01010102deadbeef00000007040f1e00000000695d15496a56fb0c166e

ALARM_ACT  (session=0x01020304, seq=41, flags=siren|strobe):
010201020102030400000029030000000000006c664dc3f5fa446c1343

ACK        (session=0xDEADBEEF, seq=8, arg=41):
01040102deadbeef0000000800000000000029e6134d8ef72a36d5a18b

SILENCE    (session=0x01020304, seq=42, flags=alarm_active|strobe):
01060102010203040000002a06000000000000c1175ce1d77c84bbd9e7
```

## 4. Bridge módem ↔ Pi (NDJSON por USB-serial, 115200)

La trama LoRa viaja como hex DENTRO de una línea JSON (depurable con minicom;
trivial en ArduinoJson). La seguridad vive en la trama, no en el bridge.

```
Pi → módem : {"t":"tx","p":"<29 bytes hex>"}
módem → Pi : {"t":"rx","p":"<29 bytes hex>","rssi":-97,"snr":7.5}
```

El módem es tonto a propósito: transmite lo que le dan y reporta lo que oye con
su RSSI/SNR medidos. Sin claves en el módem.

## 5. Disciplina de aire

- Heartbeat uplink: cada 90 s con jitter ±10 s por secundario (ALOHA; N ≤ 8).
- Órdenes downlink: unicast por gabinete, repeat-until-ACK con espaciado 2 s y
  tope 5 intentos; el panel muestra `SIN ACK` si el tope se agota (transición
  logueada una vez, regla de oro 10).
- Heartbeat ausente > 3 × periodo ⇒ `ENLACE PERDIDO` en el panel. El jamming es
  indetenible por diseño de RF: se hace VISIBLE; la sirena primaria es local y
  no depende del enlace.
- 915 MHz ISM MX no impone el duty-cycle del 1 % de EU868; este diseño lo
  cumpliría de sobra (≈0.03 % por secundario a SF10).

## 6. Notas para el firmware ESP32 (futuro)

- RadioLib (SX1276/SX1262) a 915 MHz, SF10/125 kHz sugerido de arranque; medir
  alcance real en sitio antes de fijar SF.
- El mismo códec de la §2 en C (struct empacada + mbedTLS HMAC-SHA256): validar
  contra los vectores de la §3 en el test de firmware.
- `session` = `esp_random()` al boot; `seq` en RAM (el guard del Pi resetea con
  la sesión nueva — nada que persistir en flash).
- Watchdog de alarma: si `alarm_active` y no llega `ALARM_CLEAR` ni heartbeat-ack
  del principal en N minutos, el firmware DECIDE en sitio (política por
  definir con Protección Civil: sostener vs apagar tras ventana fija).
- **Los relés se modelan como estado enclavado, no como «la última orden»** (T-5.25):
  `ALARM_ACT` enciende lo que traiga en flags sin apagar lo demás; `SILENCE` apaga
  la sirena y deja el estrobo; `ALARM_CLEAR` apaga los dos; `TEST` no toca ninguno.
  La especificación ejecutable de esas cuatro reglas vive en
  `edge/simulators/lora.py::FakeSecondaryCabinet` y la ejercitan los tests de
  `edge/tests/test_lora_link.py` — el firmware en C debería pasar los mismos casos.
- **Un `SILENCE` que el firmware no entienda NO debe ackearse.** Ackear lo que no
  se ejecutó le diría al principal que el edificio calló mientras esa sirena sigue
  sonando, y es peor que rechazarlo: el operador se iría convencido.
- Aprovisionamiento: grabar `site_key` + `cabinet_id` por puerto serie en banco;
  el alta en el Pi es añadir el par a `TAKAB_EDGE_LORA__SECONDARIES`.

## 7. Fuera de alcance (futuro)

- Aprovisionamiento de secundarios desde la NUBE (hoy: `edge.env` del Pi).
- Salud de secundarios hacia la nube (`device_health` no tiene jsonb; el panel
  local ya la muestra — decidir tabla/columnas cuando haya flota real).
- Mesh/repetidores LoRa y OTA del firmware.
