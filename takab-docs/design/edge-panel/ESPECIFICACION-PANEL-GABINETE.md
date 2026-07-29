# ESPECIFICACIÓN DE DISEÑO · Panel local del gabinete TAKAB Ailert

> **Destinatario:** Claude Design.
> **Objetivo:** rediseñar por completo la pantalla local del gabinete sísmico — la interfaz que
> ve el encargado del edificio, servida por el Raspberry Pi dentro del gabinete, en la red local
> del inmueble, **sin internet**.
> **Fecha:** 2026-07-29 · **Repo:** `MauBautista/alertamiento-sismico` · **Idioma de la UI:** español.
>
> Este documento es **autocontenido**: describe el producto, el hardware real, los datos que
> existen, los que faltan, las restricciones que no se negocian y el vocabulario visual ya
> establecido. Todo dato técnico citado aquí fue verificado contra el código en la fecha de
> arriba; donde algo no existe todavía, se dice explícitamente.
>
> **Entrega esperada:** el diseño (HTML/CSS/JSX + capturas) en esta misma carpeta
> `takab-docs/design/edge-panel/`, siguiendo la convención de `takab-docs/design/app/`.

---

## §0 · Qué es TAKAB Ailert

**TAKAB Ailert** es una plataforma SaaS multi-tenant de **alertamiento sísmico, monitoreo
estructural y continuidad operativa post-sismo** para Protección Civil, gobierno e instalaciones
críticas en México: hospitales, universidades, industria, corporativos.

Hace tres cosas:

1. **Alerta** en segundos, con el sistema oficial mexicano **SASMEX** como canal primario y
   detección instrumental local como respaldo.
2. **Actúa sola** en el sitio: suena la sirena, cierra válvulas de gas, retorna ascensores a
   planta baja, libera retenedores de puerta.
3. **Dictamina y coordina** después del sismo: evidencia instrumental, triage estructural,
   continuidad operativa.

**Arquitectura híbrida edge + cloud.** Un **gabinete físico por edificio** (el "edge") hace la
detección y la actuación; la nube (AWS) coordina la flota, guarda evidencia, notifica y sirve la
consola SOC web y la app móvil.

**Límite de responsabilidad, textual del blueprint:** TAKAB entrega un *dictamen operativo
preliminar* y *riesgo instrumental*; **no sustituye la evaluación estructural formal ni certifica
reingreso seguro sin firma de ingeniería**. Es principio de diseño, no disclaimer decorativo — y
debe notarse en el tono de la interfaz: esta pantalla informa y ejecuta, no dictamina.

### El principio que gobierna todo

> **El gabinete se protege solo.** Si se cae internet, si se cae AWS, si se cae la consola web —
> el edificio sigue detectando, sigue sonando la sirena y sigue cerrando el gas. La nube coordina;
> **nunca** está en la ruta crítica de actuación.

De ahí sale la restricción más importante para tu diseño: **esta pantalla tiene que verse
perfecta sin un solo byte de internet.** Sin CDN, sin Google Fonts, sin tiles de mapa, sin
ninguna petición fuera de la LAN del edificio. Hay un test automatizado que rompe el build si
aparece `https://`, `http://`, `cdn.` o `googleapis` en el HTML. No es una preferencia: es la
diferencia entre proteger un hospital y no protegerlo.

---

## §1 · El hardware real dentro del gabinete

| Pieza | Realidad verificada |
|---|---|
| **Sensor sísmico** | **Raspberry Shake RS4D** — un geófono vertical (`EHZ`) + un acelerómetro MEMS de 3 ejes (`ENZ`, `ENN`, `ENE`) = **4 canales a 100 muestras/segundo**. Expone SeedLink por TCP 18000. Red FDSN `AM`, estación real `R4F74`. Su sistema operativo **no se toca**: es solo sensor. |
| **Cerebro** | **Raspberry Pi 4 Model B Rev 1.5.** Corre todo el software de TAKAB. Tiene jack de 3.5 mm funcional (se usa para sirena por audio). |
| **Alerta oficial** | Receptor **SASMEX WR-1**. Tiene dos relevadores; **solo se cablea el Relevador 2** ("Alerta Sísmica Oficial") al pin **BCM 16** del Pi. Su salida es un **contacto seco = un booleano puro**. No transporta magnitud, ni epicentro, ni tiempo de llegada. |
| **Actuadores** | 5 relés: `siren` · `strobe` · `gas_valve` · `elevator` · `door_retainer` |
| **Respaldo** | UPS con monitoreo (reporta modo y carga) · NVMe 64 GB con buffer sísmico de 7–14 días · reloj RTC DS3231 + `chrony` |
| **Red** | Ethernet obligatorio. Wi-Fi integrado prohibido. |
| **Mitigación de falla única** | Un **relé de potencia en paralelo** conecta el WR-1 directo a la sirena: **suena aunque el Pi esté muerto**. Es la protección más importante del sistema. |

### Estados seguros de cada relé (importan visualmente)

| Canal | Etiqueta ES | Fail-safe | Qué significa que falle |
|---|---|---|---|
| `siren` | **SIRENA** | `NO` (normalmente abierto) | Si falla, **no** queda sonando |
| `strobe` | **ESTROBO** | `NO` | Igual |
| `gas_valve` | **GAS** | `fail_close` | Si falla, **cierra** el gas |
| `elevator` | **ASCENSORES** | `NO` | — |
| `door_retainer` | **PUERTAS** | `NC` (normalmente cerrado) | Si falla, **libera** las puertas |

El panel debe distinguir tres cosas por relé, no dos: **`ACTIVADO`** (demanda lógica de
protección), **`ENERGIZADO`** (estado eléctrico real del relé) y **`REPOSO`**. En un canal
`fail_close` o `NC`, energizado y activado son opuestos — colapsarlos sería mentir.

### Números reales medidos (úsalos, son la evidencia de que el sistema funciona)

- **Reflejo SASMEX → relé: 6.65 ms medidos** con hardware real. Presupuesto p95 < 100 ms.
- Cruce de umbral → actuación: presupuesto p95 < 200 ms.
- Movimiento del suelo → actuación: objetivo ≤ 2 s (dominado por la ventana de agregación de 1 s).
- **Piso de ruido del sensor en reposo: 0.6–1.1 mg** (miligravedades). Ese es el "silencio".
- Excitación real registrada en pruebas: **PGA 0.567 g** en `ENZ`, con STA/LTA saturado en 10.0.
- Deriva del reloj sin NTP: ±2 ppm ≈ 0.17 s/día.

