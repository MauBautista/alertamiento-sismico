# VERIFICACIÓN MANUAL — T-2.23 · Panel del gabinete rediseñado

> Los tests de pytest anclan el contrato (literales, escenas, tick único, estáticos,
> catálogo, recursos vetados). **El render de canvas se valida manualmente** con esta
> checklist — un test de DOM no ve píxeles. Corre el panel local con
> `uv run --directory edge takab-edge` (supervisor dev con simulador RS4D) y abre
> `http://localhost:8080/`.

> **RECORRIDO AUTOMATIZADO EJECUTADO (2026-07-31, navegador real):** Playwright/Chromium
> contra el **panel en producción** (`192.168.3.91:8080`, `main=902ab91`) — **44/44
> comprobaciones en verde**: §1 completo (10 escenas con asserts + capturas), §2 canvas
> pintando (conteo de píxeles con tinta), §3 mapa/rosa/catálogo/geografía, §4 red 100 %
> same-origin + cadencia 1 Hz secuencial + consola limpia + two-step con desarme real (las
> acciones SOLO contra el supervisor dev con relés mock), y el kiosco de §5 en lo medible
> (soak de 6 min: heap PLANO en 9.5 MB; el panel atravesó un restart del servicio a mitad
> del soak y volvió solo a EN VIVO). **Pescó y cerró un defecto real**: la franja SSN del
> modo MURO estaba condenada por un `display:none` inline (fix PR #30, re-verificado en el
> gabinete). Capturas y detalle: informe visual publicado como Artifact de la sesión.
> **PRESENCIAL EJECUTADO Y CONFIRMADO (2026-07-31, Mauricio en el sitio):**
> - **Pruebas audibles** (2 corridas, la segunda a las 12:36 UTC): PROBAR SIRENA 2 s y
>   PROBAR ACTUADORES ~5 s sostenidos — relés 5/5 con readback ✓, **`aplay` capturado EN VIVO
>   reproduciendo `siren.wav` por el jack** durante ambos sostenes (PIDs 14301/14325), cero
>   cadena de alerta (journal: "NO es alerta real" ×2, sin transición de tier, nada a la
>   nube). **Confirmación auditiva del operador: «se oyó todo bien»** — sirena de relé,
>   altavoz del jack y estrobo.
> - **WR-1 físico**: contacto real disparado en sitio — **reflejo SASMEX→relé 4.16 ms en
>   frío** (re-flancos 0.11/0.19 ms) contra presupuesto de 100 ms; `reflex_s` pintado en el
>   panel. (El disparo salió a la nube porque un armado del modo prueba falló con 401
>   silencioso — incidente cerrado con nota de auditoría; el rechazo silencioso quedó
>   corregido en PR #32: ahora se grita en banner `role=alert` y sondear sin PIN ya no
>   quema el lockout.)
> - **PIN de producción**: ejercitado de verdad en sitio (armados/desarmes, silencios,
>   pruebas) — flujo 200/401 vivido y endurecido.
>
> **Con esto, el checklist queda CERRADO al 100 %**: contrato por pytest (49), recorrido
> visual con navegador real (44/44 + soak), y lo presencial confirmado por el operador.

## 1 · Las 15 escenas (10 de §13.2 + 5 añadidas) × 3 densidades

> **[T-6.28 · 2026-09-07]** Esta tabla enumeraba 10 escenas cuando el panel tenía 13, y
> describía `prueba_actuadores` como «banner cian, relés en cian» cuando desde `T-2.85.a` es la
> prueba **terminada** con su tarjeta de resultado (U-12). Ahora la lista se compara por
> igualdad con la del código (`edge/tests/test_local_api.py::test_el_checklist_enumera_
> exactamente_las_escenas_del_panel`): una escena nueva sin fila aquí pone el CI en rojo. Las
> escenas `simulacro` y `prueba_actuadores` ya **no** fuerzan `siren_sounding` sobre un relé en
> reposo (U-11): la línea de estado y la tarjeta del relé de sirena dicen lo mismo.

