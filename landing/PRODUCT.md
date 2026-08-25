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
si un inmueble ocupado instala un sistema que acciona sirena, gas, ascensores y puertas.
Llegan desde una recomendación o búsqueda, la mayoría desde el teléfono, con escepticismo
profesional: han visto marketing de seguridad que promete de más. Trabajo a realizar: entender
qué hace el sistema, qué NO hace, y decidir si contactar para una cotización.

## Product Purpose

TAKAB Ailert es una plataforma de alertamiento sísmico, monitoreo estructural y continuidad
operativa post-sismo para inmuebles con gente dentro (CONSULTA-LEGAL §1). Un gabinete por
edificio recibe la alerta oficial (SASMEX, receptor WR-1 por contacto seco) y acciona
equipamiento físico del inmueble; después del sismo sostiene el proceso de revisión y dictamen.
La landing existe para explicar esto a un comprador y producir un contacto — y para sostener la
evidencia del dominio remitente ante AWS SES (T-2.156).

## Positioning

«El edificio se protege solo»: del contacto de SASMEX al relé no hay internet, no hay nube y no
hay inteligencia artificial (CONSULTA-LEGAL §2.2). La nube coordina, nunca está en la ruta
crítica. Ningún competidor que dependa de conectividad puede afirmar esto. Segunda posición
verificable: la honestidad como argumento — el sistema declara en negativo lo que no hace
(ENTREGA Parte II) y la landing lo publica.

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

Afirmable (con fuente en el repo): actuación local determinista sin nube probada con la nube
apagada; estados seguros por canal (gas `fail_close`, puertas `NC`); IA sin campo donde poner un
veredicto; evidencia append-only por triggers de base de datos, exenta de retención; dictámenes
versionados y firmados; aislamiento multi-tenant por RLS default-deny; quórum de ≥3 inmuebles
con comando firmado; panel LAN sin un solo recurso externo; 2 h sin enlace sin perder ni
duplicar eventos.

Prohibido afirmar: cifras medidas (decisión Mauricio 2026-08-25 — ni 6.65 ms, ni 214 ms, ni
13/13; solo cualitativo); cuenta regresiva o magnitud (el WR-1 entrega un booleano; invariantes
I-1/I-2); normas o certificaciones (deslinde CONSULTA-LEGAL §3; citarlas activa el gatillo #3 de
D-20); canales de aviso específicos como promesa (SMS/WhatsApp/push no entregan hoy — ENTREGA
§6.3); «la sirena suena en X ms» (G-04 abierto); badges de App Store/Play (GATE-STORE abierto);
clientes, testimonios, precios, SLA (no existen); audio de alerta (el tono SASMEX exige licencia
CIRES; D-19: tono propio); predicción de sismos (el sistema recibe y detecta, no predice).

Presupuesto técnico: LCP < 2.0 s en 4G, JS inicial < 100 KB gz (objetivo < 20 KB), CLS < 0.1,
cero orígenes externos en runtime, español (es-MX) único idioma v1.

## Brand Commitments

- Nombre del producto: **TAKAB Ailert** (en superficies: TAKAB AILERT). Empresa: TAKAB
  TECHNOLOGY (wordmark PNG `web/src/assets/LogoTakab2.png`; no existe logo del producto).
- Display de marca para superficies de marketing: **Saira Condensed** (sustituta oficial de la
  propietaria Aero Sans-Serif — `takab-docs/design/app/fonts/README.md`).
- Colores de marca utilizables: navy de la consola (`#0E2336`) y la paleta clara del PDF de
  dictamen (tinta `#14181E`, rojo `#C4302B` — `api/src/takab_api/dictamen/layout.py`).
- Dirección visual de la landing FIJADA por brief (2026-08-25): industrial-brutalist, archetype
  Swiss Industrial Print — contraste deliberado con la consola (oscura, densa). No reutilizar la
  estética de la consola; sí su marca.
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
- Capturas reales de consola: producibles vía `make soc-local` + Playwright. Capturas reales de
  app: requieren el Pixel de Mauricio (pendiente). NO usar los mockups de `takab-docs/design/`
  como producto.
- Ausencias que el trabajo futuro no debe fabricar: clientes, testimonios, precios,
  certificaciones, cifras de latencia publicables, logo del producto, favicon heredado.

## Product Principles

1. La honestidad es el argumento de venta: lo que el sistema no hace se publica, no se esconde.
2. Cada afirmación de la landing lleva su fuente anotada en el código (`<!-- fuente: … -->`).
3. El sitio es un documento técnico, no un folleto: se diseña como el artefacto más serio que
   produce el sistema (el dictamen).
4. El sitio nunca miente ni por rendimiento: sin countdown simulado, sin screenshot falso, sin
   dato congelado pintado como vivo.
5. Presupuesto de rendimiento y accesibilidad son restricciones duras, no aspiraciones.

## Accessibility & Inclusion

WCAG 2.1 AA obligatorio: contrastes calculados y declarados como número, navegación completa por
teclado, focus visible, `prefers-reduced-motion` respetado en todo (requisito, no detalle),
sin destellos (2.3.1). Mayoría de tráfico esperado desde móvil (360 px primero).