---

## §2 · Quién mira esta pantalla

**Hallazgo que cambia el enfoque de diseño: el panel local no tiene login, ni cuentas, ni roles.**

La consola web del SOC tiene 10 roles con Cognito y MFA. El panel del gabinete **no tiene nada de
eso**. Su modelo de acceso es doble barrera física:

1. **Estar en la LAN del edificio.** No hay ruta desde internet.
2. **Un PIN de 6 dígitos** en la cabecera `X-Takab-Pin` para **cualquier acción**.

**La lectura es abierta.** Cualquiera en la red del edificio abre la IP del Pi y ve todo el
estado, sin autenticarse. Textual del código: *"es el panel del guardia"*. El PIN solo protege
las acciones (silenciar, probar, resetear).

El PIN lo genera el script de aprovisionamiento y **se imprime una sola vez** — esa impresión
es la entrega física al responsable del edificio. Bloqueo: 5 PINs erróneos ⇒ 60 s bloqueado.

### Los cuatro perfiles reales (el panel no los distingue; tu diseño puede, por jerarquía visual)

| Quién | Qué necesita responder | En cuánto tiempo |
|---|---|---|
| **Guardia de caseta** | *¿Estamos bien o no?* | 1 segundo, a 5 metros de distancia, de reojo |
| **Responsable del edificio** | *¿Qué pasó, qué hizo el sistema, y qué apago?* | 10 segundos, con el PIN en la mano |
| **Brigadista** | *¿Sonó de verdad? ¿Qué tan fuerte sacudió? ¿Qué actuadores se movieron?* | 30 segundos, durante la crisis |
| **Técnico de instalación** | *¿El sensor mide? ¿El enlace sube? ¿Los cinco relés responden?* | Varios minutos, en cuclillas junto al gabinete |

Los cuatro miran **la misma URL**. El diseño debe servirle al guardia sin estorbarle al técnico.

---

## §3 · Las cuatro superficies y los tres modos de densidad

La pantalla se consume en cuatro contextos, confirmados por el cliente:

1. **Monitor fijo en sitio** — pantalla dedicada montada cerca del gabinete o en la caseta de
   vigilancia, encendida 24/7, se lee a distancia.
2. **Laptop o PC por LAN** — el encargado se conecta a la IP del Pi cuando necesita revisar.
3. **Tablet o celular en sitio** — técnico de campo junto al gabinete durante instalación,
   pruebas y mantenimiento.
4. **Proyección a sala de control / SOC** — replicada en pantalla grande.

**Recomendación de arquitectura de vista: una sola página responsive con tres densidades**, no
tres aplicaciones distintas. Declara los breakpoints explícitamente en tu entrega.

| Modo | Contexto | Carácter |
|---|---|---|
| **MURO** | Monitor fijo, proyección al SOC | **Solo lectura.** Tipografía enorme, legible a 5 m. El estado y las ondas dominan la pantalla. Cero interacción fina. Nada que requiera leer 11 px. |
| **CONSOLA** | Laptop por LAN, 1280–1920 px | **Densidad máxima.** Ondas + mapa + estadística + salud + acciones simultáneas. Objetivo: sin scroll vertical en 1080p. |
| **CAMPO** | Tablet / celular junto al gabinete | **Táctil, acción primero.** Una columna, botones grandes, la botonera de prueba arriba. Es la vista de instalación. |

El modo puede elegirse automáticamente por ancho de viewport, con un conmutador manual visible
(un monitor de 1080p montado en la pared debería poder forzarse a MURO).

---

## §4 · Los datos que YA existen

El panel obtiene todo de **un solo endpoint**, `GET /api/status`, sin autenticación, con
`Cache-Control: no-store`. Hoy se consulta con **polling encadenado a 1 Hz** (`setTimeout`, no
`setInterval`) con backoff 1→2→5 s ante fallo. **No hay WebSocket ni SSE** — decisión
deliberada: el servidor HTTP del Pi es de hilos y un stream retendría un hilo por cada pantalla
abierta.

### 4.1 · Contrato completo, campo por campo

**Raíz**

| Campo | Tipo | Significado |
|---|---|---|
| `gateway_id` | `str` | Identidad del gabinete, ej. `gw-dev-0001` |
| `site_name` | `str` | Nombre del inmueble, ej. `Sitio Dev Puebla`. Puede venir vacío |
| `now` | ISO 8601 UTC | Reloj del Pi |
| `uptime_s` | `float\|null` | Segundos desde el arranque del panel |
| `refresh_ms` | `int` | **Cadencia que el servidor le ordena a la UI** (1000 por defecto) |
| `sasmex_active` | `bool` | Alerta SASMEX **enclavada** (no es el estado instantáneo del relé) |
| `siren_sounding` | `bool` | La sirena está energizada **ahora**, físicamente |
| `audible_silenced` | `bool` | El operador silenció los audibles |
| `last_tier` | `str\|null` | Tier vigente del motor de reglas |
| `captured_at` | ISO | Hora del último dato de salud |

**`relays[]`** — siempre 5 elementos, en orden fijo `siren, strobe, gas_valve, elevator, door_retainer`

| Campo | Tipo | Valores |
|---|---|---|
| `channel` | `str` | `siren` · `strobe` · `gas_valve` · `elevator` · `door_retainer` |
| `energized` | `bool` | Estado **eléctrico** del relé |
| `activated` | `bool` | Estado **lógico** de protección (agnóstico de polaridad) |
| `fail_safe` | `str` | `NO` · `NC` · `fail_close` |

**`signal`** — `null` si el módulo de señal está caído

```
signal.channels["EHZ"|"ENZ"|"ENN"|"ENE"] = {
  pga_g        float   aceleración pico, en g
  pgv_cms      float   velocidad pico, en cm/s
  rms          float   RMS en counts crudos (NO es físico)
  sta_lta      float   razón short-term/long-term average, adimensional
  clipping     bool    el ADC saturó (|raw| ≥ 8_300_000, ~±2²³)
  health_score float   1.0 sano · 0.5 clipping · 0.0 canal muerto (rms == 0)
  window_start ISO     reloj del SENSOR (no sirve para medir antigüedad)
  received_at  ISO     reloj del PI: cuándo llegó (este sí)
  age_s        float   antigüedad, ≥ 0
}
signal.last_received_at  ISO|null   null = NUNCA llegó nada
signal.stale_after_s     float      5.0 — pasado esto, el dato está viejo
```

