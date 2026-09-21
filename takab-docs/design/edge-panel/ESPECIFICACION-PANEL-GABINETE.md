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

**`config_version`** (`P-2`) — raíz, `int|null`. Contador monótono de la configuración firmada
aplicada. `0` = nunca se ha sincronizado con la nube (el gabinete corre sus defaults); `null` =
el store de config está roto o no cableado (degradación defensiva) ⇒ se pinta `S/D`.
*(Amend 2026-07-30, T-2.16: se añade la rama `null` al implementar la sección defensiva.)*

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
| `vel_sensitivity_ms_per_count` | `float\|null` | Sensibilidad de velocidad en uso |
| `accel_sensitivity_ms2_per_count` | `float\|null` | Sensibilidad de aceleración en uso |

**Default-deny:** ausencia de procedencia **nunca** se interpreta como calibrado. Con
`calibrated: false` el panel rotula **`SIN CALIBRAR`** y usa unidades relativas (`rel.`) en lugar
de `g` y `cm/s` — en las ondas, en la estadística y en los umbrales. Las dos sensibilidades son
para el perfil técnico; pintarlas es opcional, pero el rótulo `SIN CALIBRAR` no lo es.
*(Amend 2026-07-30, T-2.21: con el módulo de señal caído la sección NO se vuelve `null` — degrada
a `{calibrated: false, source: null}` con las dos sensibilidades en `null`.)*

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

*(Amend 2026-07-30, T-2.19: `noise_floor.current_mg` es `float|null` — `null` mientras el MEMS
(EN\*) no haya aportado ni una ventana; el geófono EH\* no es aceleración y no alimenta el piso.
`by_channel` puede venir vacío en el primer segundo tras el arranque. `events_by_tier` arranca
en `normal`: un día tranquilo son puros ceros — el primer tick NO cuenta como transición.)*

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
   *(Amend 2026-07-30, T-2.15: los pares llegan **APLANADOS** en `samples[]` —
   `[min0, max0, min1, max1, …]`, longitud SIEMPRE par. Con `encoding: "raw"` la longitud es la
   serie tal cual.)*
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

*(Amend 2026-07-30, T-2.15 — **forma degradada**: con el módulo de señal caído o ausente el
endpoint responde **200** con `{"cursor": <since|0>, "reset": true, "sample_rate": null,
"decimation": 1, "channels": {}}` — jamás un 500 al kiosco. Parámetros ilegales caen a sus
defaults, jamás 400. Un tick incremental sin muestras nuevas responde `channels: {}` con
`reset: false`: el cliente simplemente no redibuja.)*

**`GET /api/catalog`** *(Amend 2026-07-30, T-2.23 — el TERCER endpoint del panel)*

Instantánea local del catálogo SSN, servida desde `/var/lib/takab/ssn-catalog.json` (formato
del entregable de diseño `data/ssn-sismos.json`; siembra inicial con
`provision_gateway.sh --catalog FILE`). Lectura abierta; la procedencia se declara en pantalla
(`INSTANTÁNEA DEL CATÁLOGO · <captured_at>`).

*(Amend 2026-07-31, T-2.24 — **feed firmado nube→edge**: el archivo se actualiza en caliente
por `takab/catalog/<thing>` con el MISMO mecanismo HMAC de la config (dominio `catalog`,
versión monótona anti-replay persistida como `feed_version` DENTRO del archivo; el archivo
provisionado a mano es v0). Firma inválida, versión vieja o payload malformado ⇒ se conserva
el último snapshot bueno. **El contrato de `GET /api/catalog` NO cambió** — el panel sigue
leyéndolo una vez al construirse; `feed_version` es interno y no viaja en la respuesta. El
push lo origina la nube: `POST /gateways/{id}/catalog`, interno-only y auditado.)*

```
available     bool     false = archivo ausente o corrupto ⇒ el panel rotula
                       CATÁLOGO NO DISPONIBLE · SIN DATOS EN CACHÉ
source        str|null fuente textual (SSN/UNAM)
captured_at   str|null ISO de la captura de la instantánea
note          str|null nota de réplicas del SSN
events[]      { m, at ("fecha hora"), lat, lon, depth_km|null, place }
references[]  { n, lat, lon }   referencias urbanas para el mapa
```

Las estaciones NO viajan aquí: la propia viene de `site_lat/lon` y las vecinas de
`neighbors[]` en `/api/status` (T-2.20). Se pide al arrancar y a lo sumo cada ~10 min,
dentro del MISMO tick secuencial.

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

### 7.5 · Comparativa sismo↔estación (T-2.27)

Dentro del overlay del mapa: se selecciona un sismo del catálogo Y una estación (propia por
default; vecinas seleccionables en «Estaciones de la red»). El cajón `#cmp-drawer` bajo el mapa
muestra las cifras (distancia epicentral lineal con rumbo, hipocentral con profundidad, arribo P
teórico a v_P 6.5 km/s, PGA estimado en el epicentro y en la estación) y la curva
PGA-vs-distancia (X lineal en km, Y log por décadas, banda ilustrativa ×3/÷3) de la ley
**ATTEN-LAW v1** — espejo de `_plausible_pga_g` de la nube, determinista, jamás en el camino de
disparo. Rótulo maestro obligatorio: **«ESTIMACIÓN TEÓRICA · LEY DE ATENUACIÓN SIMPLE — NO ES
DATO MEDIDO»**. El PGA **medido** solo se superpone con tres candados: estación propia + el
sismo cae en un bucket horario de `shake_history` (matching `at` SSN hora local UTC-6 → bucket
UTC, con caveat de bucket) + calibración presente (sin calibrar: texto «NO COMPARABLE», nunca en
el eje en g). Vecina seleccionada ⇒ «SOLO LA ESTACIÓN PROPIA MIDE». La línea y el rótulo del
mapa siguen a la estación seleccionada. **No es el mini-ShakeMap del blueprint §14**: cero
interpolación espacial, cero IA. Estados vacíos: sin sismo ⇒ «SELECCIONE UN SISMO PARA
COMPARAR»; sin ubicación ⇒ hereda §7.4; sin catálogo ⇒ hereda «CATÁLOGO NO DISPONIBLE».

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

> **[D-29 · T-6.28 · 2026-09-07]** `SIRENA` es el **relé**, y así sigue. El voceo por el **jack**
> se declara aparte, solo cuando el jack suena y el relé está en reposo: `SIRENA: EN REPOSO ·
> VOCEO: SIMULACRO|PRUEBA|ACTIVO · SASMEX: …`. Si el relé suena, `SONANDO` ya lo dice y no se
> añade nada: dos rótulos del mismo altavoz serían dos verdades que pueden discrepar.

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

El **pulso** del punto (§10.4) pertenece a **`En vivo` y a nada más**: es la única señal del
panel que afirma «esto se está midiendo ahora», así que late con el dato fresco y se queda
quieto con `DATO RETENIDO` y con `SIN CONEXIÓN`. Un punto latiendo sobre una foto vieja dice
exactamente lo contrario de lo que dice su propio rótulo.

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

**Texto:** `--tk-fg-1 #F0F2F5` · `--tk-fg-2 #B8C2CE` · `--tk-fg-3 #8A9CB1` ·
`--tk-fg-disabled #4A5765`

