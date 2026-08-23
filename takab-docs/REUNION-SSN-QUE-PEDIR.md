# Reunión con el SSN — qué pedir, qué entregar, qué traerse de vuelta

> **Creado:** 2026-08-23 · **Para:** Mauricio · **Supuesto de trabajo:** el apoyo del SSN está
> concedido; esto ya no es una gestión para conseguirlo, es la conversación técnica que lo
> convierte en algo utilizable.
>
> **Todo lo que aquí se afirma sobre el estado actual del feed está MEDIDO**, con fecha. Lo que no
> se pudo medir se dice que no se midió.

---

## 0 · Lo primero, porque equivocarse aquí cuesta la credibilidad de toda la reunión

**El SSN no opera SASMEX.** Son dos organizaciones distintas con dos funciones distintas:

| | Quién | Qué da | Qué papel tiene en TAKAB |
|---|---|---|---|
| **SSN** | Servicio Sismológico Nacional (UNAM) | **Catálogo** de sismos: dónde, cuándo, qué magnitud, qué profundidad — *después* del evento | **Contexto e información.** Nunca dispara nada |
| **SASMEX** | CIRES, A.C. | **Alertamiento temprano**: un aviso *antes* de que llegue la sacudida | El **contacto seco** del receptor WR-1 que dispara sirena y actuadores |

**No les pidas nada de alertamiento temprano ni de SASMEX** — no es suyo, y pedirlo señala que no
se entiende quién hace qué. Lo que el SSN puede darnos es el **catálogo**, y eso es exactamente lo
que tenemos bloqueado.

> **Y díselo tú primero, en la reunión.** «Nuestro disparo viene de SASMEX por contacto seco y es
> 100 % local; del SSN queremos el catálogo, que en nuestro sistema es información y jamás dispara
> un actuador.» Esa frase les quita de encima el miedo que cualquier servicio sismológico tiene al
> ceder datos: que alguien monte un sistema de alerta encima y les cuelgue la responsabilidad.

---

## 1 · El estado real hoy, para que sepas de qué te quejas

Lo que hay disponible del SSN, medido desde el entorno de desarrollo:

**✅ Lo que SÍ funciona** *(medido el 2026-08-22)*

```
curl -sI http://www.ssn.unam.mx/rss/ultimos-sismos.xml
HTTP/1.1 200 OK · application/xml · 8 091 bytes
Last-Modified: … · ETag: "2e90a-1f9b-659991dac62ed"
```

RSS 2.0 con `geo:lat` y `geo:long` limpios. Trae `ETag`, así que se puede pedir «solo si cambió»
sin descargarlo entero cada vez. Es utilizable **para los últimos sismos y nada más**.

**❌ Los tres agujeros, y son los que hay que cerrar en la reunión**

1. **No hay HTTPS.** El puerto 443 de `ssn.unam.mx` está **cerrado** — `https://` da *Failed to
   connect*. El feed viaja **en claro**.
2. **No hay catálogo histórico programático.** El formulario web solo emite CSV **por sesión de
   navegador**, y los Reportes Especiales son **PDF** y solo desde 2010. *(Medido el 2026-07-09:
   para validar el algoritmo de quórum hubo que **transcribir a mano** los parámetros de cinco
   sismos desde sus PDF, y completar el resto desde el catálogo de USGS.)*
3. **No hay esquema documentado.** Lo que sabemos del formato lo sabemos por inspección. Si el SSN
   cambia una etiqueta un martes, **nuestro catálogo se congela en silencio** — el peor modo de
   fallo que tiene este sistema.

---

## 2 · LO QUE LES PIDES — siete cosas, por orden de lo que desbloquean

> Llévalo como lista. Si de las siete te dan las tres primeras, la reunión fue un éxito.

### 2.1 · Acceso programático al catálogo, **con histórico** ⭐ la más importante

**Pide:** un endpoint consultable por máquina, con rango de fechas y filtro geográfico. Lo ideal es
un servicio **FDSN-event** (`fdsnws/event/1/query`), que es el estándar internacional y el que ya
sabemos consumir porque es el que usa USGS.

