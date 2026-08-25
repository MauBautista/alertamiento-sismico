---
name: TAKAB Ailert — Landing pública
description: Swiss Industrial Print — la landing como documento técnico en papel, tinta y un solo rojo de dictamen.
colors:
  papel: "#F4F4F0"
  banda: "#EAE8E3"
  tinta: "#14181E"
  humo: "#556070"
  regla: "#C8CED6"
  alerta: "#C4302B"
  marca: "#0E2336"
  sobre-marca: "#F4F4F0"
  sobre-marca-2: "#B8C2CE"
  blanco: "#FFFFFF"
typography:
  display:
    fontFamily: "Saira Condensed, Saira Condensed Fallback, Franklin Gothic Medium, Impact, sans-serif"
    fontSize: "clamp(3rem, 1.1rem + 9vw, 10.5rem)"
    fontWeight: 700
    lineHeight: 0.92
    letterSpacing: "-0.01em"
  h2:
    fontFamily: "Saira Condensed, Saira Condensed Fallback, Franklin Gothic Medium, Impact, sans-serif"
    fontSize: "clamp(2rem, 1.3rem + 3.5vw, 4.25rem)"
    fontWeight: 700
    lineHeight: 0.95
    letterSpacing: "-0.01em"
  h3:
    fontFamily: "Saira Condensed, Saira Condensed Fallback, Franklin Gothic Medium, Impact, sans-serif"
    fontSize: "clamp(1.25rem, 1.1rem + 0.8vw, 1.625rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "0"
  body:
    fontFamily: "Archivo, Archivo Fallback, Arial, Helvetica Neue, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.6
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, Liberation Mono, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    letterSpacing: "0.08em"
  label:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, Liberation Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    letterSpacing: "0.08em"
    fontFeature: "tabular-nums"
rounded:
  none: "0px"
spacing:
  e-1: "4px"
  e-2: "8px"
  e-3: "12px"
  e-4: "16px"
  e-5: "24px"
  e-6: "32px"
  e-7: "48px"
  e-8: "64px"
  e-9: "96px"
  e-10: "128px"
  e-11: "192px"
components:
  button-primary:
    backgroundColor: "{colors.tinta}"
    textColor: "{colors.papel}"
    typography: "{typography.mono}"
    rounded: "{rounded.none}"
    padding: "14px 22px"
  button-primary-hover:
    backgroundColor: "{colors.alerta}"
    textColor: "{colors.blanco}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.tinta}"
    typography: "{typography.mono}"
    rounded: "{rounded.none}"
    padding: "14px 22px"
  button-secondary-hover:
    backgroundColor: "{colors.tinta}"
    textColor: "{colors.papel}"
---

# Design System: TAKAB Ailert — Landing pública

<!-- Registrado DESPUÉS del build por el documenter de impeccable (2026-08-25).
     Verdad del sistema: landing/src/styles/tokens.css + global.css y el build en
     landing/dist/. Ámbito: SOLO la landing pública (landing/). La consola SOC
     (web/) tiene otro sistema visual (shared/design-tokens) que este documento
     NO gobierna. -->

## Overview

**Creative North Star: "El documento técnico"** — Swiss Industrial Print.

La landing no se diseña como folleto SaaS sino como el artefacto más serio que produce el propio sistema: el dictamen. Papel, tinta y un solo rojo; retícula visible; compartimentos separados por reglas y por hilos; cero ornamento. Cada color de la paleta proviene de un artefacto real de TAKAB (la tinta y el rojo del PDF de dictamen, el navy de la consola): nada se inventó para marketing, y esa procedencia es parte de la identidad.

El documento es la metáfora estructural, no solo el tono: las secciones se abren con una regla dura de 2 px a sangre completa y un cajetín de metadatos con folio («SEC 01 / 07»), como hojas de un documento paginado. La página es deliberadamente papel — `color-scheme: light` fijo — en cualquier tema del sistema operativo. La honestidad del producto se traduce en honestidad visual: sin capturas simuladas, sin contadores decorativos, sin teatro.

