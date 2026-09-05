# Product

<!-- impeccable:product-schema 1 -->

<!-- Este PRODUCT.md cubre SOLO la landing pública (landing/). La consola SOC (web/) es otra
     superficie con otra autoridad visual (shared/design-tokens). Entrevista de producto:
     realizada el 2026-08-25 durante la planeación (4 preguntas respondidas por Mauricio +
     plan aprobado en ~/.claude/plans/planificar-la-landing-p-blica-cosmic-pumpkin.md).
     Los hechos sin confirmación directa están marcados [inferido]. -->

## Platform

web

## Stack

Astro estático (aprobado en el plan 2026-08-25). Workspace autocontenido en `landing/`, Node 22,
sin dependencia de `shared/design-tokens`. Deploy: S3+CloudFront existentes (módulo Terraform
`site`), contenido vía `aws s3 sync` desde `make landing-deploy`.

## Users

Compradores institucionales de protección sísmica en México: responsables de Protección Civil,
administradores de hospitales, universidades, industria y corporativos — la persona que decide
si un inmueble ocupado instala un sistema de alertamiento audiovisual y continuidad operativa.
Llegan desde una recomendación o búsqueda, la mayoría desde el teléfono, con escepticismo
profesional: han visto marketing de seguridad que promete de más. Trabajo a realizar: entender
el flujo completo —edificio, personas y operación— y decidir si contactar para una evaluación.

## Product Purpose

TAKAB Ailert es una plataforma de alertamiento sísmico, monitoreo estructural y continuidad
operativa post-sismo para inmuebles con gente dentro (CONSULTA-LEGAL §1). Un gabinete principal
recibe la señal del SASMEX, distribuye el alertamiento mediante gabinetes de apoyo, sirenas y
estrobos, y gobierna los canales definidos para el inmueble. La app guía a ocupantes y brigadas;
después del sismo, la plataforma sostiene el proceso de revisión y dictamen.
La landing existe para explicar esto a un comprador y producir un contacto — y para sostener la
evidencia del dominio remitente ante AWS SES (T-2.156).

## Positioning

«Una señal. Todo el inmueble en acción»: la ruta crítica física permanece dentro del inmueble;
la app y la consola amplían la respuesta hacia instrucciones por zona, check-ins, pase de lista,
evidencia y recuperación. El argumento comercial es la continuidad de todo el flujo y la
claridad con la que cada capa asume una función verificable.

## Operating Context

- El sitio vive en takabailert.com (S3+CloudFront, bucket privado OAC; rutas inexistentes
  devuelven código 404 real — decisión T-2.156 anti-espejo).
- Debe conservar: el deslinde SASMEX («no la genera ni la sustituye, y no representa a la
  autoridad que la emite»), la declaración del dominio remitente `alertas@takabailert.com`, y
  un contacto visible.
- Contacto v1: `contacto@takabailert.com` (buzón Namecheap, creación pendiente de Mauricio) +
  WhatsApp `wa.me` (número pendiente).
- La consola SOC NO se enlaza en v1 (su URL actual es provisional, sslip.io).

## Capabilities and Constraints

Afirmable (con fuente en el repo): actuación local determinista; distribución a alertamiento
audiovisual por zona conforme al diseño de la instalación; sincronización posterior de eventos;
app móvil con instrucción por zona, check-in offline-first y perfil táctico; evidencia append-only
por triggers de base de datos; sismograma, FFT y espectrograma; analítica de evacuación con
conteos, T50/T90, tiempos de reingreso y conciliación contra check-ins; dictámenes versionados y
firmados; narrativa explicativa asistida por IA sobre hechos permitidos, con procedencia y
degradación determinista; aislamiento multi-tenant por RLS default-deny.

Prohibido afirmar: cifras medidas (decisión Mauricio 2026-08-25); magnitud o tiempo estimado en
la alerta; normas o certificaciones; «la sirena suena en X ms» (G-04 abierto); badges de App
Store/Play (GATE-STORE abierto); clientes, testimonios, precios o SLA. La landing pública nombra
la entrada únicamente como «señal del SASMEX»: omite modelos y componentes internos. El mapa de
estaciones es una escena ilustrativa y debe declararlo explícitamente.