> **La frase:** «¿Tienen un web service de catálogo consultable por programa —idealmente FDSN
> event— o solo el RSS de últimos sismos y el formulario CSV? Necesitamos poder pedir un rango de
> fechas sin pasar por un navegador.»

**Por qué:** hoy solo tenemos los últimos sismos. Sin histórico no podemos (a) validar el algoritmo
de asociación de quórum contra sismos reales —hoy corre contra **cinco eventos transcritos a
mano**—, ni (b) darle a un cliente el contexto de «qué ha pasado bajo este edificio en diez años»,
que es una de las cosas por las que un hospital paga.

**Si dicen que no:** pregunta por una **entrega periódica** (un volcado mensual del catálogo por
FTP/correo/S3). Es peor pero sirve. Y pide al menos los Reportes Especiales en un formato que no
sea PDF.

---

### 2.2 · HTTPS en el feed

**Pide:** que habiliten TLS en el host del feed, o que te den un endpoint alternativo que ya lo
tenga.

> **La frase:** «El 443 de `ssn.unam.mx` está cerrado; el feed solo responde por HTTP en claro.
> ¿Hay un endpoint con TLS, o está en plan habilitarlo?»

**Por qué:** vamos a consumir esos datos desde una plataforma que vende seguridad a hospitales y
gobierno. Un dato de terceros que llega **sin cifrar y sin autenticar el origen** es algo que
tenemos que declarar por escrito ante cada cliente, y que un auditor va a marcar.

**Si dicen que no:** no es bloqueante — el catálogo es información y **lo que baja al gabinete lo
firmamos nosotros**, así que un intermediario no puede inyectar nada en un edificio. Pero hay que
dejarlo escrito, y conviene que lo sepan ellos también.

---

### 2.3 · El esquema documentado **y aviso previo de cambios** ⭐ la que evita el fallo silencioso

**Pide dos cosas juntas, no una:**
1. La especificación de los campos (qué significa cada uno, unidades, zona horaria, precisión).
2. **Un canal por el que nos avisen antes de cambiar el formato** — una lista de correo, un
   contacto, lo que sea.

> **La frase:** «¿Existe documentación del formato? Y sobre todo: ¿hay alguna forma de que nos
> avisen si van a cambiarlo? Si cambia sin aviso, nuestro catálogo se queda congelado sin dar
> error, y eso es lo peor que nos puede pasar.»

**Por qué:** es literalmente el riesgo que la decisión `D-06` aceptó por escrito al automatizar la
ingesta. Tenemos ya construida la mitigación —una alarma que vigila la **ausencia** de catálogo
nuevo, no el error— pero una alarma avisa *después*. Un aviso previo evita el incidente.

---

### 2.4 · Identificador estable del evento y qué pasa cuando se **revisa** una solución

**Pregunta las tres:**
- ¿Cada sismo tiene un **ID que no cambia** entre consultas?
- Cuando revisan magnitud o localización, **¿el ID se mantiene** y el registro se actualiza, o
  aparece uno nuevo?
- ¿Hay una marca de **preliminar vs. revisada**?

> **La frase:** «Cuando un sismo se relocaliza o se recalcula la magnitud, ¿cómo lo vemos desde
> fuera? ¿Mismo identificador con datos nuevos, o entrada nueva?»

**Por qué, y esto es de reglas duras del sistema:**
- **Sin ID estable no hay idempotencia**: al reconectar duplicaríamos eventos. Es una regla de oro
  del proyecto, no una preferencia.
- **Sin la marca de preliminar**, la consola pintaría una magnitud provisional como si fuera
  definitiva. En este sistema **está prohibido presentar un dato como más firme de lo que es** — un
  dato provisional se rotula provisional, igual que un catálogo viejo se rotula viejo.

---

### 2.5 · Límite de consultas y política de uso aceptable, **por escrito**

> **La frase:** «¿Cada cuánto podemos consultar sin molestarles? Preferimos que nos pongan el
> límite ustedes a estimarlo nosotros y que nos bloqueen.»

**Por qué:** el job de ingesta necesita una cadencia, y la alarma de ausencia se dimensiona a partir
de ella (**el umbral es el doble de la cadencia**). Sin un número suyo, el número es una suposición
nuestra. Además, que nos lo den por escrito nos protege: usamos `ETag`, así que la mayoría de las
consultas devuelven «no cambió» y no les cuestan ancho de banda — díselo, es un argumento a favor.