Recorre `?demo=<escena>` en los 3 modos (`?mode=muro`, `?mode=consola`, `?mode=campo`
o el conmutador de cabecera). El ribbon `DEMO · NO ES ESTADO REAL` debe ser visible
SIEMPRE que `?demo=` esté en la URL. Un `?mode=` que no sea una de las tres densidades cae a
AUTO y la cabecera lo declara (`?mode=xyz NO EXISTE → DENSIDAD AUTO`).

| Escena | Qué verificar |
|---|---|
| `?demo=reposo` | Tier verde `✓ NORMAL · SIN ALERTA`; barras de proximidad casi vacías; ondas con ruido fino; UPS `line · 100 % · 41 min` |
| `?demo=vigilancia` | Tier ámbar `▲ VIGILANCIA`; barra PGA en ámbar; ondas moduladas |
| `?demo=alerta` | Banner rojo `ALERTA SÍSMICA · PROTÉJASE` PARPADEANDO; los relés `ACTIVADO` en rojo; `SIRENA: SONANDO`; marcas SASMEX/TIER sobre las trazas; botón `CERRAR ALERTA` (two-step) |
| `?demo=aviso` | Banner ámbar `⚠️ AVISO SÍSMICO · MOVIMIENTO FUERTE (UMBRAL INSTRUMENTAL)` con `SOLO AVISO · SIN ACTUACIÓN`; tier `■ EVACUAR / RESGUARDO` **sin** relés activados ni sirena: una estación sola no actúa (T-2.32) |
| `?demo=simulacro` | Banner ámbar `🔶 SIMULACRO — ESTO NO ES UNA ALERTA REAL`, sin parpadeo; meta `DRILL-… · 4 m / 8 m · INICIADO hh:mm:ss UTC`; sub `Voceo de simulacro en curso`; **`SIRENA: EN REPOSO` y relé de sirena `REPOSO`** (el simulacro es voceo por jack, cero relés) |
| `?demo=simulacro_abortado` | Banner rojo de alerta ARRIBA y, justo debajo, ámbar `SIMULACRO ABORTADO — ALERTA REAL EN CURSO (SASMEX real)` con meta `… · ABORTADO hh:mm:ss UTC · hace 42 s`; el aviso se retira solo a los 30 min (T-6.29) |
| `?demo=prueba_actuadores_en_curso` | Banner cian `🔧 PRUEBA DE ACTUADORES — NO ES ALERTA REAL`; relés `ACTIVADO` **en cian, no rojo**; `SIRENA: SONANDO · PRUEBA` (aquí sí suena, por el relé); tarjeta de prueba `EN CURSO` |
| `?demo=prueba_actuadores` | Prueba **terminada**: banner cian oculto, relés en `REPOSO`, `SIRENA: EN REPOSO`; la tarjeta de resultado dice `1 RELÉ SIN CONFIRMAR` y distingue por canal sostenido OK / pulso OK / **no confirmó** (`gas_valve`) / **no se probó** (T-2.85.a) |
| `?demo=wr1` | Banner violeta con cuenta atrás; visible el banner AUNQUE cambies a `alerta` no aplica en demo (escenas exclusivas) — la precedencia real se prueba armando el modo en el gabinete |
| `?demo=sin_senal` | Tier ámbar `⚠ MODO MANUAL — SENSORES DEGRADADOS`; carriles VACÍOS punteados (no línea plana); `SIN SEÑAL DEL SENSOR` por carril; lag en horas en rojo |
| `?demo=sin_nube` | Pill ámbar `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · 47 EN COLA` (ámbar informativo, NO rojo); RTT `S/D` |
| `?demo=arranque_frio` | TODAS las secciones degradadas a la vez: tier ámbar de arranque, relés `S/D`, umbrales `S/D`, `SIN UBICACIÓN PROVISIONADA`, calibración `SIN CALIBRAR`, salud `S/D · SIN DIAGNÓSTICO AÚN` — cero valores inventados, GET sigue 20
| `?demo=dato_retenido` | Pill ámbar `DATO RETENIDO DESDE 14:22:07 UTC`; los datos se ven pero declarados viejos |
| `?demo=retirado` | Banner `📋 RETIRADO EN LA NUBE · ESTE GABINETE SIGUE PROTEGIENDO` al FONDO de la pila (nunca sobre una alerta); evidencia atascada e ilegible declarada (T-2.65) |
| `?demo=gpio_caido` | Relés `S/D` con la razón `gpio_unreachable`: la avería en caliente del proceso de relés, distinta de un arranque en frío (T-2.68) |

