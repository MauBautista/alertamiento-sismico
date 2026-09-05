---
name: TAKAB Ailert — Landing pública
description: Telemetría — la sala de operaciones vuelta cinemática, navy de consola y cian de señal, con la honestidad declarada como argumento.
colors:
  fondo-0: "#071322"
  fondo-1: "#0E2336"
  fondo-2: "#122B44"
  fondo-3: "#1A3E62"
  texto-1: "#F0F2F5"
  texto-2: "#B8C2CE"
  texto-3: "#8A9CB1"
  cian: "#00BFFF"
  cian-hover: "#33CCFF"
  verde: "#00E676"
  ambar: "#FFC107"
  rojo: "#FF5252"
  crisis: "#160808"
  logo-a: "#006989"
  logo-b: "#00215A"
  linea: "rgba(240, 242, 245, 0.1)"
  linea-fuerte: "rgba(240, 242, 245, 0.2)"
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
rounded:
  sm: "4px"
  md: "8px"
  pill: "999px"
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
    backgroundColor: "{colors.cian}"
    textColor: "{colors.fondo-1}"
    typography: "{typography.mono}"
    rounded: "{rounded.sm}"
    padding: "14px 22px"
  button-primary-hover:
    backgroundColor: "{colors.cian-hover}"
    textColor: "{colors.fondo-1}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.texto-1}"
    typography: "{typography.mono}"
    rounded: "{rounded.sm}"
    padding: "14px 22px"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.texto-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "6px 14px"
  panel:
    backgroundColor: "{colors.fondo-2}"
    textColor: "{colors.texto-2}"
    rounded: "{rounded.md}"
    padding: "24px"
  panel-hondo:
    backgroundColor: "{colors.fondo-1}"
    textColor: "{colors.texto-2}"
    rounded: "{rounded.md}"
    padding: "24px"
  nota-limite:
    backgroundColor: "{colors.fondo-1}"
    textColor: "{colors.texto-2}"
    rounded: "{rounded.sm}"
    padding: "16px 24px"
---

# Design System: TAKAB Ailert — Landing pública v2 «Telemetría»

<!-- v2 registrado tras el finish review (ship). REEMPLAZA al DESIGN.md v1
     «Swiss Industrial Print» (papel/tinta/rojo), REVOCADO por Mauricio el
     2026-08-25 — el registro de la revocación vive en PRODUCT.md § Brand
     Commitments. Fuente de verdad: src/styles/tokens.css + global.css y el
     build en dist/. El contrato de dirección vive como primer comentario del
     <body> en src/layouts/Base.astro; donde contrato y build diverjan, gana
     el build. -->

## Overview

**Creative North Star: "La sala de operaciones, cinemática"**

La landing es la identidad REAL del producto vuelta pieza de marketing: el navy
profundo y el cian eléctrico de la consola SOC contando la física de la alerta.
No es un tema oscuro decorativo — es la superficie del producto (paneles de
consola, rótulos de telemetría en monospace, semáforo de estados) puesta en
escena. La jerarquía se construye con **luz y profundidad de navy**, no con
sombras grises: el cian es señal, y todo lo que brilla, brilla porque significa
algo. Este mundo se hermana a propósito con la consola (revoca el «contraste
deliberado» del v1).

El tono visual sirve al argumento comercial: honestidad declarada. Toda pieza
sintética se rotula como ilustrativa, la captura de consola es el producto real
con datos de demostración y lo dice, y la banda de crisis reproduce la paleta
literal de la pantalla de crisis de la app. Rechazos confirmados (vigentes del
brief v1): sin Inter/Roboto, sin degradados morado-azul, sin glassmorphism, sin
screenshots falsos.

**Key Characteristics:**

- Suelo navy #071322 con capas de profundidad (#0E2336 → #122B44 → #1A3E62); nunca negro puro ni gris.
- Un solo acento eléctrico: cian #00BFFF con glow de señal; el resto de la paleta calla.
- Semáforo verde/ámbar/rojo exclusivamente semántico (estados, nunca decoración).
- Display condensado en mayúsculas a escala enorme + rótulos monospace de telemetría.
- Instrumentos vivos (sismograma, mapa, esquema) que degradan a escena estática completa.
- Hilos de luz de 1px como separación; retícula de fondo solo bajo instrumentos.

## Colors