---

### 2.6 · El texto exacto de atribución que quieren ver ⭐ la que desbloquea lo legal

**Pide:** la frase literal de crédito y, si tienen, el logotipo con sus normas de uso.

> **La frase:** «¿Cómo quieren aparecer citados? Preferimos que nos den la frase textual a
> inventárnosla nosotros. Y díganos si hay algún uso que **no** quieren que hagamos.»

**Por qué:** es la **mitad no técnica** del bloqueo de la ficha del ingestor, y es la que no puede
resolver ningún desarrollador. Con esa frase en la mano, el trabajo restante es de horas.

**Llévales tú una propuesta** (ver §3.3) — llegar con un borrador y no con una pregunta abierta
acelera esto muchísimo.

---

### 2.7 · Un contacto técnico y un canal de estado

> **La frase:** «Si el feed se cae o cambia, ¿a quién escribimos? ¿Publican algún estado del
> servicio?»

**Por qué:** tenemos una alarma que salta cuando **deja de entrar** catálogo. Una alarma cuyo
destinatario final no existe es media alarma: alguien tiene que poder preguntar «¿es cosa suya o
mía?».

---

### 🎁 Extra — solo si la conversación va bien y sale gratis

**Acceso a datos de sus estaciones** (metadatos FDSN-station, y en el mejor caso SeedLink). No es
necesario para nada de lo que tenemos pendiente, pero permitiría **contrastar nuestra red contra la
suya** y sería un salto de calidad en la validación del quórum. Pídelo al final, como interés
genuino, sin insistir. Si notas resistencia, retíralo: **no vale la pena arriesgar las siete
anteriores por ésta.**

---

## 3 · LO QUE TÚ LES ENTREGAS

Llega con esto preparado. Que la conversación no dependa de que ellos te crean de palabra.

### 3.1 · Una hoja de una página: qué es TAKAB y qué haría con sus datos

Con estos puntos y ninguno más:
- Plataforma de alertamiento sísmico y continuidad operativa para inmuebles (hospitales,
  universidades, industria, gobierno) en México.
- **El disparo viene de SASMEX**, por contacto seco, 100 % local. El catálogo del SSN es
  **contexto**, y nunca dispara nada.
- Red propia de sensores en edificios, **una placa por inmueble**.
- El catálogo se usaría para: (a) contexto en pantalla tras un evento, (b) validación de nuestros
  algoritmos, (c) informes al cliente.

### 3.2 · El compromiso de uso y de NO-uso, firmado

Es el documento que de verdad les importa. Un borrador utilizable:

> **Compromiso de uso de datos del Servicio Sismológico Nacional**
>
> TAKAB Ailert se compromete a:
> 1. **Citar al SSN** como fuente en toda pantalla, informe o exportación que muestre datos
>    derivados de su catálogo, con el texto que el SSN indique.
> 2. **No presentar los datos del SSN como propios** ni como producto de nuestra instrumentación.
> 3. **No usar el catálogo del SSN para generar alertas ni para accionar dispositivos.** El
>    alertamiento de nuestro sistema procede exclusivamente de SASMEX y de nuestra propia
>    instrumentación; el catálogo del SSN es informativo y posterior al evento.
> 4. **Rotular la antigüedad** del dato: nunca presentar un catálogo desactualizado como vigente,
>    ni una solución preliminar como definitiva.
> 5. **No redistribuir** el catálogo en bruto como servicio a terceros.
> 6. Respetar la cadencia de consulta que el SSN establezca y usar consultas condicionales
>    (`If-None-Match`) para no generar tráfico innecesario.
> 7. **Corregir o retirar** cualquier uso que el SSN considere indebido, a simple solicitud.

Los puntos 3 y 4 **no son promesas de buena voluntad: ya están construidos en el sistema** y hay
pruebas automáticas que fallan si alguien los rompe. Díselo — es lo que separa esto de una carta de
intenciones.

### 3.3 · Cómo se vería el crédito, en concreto

Llévales dónde aparecería la frase: al pie del panel del gabinete, en la vista de contexto de la
consola y en el pie de los informes PDF. Si puedes, una captura. **Una propuesta concreta se
aprueba o se corrige en dos minutos; una pregunta abierta se queda meses en un correo.**