> **`--tk-fg-3` subió de `#6F7E8F` a `#8A9CB1` el 2026-08-05 (T-2.64) y no vuelve a bajar.**
> Medido sobre `--tk-surface-1 #122B44`: **3.48:1 → 5.14:1**. WCAG 2.1 §1.4.3 pide 4.5:1 para
> texto normal, y este token pinta justo los rótulos de 8–10 px del panel y de la consola —
> los más pequeños del producto, los que se leen en un gabinete con luz de tubo. El hex
> anterior es el único valor de esta §10.1 que llegó a divergir del código; queda escrito con
> su razón porque un token de contraste sin la medición al lado se "corrige" de vuelta al mes.
>
> **`--tk-fg-4` no aparece en esta tabla y no es un olvido:** nunca fue un token del paquete,
> vivía **solo** en la paleta hardcodeada del panel del gabinete (`#8A97A6`, 4.40:1 sobre
> `--tk-surface-2` — también por debajo de AA). El nuevo `--tk-fg-3` es más claro de lo que
> `--tk-fg-4` llegó a ser, así que el matiz que aportaba desapareció con el arreglo y quedó
> **fusionado en `--tk-fg-3`**. La constancia vive en el propio panel
> (`edge/takab_edge/local_api/index.html`, comentario de la paleta).
>
> Un test de contrato lo vigila desde T-2.61: si esta tabla y
> `shared/design-tokens/css/tokens.css` vuelven a divergir, rompe
> `api/tests/test_docs_consistency.py::test_la_spec_del_panel_declara_los_hex_que_el_codigo_usa_hoy`.
> Esta spec es entrada de diseño **normativa** (T-2.15…T-2.23 se verificaron contra ella con
> un checklist 44/44); un hex muerto aquí manda mal a quien la obedezca.

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

> **Divergencia medida el 2026-08-05, anotada y no ratificada.** Lo construido baja de esta
> escala: `edge/takab_edge/local_api/index.html` declara **38 de 101** tamaños por debajo de
> 11 px (9 y 10 px), y la consola web otros **92** entre `soc.css` y `soc-tabs.css`. La escala
> de arriba sigue siendo la referencia; lo que se registra aquí es que **el producto no la
> respetó** en los rótulos secundarios, y que ese es exactamente el tramo donde el contraste
> se vuelve crítico — de ahí el token `--tk-fg-3` de §10.1 y su corrección en T-2.64. Si algún
> día se ratifica un escalón por debajo de 11 px, se escribe aquí con su razón; mientras tanto
> esto es deuda declarada, no permiso.

<!-- La línea en blanco de arriba es NORMATIVA, no formato: sin ella, CommonMark aplica
     continuación laxa y mete las cinco declaraciones de abajo DENTRO de la nota de deuda.
     Valores normativos leídos como deuda declarada. Lo vigila
     `api/tests/test_docs_consistency.py::test_ningun_valor_normativo_queda_dentro_de_un_blockquote_por_descuido`. -->

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

---

## §15 · Vista SISMÓGRAFO (`?view=sismografo`) — T-7.23

Una segunda vista del MISMO panel, al estilo de las pantallas de estación que la gente ya
conoce, pero propia: sin logotipo ajeno, sin una sola petición a internet y con su coste
medido en el Pi 4 real. No rediseña nada de lo anterior. En particular **no toca la §9**: la
jerarquía de banners, los tiers y los cuatro estados de UI son los mismos aquí que en la vista
por defecto, y el `#actionbar` sigue presente — quien está de pie delante del gabinete durante
una alerta tiene que poder silenciar desde donde esté mirando.

### 15.1 · Cómo se entra, y qué NO cambia

`http://<gabinete>:8080/?view=sismografo`. Se conmuta con la clase `.hide` sobre las mismas
zonas de siempre (`#grid` se oculta, `#sismo` se muestra); no hay router ni segunda página.

Tres cosas deliberadas:

- **La vista por DEFECTO no cambia.** Sin `?view=` el panel es exactamente el de las §§1–14.
  Esto no es cortesía: el censo de render (`edge/tests/test_panel_render_census.py`) mide la
  vista por defecto, y moverla habría cambiado la vara con la que se mide todo lo demás.
- **`?view=` desconocido cae a la vista por defecto y lo DECLARA** en la cabecera
  (`?view=<lo-que-sea> NO EXISTE → VISTA GABINETE`), igual que ya hace `?mode=`. Un parámetro
  mal escrito que no hiciera nada y no dijera nada es la peor de las dos opciones.
- **`?view=` y `?mode=` son ortogonales.** La densidad (MURO / CONSOLA / CAMPO) sigue
  aplicándose; esta vista es una superficie más, no un cuarto modo.

### 15.2 · Qué se ve

1. **Tarjeta de estación** — la identidad completa del instrumento, `red.estación.loc.canal`
   por cada canal, la sensibilidad de velocidad y la de aceleración, y **de dónde viene esa
   calibración**. Sin calibración provisionada la tarjeta dice `SIN CALIBRAR` y las unidades
   se rotulan `rel.`, exactamente como en la §8.3.

   **Y la SALUD DEL SENSOR: «Retraso del sensor» y «Paquetes vistos».** No es decoración: esta
   vista esconde `#grid`, que es donde vive `#salud-grid`, así que sin esas dos filas un
   gabinete con el sensor mudo se veía **exactamente igual** que uno vivo — el anillo de 60 s
   sigue sirviendo su último minuto bueno y no quedaba nada en pantalla que lo delatara. Las dos
   filas las **derivan las dos superficies de la misma función** (`filaRetrasoSensor`,
   `filaPaquetesVistos`): dos copias acabarían con dos umbrales. Y `packets_seen: 0` se pinta en
   ámbar, porque un gabinete sin sensor no grita, sólo deja ese cero.
2. **Espectrograma** de los últimos 60 s de UN canal, del anillo en RAM, **con la edad de su
   dato declarada siempre** y con estado propio cuando deja de ser de ahora (§15.3).
3. **Helicorder** de 1 a 6 h de UN canal, del anillo miniSEED en disco, **cortado por cada
   hueco del anillo y con los huecos declarados**, con **la edad de su última muestra** y el
   mismo estado propio que el espectrograma cuando deja de ser de ahora (§15.4.7), y con
   **la cobertura declarada** cuando lo servido no llega hasta el principio de la ventana
   (§15.4.6).

**Los botones de canal se DERIVAN de `status().station_nslc`.** Estaban enumerados a mano en el
marcado (EHZ/ENZ/ENN/ENE) mientras la lista real ya viajaba en el status: un RS3D —tres canales,
EHE/EHN/EHZ— ofrecía tres botones que no existen y escondía los suyos, y pulsar uno es pedirle
al gabinete un canal inventado. Sin canales provisionados, la botonera lo dice (`S/D · SIN
CANALES PROVISIONADOS`) en vez de salir vacía.

**Las razones de degradación se traducen.** Llegan como DATO desde la API, en snake_case, y se
imprimían tal cual en la pared («SIN ESPECTROGRAMA · canal_sin_muestras»). Un guardia de pie
frente al gabinete no lee snake_case, y el censo del glosario (`test_glosario_de_estados.py`)
tampoco las veía: extrae literales del HTML y éstas no lo eran. Ahora hay una tabla
`RAZONES_SISMO` en el panel, con frases del vocabulario del repositorio, y una guarda que exige
la **igualdad** entre las razones que el servidor puede emitir —derivadas del propio código, no
enumeradas a mano— y las claves de esa tabla.

