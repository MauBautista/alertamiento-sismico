---
name: TAKAB Ailert — Landing pública
description: Comando cinematográfico — el inmueble como sistema, con la ruta crítica local visible y la marca real como autoridad.
colors:
  fondo-0: "#050B14"
  fondo-1: "#0B1D3A"
  fondo-2: "#102846"
  fondo-3: "#123A7A"
  texto-1: "#F6F8FB"
  texto-2: "#C0CAD8"
  texto-3: "#9BAABD"
  azul-senal: "#6AA8FF"
  azul-senal-hover: "#91C0FF"
  verde: "#00E676"
  ambar: "#FFC107"
  rojo: "#FF2D1A"
  rojo-texto: "#FF5A47"
  crisis: "#190908"
  linea: "rgba(202, 218, 239, 0.12)"
  linea-fuerte: "rgba(202, 218, 239, 0.24)"
typography:
  display:
    fontFamily: "Saira Condensed, Saira Condensed Fallback, Franklin Gothic Medium, Impact, sans-serif"
    fontSize: "clamp(3.75rem, 1.8rem + 6vw, 6.8rem)"
    fontWeight: 700
    lineHeight: 0.92
    letterSpacing: "-0.035em"
  h2:
    fontFamily: "Saira Condensed, Saira Condensed Fallback, Franklin Gothic Medium, Impact, sans-serif"
    fontSize: "clamp(2.75rem, 1.45rem + 4.2vw, 5.75rem)"
    fontWeight: 700
    lineHeight: 0.9
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Archivo, Archivo Fallback, Arial, Helvetica Neue, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.65
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, Liberation Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    letterSpacing: "0.08em"
rounded:
  sm: "4px"
  md: "12px"
  lg: "24px"
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
---

# Design System: TAKAB Ailert — Landing pública v3 «Comando cinematográfico»

## North star

La página representa un edificio como sistema de protección, no como una colección
de tarjetas SaaS. La historia avanza en una sola dirección: **señal SASMEX →
gabinete principal → cobertura por zonas → app móvil → brigada/SOC → evidencia y
reingreso**. La tecnología se ve en los instrumentos; la confianza se construye
explicando el flujo completo.

V3 toma la geometría y la paleta del imagotipo entregado. El negro azulado deja
espacio a la información, el navy construye profundidad, el azul marca la ruta
activa y el rojo aparece únicamente cuando existe una alerta o un epicentro.

## Identidad

- **Logo:** el imagotipo negativo real aparece en la navegación; el isotipo se usa
  como sello ambiental en el cierre y como favicon negativo optimizado a 64 px.
  Astro produce las variantes WebP de contenido; los PNG fuente no se alteran.
- **Azul Señal (`#6AA8FF`):** acciones, foco, enlaces y camino crítico. El nombre
  de variable `--cian` se conserva como alias por compatibilidad con los diagramas.
- **Rojo TAKAB (`#FF2D1A`):** peligro, epicentro y banda literal de alerta. Nunca CTA.
- **Rojo de texto (`#FF5A47`):** variante AA para mensajes críticos sobre navy;
  el rojo de marca se reserva a superficies, trazos e iconografía.
- **Semáforo:** verde significa protección/actuación confirmada; ámbar significa
  operación degradada; rojo significa peligro. Ninguno es decorativo.
- **Tipografía:** Saira Condensed habla en titulares; Archivo explica; JetBrains
  Mono rotula telemetría y secuencias.

## Composición

- El primer viewport enfrenta el argumento comercial con un corte técnico del
  edificio: gabinete principal, apoyos por zona, estrobos y una vista móvil.
  El sismograma cierra el acto y conecta con la física de la alerta.
- Las secciones usan encabezados de dos columnas, mucho aire y una línea de señal.
  Los paneles se reservan para instrumentos, límites o información que realmente
  necesita un perímetro.