**Key Characteristics:**

- Paleta plana extraída de artefactos reales; el rojo de dictamen (#C4302B) como único acento.
- Display condensado en mayúsculas (Saira Condensed 700) contra cuerpo neutro (Archivo) y telemetría mono (JetBrains Mono).
- Retícula visible: bordes de 2 px, hilos de 1 px, rejillas por gap de 1 px con el fondo sangrando como línea.
- Cero sombras, cero degradados, cero radios — verificado en el build (0 ocurrencias).
- Movimiento solo `transform`/`opacity`; con `prefers-reduced-motion` o sin JS, la página está completa y estática.
- Contrastes WCAG 2.1 calculados y declarados como número junto a los tokens.

## Colors

Paleta plana de papel y tinta con un solo acento rojo; cada valor tiene procedencia en un artefacto del sistema y su contraste calculado en `src/styles/tokens.css`.

### Primary

- **Rojo de dictamen** (`--alerta`, {colors.alerta}): el único color de énfasis de la página — tomado del rojo «NO HABITAR» del PDF de dictamen. Aparece como marcador del hero, enlace CTA de la barra, anillo de foco (3 px), `caret-color`/`accent-color` de formularios, etiqueta mono de las notas-límite, subtítulo «NO HACE», estados activados y pulsos del esquema, fondo de la banda de alerta y relleno hover del botón primario. Contraste 5.01:1 sobre papel; el texto sobre él es siempre blanco (5.52:1).

### Secondary

- **Navy de marca** (`--marca`, {colors.marca}): el navy de la consola SOC. Existe en un solo lugar: la banda del pie. Sobre él, texto principal en `--sobre-marca` (14.51:1) y secundario en `--sobre-marca-2` (8.87:1); el logotipo va montado en una placa de papel.

### Neutral

- **Papel** (`--papel`, {colors.papel}): fondo de toda la página y de cada compartimento; también es el valor de `--sobre-marca` (texto sobre navy) y del `theme-color` del navegador.
- **Banda** (`--banda`, {colors.banda}): superficie de banda sutil — encabezados `<th>` de tablas y pista del scrollbar.
- **Tinta** (`--tinta`, {colors.tinta}): texto y estructura (bordes, rejillas, fondo del botón primario, fondo de la selección de texto). Del INK del PDF de dictamen. Contraste 16.15:1 sobre papel.
- **Humo** (`--humo`, {colors.humo}): el único gris de texto secundario sobre papel (5.78:1) — metadatos, notas, cruces de registro, cajas de coordinación del esquema.
- **Regla** (`--regla`, {colors.regla}): hilos divisores de 1 px, marcos débiles, separadores decorativos. Nunca lleva texto.
- **Sobre-marca-2** (`--sobre-marca-2`, {colors.sobre-marca-2}): texto secundario exclusivamente sobre navy.
- **Blanco** (`--blanco`, {colors.blanco}): texto sobre rojo y estado hover de enlaces/botón primario sobre superficies oscuras.

### Named Rules

**La Regla del Acento Único.** El rojo de dictamen es el único acento; el navy es marca de pie, no un segundo acento. Un elemento nuevo que necesite énfasis lo resuelve con peso tipográfico, mayúsculas mono o borde — jamás con un color nuevo.

**La Regla del Contraste Declarado.** Todo par nuevo color-texto/fondo se calcula (WCAG 2.1) y se declara como número en un comentario junto al token, como hace la cabecera de `tokens.css`. Un contraste sin declarar es un contraste sin verificar.

**La Regla del Papel.** `color-scheme: light` fijo: la landing es papel a propósito en cualquier tema del SO. No hay modo oscuro y no se hereda el del sistema.

## Typography

**Display Font:** Saira Condensed 700 (sustituta oficial de la propietaria Aero; fallback `Saira Condensed Fallback` = Arial Narrow con métricas ajustadas para CLS ≈ 0)
**Body Font:** Archivo 400 (strong = 600; fallback `Archivo Fallback` = Arial con métricas ajustadas)
**Label/Mono Font:** JetBrains Mono 400

**Character:** titulares condensados, en mayúsculas y de interlínea apretada — voz de portada de documento técnico — contra un cuerpo neutro y legible y una capa mono de telemetría que etiqueta, folia y mide. Subsets woff2 auto-hosteados (cero orígenes externos), `font-display: swap` con fallbacks métricos.

### Hierarchy

- **Display** (700, `clamp(3rem, 1.1rem + 9vw, 10.5rem)`, 0.92, −0.01em, MAYÚSCULAS): el titular del hero, compuesto en líneas explícitas (una `<span>` por línea). Solo la portada.
- **H2 / Título de sección** (700, `clamp(2rem, 1.3rem + 3.5vw, 4.25rem)`, 0.95, −0.01em, MAYÚSCULAS, máx. 24ch): siempre debajo de un cajetín, con `padding-block` 32/24 px.
- **H3 / Subtítulo** (700, `clamp(1.25rem, 1.1rem + 0.8vw, 1.625rem)`, 1.05, MAYÚSCULAS): subtítulos de compartimento; la variante «NO HACE» va en rojo.
- **Body** (400, 1.0625rem, 1.6): prosa con medida contenida (62ch por defecto; 52–72ch según compartimento). Énfasis con `<strong>` (600), nunca con color.
- **Mono** (400, 0.875rem, 0.08em, MAYÚSCULAS): botones y telemetría a tamaño de interfaz.
- **Label** (400, 0.75rem, 0.08em, MAYÚSCULAS, `tabular-nums`): folios, metadatos, navegación, `<th>`, revisión del pie — la utilidad `.mono`.

### Named Rules

**La Regla del Cajetín.** Los metadatos de una sección (folio «SEC nn / nn» + identidad del documento) van en una fila mono separada del título por un hilo de 1 px, ANTES del título — como cajetín de plano, no como eyebrow. El título carga su propio peso; nada se le pega encima.

**La Regla de las Mayúsculas Cortas.** Mayúsculas mono solo para etiquetas (≤ 40 caracteres). Una frase completa compuesta en mono va en caja normal con tracking reducido (0.04em): más de 40 caracteres en uppercase no se leen.

## Layout

Contenedor único `.marco`: máx. 1440 px, centrado, `padding-inline: clamp(16px, 4vw, 64px)`. Espaciado en escala de base 4 px (`--e-1`…`--e-11`: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192 px); el ritmo real de la página vive entre e-2 y e-9 (los pasos 128/192 están declarados como reserva de la escala). Móvil primero: la página se compone íntegra a 360 px sin desbordar.

Cada sección abre con una regla dura de 2 px a sangre completa (`border-top` sobre la sección, fuera del marco), sigue el cajetín + título, y el cuerpo cierra con 96 px (`--e-9`) de aire inferior. Dos puntos de quiebre observados: **768 px** (rejillas pasan a 2 columnas: spec, dato-grid, pie) y **1280 px** (composición suiza asimétrica del hero — titular 3fr / argumento+CTA 2fr alineados a la base, con el lateral colgado de un hilo izquierdo; lista de 3 columnas; pie 2fr/1fr/1fr; el esquema conmuta de layout vertical a horizontal).

### Named Rules

**La Regla del Folio Indivisible.** El folio «SEC 01 / 07» es un token indivisible: `white-space: nowrap` — pero SOLO en la celda izquierda del cajetín; la celda derecha (hasta 38ch) debe poder envolver o desborda a 360 px.

## Elevation & Depth

Cero sombras — literal: 0 ocurrencias de `box-shadow` y de degradados en el build. La profundidad no existe como iluminación; existe como **compartimentación de documento**: bordes de 2 px, hilos de 1 px y cambios francos de superficie (papel → banda → navy del pie → rojo de la banda de alerta). El dispositivo de rejilla del mundo: celdas con `gap: 1px` sobre un fondo `--tinta` (hoja de especificación) o `--regla` (lista de 3 columnas) que sangra entre ellas como retícula dibujada.

### Named Rules

**La Regla de la Tinta Plana.** Nada proyecta sombra, nada se degrada, nada «flota». Si un compartimento necesita separarse, se le dibuja una regla o se le cambia la superficie — con tinta, como en un impreso.

## Shapes

Radio 0 absoluto: todo es rectángulo de esquinas vivas — botones, notas, tablas, placas, cajas del esquema. Dos pesos de línea con nombre: **borde** (2 px, `--tinta`) para estructura — marcos de sección, botones, tabla exterior, notas-límite, límites de las bandas — e **hilo** (1 px, `--regla`) para división interna. Cruces de registro tipográficas (`+` en mono 14 px, `--humo`) en esquinas de composiciones clave (portada). El marcador rojo — bloque sólido `--alerta` de proporción ~4:1 (56×14 px en el hero, 96×22 px en la tarjeta OG) — es la marca de identidad recurrente.

Dentro del esquema SVG la gramática de trazo es jerárquica: 2.5 el camino vital (SASMEX, gabinete), 1.5 el estándar, 1 el marco y la coordinación.

### Named Rules

**La Regla del Radio Cero.** Ningún `border-radius`, en ningún componente, a ninguna escala. Suavizar una esquina rompe el mundo.

**La Regla del Trazo Discontinuo.** En los esquemas, línea discontinua (`stroke-dasharray: 4 4`, `--humo`) = coordinación fuera de la ruta crítica; trazo sólido = camino de vida. La distinción es semántica, no decorativa.

## Components

El movimiento de cada componente respeta la gramática global: solo `transform`/`opacity`, curva `ease-out` (el único `linear` es el viaje de los pulsos del esquema), duraciones 120–500 ms.

### Buttons

- **Shape:** rectángulo de esquinas vivas (radio 0), borde 2 px `--tinta`.
- **Tipografía:** mono 0.875rem, 0.08em, MAYÚSCULAS; padding 14px 22px.
- **Primario:** fondo `--tinta`, texto `--papel`.
- **Secundario:** fondo transparente, texto `--tinta`.
- **Hover / Focus:** relleno que sube desde la base (`::before` con `scaleY` 0→1, 160 ms ease-out) — a rojo con texto blanco en el primario, a tinta con texto papel en el secundario. Focus además hereda el anillo global (3 px `--alerta`, offset 2 px).
- **Active:** `scale(0.97)`, 120 ms.

### Cajetín de sección

- **Estructura:** `<p class="cajetin__meta mono">` con dos celdas justificadas (folio a la izquierda — nowrap —, identidad a la derecha), `border-bottom` de hilo, texto `--humo`; después el título H2.
- **Comportamiento:** los encabezados de sección llevan el revelado por scroll (`[data-rv]`: opacity 0 + `translateY(16px)` → 450 ms ease-out, una sola vez, threshold 0.2 — solo bajo `.js` y sin reduced-motion).

### Nota límite (deslinde)

- **Estilo:** caja de borde 2 px `--tinta`, padding 16/24 px, máx. 72ch; primera línea = etiqueta mono en `--alerta` en bloque propio. Es perímetro legal con rango tipográfico de figura, no letra pequeña.

### Hoja de especificación (HACE / NO HACE)

- **Estilo:** rejilla 1→2 columnas (768 px) con `gap: 1px` sobre fondo `--tinta` y borde exterior 2 px: la retícula se dibuja sola. Celdas de papel con padding 24 px. El subtítulo de la columna negativa va en rojo.

### Listas regladas

- **Estilo:** sin viñetas; cada ítem separado por un hilo superior (el primero sin hilo), padding vertical 16 px. Variante de 3 columnas (≥1280) con el mismo dispositivo de gap de 1 px en `--regla`.

### Tabla

- **Estilo:** `border-collapse`, borde exterior 2 px y rejilla interior de hilos en `--tinta`; `<th>` en label mono sobre fondo `--banda`, peso 400; celdas con padding 12/16 px y medida máx. 60ch.

### Banda de alerta

- **Estilo:** banda a sangre completa en `--alerta` con bordes horizontales 2 px `--tinta`; titular display propio en blanco; línea mono en caja normal (Regla de las Mayúsculas Cortas). **Estática a propósito:** es una cita literal del producto (`role="img"`), no teatro.

### Navigation

- **Barra:** papel con `border-bottom` 2 px; wordmark en display 1.375rem; enlaces en label mono sin subrayado, hover con subrayado de 2 px y offset 4 px; el enlace de contacto en `--alerta` es el único CTA de color. Skip-link (`.salto`) en placa de tinta, visible solo con foco.
- **Pie:** banda navy (`--marca`) con borde superior 2 px; retícula 1→2→3 columnas; logotipo sobre placa de papel; enlaces en `--sobre-marca` que blanquean al hover.

### Esquema del camino de activación (componente firma)

Diagrama SVG inline por duplicado (layout vertical <1280, horizontal ≥1280 — mismas clases, misma coreografía, conmutados por CSS sin scope en `global.css` porque Astro no marca el `<svg>` raíz). Cajas de papel con la jerarquía de trazo de Shapes; texto mono interior con su propia microescala; estados de actuador en pares «EN ESPERA» (`--humo`) / activado (`--alerta`, 700). Coreografía al entrar en viewport y reejecutable por botón («simulacro»): marco 300 ms → nodos 400 ms escalonados → hilos que se trazan con `scaleX/scaleY` (nada de `stroke-dashoffset`) → pulsos rojos 500 ms linear → conmutación de estados a los 2.4 s → latido del gabinete cada 4 s. Con reduced-motion el diagrama es completo y estático y el botón conmuta los estados sin transición.

### Named Rules

**La Regla del Estado Final.** Sin JS, o con `prefers-reduced-motion`, la página entera se entrega completa y estática: los estados ocultos de la animación solo existen bajo `.js` y sin reduced-motion. El movimiento presenta contenido que ya existe; jamás es la única forma de verlo.

## Do's and Don'ts

### Do:

- **Do** abrir toda sección nueva con el cajetín: regla de 2 px a sangre, fila de metadatos mono con folio (nowrap solo en la celda izquierda), hilo, título en mayúsculas.
- **Do** declarar el contraste calculado (WCAG 2.1, como número) de cualquier par de colores nuevo en un comentario junto al token.
- **Do** dibujar la retícula: separar compartimentos con hilos de 1 px o con el dispositivo de `gap: 1px` sobre fondo `--tinta`/`--regla`; estructura con borde de 2 px.
- **Do** contener la prosa entre 52 y 72ch (62ch por defecto) y enfatizar con `<strong>` (600), no con color.
- **Do** limitar el movimiento a `transform`/`opacity` con ease-out entre 120 y 500 ms, y entregar el estado final completo bajo reduced-motion y sin JS.
- **Do** usar `--humo` como único gris de texto sobre papel, y `--sobre-marca-2` como único secundario sobre navy.

### Don't:

- **Don't** sombras, degradados, radios ni transparencias decorativas: 0 ocurrencias en el build es el estándar, no una casualidad.
- **Don't** introducir un segundo acento: el navy no sale del pie y ningún color nuevo entra a la paleta sin procedencia en un artefacto real de TAKAB.
- **Don't** eyebrows ni kickers pegados a un título: los metadatos van en el cajetín, separados por hilo, antes del título.
- **Don't** mayúsculas en frases mono de más de 40 caracteres; una frase completa va en caja normal con tracking 0.04em.
- **Don't** modo oscuro ni obedecer el tema del SO: la landing es papel (`color-scheme: light`) por decisión.
- **Don't** capturas simuladas, contadores decorativos ni datos congelados pintados como vivos: la honestidad del producto también es regla visual de esta página.