## 2 · Ondas (§6) — variantes A y B

- [ ] Variante A: 4 carriles iguales, trazas min/máx por píxel.
- [ ] Variante B: carril `ENZ` a 3×, envolvente rellena + líneas de retención de pico.
- [ ] Líneas de umbral punteadas (ámbar cautela / rojo disparo) en TODOS los carriles
      (PGA en EN\*, **PGV en EHZ** — corregido del prototipo).
- [ ] `encoding: "minmax"` (llega en el reset inicial, factor 4) se ve como **banda**, no línea.
- [ ] Un hueco del sensor corta el trazo (probar matando el simulador unos segundos).
- [ ] Escala vigente rotulada por carril (`± … · piso de escala fijo`).
- [ ] `SIN CALIBRAR · UNIDADES rel.` visible mientras `calibration.calibrated=false`
      (el supervisor dev arranca sin procedencia).

## 3 · Mapa y rosa (§7)

- [ ] Rosa con vector horizontal ENN/ENE vibrando y barra Z contra umbral.
- [ ] Vecinas REALES de `neighbors[]` proyectadas por rumbo/distancia (en dev: vacío ⇒
      nota "Sin vecinas provisionadas").
- [ ] `AMPLIAR MAPA REGIONAL`: costas y estados de Natural Earth bajo la retícula,
      anillos 100/200/400/800 km SOLO si hay sitio; epicentros con área ∝ M; clic en un
      evento del listado lo resalta con su radial.
- [ ] Sin `site_lat/lon`: `SIN UBICACIÓN PROVISIONADA`, sin anillos, sin centro inventado.
- [ ] Rótulo `GEOGRAFÍA: NATURAL EARTH · DOMINIO PÚBLICO` visible.

## 4 · Red y honestidad

- [ ] DevTools → Network: **cero peticiones fuera de localhost** (fuentes incluidas:
      `/fonts/geist.ttf` y `/fonts/jbmono.woff2` en 200 con `max-age=86400`).
- [ ] Consola del navegador sin errores.
- [ ] Un solo request `/api/status` + uno `/api/waveform` por segundo (secuenciales);
      `/api/catalog` solo al arrancar y cada ~10 min.
- [ ] Apagar la API ⇒ `DATO RETENIDO…` y luego `SIN CONEXIÓN…` con backoff 2 s → 5 s,
      y el punto del pill **deja de latir** en cuanto el dato deja de ser de ahora.
- [ ] PIN: sin PIN configurado en prod ⇒ `SIN PIN CONFIGURADO · ACCIONES BLOQUEADAS`;
      PIN malo ⇒ `PIN INCORRECTO`; 5 intentos ⇒ `BLOQUEADO POR INTENTOS · ESPERA 60 s`;
      two-step se desarma SOLO a los 5 s.
- [ ] Recargar la página ⇒ el PIN se pide de nuevo (no persiste).

## 5 · Kiosco (smoke en el Pi, tras merge)

- [ ] 10 min abierto: fluidez, memoria estable (DevTools performance monitor).
- [ ] Fuentes Geist/JetBrains Mono aplicadas (no la pila del sistema).
- [ ] `?mode=muro` en el monitor de pared: tier a 72 px, sin acciones, sin PIN.
- [ ] Prueba WR-1 real ⇒ `latencies.reflex_s` pasa de `S/D` a ~6-7 ms pintado contra
      el presupuesto de 100 ms.