> **Ojo con las unidades:** `EHZ` es un **geófono**, mide velocidad nativamente y su PGA es
> derivado. `ENZ`/`ENN`/`ENE` son **acelerómetro**, miden aceleración nativamente y su PGV es
> integrado. No comparten escala vertical y no deben compartir eje.

**`health`** — `null` hasta el primer diagnóstico. Es **caché**: el panel nunca dispara sondas.

| Campo | Tipo | Unidad | Nota |
|---|---|---|---|
| `ntp_offset_s` | `float\|null` | **segundos** | La UI lo pinta ×1000 como ms |
| `seedlink_lag_s` | `float` | s | Retraso del flujo del sensor |
| `packet_loss_pct` | `float` | % | 0–100 |
| `mqtt_rtt_ms` | `float\|null` | ms | Ida y vuelta al último acuse de la nube |
| `ups_status` | `str` | — | `line` (red eléctrica) · `battery` · `unknown` |
| `battery_pct` | `float\|null` | % | — |
| `temperature_c` | `float` | °C | Del SoC del Pi |
| `cert_days_remaining` | `int\|null` | días | Certificado mTLS de la nube |
| `disk_used_pct` | `float\|null` | % | — |
| `captured_at` | ISO | — | Cuándo se **midió** |
| `age_s` | `float` | s | **Antigüedad declarada del diagnóstico** (heartbeat 60 s) |

**`cloud`** (nunca `null`) — `{ online: bool, mqtt_rtt_ms: float|null, queued: int|null }`
`queued` = mensajes esperando a que vuelva el enlace.

**`drill`** (simulacro) — `{ active, drill_id, started_at, duration_s, aborted, abort_reason, ended_reason }`

**`actuation_test`** (nunca `null`)
```
{ active: bool,
  results: { ok, reason, relays: { <canal>: { held|pulsed, readback_ok, fail_safe, energized } } } | null }
```
`held` y `pulsed` son mutuamente excluyentes: sirena y estrobo se **sostienen** (para oírlos),
los otros tres hacen **pulso de verificación** con lectura de retorno.

**`test_mode`** (nunca `null`) — `{ active: bool, remaining_s: float }`. Ventana de 120 s.

**`audio`** — `{ enabled: bool, sounding: bool }` o `null` si no hay módulo de audio.

**`events[]`** — máximo 10, orden descendente, **dos formas mezcladas**:
```
{ at, from_tier, to_tier, source, event_id, pga, reasons[] }   ← transición de tier
{ at, action, via: "lan" }                                     ← acción desde el panel
```
`source` ∈ `sasmex` · `local_threshold` · `manual`. `pga` solo viene si la fuente es
instrumental — en una alerta SASMEX es `null`, porque el WR-1 no mide nada.
`action` ∈ `silence` · `siren_test` · `actuator_test` · `test_mode_on` · `test_mode_off` ·
`reset` · `drill_audio`.

> **Todo `events[]` es volátil en RAM.** Se pierde al reiniciar. Por eso la card actual se rotula
> **"DESDE EL ARRANQUE"** — mantén esa honestidad.

### 4.2 · Dos invariantes del backend que el diseño debe respetar

1. **Toda sección es defensiva.** Un módulo roto devuelve `null` en su sección y el GET responde
   **200**, nunca 500. Tu diseño tiene que verse íntegro con `signal: null`, con `health: null` y
   con `audio: null` — simultáneamente. No es un caso raro: es el arranque en frío.
2. **`status()` jamás ejecuta sondas ni publica nada.** Fue un bug real: cada carga del panel
   lanzaba subprocesos de diagnóstico y publicaba a la nube ~30 veces por minuto. Consecuencia
   de diseño: **el diagnóstico de salud siempre viene con su edad declarada** (`age_s`) y la UI
   debe mostrarla. Un dato de hace 4 minutos no puede pintarse como si fuera de ahora.

### 4.3 · Datos que el edge ya calcula y el panel actual tira a la basura

Ganancia barata para el rediseño — todo esto existe en memoria del Pi hoy:

`rms` y `health_score` por canal (llegan en el JSON, no se pintan) · latencia medida del reflejo
SASMEX→relé · latencia del motor de reglas · paquetes vistos / reconexiones / duplicados / huecos
del flujo SeedLink · mensajes enviados a la nube y cola por tópico · autonomía restante del UPS ·
bytes y paquetes del buffer sísmico en disco · acuses de ejecución de actuadores con su latencia
(`T+0.42s`) · si la sirena por audio está habilitada.

---

## §5 · Datos NUEVOS que este rediseño exige

**Léelo antes de diseñar.** Lo que pidió el cliente — ondas en vivo, mapa, estadística — requiere
datos que el gabinete **todavía no produce**. Están aprobados para construirse y planificados como
la **Fase 2.1 (`T-2.15`…`T-2.23`) del backlog** (`takab-docs/TASKS.md`); diséñalos con confianza,
pero sabiendo que hoy no existen y que el diseño debe degradar con dignidad si alguno falta.

La **§5.1** de abajo congela el contrato exacto — claves, unidades y semántica de `null` — de todo
lo que estas ocho tareas van a producir. Diseña contra esa tabla, no contra tu intuición de cómo
debería llamarse un campo.

| # | Tarea | Qué falta | Habilita |
|---|---|---|---|
| **P-1** | `T-2.15` | **Buffer en RAM de muestras (60 s × 4 canales) + endpoint incremental de forma de onda.** Hoy solo se guarda el *último* valor por canal; no hay historia de muestras ni endpoint que las sirva. | §6 — las ondas |
| **P-2** | `T-2.16` | **Exponer los umbrales del sitio** (`pga_watch_g`, `pga_trip_g`, `pgv_watch_cms`, `pgv_trip_cms`) y la versión de configuración. Existen en el gabinete, no salen en el JSON. | §8.1 — proximidad al disparo |
| **P-3** | `T-2.17` | **Exponer las latencias de la cadena crítica** (reflejo SASMEX→relé, motor de reglas). Ya se miden. | §8.4 |
| **P-4** | `T-2.18` | **Exponer contadores del flujo del sensor** (paquetes, reconexiones, duplicados, huecos). Ya se cuentan. | §8.3 |
| **P-5** | `T-2.19` | **Agregador rodante de sacudida** (PGA máximo por hora y por 24 h, conteo de eventos, tendencia del ruido de fondo). En RAM, rotulado "DESDE EL ARRANQUE". | §8.2 |
| **P-6** | `T-2.20` | **Coordenadas del sitio** (`site_lat`, `site_lon`) y, opcionalmente, estaciones vecinas. **El gabinete literalmente no sabe dónde está**: no hay latitud ni longitud en ninguna parte de su configuración. | §7 — el mapa |
| **P-7** | `T-2.21` | **Bandera de calibración.** Sin procedencia instrumental declarada, la UI debe rotular **`SIN CALIBRAR`** y usar unidades relativas (`rel.`) en vez de `g` y `cm/s`. | §6, §8 |
| **P-8** | `T-2.22` | **Autonomía restante del UPS.** Se mide y se pierde antes de llegar al panel. | §8.3 |

