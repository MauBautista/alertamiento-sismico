# TAKAB Ailert — qué afirma el sistema, para consulta legal

> **Para qué existe este documento.** Es el paso 1 de `T-2.96` (`GATE-LEGAL`) y de
> `PENDIENTES-MAURICIO §4.1`: **lo que un abogado necesita leer para poder opinar.** No pide
> investigar normativa; pide que alguien con firma diga **qué marco es citable** para un sistema
> que hace exactamente lo que aquí se describe, y **qué frases de las que hoy usamos habría que
> cambiar**.
>
> **Regla que gobierna este documento:** aquí solo se escribe lo que el sistema **hace y afirma
> hoy**, separado de lo que **todavía no está acreditado**. Un documento legal que mezcle las dos
> cosas es peor que no tenerlo: convierte una consulta en una declaración.
>
> **Estado:** borrador para llevar a consulta · **Fecha:** 2026-08-16 · **Interlocutor buscado:**
> abogado con experiencia en **protección civil** o en **responsabilidad de producto** en México.

---

## 1 · Qué es el sistema, en un párrafo

TAKAB Ailert es una plataforma de **alertamiento sísmico, monitoreo estructural y continuidad
operativa post-sismo** para inmuebles con gente dentro (hospitales, universidades, industria,
corporativos, dependencias de gobierno). Se instala un **gabinete por edificio** que recibe la
alerta del **SASMEX** y **acciona equipamiento físico del inmueble** —sirena, cierre de válvulas de
gas, retorno de ascensores a planta, retenedores de puerta— y, después del sismo, sostiene el
proceso de **revisión y dictamen** que decide si el edificio se reocupa.

Las dos frases que definen el perfil de riesgo:

- **El sistema acciona equipamiento de un edificio ocupado.**
- **El sistema produce el registro con el que se decide si se vuelve a entrar.**

---

## 2 · Lo que el sistema AFIRMA hoy — la lista completa

Cada punto es una afirmación **verificable en el sistema**, no una aspiración comercial.

### 2.1 · El origen de la alerta es un contacto seco de SASMEX, y nada más

El gabinete recibe la alerta sísmica de un **receptor WR-1** homologado, por **contacto seco**
(un cierre eléctrico). Es un **booleano**: hay alerta o no la hay.

**Consecuencia que conviene subrayar, porque limita lo que podemos decir:** el sistema **no conoce
la magnitud, ni el epicentro, ni el tiempo restante**. No los muestra porque no los tiene. El
mensaje al ocupante es «ALERTA SÍSMICA · PROTÉJASE», sin cuenta regresiva ni magnitud.

### 2.2 · La actuación local es determinista y no depende de nadie

Del contacto de SASMEX al relé del edificio **no hay internet, no hay nube y no hay inteligencia
artificial**. Es una cadena eléctrica y de software con reintento, dentro del propio gabinete.

**Medido en el equipo real:** **6.65 ms** y **4.16 ms** de contacto SASMEX a relé, en dos pruebas
independientes con hardware instalado.

> **Lo que NO está acreditado todavía, y va aquí a propósito:** la latencia física completa
> **contacto → relé → sirena sonando**, con los relés definitivos del inmueble, es el gate `G-04`
> y **sigue abierto**. Lo medido arriba llega al relé, no al altavoz.

Si el gabinete pierde internet, **sigue detectando y sigue accionando**. La nube coordina; no es
condición de la seguridad local.

### 2.3 · La inteligencia artificial no puede disparar ni impedir una alerta

Es una restricción de diseño, no una política de uso: la IA **asesora, prioriza y redacta**, y
**jamás** dispara una alerta ni la suprime. El andamiaje de IA está construido y **apagado**, y la
estructura de datos que usaría **no tiene campo donde poner un veredicto** — añadirlo rompe la
compilación antes de que pudiera llegar a un dictamen.

### 2.4 · Quién puede ordenar una evacuación

- **SASMEX** — actúa siempre, es la fuente autoritativa.
- **Un quórum de ≥3 inmuebles** que sacuden a la vez, correlacionado en la nube, que emite un
  **comando firmado** a los gabinetes.
- **Un solo edificio detectando por su cuenta NO evacúa a nadie.** Su sensor propio produce
  **únicamente un aviso visual** al centro de operaciones y al panel del gabinete. Un cliente puede
  activar explícitamente la actuación autónoma para su sitio, y entonces es una decisión suya,
  registrada.

### 2.5 · El registro de evidencia es inmutable y no se poda

`audit_log`, la evidencia de incidentes y los **dictámenes** son **append-only**: garantizado por
disparadores en la propia base de datos, no por disciplina de los programadores. **Están exentos de
las políticas de retención**: no se borran por antigüedad.

Un dictamen queda con su **base** (versión del juego de reglas, evidencia, notas) y su **firma**.
**Una corrección nunca reescribe**: inserta una versión nueva que declara a cuál sustituye. La
evidencia (registro sísmico crudo + PDF del dictamen) se puede exportar por incidente.

### 2.6 · Separación entre clientes

Cada cliente está aislado a nivel de base de datos con **seguridad por fila y denegación por
defecto**. Existe además la opción de base dedicada para clientes críticos.

### 2.7 · Datos personales