### 15.3 · `GET /api/spectrogram` — el CUARTO endpoint

Petición: `?channel=<CH>&nperseg=<128|256>`. Lectura abierta, sin autenticación, igual que
`/api/status` y `/api/waveform`: es el panel del guardia.

```
degraded          bool      true = no hay espectrograma que pintar
reason            str|null  por qué (jamás "ok"): sin_modulo_de_senal · sin_anillo ·
                            canal_sin_muestras · muestras_insuficientes · error_de_calculo
channel           str|null  canal SERVIDO
requested_channel str|null  lo que pidió el cliente; distinto de `channel` = se sustituyó
sample_rate       float|null sps de las muestras usadas
nperseg           int       ventana FFT aplicada
noverlap          int       solape aplicado (nperseg/2)
window            str       "hann"
freq_hz[]         float     eje de frecuencias — una entrada por FILA de `rows`
t_offset_s[]      float     eje de tiempos, en segundos desde `first_sample_at` — una
                            entrada por COLUMNA
first_sample_at   ISO|null  instante de la primera muestra del tramo (cabecera del Shake)
last_sample_at    ISO|null  instante de la ÚLTIMA muestra del tramo (cabecera del Shake)
age_s             float|null `now` del Pi − `last_sample_at`. Puede ser de horas
stale             bool      `age_s > stale_after_s`: el dibujo ya no es «de ahora»
stale_after_s     float     umbral que aplicó el servidor (10 s)
gap_before        bool      hubo un hueco del sensor justo antes de este tramo
dc_counts         float|null media restada antes de transformar
db_min            float     dB que representa el valor 0 de la matriz
db_max            float     dB que representa el valor 255
rows[][]          int       matriz `uint8`, [frecuencia][tiempo]
below_scale       int       celdas por DEBAJO de db_min (saturadas a 0)
above_scale       int       celdas por ENCIMA de db_max (saturadas a 255)
```

Cinco cosas que el diseño tiene que respetar (decía «cuatro» y la lista tiene cinco desde que
`stale` entró en T-7.23·A2 — la misma clase de recuento tecleado que T-7.23·Q3):

1. **La escala en dB es FIJA, no automática.** `db_min`/`db_max` son constantes del servidor
   (`-20` y `+130` dB rel. counts²/Hz), y salen de los extremos del propio instrumento: un
   ADC de 24 bits da counts hasta ~8.4·10⁶, y a 100 sps la densidad espectral de una señal a
   fondo de escala ronda los 120 dB, mientras que 1 count² rms cae cerca de −17 dB. Una escala
   automática por petición se vería más bonita y sería una mentira: dos columnas pintadas con
   un minuto de diferencia dejarían de significar lo mismo, que es justo lo que un
   espectrograma sirve para comparar. Cuando algo se sale, `below_scale`/`above_scale` lo
   cuentan y la leyenda lo dice.
2. **La matriz viaja ENTERA en cada respuesta, no una columna.** El anillo de 60 s es toda la
   historia que hay (§6.3); servir la ventana completa significa que lo pintado es exactamente
   lo que el gabinete tiene ahora, sin que el cliente acumule columnas viejas cuyo origen ya
   nadie puede auditar. A `nperseg=128` son 65 filas × 92 columnas ≈ 24 KB de JSON.
3. **Parámetro ilegal ⇒ default, jamás 400** (misma doctrina que `/api/waveform`).
   `nperseg` fuera de `{128, 256}` cae a 128. Un `channel` que el anillo no tiene se sustituye
   por uno que sí, y la sustitución se DECLARA en `requested_channel` ≠ `channel`: el rótulo
   del panel nombra el canal servido, nunca el pedido.
4. **`gap_before: true` ⇒ el tramo no llega hasta el borde izquierdo.** El anillo corta en el
   último hueco (§6.4) y el espectrograma hereda ese corte; se rotula, no se rellena.
5. **`stale` es un estado, no un matiz.** `WaveformRing` **sólo poda al appendear**: con el
   sensor callado, el último tramo se queda en RAM tal cual y el endpoint lo servía con
   `degraded: false` y `first_sample_at` de hace tres horas, mientras la tarjeta lo rotulaba
   «últimos 60 s» con «AHORA» en el borde derecho. Eso es la regla de oro 7 justo del revés, en
   la pantalla de un sismógrafo. Ahora la respuesta declara `last_sample_at`, `age_s` y `stale`,
   y **el panel cambia de estado**: el rótulo pasa a `Espectrograma · DATO RETENIDO`, la meta
   dice `DATO RETENIDO HACE 3.0 h` en rojo, y el borde derecho del lienzo deja de decir «AHORA»
   para decir la HORA UTC de la última muestra. No es un color más pálido: el dibujo sigue
   siendo cierto, lo que dejaba de serlo era el rótulo.

   **El umbral del espectrograma son 10 s y no se inventa aquí**: es el mismo con el que la
   tabla de salud ya pinta en rojo el «Retraso del sensor» (`umbralColor(v, 2, 10)`). La
   constante se llamaba `ESPECTRO_RANCIO_S` y ahora es `RANCIO_S`, y lo comprueba
   `test_el_umbral_de_rancio_es_el_mismo_que_el_rojo_del_retraso…`. Por debajo de ese umbral
   cabe con holgura el retraso normal del enlace (~0.4 s medidos en el gabinete) y el rótulo no
   parpadea.

   **Lo que este umbral NO puede hacer es gobernar el helicorder, y hacerlo costó una falsa
   alarma en el muro.** Aquí decía «es UNO para los dos lienzos» y el helicorder lo aplicaba
   desde T-7.23·V2. Mide el retraso del anillo de RAM, que se re-pide a 1 Hz; el helicorder sale
   del anillo de DISCO y se re-pide cada 60 s. Medido con el arnés y el sensor al día
   (`age_s = 1.0 s`): a t=0 y t=9 s la tarjeta estaba bien y a t=11 s ya gritaba «EL SENSOR NO
   ENTREGA MUESTRAS NUEVAS» — unos **50 de cada 60 segundos en rojo con el gabinete sano**. Los
   cuatro campos siguen siendo los mismos y la función de dibujo también; el número es otro y
   se deriva (§15.4.7).

**Forma degradada:** sin módulo de señal, sin anillo, con el canal vacío o con menos muestras
que una ventana FFT, la respuesta es **200** con `degraded: true`, su `reason` y `rows: []`.
Nunca un 500 ni una excepción al kiosco.

### 15.4 · `GET /api/helicorder` — el QUINTO endpoint

Petición: `?channel=<CH>&hours=<1..6>`. Lectura abierta.