---

### 5.1 · Contrato CONGELADO de los campos nuevos

> **Esto es un compromiso, no un borrador.** Los nombres de clave, las unidades y la semántica de
> `null` de abajo quedaron fijados el 2026-07-29, **antes** de escribir el backend, precisamente
> para que puedas diseñar contra el contrato real y no contra uno inventado. Si la implementación
> necesitara desviarse, se actualiza esta sección y se te avisa — no se cambia en silencio.
>
> Las mismas dos reglas de la §4.2 aplican a todo lo nuevo: **sección defensiva** (módulo roto ⇒
> `null` en su sección, GET **200**) y **`status()` jamás sondea ni publica**.

**`thresholds`** (`P-2`) — `null` si el motor de reglas está caído

| Campo | Tipo | Unidad | Nota |
|---|---|---|---|
| `pga_watch_g` | `float` | g | Entrada a `watch` |
| `pga_trip_g` | `float` | g | **Disparo** |
| `pgv_watch_cms` | `float` | cm/s | — |
| `pgv_trip_cms` | `float` | cm/s | **Disparo** |

Son los umbrales **VIGENTES en el motor**, no los del archivo de configuración: se reemplazan en
vivo desde la nube. La línea de umbral que dibujes sobre las trazas es siempre esta.

**`config_version`** (`P-2`) — raíz, `int`. Contador monótono de la configuración firmada aplicada.
`0` = nunca se ha sincronizado con la nube (el gabinete corre sus defaults).

**`latencies`** (`P-3`) — nunca `null`; los campos medidos sí pueden serlo

| Campo | Tipo | Unidad | Nota |
|---|---|---|---|
| `reflex_s` | `float\|null` | **segundos** | SASMEX→relé. `null` = aún no ha ocurrido ninguno |
| `reflex_budget_s` | `float` | s | `0.100` — el presupuesto, para pintar **contra** él |
| `rules_s` | `float\|null` | s | Última evaluación del motor |
| `rules_budget_s` | `float` | s | `0.200` |

`null` significa **sin medición**, y se pinta `S/D`. **Nunca habrá un `0.0`** en estos campos: un
cero se leería como "instantáneo" y sería una mentira. Ojo con la escala: los valores reales son de
milisegundos (**6.65 ms** medidos con hardware real), así que la UI los multiplica ×1000, igual que
ya hace con `ntp_offset_s`.

**`seedlink`** (`P-4`) — `null` si no hay cliente SeedLink (dev / simulador)

| Campo | Tipo | Nota |
|---|---|---|
| `packets_seen` | `int` | Acumulado |
| `reconnects` | `int` | El enlace al Shake se cayó y se levantó |
| `duplicates` | `int` | Reenvíos del ringserver |
| `gaps` | `int` | Huecos en la secuencia |

Los cuatro son **acumulados DESDE EL ARRANQUE** y hay que rotularlos así. Sirven para distinguir
"el enlace se cae y se levanta" (`reconnects`) de "el Shake manda con huecos" (`gaps`) — que es
justo lo que nadie pudo ver durante las 15 h en que el sistema estuvo ciego.

**`calibration`** (`P-7`) — nunca `null`

| Campo | Tipo | Nota |
|---|---|---|
| `calibrated` | `bool` | **Derivado**: `source` no vacío. No existe un checkbox de "calibrado" |
| `source` | `str\|null` | Procedencia, ej. `StationXML FDSN AM.R4F74 2026-07-09` |
| `vel_sensitivity_ms_per_count` | `float` | Sensibilidad de velocidad en uso |
| `accel_sensitivity_ms2_per_count` | `float` | Sensibilidad de aceleración en uso |

**Default-deny:** ausencia de procedencia **nunca** se interpreta como calibrado. Con
`calibrated: false` el panel rotula **`SIN CALIBRAR`** y usa unidades relativas (`rel.`) en lugar
de `g` y `cm/s` — en las ondas, en la estadística y en los umbrales. Las dos sensibilidades son
para el perfil técnico; pintarlas es opcional, pero el rótulo `SIN CALIBRAR` no lo es.

**`site_lat` / `site_lon`** (`P-6`) — raíz, `float\|null`

`null` ⇒ **`SIN UBICACIÓN PROVISIONADA`**. Jamás un punto inventado ni un centro por defecto: un
mapa centrado en el Zócalo cuando el gabinete está en Puebla es peor que no tener mapa.

**`neighbors[]`** (`P-6`) — lista, posiblemente vacía. `{ code, lat, lon, distance_km }`.
**Puramente informativa.** El quórum de estaciones se correlaciona en la nube y **JAMÁS** gatea la
sirena local; el diseño no puede sugerir lo contrario.

**`health.ups_runtime_s`** (`P-8`) — `float\|null`, **segundos** de autonomía restante.

Vive **dentro de `health`**, así que hereda su `age_s`: es un dato de heartbeat, no instantáneo.
`null` ⇒ `S/D`. Hoy será `null` en campo hasta que el gabinete tenga un UPS visible — y eso es la
respuesta correcta, no un hueco del diseño.

**`shake_history`** (`P-5`) — `null` si el módulo de señal está caído

```
shake_history.since            ISO      arranque del agregador
shake_history.by_channel["<ch>"] = {
  pga_g_max_24h    float    máximo de las últimas 24 h
  pgv_cms_max_24h  float
  hourly[]         hasta 24 buckets, del más viejo al más nuevo:
                   { hour_start ISO, pga_g_max float, pgv_cms_max float }
}
shake_history.events_by_tier   { normal, watch, restricted, evacuate_or_hold, manual_only } → int
shake_history.noise_floor = {
  current_mg     float    ruido de fondo actual, en mili-g
  baseline_low_mg  float  0.6  ┐ piso conocido del sensor, MEDIDO en el gabinete real
  baseline_high_mg float  1.1  ┘
  trend          str      "rising" | "stable" | "falling"
}
```

