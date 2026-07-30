# Panel local del gabinete — notas de diseño

Entregable: `Panel Gabinete.dc.html` (prototipo vivo, datos simulados a 1 Hz).
Escenas, modo de densidad y variante se conmutan en la barra de demostración superior
(no forma parte del panel; se apaga con el prop `showHarness`).

## 1 · Modos de densidad y breakpoints declarados

| Modo | Regla | Carácter |
|---|---|---|
| **CAMPO** | `< 1024 px` | Una columna, botonera de prueba arriba, objetivos táctiles ≥ 48 px, PIN de 48 px |
| **CONSOLA** | `1024 – 1919 px` | Densidad máxima. Ancho mínimo real del layout: **1280 px** (por debajo hay scroll horizontal, nunca compresión de datos) |
| **MURO** | manual | Solo lectura. Tier a 72 px, ondas a pantalla completa, relés a 28 px. Sin acciones y sin PIN |

El cambio automático ocurre al redimensionar; el conmutador manual siempre gana (un monitor de
1080p en pared se fuerza a MURO).

## 2 · Tipografía — decisión (§10.3): **opción (a), empaquetada localmente**

- **Geist** se sirve desde el propio Pi (`fonts/Geist_wght_.ttf`, variable 100–900, `font-display: block`).
  Un solo archivo cubre todos los pesos de interfaz.
- **JetBrains Mono** se declara primero en la pila de datos y se empaqueta como subconjunto
  (`0-9 . , : ± ° < > · a-z A-Z /`, latin básico) en el aprovisionamiento; la pila cae a
  `ui-monospace / Menlo / Consolas` si el archivo no está presente.
- **Saira Condensed no se empaqueta.** Es marca, no interfaz: el panel solo muestra el isotipo (SVG local).

Justificación: la monoespaciada carga todos los datos y es la que define la lectura a 5 m;
el costo de un subconjunto woff2 (~25 KB) es despreciable contra el riesgo de que el panel
se vea distinto en cada sistema operativo del inmueble. Cero peticiones externas: sin CDN,
sin Google Fonts, sin tiles.

## 3 · Ondas — dos variantes (conmutador `VARIANTE ONDAS + MAPA`)

- **A · trazas min/máx por píxel** — cuatro carriles iguales, lectura de sismograma clásica.
  El mapa es el **plano de estación**: anillos de 5/10/25/50 km, vecinas con estado de
  corroboración, rosa de ejes al centro, barra vertical Z contra el umbral.
- **B · envolvente rellena + retención de pico** — carril dominante `ENZ` a 3× y tres carriles
  compactos. El mapa se convierte en **instrumento de ejes**: vector horizontal resultante
  ENN/ENE sobre dial, magnitud Z como columna con marca de disparo.

Comunes a ambas: escala vertical independiente por canal (geófono `cm/s` vs acelerómetro `g`),
piso de escala fijo rotulado en pantalla, líneas de cautela/disparo, ticks de saturación en rojo,
marca vertical de SASMEX y de transición de tier, decimación declarada
(`100 sps del sensor · decimado a 50 sps en pantalla`), y rótulo `SIN CALIBRAR · UNIDADES rel.`
mientras no haya procedencia instrumental (P-7).

## 4 · Honestidad de datos implementada

- `S/D` / `<0.001 g` / `0.000 g` según corresponda; nunca un número inventado.
- Todo diagnóstico de salud declara su edad (`DIAGNÓSTICO DE HACE 38 s`); el panel nunca dispara sondas.
- `sin_senal` no dibuja línea plana: dibuja el carril vacío con su razón, y el tier baja a
  `⚠ MODO MANUAL — SENSORES DEGRADADOS` (ámbar, nunca verde).
- `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · 47 EN COLA` es ámbar informativo, no rojo de falla.
- Tres estados por relé: `ACTIVADO` (lógico) · `ENERGIZADO/DESENERGIZADO` (eléctrico) · fail-safe.
  En `fail_close` y `NC` se ven correctamente opuestos.
- Sin cuenta regresiva, sin magnitud preliminar, sin `localStorage`: el PIN vive en memoria de la
  página y se vuelve a pedir al recargar. En MURO no se pide nunca.
- Precedencia de banners respetada: alerta real tapa todo; el banner violeta de MODO PRUEBA WR-1
  permanece visible incluso bajo alerta real.

## 5 · Mapa regional y registro de sismos (SSN)

- El **mapa ampliado** (`AMPLIAR MAPA REGIONAL`) se abre como overlay a pantalla completa:
  proyección equirectangular local, retícula de grados, anillos de 100/200/400/800 km desde el
  sitio, estaciones de la red, epicentros del SSN con área proporcional a la magnitud, y
  referencias urbanas en coordenadas reales.
- **No hay geometría dibujada a mano**: ni costas, ni fronteras, ni tiles. Todo lo que se
  ve es un punto con coordenadas verificables. El panel es offline por diseño (§10.3), así que
  ningún mapa de tiles es admisible; la retícula + los anillos dan el anclaje geográfico.
- El **registro de sismos** vive en el segundo tab del panel de bitácora (`Bitácora local` /
  `Sismicidad SSN`) y completo en el overlay: magnitud, epicentro, fecha y hora del centro,
  profundidad y **distancia + rumbo calculados al sitio** (haversine). Al hacer clic en un evento
  se resalta en el mapa con su radial al sitio.
- **Procedencia declarada, no en vivo.** Los datos son una instantánea del catálogo del
  Servicio Sismológico Nacional (UNAM) en `data/ssn-sismos.json`, con su marca de captura
  visible en pantalla (`INSTANTÁNEA DEL CATÁLOGO · …`). El gabinete no puede hacer scraping en
  producción: no tiene salida a internet y el SSN no es una fuente de alertamiento
  (el propio SSN aclara que no opera alerta sísmica). En el equipo real este bloque lo
  alimenta la nube de Takab por mTLS y degrada a `CATÁLOGO NO DISPONIBLE · SIN DATOS EN CACHÉ`.
- Coherente con la regla de color: la escala de magnitud usa verde/amarillo/ámbar/rojo del
  sistema, nunca verde como color de marca.

## 6 · Pendientes de backend que el diseño ya consume

P-1 buffer de forma de onda · P-2 umbrales del sitio · P-3 latencias de la cadena crítica ·
P-4 contadores del flujo · P-5 agregador rodante · P-6 coordenadas del sitio · P-7 bandera de
calibración · P-8 autonomía del UPS. Cada módulo degrada solo si su dato falta.