```
degraded          bool      true = no hay nada que pintar
reason            str|null  sin_anillo · canal_sin_ficheros · sin_dato_en_la_ventana ·
                            anillo_ilegible · ocupado
channel           str|null  canal SERVIDO
requested_channel str|null  lo que pidió el cliente
hours             float     horas SERVIDAS, acotadas a [1, 6]
requested_hours   float|null lo que pidió el cliente; distinto = se acotó
window_start      ISO|null  inicio de la ventana pedida
window_end        ISO|null  fin de la ventana (= `now` del gabinete)
sample_rate       float|null sps del dato leído
bucket_s          float     1.0 — un par mín/máx por segundo
last_sample_at    ISO|null  instante de la ÚLTIMA muestra servida (cabecera del Shake)
age_s             float|null `window_end` − `last_sample_at`. Puede ser de horas
stale             bool      `age_s > stale_after_s`: el dibujo ya no es «de ahora»
stale_after_s     float     umbral que aplicó el servidor. **NO es el del espectrograma**:
                            se DERIVA de la cadencia de esta vista (§15.4.7)
segments[]        { start ISO, buckets int, dc_counts float, minmax[] }
gaps[]            { start ISO, end ISO, seconds float }
bytes_read        int       cuánto se leyó del anillo en esta petición
files[]           str       ficheros del anillo que se tocaron
truncated         bool      el dato servido empieza DESPUÉS de `window_start`
truncated_reason  str|null  presupuesto · anillo
ring_unordered    bool      el anillo perdió la monotonía: esta ventana PUEDE estar
                            incompleta. Es una advertencia, no un apagado (§15.4.6)
```

Siete cosas que el diseño tiene que respetar (decía «cinco» y la lista tiene siete desde
T-7.23·M2 y T-7.23·V2 — ídem):

1. **`minmax[]` son pares APLANADOS** `[mín0, máx0, mín1, máx1, …]`, longitud siempre par, un
   par por segundo, en counts crudos. Es la misma forma que sirve `/api/waveform` con
   `encoding: "minmax"` (§5.1) y por la misma razón: el submuestreo se salta el pico y dibuja
   un sismo más chico del que fue.
2. **Los huecos se CORTAN y se DECLARAN.** Cada tramo continuo es un `segment` con su propio
   `start`; entre dos tramos hay una entrada en `gaps[]`. Medido en el gabinete el 2026-09-20:
   el anillo cubría 20.93 h en **siete tramos con seis huecos**, así que una ventana de 1–6 h
   cruza un hueco casi con seguridad. Rellenar con ceros escribiría «el suelo estuvo quieto»
   justo donde no hubo medición, dentro de la pantalla de un sismógrafo; unir dos tramos con
   una línea recta inventa movimiento que no ocurrió. El helicorder deja el hueco en blanco y
   lo rotula.
3. **El anillo NO se lee entero.** `RingBuffer.extract_window()` hace `obspy.read()` del
   fichero del día completo: **2.9 s y 159 MB de RSS pico** medidos sobre el fichero EHZ del
   2026-09-20 (100.2 MB a media tarde), y 8.75 s / 421 MB sobre uno de 287 MB. En un Pi 4 con
   905.7 MiB de RAM total y ~260 MiB libres eso es inaceptable para una pantalla. Este
   endpoint localiza el registro por **búsqueda binaria sobre las cabeceras miniSEED** (el
   fichero está ordenado en el tiempo y los registros son de longitud fija) y lee **sólo la
   cola** desde ese desplazamiento: 1 h en 0.17 s leyendo 5.8 MB, 6 h en 0.89 s leyendo
   34.5 MB. `bytes_read` publica lo que costó, petición a petición.
4. **UN canal y como mucho 6 h por petición.** El tope no es estético: es el presupuesto de
   memoria del Pi. Por encima de `48 MiB` leídos la ventana se recorta por el principio,
   `truncated` pasa a `true` y `truncated_reason` dice `presupuesto`. Si es el anillo el que no
   llega tan atrás, `truncated_reason` dice `anillo` — son dos hechos distintos y el operador
   tiene que poder distinguirlos.
5. **Una lectura a la vez.** Un cerrojo sin espera protege el proceso: si ya hay una lectura en
   curso, la segunda responde **200** con `degraded: true, reason: "ocupado"` en vez de apilar
   otra lectura de disco. Tres kioscos abiertos no pueden multiplicar por tres el coste del
   gabinete. **`ocupado` es el ÚNICO estado que el kiosco reintenta en el tick siguiente** (ver
   §15.5): marcarlo como una respuesta más dejaba el lienzo en blanco 60 s enteros por una
   colisión de milisegundos.
