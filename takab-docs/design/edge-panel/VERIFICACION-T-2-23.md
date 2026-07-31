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
> **Sigue pendiente lo presencial:** pruebas audibles, disparo físico del WR-1
> (`reflex_s` de S/D a ~7 ms), PIN de producción en sitio y la apreciación estética en el
> monitor del inmueble.

## 1 · Los 10 estados (§13.2) × 3 densidades

Recorre `?demo=<escena>` en los 3 modos (`?mode=muro`, `?mode=consola`, `?mode=campo`
o el conmutador de cabecera). El ribbon `DEMO · NO ES ESTADO REAL` debe ser visible
SIEMPRE que `?demo=` esté en la URL.

| Escena | Qué verificar |
|---|---|
| `?demo=reposo` | Tier verde `✓ NORMAL · SIN ALERTA`; barras de proximidad casi vacías; ondas con ruido fino; UPS `line · 100 % · 41 min` |
| `?demo=vigilancia` | Tier ámbar `▲ VIGILANCIA`; barra PGA en ámbar; ondas moduladas |
| `?demo=alerta` | Banner rojo `ALERTA SÍSMICA · PROTÉJASE` PARPADEANDO; los 5 relés `ACTIVADO`; marcas SASMEX/TIER sobre las trazas; botón `CERRAR ALERTA` (two-step) |
| `?demo=simulacro` | Banner ámbar `🔶 SIMULACRO — ESTO NO ES UNA ALERTA REAL`, sin parpadeo |
| `?demo=prueba_actuadores` | Banner cian `🔧 PRUEBA DE ACTUADORES`; relés en cian, no rojo |
| `?demo=wr1` | Banner violeta con cuenta atrás; visible el banner AUNQUE cambies a `alerta` no aplica en demo (escenas exclusivas) — la precedencia real se prueba armando el modo en el gabinete |
| `?demo=sin_senal` | Tier ámbar `⚠ MODO MANUAL — SENSORES DEGRADADOS`; carriles VACÍOS punteados (no línea plana); `SIN SEÑAL DEL SENSOR` por carril; lag en horas en rojo |
| `?demo=sin_nube` | Pill ámbar `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · 47 EN COLA` (ámbar informativo, NO rojo); RTT `S/D` |
| `?demo=arranque_frio` | TODAS las secciones degradadas a la vez: tier ámbar de arranque, relés `S/D`, umbrales `S/D`, `SIN UBICACIÓN PROVISIONADA`, calibración `SIN CALIBRAR`, salud `S/D · SIN DIAGNÓSTICO AÚN` — cero valores inventados, GET sigue 200 |
| `?demo=dato_retenido` | Pill ámbar `DATO RETENIDO DESDE 14:22:07 UTC`; los datos se ven pero declarados viejos |

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
- [ ] Apagar la API ⇒ `DATO RETENIDO…` y luego `SIN CONEXIÓN…` con backoff 2 s → 5 s.
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