`hourly[]` arranca **corto** y crece hasta 24: recién reiniciado el gabinete tiene un bucket, no
veinticuatro vacíos. Rotúlalo **DESDE EL ARRANQUE** hasta que `since` tenga más de 24 h de
antigüedad — el agregador vive en RAM y se pierde al reiniciar, a propósito. No finjas una
continuidad que el gabinete no tiene.

**`GET /api/waveform`** (`P-1`) — **el segundo endpoint**, y el único además de `/api/status`

Petición: `?since=<cursor>&channels=<lista opcional>&max_points=<n opcional>`.
Lectura abierta, sin autenticación, igual que `/api/status` — es el panel del guardia.

```
cursor        int      el cursor a mandar en la SIGUIENTE petición
reset         bool     true = tu `since` ya se cayó del ring: REDIBUJA, no empalmes
sample_rate   float    sps EFECTIVO de lo que vas a recibir (tras decimar)
decimation    int      factor aplicado; 1 = resolución completa
channels["<ch>"] = {
  samples[]        counts crudos del ADC 24-bit (NO es físico: convierte con `calibration`)
  encoding         "raw" | "minmax"
  first_sample_at  ISO   reloj del PI
  gap_before       bool  hubo un hueco del sensor antes de este tramo
}
```

Cuatro cosas que el diseño tiene que respetar:

1. **`encoding: "minmax"` cambia la forma de `samples[]`**: son **pares** (mínimo, máximo) por
   bucket, no una serie. Es una envolvente y se dibuja como banda, no como línea. Se eligió sobre
   el submuestreo porque el submuestreo se salta el pico y dibuja un sismo **más chico del que
   fue**. Rotula el `sample_rate` efectivo y el factor cuando `decimation > 1` (§6.4).
2. **`gap_before: true` ⇒ segmento nuevo.** No unas dos tramos discontinuos con una línea recta:
   eso inventa movimiento que no ocurrió.
3. **`reset: true` ⇒ tira el buffer del cliente y redibuja.** Pasa con una pestaña dormida o una
   reconexión.
4. **Una sola cadencia, secuencial.** Pide `/api/status` y `/api/waveform` en el **mismo tick** del
   polling encadenado a 1 Hz, no en dos bucles paralelos: el servidor HTTP del Pi es de hilos y dos
   bucles duplican los hilos retenidos por pantalla abierta. Misma razón por la que no hay
   WebSocket ni SSE (§4).

A 1 Hz, un tick típico son ~50 muestras × 4 canales ≈ **2 KB**. El ring retiene **60 s a 100 sps
por canal** — esa es toda la historia disponible, y es la ventana máxima que puedes ofrecer.

---

## §6 · Ondas de movimiento en vivo — el corazón del rediseño

Esto es lo que hoy no existe y es lo primero que el cliente pidió. Hoy el panel muestra cuatro
tarjetas con números y nada más. **Debe mostrar el sismograma en vivo de los cuatro canales.**

### 6.1 · Qué se dibuja

- **Cuatro trazas apiladas**, una por canal, con etiqueta permanente del canal y de su unidad.
- **Escala vertical independiente por canal.** El geófono y el acelerómetro no comparten unidad;
  forzarlos al mismo eje haría que uno se vea plano siempre. Regla ya implementada en la consola
  web: canal que empieza con `EH` → velocidad (`cm/s`); canal que empieza con `EN` → aceleración
  (`g`).
- **Ventana desplazable de 60 segundos**, borde derecho = ahora, desplazamiento continuo.
- **Piso de escala.** Sin él, un micro-temblor imperceptible se dibuja como un terremoto. La
  consola web usa un mínimo fijo del eje por esta razón exacta; replica el criterio y **muestra
  la escala vigente en pantalla** para que quien mira sepa si está viendo ruido amplificado o
  movimiento real.

### 6.2 · Marcas superpuestas obligatorias

Sobre las trazas, no en una leyenda aparte:

- **Líneas de umbral** de cautela y de disparo, por canal (requiere P-2). Son el contexto que
  convierte una onda bonita en información accionable.
- **Ticks de saturación (clipping)** en rojo crítico. Un canal saturado no está midiendo: está
  topado. Es una advertencia, no un dato.
- **Marca vertical del instante SASMEX**, cuando el WR-1 cerró contacto.
- **Marca vertical de cada transición de tier**, con su color de tier.

La secuencia visual "SASMEX cerró → 6.65 ms después el relé actuó → 12 s después llegó la onda al
edificio" es la historia más valiosa que este sistema puede contar. Diséñala para que se lea.

### 6.3 · Cómo llegan los datos

El transporte es **incremental por polling**, no streaming:

- El buffer de 60 s vive en el Pi (P-1). El navegador pide **solo lo nuevo** desde un cursor,
  cada segundo: unas 50 muestras × 4 canales ≈ 2 KB por petición.
- El navegador conserva la ventana de 60 s en memoria y anima el desplazamiento entre peticiones.
- Esto respeta la decisión ya tomada de no usar SSE ni WebSocket en el gabinete y mantiene el
  patrón de polling encadenado con backoff que ya existe.

### 6.4 · Honestidad de la señal (no negociable)

- **Declara la decimación.** Si se dibujan 50 muestras/s de una señal de 100, la pantalla lo dice.
  Prohibido presentar como 100 sps algo decimado.
- **Sin calibración instrumental declarada, no hay unidades físicas.** Se rotula
  **`SIN CALIBRAR`** y los ejes van en unidades relativas (`rel.`). Los valores de fábrica del
  software son marcadores de posición; las sensibilidades reales vienen del StationXML del
  sensor. Presentar `0.15 g` sin esa procedencia sería inventar una magnitud física.
- **Un canal sin datos no se dibuja plano.** Se dibuja vacío, con su etiqueta y la razón. Una
  línea recta se lee como "todo tranquilo"; la verdad es "no sé".
- **Referencia técnica reutilizable:** la consola web ya dibuja sismogramas multicanal **en SVG a
  mano, sin librería de gráficas**, con geófono en `#7CE7FF` y acelerómetro en `#00BFFF`, trazo
  de 1.3 px, y ticks de saturación en rojo. Es una base válida y probada — pero el panel del
  gabinete puede y debe superarla visualmente.

---

## §7 · Mapa de la estación — esquemático, siempre offline