6. **La búsqueda binaria exige orden cronológico, y ahora se COMPRUEBA.** Decía «el fichero del
   día está escrito en orden (el anillo sólo appendea)», como si appendear implicara orden.
   `RingBuffer.append` escribe lo que llegue y la deduplicación de SeedLink es un `deque`
   acotado: tras una reconexión larga el Shake puede re-entregar un bloque que el deque ya
   olvidó y el anillo lo appendea al final, más viejo que su vecino. A partir de ahí la búsqueda
   binaria devuelve cualquier cosa y la cola que se lee **pierde dato sin decirlo** — y en la
   pantalla de un sismógrafo, un tramo que falta se lee como «el suelo estuvo quieto».

   Cuánto se pierde, simulado sobre el algoritmo exacto con 720 registros y un bloque
   re-entregado al final **[MEDIDO · simulación del algoritmo · 2026-09-20]**: con 40 registros
   re-entregados, 6 de las 720 posiciones de ventana pierden dato (peor caso, 6 registros); con
   239, son 122 de 720 (peor caso, 122 registros). Con el fichero en orden, cero. Y nada de eso
   levantaba `truncated`: el operador veía una pantalla llena y sin avisos.

   **El testigo del escritor AVISA; la GARANTÍA es del lector.** La primera versión de esto
   puso toda la detección en el escritor por una razón medida —barrer todas las cabeceras de un
   fichero de día cuesta 25.2 µs por cabecera **[MEDIDO · equipo de desarrollo x86-64 ·
   2026-09-20]**, o sea ~0.62 s aquí y del orden de 2.5 s en el Pi 4 sobre las ~24 500 de un EHZ
   de 100 MB: más caro que la lectura entera que se quiere hacer— y eso dejó un agujero peor que
   el original. El testigo **sólo ve el desorden que ESE proceso presenció**: al arrancar, el
   puntero se siembra con el ÚLTIMO REGISTRO del fichero, que en un fichero ya desordenado es
   justamente el re-entregado —el más viejo—, así que todo lo que venga detrás parece «más
   nuevo» y no se marca nada. Antes se perdía dato en silencio; con el testigo solo, además se
   afirmaba que el anillo estaba ordenado.

   La comprobación que SÍ cubre el caso vive en el lector y **no cuesta nada, porque usa dato
   que ya está decodificado**: tras recortar la cola a la ventana, el primer `segment` es la
   primera muestra que se va a servir. Si empieza después de `window_start`, la cobertura no es
   la que se pidió y se DECLARA (`truncated: true`, con `presupuesto` o `anillo` según la
   causa) en vez de servir media ventana como si fuera entera. Misma doctrina que
   `truncated_reason: "anillo"` ya tenía; lo que cambia es de dónde sale el instante que se
   compara —antes, de la cabecera a la que saltó la búsqueda binaria, que es justo el número que
   deja de significar nada cuando el fichero está desordenado—.

   Medido sobre el escenario real (una hora continua con un bloque de hace un minuto metido en
   el medio, la posición que la búsqueda binaria prueba primero): se sirve de 14:30 en adelante
   para una ventana que empieza a las 14:00 — media hora que existe en el anillo y no se lee —,
   y hasta esta ficha con `truncated: false`.

   **Y el testigo NO apaga el helicorder: cambia cómo se lee.** Respondía `degraded: true,
   reason: "anillo_desordenado"`, y el testigo no se borra al rodar el día sino con su fichero:
   o sea la pantalla del sismógrafo **en blanco unas 30 h porque un paquete llegó dos veces**,
   que es peor que el defecto que arreglaba — re-entregar bloques es lo que hace una reconexión
   larga de SeedLink, por diseño. La regla que gobierna esto es **servir lo que haya y DECLARAR
   lo que no se sabe**: el desorden pasa a `ring_unordered: true`, una advertencia sobre la
   VENTANA que convive con el dibujo, y apagar vuelve a ser una decisión del operador.

   Con el testigo puesto, el helicorder deja de localizar por índice —que es lo que el desorden
   invalida— y lee **la cola acotada por el presupuesto**, declarando después la cobertura real
   sobre dato decodificado (`truncated`). No es sólo que deje de apagarse: sirve MÁS. Medido
   sobre el escenario V1 escrito por `RingBuffer` (una hora continua con un bloque de hace un
   minuto en el medio) **[MEDIDO · equipo de desarrollo x86-64 · 2026-09-20]**: confiando en el
   índice se sirve desde las 14:30 para una ventana que empieza a las 14:00 y sale `truncated:
   anillo`; leyendo la cola se sirve desde las 14:00 y la ventana sale completa. El precio es
   disco: hasta `PRESUPUESTO_BYTES` en vez de los 5.8 MB de una hora, y sólo mientras ese
   fichero del día siga en el anillo.

   El testigo se queda porque es barato —**una comparación por paquete** y una escritura sólo
   cuando de verdad pasa— y avisa antes: `RingBuffer.append` deja un fichero hermano
   `<dayfile>.desorden` (ni `extract_window` ni la poda ni el glob de canales lo ven como
   miniSEED), y el helicorder lo lee en O(1). Se escribe y se registra **UNA vez por fichero**,
   no una por paquete: esto corre en el hilo de ingesta de SeedLink y justo durante la
   reconexión, que es cuando el Shake re-entrega bloques a puñados — una línea de log por
   paquete es un intervalo, no una transición (regla de oro 10), y se come la cota de log de
   T-7.47. El testigo se borra con su fichero, no al rodar el día: un anillo que perdió la
   monotonía la perdió hasta que ese fichero desaparezca.

   **Y el LECTOR anota también una sola vez, por fichero y por proceso.** El desorden dura lo
   que dura ese fichero del día y el kiosco pregunta cada 60 s: una línea por lectura serían
   del orden de mil ochocientas sobre un hecho que ocurrió una vez, el mismo intervalo
   disfrazado de evento. Su registro no sobra aunque el escritor ya tenga el suyo: el del
   escritor no ve el fichero que llegó desordenado de otro proceso o de antes del reinicio, que
   es justo el caso en que nadie lo anotó nunca.

7. **El helicorder declara la EDAD de su última muestra, y su umbral se DERIVA de su cadencia.**
   Su borde derecho decía «AHORA» con dato de cualquier edad, y es peor aquí que en el
   espectrograma porque este lienzo **sólo se repinta cuando llega dato nuevo** —cada 60 s por
   diseño, o nunca si el gabinete deja de dar dato— así que el rótulo se quedaba pegado a un
   bitmap de hace una hora. La cura es el MISMO mecanismo, no un segundo: los mismos cuatro
   campos (`last_sample_at`, `age_s`, `stale`, `stale_after_s`) y la misma función de dibujo
   (`rotularBordeDerecho`). El panel le suma a `age_s` lo que ha corrido su propio reloj
   monótono desde la respuesta y ensucia el lienzo cuando el veredicto cambia, que es lo que
   impide que un bitmap quieto siga rotulando «AHORA». Y la tarjeta pasa a `Helicorder · DATO
   RETENIDO`, como la del espectrograma.

   **El umbral, en cambio, NO puede ser el del espectrograma, y serlo costó una falsa alarma en
   el muro.** Aquí hay DOS hechos y estaban mezclados en uno:

   - **«este dibujo se calculó hace N s»** — lo declara la tarjeta (`CALCULADO HACE 37 s`) y es
     NORMAL que llegue hasta un minuto entero: se re-pide cada 60 s. No acusa a nadie;
   - **«el sensor dejó de entregar»** — una propiedad del DATO, que la tabla de salud ya mide a
     1 Hz por otro camino (`seedlink_lag_s`).

   Aplicarle al segundo el umbral del primero ponía la tarjeta en rojo con «EL SENSOR NO ENTREGA
   MUESTRAS NUEVAS» unos **50 de cada 60 segundos con el sensor sano**. El umbral del helicorder
   se deriva de las tres cosas que, con el gabinete sano, separan la última muestra del reloj
   del kiosco:

   | Sumando | Qué mide | De dónde sale |
   |---|---|---|
   | `RANCIO_S` | el retraso que el panel ya le tolera al enlace | los 10 s del rojo de «Retraso del sensor» |
   | `GRANULARIDAD_ANILLO_S` | el registro que el anillo todavía no ha escrito | **26 305 registros para 86 400 s** en el fichero EHZ real de un día **[MEDIDO · fichero EHZ del anillo de `gw-dev-0001` · 2026-09-20]**, o sea 3.28 s por registro |
   | `REFRESCO_HELI_S` | lo que el kiosco tarda en volver a preguntar | `HELI_REFRESH_MS` del panel, leído del panel por la guarda |

   `RANCIO_HELI_S` es su suma y nada más: por debajo, un helicorder viejo es lo esperado; por
   encima, ya no lo explica ninguna cadencia. Que los tres sumandos sigan siendo los del panel y
   los del anillo lo comprueba
   `test_el_umbral_del_helicorder_se_deriva_de_su_cadencia_y_de_la_del_anillo`, y que no grite en
   ningún instante del ciclo de 60 s con el sensor sano —ni calle con el sensor callado— lo
   comprueban las dos direcciones de
   `test_con_el_sensor_sano_el_helicorder_no_grita_en_ningun_instante`.

**Forma degradada:** sin módulo de anillo, sin ficheros de ese canal, con el anillo ilegible,
con otra lectura en curso, o con la ventana pedida sin una sola muestra dentro, la respuesta es
**200** con `degraded: true`, su `reason` y `segments: []`. Ese último caso
(`sin_dato_en_la_ventana`) va aparte a propósito: servirlo como respuesta buena con la lista
vacía dejaría la tarjeta diciendo «0 huecos declarados» sobre una pantalla en blanco, y el
operador leería «todo bien» donde lo que hay es «el sensor lleva horas callado».

**El anillo fuera de orden ya NO está en esa lista.** Es `ring_unordered`, que viaja **con** el
dibujo y no en su lugar — y también en la forma degradada, porque una ventana sin dato sobre un
anillo que perdió la monotonía y otra sobre uno sano mandan al operador a sitios distintos.

### 15.5 · Cadencias — y por qué el helicorder NO va a 1 Hz