- El contenido se agrupa en una portada y ocho actos numerados: flujo completo,
  física, respuesta del inmueble, app móvil, inteligencia post-sismo, sala de
  operaciones, configuración y contacto.
- El máximo de lectura es 62 caracteres; el lienzo tiene 1440 px y margen fluido.
- Breakpoints principales: 640, 768, 960 y 1280 px. El piso de diseño es 360 px.

## Instrumentos

- **ComandoHero:** corte ilustrativo del edificio. La señal alcanza primero el
  gabinete principal; después se iluminan apoyos por piso, estrobos y app. No
  muestra un receptor independiente ni simula mediciones o cobertura real.
- **Onda:** traza sintética determinista, declarada como ilustrativa; usa SVG sin JS
  y canvas cuando el movimiento está permitido.
- **MapaAlerta:** conserva las estaciones inmóviles y revela una ruta radial desde
  el epicentro hacia cada una. Capas superpuestas cambian su color al detectar el
  frente; anillos rojo, naranja y ámbar explican cercanía. Incluye Puebla y
  Tlaxcala y no afirma despliegues, cobertura o segundos medidos.
- **Esquema:** permite ejecutar un simulacro visual que activa gabinete principal,
  gabinetes de apoyo, sirenas y estrobos por zona.
- **FlujoMovil:** recrea con HTML/CSS los estados reales de crisis, check-in, pase de
  lista y control de reingreso. Es una representación editorial, no una captura.
- **Consola:** representación editorial responsive de los campos de trabajo. No
  publica cifras ni el estado de una flota de desarrollo; se rotula como datos
  ilustrativos y conserva legibilidad en móvil.
- **PostEvento:** instrumento editorial con sismograma, espectrograma, fotografías,
  conteo/conciliación de personas, T50/T90, reingreso, narrativa asistida por IA y
  reporte PDF. Expone campos reales sin fabricar resultados de un incidente.

## Movimiento

El movimiento se usa para **explicación**, **estado** y **feedback**:

- Hero: título por `transform` durante 420 ms; grupos secundarios con
  `transform/opacity` a 450 ms y stagger de 60–70 ms.
- Scroll: cada escena entra una sola vez a 450 ms con `--ease-out`.
- Botones: press a 140 ms; hover solo bajo `(hover: hover) and (pointer: fine)`.
- Instrumentos: ciclos CSS/canvas que se pausan fuera del viewport y mediante un
  control visible junto a la traza del hero.
- Sin JS todo es visible. Con `prefers-reduced-motion` se elimina desplazamiento y
  se muestra el cuadro final estático; el botón de simulacro conmuta el estado sin
  transición.

No se permite `transition: all`, `ease-in`, movimiento de propiedades de layout,
scroll con inercia artificial ni efectos de cursor sobre datos que el usuario lee.

## Reglas de contenido

- Toda afirmación técnica conserva su comentario de fuente.
- No se publican cifras medidas, predicciones, certificaciones, clientes, precios,
  SLA ni actuadores que todavía no estén acreditados en el inmueble.
- El deslinde SASMEX, el dominio remitente y el contacto son contenido obligatorio.
- Toda pieza sintética dice «ilustrativa» y toda captura real con datos de prueba
  dice «demostración». Ningún estado congelado se rotula como «en vivo».
- La pantalla móvil conserva «Protéjase», la instrucción por zona y el tiempo
  transcurrido como jerarquía de crisis.

## Calidad

- WCAG 2.1 AA, foco visible, navegación por teclado y salto al contenido.
- El encabezado ofrece los ocho destinos en escritorio y un menú nativo `<details>`
  en móvil; todos los anclajes reservan el alto de la barra fija.
- Cero orígenes externos en runtime.
- JS inicial menor a 20 KB gzip; fuentes menores a 200 KB.
- LCP menor a 2 s, CLS menor a 0.1 y TBT menor a 200 ms bajo la auditoría local.