Presupuesto técnico: LCP < 2.0 s en 4G, JS inicial < 100 KB gz (objetivo < 20 KB), CLS < 0.1,
cero orígenes externos en runtime, español (es-MX) único idioma v1.

## Brand Commitments

- Nombre del producto: **TAKAB Ailert** (en superficies: TAKAB AILERT). Empresa: TAKAB
  TECHNOLOGY. La identidad entregada en `img/Logos Finales/` incluye imagotipo e isotipo
  negativos; la landing conserva copias fuente en `src/assets/img/` y deriva de ahí el favicon.
- Display de marca para superficies de marketing: **Saira Condensed** (sustituta oficial de la
  propietaria Aero Sans-Serif — `takab-docs/design/app/fonts/README.md`).
- Colores de marca utilizables: navy de la consola (`#0E2336`) y la paleta clara del PDF de
  dictamen (tinta `#14181E`, rojo `#C4302B` — `api/src/takab_api/dictamen/layout.py`).
- Dirección visual VIGENTE (v3, elegida por Mauricio el 2026-09-05): mundo oscuro «Comando
  cinematográfico». La identidad entregada (#0B1D3A/#123A7A/#FF2D1A) ordena el sitio; el azul
  de señal ilumina acciones y ruta crítica, y el rojo se reserva para alerta. La narrativa hace
  visible el inmueble como sistema: señal SASMEX → gabinete principal → gabinetes de apoyo y
  alertamiento por zonas → app móvil → brigada/SOC → evidencia → analítica post-sismo → dictamen
  y reingreso. Conserva el mapa físico con estaciones fijas e ilustrativas —incluidas Puebla y
  Tlaxcala—, una representación editorial responsive de la consola con datos ilustrativos y un instrumento de
  sismograma, espectrograma, personas, evacuación y salida documental. Siguen vigentes los rechazos:
  sin Inter/Roboto, sin degradados morado-azul, sin glassmorphism y sin screenshots falsos.
- Tagline de producto disponible: «ALERTAMIENTO SÍSMICO · CONTINUIDAD OPERATIVA» (la de la app).
  [inferido: la de la empresa «LO MEJOR LO ESTAMOS CREANDO» se omite en la landing — propuesto a
  Mauricio, pendiente de confirmación en pregunta abierta #4]
- Tono: directo, técnico, honesto. Es un producto de seguridad, no marketing de SaaS. Cero
  promesas que el sistema no cumpla.

## Evidence on Hand

- Copy semilla aprobado de facto (desplegado): `infra/terraform/envs/dev/site/index.html` —
  definición, «Qué hace», deslinde SASMEX, declaración de correo.
- Fuentes de verdad del contenido: `takab-docs/CONSULTA-LEGAL-TAKAB.md` (§2 afirmable, §3
  deslinde), `takab-docs/ENTREGA-Y-ACEPTACION-TAKAB.md` (Parte I qué hace / Parte II qué no).
- Capturas reales de consola: producibles vía `make soc-local` + Playwright, pero no se publican
  hasta contar con una flota sana, un sitio neutro y un recorte sin cifras medidas. Capturas reales de
  app: requieren el Pixel de Mauricio (pendiente). NO usar los mockups de `takab-docs/design/`
  como producto.
- Ausencias que el trabajo futuro no debe fabricar: clientes, testimonios, precios,
  certificaciones y cifras de latencia publicables.

## Product Principles

1. El flujo completo es el argumento de venta: cada etapa explica su función con lenguaje directo.
2. Cada afirmación de la landing lleva su fuente anotada en el código (`<!-- fuente: … -->`).
3. El sitio es un documento técnico: la arquitectura visual sigue el recorrido real del sistema.
4. El sitio nunca miente ni por rendimiento: sin countdown simulado, sin screenshot falso, sin
   dato congelado pintado como vivo.
5. Presupuesto de rendimiento y accesibilidad son restricciones duras, no aspiraciones.

## Accessibility & Inclusion

WCAG 2.1 AA obligatorio: contrastes calculados y declarados como número, navegación completa por
teclado, focus visible, `prefers-reduced-motion` respetado en todo (requisito, no detalle),
sin destellos (2.3.1). Mayoría de tráfico esperado desde móvil (360 px primero).