La regla de la §5.1 (una sola cadencia, secuencial, sin bucles paralelos) sigue vigente y esta
vista no la relaja:

| Petición | Cadencia en esta vista | Por qué |
|---|---|---|
| `/api/status` | 1 Hz | Es la que sostiene banners, relés y estados. No se toca |
| `/api/waveform` | **no se pide** | En esta vista no hay carriles de onda: el espectrograma ocupa su lugar y pedir las dos cosas sería pagar dos veces por el mismo anillo |
| `/api/spectrogram` | 1 Hz, en el MISMO tick | 2.4 ms de cálculo medidos; a 1 Hz es ruido |
| `/api/helicorder` | cada **60 s**, o al tocar un mando | 0.17–0.89 s de lectura de disco. A 1 Hz sería el 89 % de un núcleo del Pi dedicado a repintar algo que cambia un píxel por segundo |
| `/api/catalog` | **no se pide** | El mapa y la comparativa viven en la vista por defecto |

Como el helicorder puede tener hasta 60 s de antigüedad **por diseño**, su tarjeta declara
SIEMPRE su edad (`CALCULADO HACE 37 s`). Es el caso de libro de la regla de oro 7: un dato
viejo pintado como vivo es peor que «sin datos», y aquí el dato viejo es lo normal. Esa edad es
una RESTA contra el reloj de la última respuesta buena, y la guarda que la defiende adelanta el
reloj del arnés en vez de buscar el rótulo: un marcador tapa una resta rota (T-7.60).

**Y esta cadencia es el sumando mayor del umbral de frescura del helicorder.** «Hasta 60 s de
antigüedad por diseño» y «el sensor lleva 10 s sin entregar» no pueden convivir en la misma
tarjeta: la segunda frase se cumple sola cada minuto. Por eso `REFRESCO_HELI_S` es un sumando
de `RANCIO_HELI_S` (§15.4.7) y por eso este número vive en el panel y en el servidor a la vez,
con una guarda que lo lee del panel en vez de teclearlo dos veces.

**La marca de «ya lo pedí» se pone DESPUÉS de la respuesta, y no con `ocupado`.** Se ponía
antes del `fetch`, así que un `ocupado` transitorio —otro kiosco leyendo el mismo anillo, que es
para lo que existe ese estado— dejaba el lienzo en blanco un minuto entero sin reintentar.
`ocupado` se reintenta en el tick siguiente; **las demás razones no**, y eso es justo lo que
impide que una ventana sin dato ponga a leer el disco a 1 Hz. Un 404 o un 500 tampoco se
reintentan: pedir más deprisa no arregla un gabinete que no sirve el endpoint.

### 15.6 · Movimiento y recursos

- **Cero animaciones nuevas.** El inventario de movimiento del panel sigue siendo dos
  `@keyframes` (`tk-blink`, `tk-pulse`) y ninguna `transition`, y la regla global
  `@media (prefers-reduced-motion:reduce){*{animation:none!important}}` los apaga los dos. Un
  espectrograma que se desliza sería movimiento continuo en una pantalla de pared: aquí el
  lienzo se **repinta** cuando llega dato nuevo, que no es lo mismo que animarse.
- **Cero recursos externos.** Ni fuentes, ni tiles, ni paletas de fuera: los dos lienzos son
  `<canvas>` 2D como los demás y la rampa de color se calcula en el propio script.
- **Repintado por dato, no por fotograma.** Los dos lienzos se redibujan sólo cuando cambia el
  dato que representan (o cuando cambia su estado de frescura). El espectrograma son ~6 000
  celdas: pintarlas 60 veces por segundo para enseñar la misma imagen sería quemar el
  navegador del kiosco sin ganar nada.
- **…y también cuando cambia su TAMAÑO.** `fitCanvas()` vive dentro de los dos `draw*`, que sólo
  corren por dato: un `resize` o un clic en MURO/CONSOLA/CAMPO —que cambia el alto del lienzo
  por CSS— dejaba el helicorder hasta 60 s con el bitmap viejo **estirado**, o sea un sismograma
  deformado, que es peor que uno ausente. Los dos manejadores ensucian ahora los contadores
  (`invalidarLienzosSismo()`) y el fotograma siguiente repinta, sin volver a pedir nada.
- **La rampa de color no es una paleta nueva.** Las cinco paradas del espectrograma y la franja
  ámbar del hueco eran la tercera y la cuarta copia literal de la paleta, escritas fuera del
  `:root` y fuera del objeto `C`, que son las dos únicas que el censo de color sabe leer — el
  agujero exacto de T-2.137, donde un violeta vivía inline en el rótulo que la persona lee.
  Ahora las tres paradas altas son `C.cyan`, `C.warn` y `C.crit`, las dos bajas se derivan de
  `C.surface0`, y una guarda prohíbe cualquier componente de la paleta escrito a mano en el
  bloque de esta vista.
- **El helicorder tiene piso de escala de verdad, y es el MISMO que el de los carriles.** El
  comentario prometía uno —«sin piso, un anillo en calma se dibujaría como un terremoto»— y
  debajo ponía `let amp = 1`: un count, o sea ningún piso. El arreglo puso el de los carriles de
  onda… **intercambiado entre familias de canal**, 8.33× en cada sentido, con el comentario de
  al lado afirmando lo contrario: al geófono (velocidad, cm/s) le daba el piso de los
  acelerómetros y a los acelerómetros (aceleración, g) el del geófono. En pantalla eso es un
  anillo en calma dibujado como un sismo, o un sismo dibujado como una línea plana.

  Ahora el piso vive en UN sitio (`pisoEscala`: 0.10 cm/s en velocidad, 0.012 g en aceleración)
  y la familia se elige con el MISMO predicado que decide la unidad en `toPhys` (`c[1] === 'N'`)
  — no con `c === 'EHZ'`, que además le daba el piso de aceleración a dos de los tres carriles
  de velocidad de un RS3D. La guarda **deriva el piso que le toca al helicorder de `scaleFor` y
  `toPhys`**, nunca de `pisoHeliCounts`, que es lo que está bajo prueba: la primera versión
  medía ±9 y ±400 000 counts, tan lejos de cualquier piso plausible que seguía verde con los dos
  intercambiados.

### 15.7 · Coste — cómo se mide, y qué se midió

**MEDIDO SOBRE EL ENDPOINT SERVIDO, no sobre un prototipo** — `Raspberry Pi 4 Model B
Rev 1.5`, 905.7 MiB de RAM, release `20260921T100641Z-fead5e8`, el 2026-09-21 con los comandos
de más abajo corridos desde el propio gabinete.

| Petición al panel YA DESPLEGADO | 1ª llamada | en caliente | tamaño |
|---|---|---|---|
| `/api/status` | 3.8 ms | — | 5.5 KB |
| `/api/spectrogram?channel=EHZ&nperseg=128` | **4.116 s** | 8.4 ms | 25 KB |
| `/api/spectrogram?channel=EHZ&nperseg=256` | 5.8 ms | — | 25 KB |
| `/api/helicorder?channel=EHZ&hours=1` | 221 ms | 188 ms | 51 KB |
| `/api/helicorder?channel=EHZ&hours=6` | 1.028 s | 1.087 s | 303 KB |