El sistema trata datos personales y está diseñado con la **LFPDPPP** a la vista: aviso de
privacidad, consentimiento y derechos ARCO. Dos categorías merecen mención expresa:

- **Ubicación de personas dentro del inmueble** (pase de lista post-sismo: quién está a salvo y
  dónde). Es el dato más sensible del sistema y existe para localizar personas atrapadas.
- **Teléfonos** de quienes consintieron recibir notificaciones.

---

## 3 · Lo que el sistema NIEGA afirmar — el deslinde, literal

Hoy el sistema **no declara un marco normativo propio**. Lo que hace es **transcribir el marco que
declara el cliente**, y pegarle este aviso, que se imprime en la consola y en el PDF del dictamen
firmado:

> «Las afirmaciones de este apartado las DECLARA el cliente. TAKAB Ailert no las verifica, no las
> certifica y no emite dictamen de cumplimiento normativo. El marco normativo citable de la
> plataforma está pendiente de confirmación; ninguna referencia de este apartado procede de
> TAKAB.»

Y cuando el cliente **no declaró nada**, el sistema tampoco se calla —un apartado en blanco dentro
de un dictamen firmado se lee como «todo en orden»—, sino que dice:

> «SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE · la ausencia de etiquetas no significa
> cumplimiento ni incumplimiento: significa que no se declaró ninguna.»

**Ese es el hueco que trae esta consulta.** Es honesto, pero **no es un marco propio**, y un
cliente institucional lo va a pedir.

> **Antecedente que conviene conocer, porque es la razón de ser de esta consulta.** La
> documentación citó durante un tiempo la **«NOM-003-SCT»** como norma vinculante. Verificado
> contra el Diario Oficial: esa norma regula **etiquetas de envases y embalajes para transporte de
> materiales y residuos peligrosos**, y **no aplica** al alertamiento sísmico. La cita se retiró.
> **La regla de inmutabilidad de la evidencia no cambió** —se sostiene como requisito propio de
> TAKAB—, pero se quedó sin norma que citar.

---

## 4 · Las preguntas concretas

### 4.1 · Marco citable

**¿Qué marco normativo es citable para un sistema que hace lo descrito en §2?** Candidatos que
hemos identificado sin verificar, y que la consulta debería confirmar o descartar:

- Ley General de Protección Civil y sus reglamentos estatales y municipales.
- Términos de referencia de los contratos con unidades de Protección Civil.
- Normativa local de revisión estructural post-sismo (el dictamen de reocupación).
- Normas aplicables al accionamiento de válvulas de gas y a ascensores en inmuebles.

### 4.2 · Qué frases hay que cambiar

**¿Qué afirmaciones de §2 y §3 habría que reformular** para que no comprometan más de lo que el
sistema puede sostener? Nos interesan especialmente:

- Decir que la actuación local es «determinista» y «no depende de internet».
- Decir que el registro es «inmutable» y «exento de poda».
- El deslinde de §3: ¿protege, o admite mejora?

### 4.3 · Responsabilidad

**¿Dónde queda la responsabilidad** cuando el sistema acciona correctamente y aun así hay daño; y
cuando **no** acciona por una causa ajena (el WR-1 no recibió, el edificio cortó la energía)?
¿Cambia si el cliente activó la **actuación autónoma por sensor propio** de §2.4?

### 4.4 · Protección de datos — dos preguntas específicas

1. **La ubicación de personas** (§2.7) dentro de un inmueble: ¿qué base legal la sostiene y qué
   hay que decirle al ocupante?
2. **El teléfono en un registro append-only.** Un titular puede ejercer cancelación sobre su
   número, pero ese número es **la prueba de la base legal** del envío que él mismo autorizó, y el
   registro **no admite borrados**.

   > **Nuestra postura por defecto, que la consulta debe confirmar o corregir** (decisión `D-07`):
   > guardar el número **cifrado con una clave por titular**, y que ejercer la cancelación
   > **destruya la clave**. Así el registro queda íntegro y verificable, se conserva la prueba de
   > **que** hubo consentimiento y **cuándo**, y desaparece de forma irreversible la capacidad de
   > leer **a quién**.
   >
   > **Las dos preguntas que esa postura deja abiertas a propósito:**
   > - ¿Un número **cifrado** sigue siendo dato personal mientras la clave exista?
   > - ¿Se acepta la **destrucción de la clave** como cancelación a efectos de la LFPDPPP?

### 4.5 · Una pregunta comercial con fondo legal

El tono de alerta del SASMEX es el sonido que la población **ya asocia a evacuar**. Usarlo requiere
licencia de **CIRES**. ¿Qué implica usarlo sin ella, y qué implica **no** usarlo?

---

## 5 · Qué esperamos llevarnos de la consulta

1. **Un marco citable**, o la confirmación de que no lo hay y de que el deslinde de §3 es la
   postura correcta.
2. **Una lista de frases a cambiar**, con la redacción sugerida.
3. **Una respuesta a §4.4**, que desbloquea trabajo de software ya diseñado y en espera.

> **Cuando haya respuesta, se escribe en tres sitios a la vez** —`BLUEPRINT §9`, `RBAC-TAKAB §8`
> punto 3 y la pregunta abierta #1 del análisis de arquitectura—, porque es donde la cita anterior
> se sostuvo circularmente a sí misma: cada documento la daba por buena citando al otro.