### 3.4 · Lo que puedes OFRECER a cambio

Una colaboración con dos direcciones es mucho más fácil de sostener dentro de una institución que
un favor. Lo que TAKAB tiene y ellos no:

- **Registros de aceleración dentro de estructuras.** Su red mide el campo libre; la nuestra mide
  lo que el edificio realmente sintió. Para un servicio sismológico eso es interesante de verdad.
- **Densificación urbana**: una placa por inmueble, creciendo con cada cliente.
- **Acceso de consulta** a nuestra consola para fines académicos.

> ⚠️ **No prometas los datos de los clientes en esa reunión.** Cada registro pertenece al inmueble
> donde se tomó y su cesión exige el consentimiento del cliente y una revisión de privacidad que no
> está hecha. La forma correcta de decirlo es: **«nos interesa explorar una vía de colaboración de
> datos; tendríamos que resolver antes los permisos con cada inmueble.»** Prometer y luego retirar
> hace más daño que no ofrecer.

---

## 4 · La hoja para traerse de vuelta

Vuelve con esto respondido. Si algo queda en blanco, queda en blanco — **no lo rellenes con lo que
crees que dijeron.**

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | ¿Hay endpoint de catálogo consultable por programa? ¿URL? | |
| 2 | ¿Llega a histórico? ¿Desde qué año? | |
| 3 | ¿Es FDSN-event o formato propio? | |
| 4 | ¿HTTPS disponible o previsto? | |
| 5 | ¿Hay documentación del formato? ¿Dónde? | |
| 6 | ¿Cómo nos avisan de un cambio de formato? | |
| 7 | ¿El ID del evento es estable entre revisiones? | |
| 8 | ¿Cómo se distingue una solución preliminar de una revisada? | |
| 9 | ¿Cadencia máxima de consulta? | |
| 10 | Texto exacto de atribución | |
| 11 | ¿Hay usos que prohíban expresamente? | |
| 12 | Contacto técnico (nombre y correo) | |
| 13 | ¿Hace falta convenio firmado, o basta el acuerdo de uso? | |
| 14 | ¿Quién firma por el SSN y qué plazo lleva? | |

---

## 5 · Qué se desbloquea con cada respuesta

Para que sepas qué estás comprando con cada pregunta:

| Respuesta que traigas | Qué destraba |
|---|---|
| **Endpoint programático + esquema** | El ingestor del catálogo (`T-2.149`), bloqueado desde que se decidió automatizarlo |
| **+ atribución aprobada** | El ingestor queda **completamente** desbloqueado: es su otra mitad |
| **Histórico** | Validación del quórum contra sismos reales en vez de cinco transcritos a mano; y la capa estimada de sacudida del Bloque IV |
| **ID estable + marca de preliminar** | Que el catálogo se pueda actualizar sin duplicar y sin presentar un dato provisional como firme |
| **Cadencia por escrito** | El umbral de la alarma de ausencia deja de ser una suposición |
| **Contacto técnico** | La alarma de ausencia tiene a quién preguntar |

---

## 6 · Lo que NO hay que pedir

Pedir de más resta credibilidad y consume el capital de la reunión:

- ❌ **Nada de SASMEX** — no es suyo (ver §0).
- ❌ **Que validen o certifiquen TAKAB.** Un servicio sismológico no avala productos comerciales, y
  pedirlo pone en guardia a cualquiera.
- ❌ **Exclusividad.** El catálogo es público; pedir trato exclusivo es pedir algo que no pueden dar
  y que además nos haría quedar mal.
- ❌ **Que asuman responsabilidad** por lo que nuestro sistema haga con sus datos. Al contrario:
  conviene que nuestro compromiso escrito les deje claro que **no la tienen**.

---

## 7 · Si de la reunión sale que hace falta convenio

Es lo más probable si el SSN es formal. Averigua **quién firma y cuánto tarda**, porque eso marca
la fecha real y no la de la reunión. Y pregunta si mientras tanto pueden darte un **acceso de
prueba**: casi siempre existe, y con eso se puede escribir y probar el ingestor entero mientras el
papel avanza por su camino.