⚠️ **Esos 4.116 s de la primera llamada son el import perezoso de `scipy.signal`, y en el Pi
cuesta DIEZ VECES lo medido en el equipo de desarrollo** (0.39 s en x86-64). La §15.3 ya
advertía «falta medirlo en el Pi, donde será igual o peor»: es peor, y por un orden de
magnitud. Se paga UNA vez por arranque del proceso y sólo si alguien abre esta vista; la vista
por defecto del panel, el latido a la nube y la ruta de disparo no lo pagan nunca — el dueño de
los pines es otro proceso (`takab-gpio`, 14 MB de RSS, que no se entera de nada de esto).

**Memoria, y la pregunta que importa: ¿crece?** No. Tras ejercer las dos vistas el RSS de
`takab-edge` pasa de la banda de reposo (95–119 MB) a **219 MB**, y ahí se queda: tres lecturas
seguidas de 6 h más cinco espectrogramas lo dejan **exactamente en 219 MB**. Es una marca de
agua que se paga una vez —el import y los búferes que el asignador no devuelve al sistema—, no
una fuga. El sistema queda con 124 MiB libres y **526 MiB disponibles**, y `takab-gpio` intacto.

**Lo que costó leer del anillo**, en la misma corrida: una ventana de 6 h leyó **24.1 MB** del
fichero del día y sirvió **dos tramos con dos huecos declarados**, sin recorte (`truncated:
false`) y con el dato a **2.9 s** de antigüedad. El anillo tenía 20.93 h en siete tramos el día
anterior: los huecos no son una hipótesis del diseño, salen en cada lectura.

Línea base del gabinete en reposo, el día anterior: ~260 MiB libres y ~476 MiB en caché; CPU
96 % ociosa; 50 °C; `takab-edge` entre 95 y 119 MB de RSS y `takab-gpio` 27 MB. Y con el panel
nuevo sirviendo: CPU **94–99 % ociosa** en las tres pasadas de `top -bn3`.

Las cifras de PROTOTIPO que llevaron a este diseño se conservan abajo, porque son las que
explican POR QUÉ el helicorder no usa `extract_window`:

| Operación (prototipo) | Coste medido |
|---|---|
| `scipy.signal.spectrogram`, 60 s a 100 sps, `nperseg=128` (65×92) | 2.4 ms |
| `scipy.signal.spectrogram`, 60 s a 100 sps, `nperseg=256` (129×45) | 1.1 ms |
| Importar `scipy.signal` en el proceso `takab-edge` | **0.39 s y +24.3 MB de RSS** (de 94.3 a 118.6 MB). **La cifra anterior aquí era falsa** — decía «0 MB, ya está mapeado» |
| Cola del anillo, 1 h de EHZ (5.8 MB leídos) | 0.17 s |
| Cola del anillo, 6 h de EHZ (34.5 MB leídos) | 0.89 s |
| mín/máx a 1 Hz sobre esas muestras | 4–33 ms |
| `obspy.read()` del fichero del día ENTERO — **lo que este endpoint NO hace** | 2.9 s / 159 MB RSS (fichero de 100.2 MB) · 8.75 s / 421 MB (fichero de 287 MB) |

Latencias del panel antes de esta ficha, para tener con qué comparar: `/api/status` 2.5 ms
(5.4 KB) y `/api/waveform` 7.8 ms (99 KB).

**Corrección del 2026-09-20 — el import de `scipy.signal` NO es gratis.** Esta tabla afirmaba
«0 MB» apoyándose en que `scipy` aparecía en `/proc/<pid>/maps` del proceso vivo. Lo que estaba
mapeado era `scipy.integrate` (y `scipy.fft`), que es lo que arrastra `obspy`; `scipy.signal`
no. Medido de nuevo cargando exactamente lo que carga el arranque del edge: `scipy.signal` **no
está en `sys.modules`**, y el primer `from scipy import signal` cuesta **0.39 s y +24.3 MB de
RSS** (el mismo día, con otro guion, salieron 0.41 s y +24 MB: la cifra es estable).

Esa medición es **[MEDIDO · equipo de desarrollo x86-64 · Python 3.12 · 2026-09-20]**, no del
Pi 4 — en el Pi será igual o peor, y es una de las cifras que hay que re-tomar al desplegar.
Lo ancla `test_scipy_signal_no_esta_cargado_tras_el_arranque_y_su_import_no_es_gratis`, que lo
comprueba en un subproceso limpio.

**Qué se decide con eso, y por qué el import sigue siendo perezoso.** La primera petición a
`/api/spectrogram` paga 0.39 s y +24.3 MB, una vez y para siempre, en el mismo proceso que corre
SeedLink y las reglas. Se paga ahí y no en el arranque porque un gabinete que nunca abre esta
vista —que son casi todos— no tiene por qué llevar 24 MB residentes en un Pi con ~260 MiB
libres. Lo que ese cuarto de segundo **no puede tocar** es la ruta de disparo: SASMEX→relé vive
en otro proceso (`takab-gpio`, regla de oro 4), así que el peor efecto de la pausa es un tick
del panel tarde y un segundo de SeedLink esperando en el búfer del socket.

**Y el presupuesto de 48 MiB del helicorder, re-derivado con esos 24 MB dentro de la cuenta**
(se había calculado suponiéndolos cero):

```
  ~260 MiB libres en reposo                       [PROTOTIPO · Pi 4 · 2026-09-20]
  −  24.3 MB  scipy.signal, residentes desde la primera petición de la vista
  = ~236 MiB libres con la vista SISMÓGRAFO abierta
  −  ~76 MB   pico de RSS de una lectura de 48 MiB (obspy pide ~1.5× lo leído)
  = ~160 MiB libres en el peor instante
```

**El número no baja, y la razón no es la memoria: es el dato.** 6 h de EHZ midieron 34.5 MB, así
que cualquier tope por debajo de ~35 MB convertiría `truncated_reason: "presupuesto"` en el
desenlace NORMAL de una ventana de 6 h sobre el anillo real — el panel estaría recortando dato
bueno y culpando al presupuesto. 48 MiB son esos 34.5 MB con 1.46× de holgura para un anillo más
denso, y siguen dejando ~160 MiB libres en el peor instante.

**Cómo se re-miden en el Pi** (sobre el gabinete ya desplegado, desde el propio Pi):

```sh
# 1 · CPU y memoria del gabinete con el panel abierto en la vista sismógrafo.
#     Tres iteraciones: la primera de `top` trae medias desde el arranque y no
#     sirve para nada; la tercera es la que se apunta.
top -bn3 | grep -E '^(%Cpu|MiB Mem|MiB Swap)|takab-(edge|gpio)'

# 2 · Latencia y peso de cada endpoint, ya servidos.
for u in \
  'http://127.0.0.1:8080/api/status' \
  'http://127.0.0.1:8080/api/spectrogram?channel=EHZ&nperseg=128' \
  'http://127.0.0.1:8080/api/spectrogram?channel=EHZ&nperseg=256' \
  'http://127.0.0.1:8080/api/helicorder?channel=EHZ&hours=1' \
  'http://127.0.0.1:8080/api/helicorder?channel=EHZ&hours=6' ; do
  curl -s -o /dev/null -w "%{time_total}s  %{size_download}B  $u\n" "$u"
done

# 3 · El helicorder otra vez, en caliente, para separar el disco del cálculo.
curl -s 'http://127.0.0.1:8080/api/helicorder?channel=EHZ&hours=6' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["bytes_read"], len(d["segments"]), len(d["gaps"]))'
```