Cuatro suelos de navy, tres grises azulados de texto, un solo cian eléctrico —
y un semáforo que solo habla cuando hay estado. Los contrastes están calculados
y declarados como número en `src/styles/tokens.css` (texto-1/fondo-0 16.64:1 ·
texto-2 10.35:1 · texto-3 6.64:1 · cian 8.79:1 · navy-sobre-cian 7.54:1 ·
blanco/crisis 19.58:1); toda incorporación nueva declara el suyo.

### Primary

- **Cian Señal** (#00BFFF): EL acento. Enlaces, énfasis dentro de titulares, botón primario, hilos del camino crítico en el esquema, punto de los chips, focus, selección, caret. Es literalmente la señal: donde hay cian, hay camino de alerta o acción.
- **Cian Encendido** (#33CCFF): único hover/active del acento (enlaces y botones).

### Neutral

- **Navy Suelo** (#071322): fondo de página (`--fondo-0`); el navy de consola profundizado. También `theme-color` del documento.
- **Navy Superficie** (#0E2336): `--fondo-1` — paneles hondos, pie, notas límite, fondo de instrumentos.
- **Navy Panel** (#122B44): `--fondo-2` — el panel de consola estándar y las celdas de tabla.
- **Navy Marca** (#1A3E62): `--fondo-3` — superficie de marca; hoy pinta el pulgar del scrollbar.
- **Texto Vivo** (#F0F2F5): titulares, texto primario y `strong`.
- **Texto Operativo** (#B8C2CE): prosa estándar y celdas de tabla.
- **Texto Humo** (#8A9CB1): metadatos, rótulos de tabla, sellos ilustrativos (clase `.humo`).
- **Hilo** (rgba(240,242,245,0.1)) y **Hilo Fuerte** (rgba(240,242,245,0.2)): todas las líneas del mundo — bordes de panel, retículas, separadores. Nunca bordes grises opacos.
- **Blanco** (#FFFFFF): reservado al titular de la banda de crisis (19.58:1 sobre crisis).

### Semánticos — el semáforo

- **Verde Estado** (#00E676): SOLO estado logrado — actuadores en «ACTIVADO/CERRADA/LIBERADAS» del esquema, punto del panel «Hace».
- **Ámbar Degradado** (#FFC107): SOLO condición degradada-pero-operando — anillos de las ondas sísmicas del mapa (lo lento, lo que llega tarde), y el estado «SIN ENLACE» cuando se cite.
- **Rojo Crisis** (#FF5252): SOLO peligro/negación — epicentro, borde de la banda de crisis, punto y subtítulo del panel «No hace».
- **Fondo Crisis** (#160808): el fondo literal de la pantalla de crisis de la app; existe únicamente para la banda «ALERTA SÍSMICA · PROTÉJASE».

### Marca (luz ambiental, nunca texto)

- **Radial Petróleo** (#006989) y **Radial Ultramar** (#00215A): los dos extremos del degradado del logo. Solo como radiales ambientales a baja opacidad (fondo del hero y del cierre de contacto), jamás como color de texto o de componente.

### Named Rules

**La Regla del Cian Único.** Hay un solo acento eléctrico en este mundo y es
#00BFFF. Cualquier cosa interactiva o de señal es cian; nada más compite. Si un
elemento nuevo pide "otro color de acento", la respuesta es cian o neutral.

**La Regla del Semáforo Semántico.** Verde, ámbar y rojo aparecen únicamente
cargando su significado de estado (logrado / degradado / peligro). Usarlos de
decoración — un icono verde "porque se ve bien" — rompe el instrumento entero.

**La Regla de la Luz de Marca.** Los colores del logo (#006989, #00215A) son luz
radial de fondo a opacidad ≤ 0.28, nunca tinta: no rotulan texto, no rellenan
botones, no bordean paneles.

## Typography

**Display Font:** Saira Condensed 700 (fallback métrico: Arial Narrow / Liberation Sans Narrow)
**Body Font:** Archivo 400/600 (fallback métrico: Arial / Helvetica Neue)
**Label/Mono Font:** JetBrains Mono 400 (ui-monospace, Cascadia Mono, Consolas)

**Character:** Voz doble de sala de operaciones: el display condensado en
MAYÚSCULAS grita el argumento a escala enorme; el monospace en versalitas
espaciadas rotula la telemetría con frialdad técnica. Archivo, neutral y
legible, carga la prosa. Las cuatro caras son subsets woff2 auto-hosteados con
fallbacks de métricas ajustadas (`size-adjust`/`ascent-override`) — cero
orígenes externos.

### Hierarchy

- **Display** (700, clamp(3rem, 1.1rem + 9vw, 10.5rem), lh 0.92): solo el titular del hero, en mayúsculas, tracking -0.01em, una palabra clave en cian mediante `em`.
- **H2 / .titulo** (700, clamp(2rem, 1.3rem + 3.5vw, 4.25rem), lh 0.95): titulares de sección, mayúsculas, máx. 26ch, con su `em` en cian.
- **H3 / .subtitulo** (700, clamp(1.25rem, 1.1rem + 0.8vw, 1.625rem), lh 1.05): títulos de panel, mayúsculas.
- **Body** (400, 1.0625rem, lh 1.6): prosa en `--texto-2`, máx. 62ch (`.prosa`); `strong` = 600 en `--texto-1`.
- **Mono** (400, 0.875rem, ls 0.08em, MAYÚSCULAS): texto de botones.
- **Label / .mono** (400, 0.75rem, ls 0.08em, MAYÚSCULAS, `tabular-nums`): chips, rótulos de tabla, navegación, sellos, leyendas. Los sellos ilustrativos usan esta cara con `text-transform: none`.

### Named Rules

**La Regla del Énfasis Cian.** El énfasis dentro de un titular display no es
cursiva ni otra fuente: es `em` sin estilo itálico pintado de cian («se protege
_solo._», «actúa»). Un titular, una palabra encendida.

**La Regla del Rótulo de Telemetría.** Todo dato, estado, leyenda o metadato se
rotula en JetBrains Mono 0.75rem, mayúsculas, tracking 0.08em. Si parece dato,
se viste de dato.

## Layout

Contenedor `.marco` de máx. 1440px con margen lateral fluido clamp(16px, 4vw,
64px). Espaciado en base 4px con escala nombrada `--e-1`…`--e-11` (4→192px);
las secciones respiran 96px arriba (`--e-9`) y su cuerpo cierra con 96px.
Móvil primero (360px es el piso de diseño); breakpoints activos: **640px**
(la tabla se apila), **768px** (grids a 2 columnas: `dato-grid`, `spec`, pie),
**1280px** (hero a grid 3fr/2fr, tres-paneles a 3 columnas, esquema horizontal,
pie a 2fr/1fr/1fr).

Cada sección abre con un **hilo de luz**: 1px degradado 90° de cian→hilo→
transparente a opacidad 0.55 — es la separación del mundo, en lugar de cajas o
fondos alternados. Los encabezados de sección son título solo (sin kicker
encima).

El hero es un instrumento: en ≥1280 se ancla a `calc(100svh - 73px)` para que
el sismograma vivo entre completo al primer viewport; el titular ocupa 3fr y el
lede+CTA viven a su derecha (2fr) tras un borde de 1px; en móvil el orden es
titular → lede → CTA → riel de chips → sismograma.

**La Regla del Hero-Instrumento.** El primer viewport contiene el instrumento,
no solo texto: titular display, lede con CTA, y el sismograma con su riel de
chips pegado al borde del instrumento — los chips son rótulos del instrumento,
no un eyebrow del titular.

## Elevation & Depth

Este mundo no usa sombras grises. La profundidad se construye con **capas de
navy** (fondo-0 → fondo-1 → fondo-2 sube hacia el lector) y con **luz de
señal**: glows cian/rojo de offset cero que emanan del elemento. El glow no es
decoración — es el material con que se pinta la señal (traza del sismograma,
hilos del camino crítico, puntos de estado, botón primario, focus del titular
en cian).

**El glow es de ESTE mundo.** La dirección v2 lo pinnea como material de la
landing «Telemetría»; no se hereda a otras superficies TAKAB (consola SOC, PDF
de dictamen, app) ni a futuros mundos, donde el piso de artesanía lo trata como
efecto prohibido por defecto.

### Shadow Vocabulary

- **Glow señal** (`box-shadow: 0 0 24px -6px rgba(0, 191, 255, 0.5)` — `--glow-cian`): puntos de estado encendidos, hover del botón primario, marca de la barra.
- **Glow señal suave** (`box-shadow: 0 0 40px -12px rgba(0, 191, 255, 0.35)` — `--glow-cian-suave`): reposo del botón primario, hover del botón fantasma, marco de la consola.
- **Glow peligro** (`box-shadow: 0 0 24px -6px rgba(255, 82, 82, 0.45)` — `--glow-rojo`): punto del panel «No hace»; equivalente en `text-shadow` para el titular de crisis.
- **Glow de trazo** (`filter: drop-shadow(0 0 6-8px rgba(0,191,255,.45-.8))`): la versión SVG/canvas del mismo material — traza del sismograma, hilos y pulsos del esquema, núcleos del mapa.

### Named Rules

**La Regla del Glow Solo Señal.** La única sombra permitida es luz de señal:
offset cero, color del semáforo o cian, emanando de algo que significa. Nada de
`box-shadow` gris de elevación, nada de sombras duras con offset.

## Shapes

Esquinas suaves de consola: **8px** (`--radio`) para paneles, tablas, marcos de
instrumento; **4px** (`--radio-sm`) para controles pequeños (botones, notas,
placa, skip-link); **999px** solo para chips. Las líneas del mundo son hilos de
1px en blanco translúcido (0.1/0.2), nunca bordes grises opacos.

En los diagramas SVG el trazo lleva gramática: **cian sólido 2px** = camino
crítico (SASMEX·WR-1, gabinete), **hilo fuerte 1.25px** = equipamiento
estándar, **gris discontinuo 1px** = coordinación fuera de la ruta crítica
(nube, quórum). La retícula técnica (repeating-linear-gradient de hilos a
80–96px) existe solo como fondo de instrumentos.

**La Regla del Trazo Crítico.** El peso y el estilo de línea codifican
criticidad: sólido y cian lo vital, fino lo estándar, discontinuo y gris lo que
coordina pero no dispara. Un diagrama nuevo hereda esta gramática.

**La Regla de la Retícula Bajo Instrumento.** Las franjas de retícula aparecen
únicamente con un instrumento encima (sismograma, mapa). Una sección de prosa
jamás lleva retícula de fondo.

## Components

### Botones

- **Carácter:** controles de consola — monospace en mayúsculas, esquina 4px, transiciones 120–160ms ease-out.
- **Primario** (`.btn--primario`): fondo cian, texto navy `--fondo-1` (7.54:1), glow suave en reposo; hover = cian-hover + glow pleno. Uno por momento de conversión.
- **Fantasma** (`.btn`): transparente con borde 1.5px de hilo fuerte, texto vivo; hover = borde y texto cian + glow suave.
- **Active:** `scale(0.97)` a 120ms. **Focus:** outline global de 3px cian con offset 2px.

### Chips de telemetría

- **Estilo:** píldora (999px) de borde hilo fuerte, label mono 0.75rem mayúsculas, texto `--texto-2`, punto de 7px cian con glow.
- **Uso:** riel del instrumento del hero; rotulan dominio («Alertamiento sísmico», «Edge + nube», «México»), no navegan.

### Paneles de consola

- **`.panel`:** fondo `--fondo-2`, borde 1px hilo, radio 8px, padding 24px; título `.subtitulo` + prosa `--texto-2` máx. 52ch.
- **`.panel--hondo`:** variante en `--fondo-1` para contener instrumentos o el cierre de contacto (que añade una radial cian a 0.1).
- **`.nota-limite`:** el perímetro legal como componente — fondo `--fondo-1`, borde hilo fuerte, radio 4px, rótulo mono en cian arriba, máx. 72ch. Es deslinde, no adorno.

### Listas y tabla

- **`.lista-regla`:** lista sin viñetas separada por hilos de 1px, padding vertical 16px.
- **`.tabla`:** panel de consola tabular — encabezados mono 0.75rem sobre `--fondo-1`, celdas `--texto-2` sobre `--fondo-2`, hilos entre filas. **<640px se apila**: thead se oculta accesiblemente, cada `tr` es un bloque separado por hilo y el primer `td` (en `strong`) hace de rótulo de fila. El markup sigue siendo `<table>`.
- **`.spec` (HACE / NO HACE):** dos paneles gemelos 1fr/1fr en ≥768; el título lleva punto-semáforo con glow (verde=hace, rojo=no hace) y el «No hace» tiñe su subtítulo de rojo.

### Banda de crisis

La paleta REAL de la pantalla de crisis de la app, estática: fondo #160808,
bordes horizontales 3px rojos, titular display en blanco con text-shadow rojo
(«ALERTA SÍSMICA · PROTÉJASE»), anotación mono abajo. Es cita literal del
producto (`role="img"` + rótulo) — no se anima, no se adorna, no se versiona.

### Instrumentos (firma del mundo)

- **Sismograma (`Onda`):** traza cian 1.6px con glow sobre `--fondo-1` y retícula vertical de 96px; sello «Traza ilustrativa · no es un evento real». Generador determinista compartido build/cliente (misma semilla): sin JS o con reduced-motion se sirve el SVG estático idéntico; con JS, canvas rAF que se pausa fuera del viewport.
- **Mapa de la física (`MapaAlerta`):** México como matriz de puntos (blanco 0.2), epicentro rojo, haz cian inmediato vs. anillos ámbar lentos, ciclo CSS de 10s (solo transform/opacity); leyenda mono + «EPICENTRO ILUSTRATIVO» + sello sin sitios ni cobertura.
- **Esquema del gabinete (`Esquema`):** dos layouts SVG (vertical <1280, horizontal ≥1280) con la gramática de trazo; coreografía de dibujado por scaleX/scaleY + pulsos, latido del cerebro cada 4s; botón «[ Ejecutar simulacro ]» re-corre la señal (con reduced-motion conmuta el estado final sin transición, vía `aria-live`).
- **Consola (`Consola`):** captura REAL del SOC en marco de navegador propio (barra con tres puntos y URL mono), rotulada «incidente de demostración».

### Superficies del navegador

El mundo tematiza el propio navegador: `color-scheme: dark`, selección
cian/navy, `caret-color` y `accent-color` cian, scrollbar navy
(`--fondo-3`/`--fondo-0`), `theme-color` #071322, focus 3px cian. El skip-link
es un control cian/navy en mono.

### Movimiento

Solo `transform` y `opacity`. Micro: 120–450ms ease-out (botones 160ms,
revelado de encabezados 450ms translateY(16px) una sola vez, titular del hero
420ms escalonado 70ms/línea animando SOLO transform para que el LCP pinte al
primer frame). Macro: ciclos de instrumento (10s mapa, 4s latido). Los estados
ocultos de revelado existen solo bajo `.js`.

**La Regla del Estado Final.** Sin JS o con `prefers-reduced-motion`, la página
es la escena COMPLETA y estática: onda→SVG, mapa→escena base, esquema→reposo
con conmutación sin transición, revelados visibles. La animación es mejora
progresiva del mismo cuadro final, nunca contenido.

**La Regla de la Rotulación Ilustrativa.** Toda pieza sintética o de
demostración lleva su sello mono a la vista: «traza ilustrativa», «epicentro
ilustrativo», «datos de demostración». La honestidad de la casa aplica también
al marketing.

## Do's and Don'ts

### Do:

- **Do** separar secciones con el hilo de luz (1px, degradado cian→transparente a 0.55) y aire de 96px; el mundo se divide con luz, no con cajas.
- **Do** rotular todo dato o estado en mono 0.75rem mayúsculas tracking 0.08em, y todo sintético con su sello ilustrativo.
- **Do** declarar el contraste WCAG como número (en `tokens.css`) para cualquier color nuevo; texto navy sobre cian en el botón primario (7.54:1), nunca blanco sobre cian.
- **Do** componer sobre la escala base-4 (`--e-1`…`--e-11`) y los tres breakpoints del mundo (640/768/1280).
- **Do** animar únicamente `transform`/`opacity`, con el cuadro final completo como estado sin JS/reduced-motion.
- **Do** encender una sola palabra del titular en cian mediante `em`.

### Don't:

- **Don't** usar Inter/Roboto, degradados morado-azul, glassmorphism ni screenshots falsos (rechazos confirmados en PRODUCT.md).
- **Don't** introducir sombras grises o con offset: la única sombra es glow de señal (offset cero, cian/semáforo) — y el glow no se exporta fuera de este mundo.
- **Don't** usar verde/ámbar/rojo sin significado de estado, ni cian para nada que no sea señal o acción.
- **Don't** poner retícula de fondo bajo prosa, ni kickers/eyebrows sobre los titulares (los chips pertenecen al riel del instrumento).
- **Don't** animar la opacidad del titular LCP (solo transform), ni dejar contenido invisible sin JS.
- **Don't** adornar o animar la banda de crisis: es cita literal del producto, estática, sin cuenta regresiva ni magnitud.
- **Don't** pintar dato congelado como vivo ni cifras de marketing: si un dato es de demostración, se dice.