El cliente pidió "un mapa con la estación y su información". Hay que resolverlo dentro de la
restricción de cero internet.

### 7.1 · Por qué no hay mapa de calles

El panel no puede descargar tiles: no hay internet en la LAN del edificio y un test veta cualquier
recurso externo. **Un mapa que se rompe cuando cae el enlace es peor que no tener mapa**, porque
el enlace se cae justo cuando más importa.

**Decisión tomada: mapa esquemático vectorial, dibujado por el propio panel.** Sin basemap. Debe
verse **deliberado, no roto** — un instrumento, no un mapa fallido.

### 7.2 · Qué contiene

- **El sitio al centro**, con su identidad completa: `site_name`, `gateway_id`, código de estación
  (`AM.R4F74`), coordenadas si están provisionadas (P-6).
- **La rosa de los ejes del sensor** — Z vertical, N-S, E-O — con la magnitud instantánea por eje.
  El acelerómetro es tridimensional y esa direccionalidad es información real que hoy se
  desperdicia por completo: se puede ver **en qué dirección** está sacudiendo, no solo cuánto.
  Es, probablemente, el elemento más vistoso y más honesto que puedes poner en esta pantalla.
- **Anillos de distancia** con escala rotulada.
- **Estaciones vecinas de la red** si la configuración las trae, con su estado de corroboración.
- **El enlace a la nube** representado como estado, no como línea decorativa.

### 7.3 · Contexto de la red multi-estación

La corroboración entre estaciones ("quórum") es una función de **la nube**, no del gabinete: un
gabinete con un solo sensor no tiene nada que correlacionar localmente. La regla física es que
la ventana de asociación depende de la distancia — las ondas P viajan a ~6.5 km/s y entre sitios
a 90–110 km hay 10–20 s de diferencia de llegada. Se requieren **≥3 estaciones** para confirmar
un evento regional.

> **Invariante absoluto:** el quórum **corrige y confirma**, y se **muestra**; **jamás** condiciona
> la sirena local. Si el diseño insinúa que el gabinete espera a otras estaciones para actuar,
> está mal. Actúa solo, siempre, de inmediato.

### 7.4 · Degradación honesta

Si `site_lat` / `site_lon` no están provisionados, se muestra **`SIN UBICACIÓN PROVISIONADA`** y
el módulo colapsa a la rosa de ejes del sensor, que no necesita coordenadas. **Jamás un punto
inventado, jamás un centro por defecto.** Un gabinete mal ubicado en el mapa es peor que un
gabinete sin mapa.

---

## §8 · Estadística de los movimientos

Los cuatro bloques pedidos. Todos deben rotular su ventana temporal y su procedencia.

### 8.1 · Proximidad al disparo *(requiere P-2)*

Barras de PGA y PGV actuales contra los umbrales del sitio: cuánto falta para `cautela` y cuánto
para `disparo`. Es la conversión de un número abstracto en una respuesta: *¿estoy cerca?*

Valores por defecto (perfil hospital, se calibran por tipología y altura del inmueble):

| Umbral | Valor |
|---|---|
| PGA cautela | 0.040 g |
| PGA disparo | 0.060 g |
| PGV cautela | 2.0 cm/s |
| PGV disparo | 4.0 cm/s |

Referencias del blueprint por tipo de instalación: hospitales 0.040–0.060 g · industriales
0.080–0.120 g · corporativos 0.100–0.150 g.

**Contexto que hace la barra legible:** el piso de ruido en reposo es 0.6–1.1 mg, es decir
~0.001 g. El umbral de disparo está **60 veces** por encima del ruido. En reposo, esa barra debe
verse tranquilizadoramente vacía — y eso es información, no espacio muerto.

### 8.2 · Histórico de sacudida *(requiere P-5)*

- PGA máximo por hora y en las últimas 24 h.
- Conteo de eventos por tier.
- Último evento significativo, con su hora y su pico.
- Tendencia del ruido de fondo contra el piso conocido (0.6–1.1 mg) — es como el técnico detecta
  que el sensor se está degradando antes de que falle.

Mientras viva en RAM, se rotula **"DESDE EL ARRANQUE"** junto al tiempo de actividad. No inventes
una continuidad que el gabinete no tiene.

### 8.3 · Salud y calidad de la señal *(mayormente ya existe; P-4 y P-8 lo completan)*

**Por canal:** RMS, puntaje de salud, saturación, antigüedad del último dato.
**Del flujo:** retraso del sensor, pérdida de paquetes, huecos, reconexiones, duplicados.
**Del gabinete:** desfase de reloj NTP, temperatura, disco, certificado, UPS (modo, carga y
**autonomía restante**), enlace a la nube y cola pendiente.

Umbrales de color ya establecidos en el panel actual — respétalos o justifica el cambio:

| Métrica | Ámbar | Rojo |
|---|---|---|
| Retraso del sensor | ≥ 2 s | ≥ 10 s |
| Pérdida de paquetes | ≥ 1 % | ≥ 10 % |
| Temperatura | ≥ 70 °C | ≥ 80 °C |
| Certificado mTLS | < 30 días | — |
| Disco usado | > 90 % | — |
| UPS | `battery` | — |

> **Contexto que justifica esta sección:** el sistema estuvo **15 horas ciego** porque el sensor
> salió de la red, y el panel seguía diciendo OPERATIVO. Esta card existe para que eso no se
> repita. Diséñala como si su trabajo fuera gritar, no decorar.

### 8.4 · Latencias de la cadena crítica *(requiere P-3)*

- **Reflejo SASMEX → relé** (medido: 6.65 ms · presupuesto p95 < 100 ms).
- **Latencia del motor de reglas** (presupuesto < 200 ms).
- **RTT a la nube** y cola pendiente.

Es la prueba viva de que el sistema responde. Contra su presupuesto, no en el vacío: `6.65 ms`
solo significa algo junto a `< 100 ms`.

---

## §9 · Jerarquía de estados — invariante, no rediseñable

### 9.1 · Los cuatro banners y su precedencia exacta

**Lo real siempre gana.** Esta jerarquía está probada en producción y no se renegocia:

| Prioridad | Banner | Estilo actual | Regla |
|---|---|---|---|
| **1** | `ALERTA SÍSMICA · PROTÉJASE` | Rojo, **parpadea** | Tapa todo |
| **2** | `🔶 SIMULACRO — ESTO NO ES UNA ALERTA REAL` | Ámbar, sin parpadeo | **Solo si no hay alerta real.** Si aborta: `SIMULACRO ABORTADO — ALERTA REAL EN CURSO (motivo)` |
| **3** | `🔧 PRUEBA DE ACTUADORES — NO ES ALERTA REAL` | Cian, sin parpadeo | Solo si no hay alerta real |
| **4** | `🧪 MODO PRUEBA WR-1 — LA NUBE NO RECIBE ALERTAS (Ns)` | Violeta, con cuenta atrás | **SIEMPRE visible mientras esté armado, incluso bajo alerta real** |

El caso 4 es deliberadamente la excepción: mientras el modo prueba está armado, el gabinete
**protege igual en local** pero **no le avisa a la nube**. El operador *debe* saberlo aunque haya
una alerta real encima. La ventana auto-expira a los 120 s justamente para que nadie lo deje
armado por olvido.

### 9.2 · Los tiers y sus etiquetas exactas

| Valor | Etiqueta en pantalla | Tono | Actuadores que dispara |
|---|---|---|---|
| `normal` | `✓ NORMAL · SIN ALERTA` | Verde | — |
| `watch` | `▲ VIGILANCIA` | Ámbar | — |
| `restricted` | `■ ACCESO RESTRINGIDO` | Rojo | Ascensores, puertas |
| `evacuate_or_hold` | `■ EVACUAR / RESGUARDO` | Rojo | **Los cinco** |
| `manual_only` | `⚠ MODO MANUAL — SENSORES DEGRADADOS` | Ámbar | — |

`manual_only` es ámbar, no verde: significa *"no sé"*, y lo desconocido nunca se pinta como bueno.

Subtítulo del estado actual: `SIRENA: SONANDO|SILENCIADA|EN REPOSO · SASMEX: ACTIVO|NO`.

### 9.3 · Los cuatro estados de UI obligatorios

Regla de oro del proyecto: **todo componente maneja `loading`, `error`, `empty` y `stale`.**
Mostrar un dato congelado como si fuera "en vivo" es peor que mostrar "sin datos". Hay un gate de
tests en la consola web: *un componente sin los cuatro estados no pasa*.

Copy ya establecido, reutilízalo:

| Estado | Texto |
|---|---|
| En vivo | `PANEL EN VIVO` |
| Dato viejo | `DATO RETENIDO DESDE HH:MM:SS UTC` (ámbar) |
| Sin conexión | `SIN CONEXIÓN CON EL GABINETE · REINTENTANDO…` (rojo) |
| Sin señal del sensor | `SIN SEÑAL DEL SENSOR · SIN FEATURES RECIBIDAS` |
| Enlace a la nube | `ENLACE NUBE · CONECTADO` / `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · N EN COLA` |
| Dato ausente | `S/D` |
| Sin eventos | `DESDE EL ARRANQUE` + tiempo de actividad |

Nota sobre `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA`: ese texto **no es un error**. Es el sistema
funcionando como fue diseñado. Píntalo ámbar informativo, nunca rojo de falla.

---

## §10 · Sistema de diseño

### 10.1 · Color — valores exactos, verificados

Hay un gate de CI que rompe si estos hex cambian. Son la identidad del producto en la consola
web y en la app móvil; el panel debe hablar el mismo idioma.

**Superficies**

| Token | Hex |
|---|---|
| `--tk-surface-0` / `--tk-navy-900` | `#0E2336` |
| `--tk-surface-1` / `--tk-navy-800` | `#122B44` |
| `--tk-surface-2` | `#18324E` |
| `--tk-surface-3` | `#1F3D5C` |
| `--tk-surface-overlay` | `rgba(14, 35, 54, 0.92)` |

**Texto:** `--tk-fg-1 #F0F2F5` · `--tk-fg-2 #B8C2CE` · `--tk-fg-3 #6F7E8F` ·
`--tk-fg-disabled #4A5765`

**Acento único (interacción):** `--tk-cyan #00BFFF` · hover `#33CCFF` · press `#009ACC` ·
tintes `rgba(0,191,255,0.15)` y `rgba(0,191,255,0.08)`

**Semáforo de estado**

| Token | Hex | Uso |
|---|---|---|
| `--tk-status-normal` | `#00E676` | Normal, operativo |
| `--tk-status-warning` | `#FFC107` | Vigilancia, degradado, **desconocido** |
| `--tk-status-critical` | `#FF5252` | Crítico, evacuación, saturación |

Tintes al 15/18 % y 8 % para fondos de pill.

**Bordes:** `--tk-border rgba(240,242,245,0.08)` · `--tk-border-strong rgba(240,242,245,0.16)`

**Sombras semánticas:**
```
--tk-shadow-critical: 0 0 0 1px #FF5252, 0 0 24px -6px rgba(255,82,82,0.45)
--tk-shadow-warning:  0 0 0 1px #FFC107, 0 0 16px -8px rgba(255,193,7,0.35)
--tk-shadow-active:   inset 0 0 0 1px #00BFFF, 0 0 0 1px rgba(0,191,255,0.15)
--tk-focus-ring:      0 0 0 2px #0E2336, 0 0 0 4px #00BFFF
```

### 10.2 · Escala tipográfica y espacio

**Tamaños:** 11 · 13 · 14 · 16 · 18 · 22 · 28 · 40 · 56 · 72 px
**Interlineado:** ajustado 1.1 · cómodo 1.25 · normal 1.45 · **dato 1.0**
**Tracking:** ajustado −0.02em · normal 0 · ancho 0.04em
**Espaciado:** 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 px
**Radios:** 4 · 6 · 8 px · pill 999px
**Movimiento:** `cubic-bezier(0.2, 0, 0.2, 1)` a 120 / 180 / 280 ms — **excepto las animaciones
de dato, que van `linear`**. Una traza sísmica con easing sería una traza mentirosa.

Convención firme: **todo número va en monoespaciada con cifras tabulares**. Un PGA que baila
horizontalmente al actualizarse a 1 Hz es ilegible.

### 10.3 · El problema de las fuentes — decídelo tú

La consola web usa **Geist** (interfaz), **JetBrains Mono** (datos) y **Saira Condensed** (marca).
Las dos últimas se cargan por `@import` de Google Fonts — **inservibles en la LAN sin internet**.
El panel actual se rindió y usa `system-ui` + `ui-monospace`.

Tienes dos caminos y el documento te pide que **elijas uno y lo justifiques**:

- **(a) Empaquetar las fuentes localmente en el Pi** — coherencia total con la consola y la app,
  a costa de peso en el HTML servido y de un paso en el aprovisionamiento.
- **(b) Quedarse con las pilas del sistema** — cero peso, cero riesgo, a costa de que el panel se
  vea distinto en cada sistema operativo.

Si eliges (a), considera que solo la monoespaciada es realmente crítica: es la que carga todos los
datos.

### 10.4 · Vocabulario visual heredado (reutilizable)

- **Pills de estado:** `inline-flex`, `padding 5px 12px`, radio pill, 11 px, peso 700, tracking
  0.10em, con un punto de 8 px del color de estado. Variante con pulso animado para "en vivo".
- **Botones:** 11 px, peso 700, tracking 0.10em, mayúsculas, `padding 9px 16px`, radio 4 px.
  Primario = fondo cian con texto navy. Peligro = fondo rojo crítico.
- **Confirmación en dos pasos** para lo destructivo: el botón se arma, pulsa, y da 5 s para
  cancelar con el texto `CLIC NUEVAMENTE PARA CONFIRMAR` + `Orden bajo verificación humana ·
  Ns para cancelar`.
- **Etiquetas de sección:** 11 px, peso 600, tracking 0.12em, mayúsculas, en `--tk-fg-2`.

---

## §11 · Las seis acciones del panel

Todas exigen el PIN en la cabecera `X-Takab-Pin`. Códigos: `200` correcto · `401` sin PIN o PIN
erróneo · `403` producción sin PIN provisionado (bloqueo por diseño) · `429` bloqueado por
intentos.

| Botón | Qué hace realmente |
|---|---|
| `SILENCIAR AUDIBLES` | Calla la sirena. **No puede callar el pulso de la rama de hardware paralela mientras SASMEX mantenga el contacto cerrado** — cubre >95 % del tiempo audible, pero la UI no debe prometer más de lo que puede |
| `PROBAR SIRENA` | Suena 2 segundos |
| `PROBAR ACTUADORES` | Sostiene sirena+estrobo ~5 s (para oírlos y verlos) y hace pulso de verificación con lectura de retorno en gas, ascensores y puertas. **Nunca dispara la cadena de alerta**: sin evento, sin incidente en la nube, sin correos. Una alerta real a media prueba **gana** |
| `MODO PRUEBA WR-1` / `SALIR DE PRUEBA WR-1` | Arma una ventana de 120 s auto-expirable donde el gabinete **protege igual en local** pero **suprime todo lo que va a la nube**. Existe porque probar el WR-1 real abría un incidente crítico y mandaba correos |
| `CERRAR ALERTA` | Libera el enclave |
| `SIMULACRO DE VOCEO` | **Solo visible si el módulo de audio está habilitado.** Nada de botones muertos |

Mensajes de error del PIN, ya establecidos: `PIN INCORRECTO` ·
`SIN PIN CONFIGURADO · ACCIONES BLOQUEADAS` · `BLOQUEADO POR INTENTOS · ESPERA 60 s`.

**El PIN vive solo en memoria de la página.** `localStorage` y `sessionStorage` están prohibidos.
Diseña el flujo de captura sabiendo que se vuelve a pedir al recargar — y que en el modo MURO,
que es solo lectura, no se pide nunca.

---

## §12 · Qué NO hacer

Prohibiciones con su razón. Varias están ancladas por tests automatizados que rompen el build.

| Prohibido | Por qué |
|---|---|
| **Cuenta regresiva / T-MINUS** | El WR-1 entrega un booleano. No hay dato de tiempo de llegada. Un cronómetro "15 s" en una pantalla de vida o muerte sería un número inventado |
| **Magnitud preliminar** | Mismo motivo: el contacto seco no transporta magnitud. En la alerta el texto es `ALERTA SÍSMICA · PROTÉJASE`, sin número |
| **Cualquier recurso externo** | CDN, fuentes remotas, tiles, analíticas. La LAN no tiene internet y hay un test que lo veta |
| **`localStorage` / `sessionStorage`** | Regla del proyecto |
| **IA en el camino de disparo** | La ruta de actuación es 100 % determinista |
| **Números inventados** | `S/D` cuando no hay dato · `0.000 g` **solo** si es cero medido · `<0.001 g` para picos diminutos · `—` honesto |
| **Desconocido pintado de verde** | Lo desconocido va **ámbar**. Siempre |
| **Un dato viejo pintado como vivo** | Todo dato con antigüedad la declara |
| **Botones muertos** | Si la capacidad no está, el botón no está |
| **Que el simulacro o la prueba tapen la alerta real** | Lo real siempre gana |
| **Sugerir que el gabinete espera a la nube o a otras estaciones para actuar** | Actúa solo, siempre |

---

## §13 · Qué entregar

1. **Los tres modos de densidad** (MURO / CONSOLA / CAMPO) con sus breakpoints declarados.
2. **Los estados completos**, no solo el feliz: reposo · vigilancia · **alerta real** ·
   simulacro · prueba de actuadores · modo prueba WR-1 · sin señal del sensor · sin enlace a la
   nube · arranque en frío (todas las secciones `null`) · dato retenido.
3. **El sismograma multicanal** con sus marcas de umbral, saturación, SASMEX y transición de tier.
4. **El mapa esquemático** con la rosa de ejes del sensor, y su degradación sin coordenadas.
5. **Los cuatro bloques de estadística.**
6. **La decisión de tipografía** (§10.3) con su justificación.
7. **La botonera de acciones** con el flujo de PIN y la confirmación en dos pasos.

Deposita la salida en `takab-docs/design/edge-panel/`.

---

## §14 · Una nota sobre el tono

Esta pantalla vive en un cuarto de máquinas, en la caseta de un vigilante, o en la pared de un
hospital. La ve gente que no eligió mirarla. La mayor parte del tiempo dice **"todo normal"** y
nadie le presta atención; el día que importa, alguien la mira aterrado buscando una respuesta en
menos de un segundo.

Esos dos modos de uso son el problema de diseño real. No puede ser tan aburrida que se vuelva
invisible, ni tan alarmista que se ignore. Debe **inspirar confianza en reposo** — que se note
que hay un instrumento vivo midiendo, no una página estática — y **ser brutalmente clara en
crisis**.

El sistema mide un edificio entero 100 veces por segundo, dispara relés en 6.65 milisegundos y
sigue protegiendo aunque se caiga medio internet. Hoy eso se ve como cuatro números grises en una
tarjeta. **Que se vea lo que realmente es.**