Lo que hay que mirar al leerlas: que `takab-gpio` **no se mueva** —no comparte proceso con
esto y no puede aparecer en la cuenta—, que el RSS de `takab-edge` vuelva a su banda de
95–119 MB después de la petición de 6 h, y que `bytes_read` siga siendo una fracción del
fichero del día.

### 15.8 · Todo número medido lleva su procedencia

Las mismas cifras estaban en tres sitios —esta spec, el docstring de `sismografo.py` y los
comentarios de `index.html`— y **sólo aquí llevaban la advertencia de que son de prototipo**.
Una cifra sin procedencia se lee como definitiva, y la primera factura ya se pagó en esta misma
ficha: «importar `scipy` no cuesta RSS» era una conclusión sacada de una medición que medía
otra cosa.

**Y hay una tercera clase de cifra, que no se etiqueta: se BORRA.** Un RECUENTO de algo que el
propio repositorio puede contar —cuántas puertas de JSON hay, cuántos ítems tiene una lista de
esta spec— no lleva procedencia que valga: se deriva o no se escribe. Los tres casos medidos en
T-7.23·Q3 estaban aquí mismo: «15» en la §15.9 contra «21» en el docstring del censo, «cuatro
cosas» sobre una lista de cinco en la §15.3 y «cinco» sobre una de siete en la §15.4.

Dos etiquetas, y ninguna cifra MEDIDA sin una de ellas:

- **`[PROTOTIPO · <equipo> · <fecha>]`** — se midió la OPERACIÓN que el endpoint hace, no el
  endpoint servido. Son las de la tabla de arriba y se re-toman tras desplegar.
- **`[MEDIDO · <equipo> · <fecha>]`** — se midió lo que se nombra, en el equipo que se nombra.

Lo vigila `test_ninguna_cifra_medida_se_repite_sin_su_etiqueta_de_procedencia`, que **deriva la
lista de cifras de la tabla de la §15.7** —no la teclea— y exige que cualquier repetición en
`sismografo.py` o en `index.html` viva dentro de un comentario que lleve etiqueta.

### 15.9 · El JSON que sale nunca puede romper al kiosco

`json.dumps` de Python escribe `Infinity`, `-Infinity` y `NaN` tal cual, y **eso no es JSON**:
el `JSON.parse` del kiosco lanza, la excepción sube al `catch` del tick y el panel declara caído
un gabinete perfectamente sano — peor que el 400 que la doctrina de estos endpoints prohíbe.

Entraba por la puerta más tonta: `?hours=inf` **parsea** en Python (igual que `nan` y `1e400`),
caía fuera del `except` de `_helicorder_params` y viajaba crudo hasta `requested_hours`. Pero el
agujero no era ése: era que **ningún flotante de la respuesta estaba mirado**.

Dos verjas, cada una con su guarda, porque la de la salida tapa a la de la entrada:

1. **El parámetro se arregla donde se lee**: un `hours` no finito es `None`, igual que
   `?hours=hola`.
2. **El cuerpo se sanea donde se escribe**: `sanear_no_finitos` recorre la respuesta entera —a
   cualquier profundidad, listas y diccionarios incluidos— y convierte todo no-finito en `null`,
   que es la forma que el contrato ya tiene para «este número no existe». Se aplica a **todas**
   las respuestas JSON del panel, no sólo a la que tenía el defecto.

**«La única puerta» era una afirmación, no un hecho.** `_send_json` decía serlo mientras varios
`json.dumps` sueltos del mismo manejador —los cuerpos de error de `do_GET`, los de `do_POST` y
los del grant de CCTV— salían al socket sin pasar por ella, y una sola guarda la ejercía
(la del helicorder): medido, devolviendo `/api/status`, `/api/waveform`, `/api/spectrogram` y
`/api/catalog` a un `self._send(200, json.dumps(…))` crudo, la suite del edge seguía en
**489 passed**. Ahora todos pasan por la puerta y lo exigen dos censos que se DERIVAN del árbol
de sintaxis de `_DashboardHandler`, no de una lista: ningún `json.dumps` dentro del manejador, y
ningún `_send` que sirva el `application/json` por defecto sin pasar por `_send_json`. La prueba
de comportamiento saca además la lista de endpoints de `do_GET`, así que el sexto que alguien
añada entra solo.

**CUÁNTAS eran no se escribe en ninguna prosa [T-7.23 · Q3].** Este párrafo decía «15» mientras
el docstring del censo decía «21»: dos recuentos del mismo barrido, uno de los dos falso por
construcción y ninguno medido por nadie. Las puertas las cuenta
`_puertas_de_json_del_panel`, que las deriva del `ast`, y una guarda prohíbe que la cifra
vuelva a teclearse en los docstrings de `_send_json` y de su censo. Misma familia que la de
`scipy.signal` de la §15.7: una cifra en un comentario no la mide nadie.

**Y el saneo cuesta lo que vale.** Reconstruía la respuesta ENTERA en Python, incluidas las
listas de muestras de `/api/waveform`, donde un no-finito no cabe: son enteros decimados. Medido
**[MEDIDO · equipo de desarrollo x86-64 · Python 3.12 · 2026-09-20]**, con el `json.dumps` que
ya se hacía como vara:

| Cuerpo | `json.dumps` | saneo + `json.dumps` | `json.dumps(allow_nan=False)` |
|---|---|---|---|
| `/api/waveform`, 8 000 valores | 0.61 ms | **1.82 ms** | 0.43 ms |
| helicorder de 6 h, 43 200 valores | 2.43 ms | **9.95 ms** | 2.37 ms |

`allow_nan=False` hace la comprobación dentro del codificador en C, que es el mismo recorrido
que ya se hacía, y levanta `ValueError` sin haber escrito nada cuando encuentra uno. Así que el
cuerpo se vuelca directo y el saneador corre **sólo cuando de verdad hay algo que sanear**
(12.05 ms sobre el peor cuerpo, una vez y no una por petición). La verja no se relaja: lo que se
quita es el peaje del camino limpio. Y no se enumera qué endpoints o qué campos pueden traer un
no-finito — esa lista se quedaría atrás igual que se quedaría la del saneador. Lo mide
`test_el_saneo_del_cuerpo_no_lo_paga_el_camino_limpio`, que cuenta CUÁNTAS VECES corre el
saneador y no cuánto tarda: un reloj en el CI es ruido.

### 15.10 · Lo que esta vista NO hace

- **No añade una fuente de disparo.** Nada de lo que hay aquí toca reglas, relés ni la ruta
  SASMEX→actuador: son tres lecturas de sólo lectura sobre memoria y disco. El proceso que
  sostiene los pines (`takab-gpio`) es otro y no se entera.
- **No pone magnitud, ni cuenta regresiva, ni escala de intensidad.** Las prohibiciones de la
  §12 valen igual aquí.
- **No sube waveform crudo a ninguna parte** (regla de oro 9): todo se queda en la LAN.
- **No sustituye a la vista por defecto.** Es una pantalla para quien quiere mirar el
  instrumento; la que decide si hay que evacuar sigue siendo la otra.
