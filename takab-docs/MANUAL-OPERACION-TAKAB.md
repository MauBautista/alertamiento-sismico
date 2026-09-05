# MANUAL DE OPERACIÓN · TAKAB Ailert

> **Para quién es esto:** para la persona que vigila el edificio. Protección Civil interna,
> jefe de mantenimiento, encargado de turno, vigilante de caseta, brigadista.
> **No hace falta saber de computadoras para usar este manual.**
>
> **Para quién NO es:** no es el manual de instalación ni el de mantenimiento del software.
> Esos son `takab-docs/RUNBOOK-ALTA-DE-ESTACION.md` y los demás runbooks, y son para el
> técnico de TAKAB.

**Cómo leerlo:** la sección 3 y la sección 4 son las que se leen de pie, con el edificio
temblando. Las demás se leen sentado, un martes por la mañana. Léelas ese martes.

---

## FICHA DE ESTE SITIO — rellénala el día de la instalación

Esta tabla no viene rellenada de fábrica y **no puede venirlo**: cada edificio tiene su
dirección de red, su PIN y su gente. Rellénala a mano, imprime esta página y déjala pegada
junto al gabinete y en la caseta de vigilancia.

| Dato | Valor en este sitio |
|---|---|
| Nombre del sitio | |
| Identificador del gabinete (`gateway_id`) | |
| **Dirección del panel** (lo que se escribe en el navegador) | `http://______________:8080` |
| **PIN de 6 dígitos** del panel | *(no lo escribas aquí si esta hoja queda a la vista)* |
| Dónde está físicamente el gabinete | |
| ¿Este gabinete tiene bocina de voceo? | Sí / No |
| ¿Este gabinete tiene botón físico de silencio? | Sí / No — ver §10, hueco H-4 |
| **Soporte TAKAB — teléfono** | |
| **Soporte TAKAB — correo** | |
| Responsable interno del edificio | |
| Fecha de instalación | |

---

## 1 · Qué hace el sistema, en treinta segundos

Hay un gabinete en este edificio. Dentro hay dos aparatos: un **sensor sísmico** que mide
cómo se mueve el suelo cien veces por segundo, y una **computadora pequeña** que decide y
acciona. Al gabinete llega además la señal de la **alerta sísmica oficial mexicana (SASMEX)**
por un receptor propio, el **WR-1**.

Cuando entra la alerta oficial, el gabinete, **por su cuenta y en milisegundos**:

- suena la **sirena** y enciende el **estrobo**;
- **cierra la válvula de gas**;
- **manda los ascensores a planta baja**;
- **libera los retenedores de puerta**;
- (si este sitio tiene bocina) suelta un **mensaje hablado** de instrucciones.

Después avisa a la nube, guarda la evidencia y la sube. **Ese "después" no condiciona nada de
lo anterior.**

El tiempo medido entre que el WR-1 cierra su contacto y el relé de la sirena se mueve es de
**milisegundos** — la medición con el hardware real dio **6.65 ms** (fuente: [`MEDICIONES-TAKAB.md`](MEDICIONES-TAKAB.md))
(`takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:85`). Es más rápido que un
parpadeo.

### Y qué NO hace — esto importa igual

| El sistema **no** te va a dar | Por qué |
|---|---|
| **Una cuenta regresiva.** No hay "faltan 15 segundos" en ninguna pantalla | El receptor WR-1 entrega **un sí o un no**, nada más. No trae la hora de llegada de la onda. Un cronómetro ahí sería un número inventado. **Si alguien espera ese número, va a esperar para siempre** |
| **La magnitud del sismo** en el momento de la alerta | Por lo mismo: el contacto seco no transporta magnitud. El letrero rojo dice exactamente `ALERTA SÍSMICA · PROTÉJASE` y nada más |
| **El epicentro** en el momento de la alerta | Igual. El mapa del panel muestra sismos del catálogo del SSN, que llegan **después** y son información de contexto, no la alerta |
| **Un dictamen de si el edificio es seguro** | TAKAB entrega un *dictamen operativo preliminar*. **No sustituye la evaluación estructural formal ni autoriza el reingreso sin firma de ingeniería.** Esto es límite de responsabilidad, no letra chica |

> Regla que gobierna toda la pantalla: **lo que el sistema no sabe se pinta en ámbar y dice
> que no lo sabe.** Nunca se pinta de verde "por si acaso". Si ves ámbar, el sistema te está
> diciendo *"no lo sé"*, no *"probablemente esté bien"*.

---

## 2 · La pantalla del gabinete: cómo entrar

El gabinete sirve su propia pantalla dentro de la red del edificio. **No pasa por internet.**
Aunque el edificio esté incomunicado del mundo, esta pantalla funciona.

1. Conéctate a la red del edificio (cable o wifi del inmueble).
2. Abre el navegador y escribe la dirección de la ficha: `http://<dirección>:8080`
3. Listo. **No pide usuario ni contraseña para mirar.** Es a propósito: es el panel del
   guardia (`edge/takab_edge/local_api/__init__.py:6-10`).

**Para tocar botones sí pide un PIN de 6 dígitos.** Ese PIN se imprimió **una sola vez** el
día de la instalación y se entregó al responsable del edificio
(`takab-docs/RUNBOOK-ALTA-DE-ESTACION.md:97`).

- El PIN **no se guarda** en el navegador. Al recargar la página te lo vuelve a pedir. Es a
  propósito.
- **Cinco PIN equivocados y el panel se bloquea 60 segundos**
  (`edge/takab_edge/local_api/__init__.py:56-58`). No es una avería: espera un minuto.

**La pantalla se adapta sola** a lo que la abre: en un monitor de pared se ve enorme y sin
botones (modo MURO); en una laptop se ve todo junto (modo CONSOLA); en un celular se ve en una
columna con botones grandes (modo CAMPO). Hay unos chips arriba a la derecha —
`AUTO` / `MURO` / `CONSOLA` / `CAMPO` — para forzar uno.

---

## 3 · El semáforo grande: estado del inmueble

Es la línea más grande de la pantalla. Contesta la única pregunta que importa a cinco metros
de distancia.

| Lo que dice | Qué significa | **Qué haces** |
|---|---|---|
| `✓ NORMAL · SIN ALERTA` (verde) | Todo tranquilo. El suelo está en su ruido de fondo | Nada. Sigue con lo tuyo |
| `▲ VIGILANCIA` (ámbar) | Se midió movimiento por encima del piso de ruido, pero por debajo del umbral de disparo | **No evacues.** Mira la pantalla 30 segundos. Si sube a rojo, actúa |
| `■ ACCESO RESTRINGIDO` (rojo) | Movimiento fuerte medido. En un sitio con actuación instrumental habilitada, esto mueve ascensores y puertas | Impide el paso a las zonas restringidas del plan del edificio. Espera instrucciones |
| `■ EVACUAR / RESGUARDO` (rojo) | El nivel más alto de movimiento medido | **Aplica el protocolo de evacuación o resguardo del edificio.** El sistema no decide por ti cuál de los dos: eso lo fija tu plan de emergencia |
| `⚠ MODO MANUAL — SENSORES DEGRADADOS` (ámbar) | **El sistema no sabe.** El sensor no le está dando datos confiables | Trata al edificio como **sin instrumentación**. La alerta oficial SASMEX sigue funcionando (es otro camino), pero la detección propia está ciega. **Avisa a soporte hoy mismo** |
| `ARRANQUE EN FRÍO · SIN DECISIÓN AÚN` (ámbar) | El gabinete acaba de encender, o se acaba de cerrar una alerta. Todavía no ha tomado ninguna decisión | Espera un minuto. Si sigue así después de cinco minutos, avisa a soporte |

`edge/takab_edge/local_api/index.html:530-536` (los cinco niveles) y `:900` (el arranque en frío).

**`⚠ MODO MANUAL` es ámbar y no verde a propósito.** Significa "no lo sé". Lo desconocido
nunca se pinta como bueno.

### La línea de abajo: sirena, SASMEX, nivel

Justo debajo del semáforo hay una línea del tipo
`SIRENA: EN REPOSO · SASMEX: NO · TIER normal`. Léela así:

| Trozo | Qué significa | **Qué haces** |
|---|---|---|
| `SIRENA: SONANDO · ALERTA` | Está sonando porque hay alerta | Protocolo de sismo |
| `SIRENA: SONANDO · PRUEBA` | Está sonando porque alguien pulsó una prueba | Nada. **Tranquiliza a quien pregunte:** es una prueba |
| `SIRENA: SONANDO · ESTADO SEGURO` | Suena porque los relés se fueron a su posición segura | Avisa a soporte hoy: no es un sismo, es el sistema protegiéndose de una falla |
| `SIRENA: SILENCIADA` | Alguien la calló desde el panel. **La alerta puede seguir viva** | Mira el semáforo, no la sirena |
| `SIRENA: EN REPOSO` | No suena | Normal |
| `SIRENA: S/D` | **El gabinete no pudo leer si la sirena suena.** No es "no suena": es "no sé" | Ve a §5, fila `NO CONTESTA`. **Avisa a soporte AHORA** |
| `SASMEX: ACTIVO` | La alerta oficial está entrando **en este momento** | Protocolo de sismo |
| `SASMEX: NO` | No hay alerta oficial | Normal |
| `SASMEX: S/D` | **No se pudo leer el receptor WR-1** | Avisa a soporte AHORA |

`edge/takab_edge/local_api/index.html:960-971`.

---

## 4 · Los letreros grandes (banners) y qué pide cada uno

Aparecen arriba, sobre todo lo demás. **Lo real siempre gana:** si hay una alerta de verdad,
tapa al simulacro y a la prueba.

| Letrero | Color | Qué está pasando | **Qué haces** |
|---|---|---|---|
| `ALERTA SÍSMICA · PROTÉJASE` | **Rojo, parpadeando** | Alerta real. Viene de SASMEX o del quórum confirmado de la red | **Protocolo de sismo del edificio.** El letrero mismo lo resume: alejarse de ventanas, no usar ascensores, seguir la ruta señalizada |
| `⚠️ AVISO SÍSMICO · MOVIMIENTO FUERTE (UMBRAL INSTRUMENTAL)` | Ámbar fuerte | **Este sensor midió movimiento fuerte, pero nada se ha accionado.** Una sola estación no dispara alarmas | **No es una alerta.** Es un aviso. Mira el semáforo y prepárate; si es un sismo real, en segundos suele llegar la confirmación. No evacues solo por esto salvo que tu plan lo diga |
| `🔒 ACTUADORES ENCLAVADOS · CIERRE LA ALERTA PARA LIBERAR` | Ámbar | Ya pasó la alerta, pero los relés siguen en posición de protección (gas cerrado, ascensores abajo). **Es por diseño**, para que nadie los libere sin querer | Cuando la situación esté controlada y **una persona lo decida**, pulsa `CERRAR ALERTA` con el PIN. Ver §7 |
| `🔶 SIMULACRO — ESTO NO ES UNA ALERTA REAL` | Ámbar | Hay un simulacro de voceo en curso | Nada. Si entra una alerta real, el simulacro se aborta solo y el letrero cambia a `SIMULACRO ABORTADO — ALERTA REAL EN CURSO` |
| `🔧 PRUEBA DE ACTUADORES — NO ES ALERTA REAL` | Cian | Alguien está probando sirena, gas, ascensores y puertas | Nada, pero **avisa por radio a la gente del edificio** antes de que alguien vea la sirena y se asuste |
| `🧪 MODO PRUEBA WR-1 — LA NUBE NO RECIBE ALERTAS` + `N s RESTANTES` | Violeta, con cuenta atrás | Un técnico armó una ventana de prueba. **El edificio sigue protegido igual en local**, pero durante esa ventana la nube no se entera de nada | Nada. **La ventana se apaga sola a los 120 segundos.** Este letrero se ve incluso encima de una alerta real, a propósito: para que sepas que la nube está ciega |
| `📋 RETIRADO EN LA NUBE · ESTE GABINETE SIGUE PROTEGIENDO` | Ámbar | Alguien **retiró** este gabinete en la consola central. Sigue sonando la sirena y cerrando el gas, pero ya no recibe configuración ni órdenes de la nube | **Si no fue intencional, avisa a TAKAB.** Este letrero no caduca solo |
| `ORDEN RECHAZADA` | Ámbar, se va solo | El botón que pulsaste no se ejecutó | Ver §7, tabla de mensajes del PIN |

`edge/takab_edge/local_api/index.html:246-290` (los letreros) y `:919-949` (cuándo sale cada uno).

---

## 5 · **Cuando cae la nube**

Esta es la sección más importante del manual, y la que más gente entiende al revés.

### Lo primero: no pasa nada grave

**El gabinete no necesita internet para protegerte.** Está diseñado así desde el primer día.
Si se cae el enlace de internet del edificio, si se cae el proveedor, si se cae la nube entera
de TAKAB: **el edificio sigue protegido**.

Lo vas a ver escrito en la pantalla, arriba a la derecha, en ámbar:

```
SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · 47 EN COLA
```

**Ese letrero no es un error.** Es el sistema funcionando como fue diseñado. Está en ámbar y
no en rojo justamente por eso. El número (`47 EN COLA`) son mensajes esperando a que vuelva el
enlace para subir.

### Qué sigue funcionando (todo esto es local, no toca internet)

| Sigue funcionando | Detalle |
|---|---|
| **La alerta oficial SASMEX → sirena** | El camino completo vive dentro del gabinete. El receptor WR-1 está cableado a la computadora del gabinete y esta a los relés. Internet no aparece por ninguna parte (`edge/takab_edge/gpio/__init__.py:1-5`, `:740-758`) |
| **Cierre de gas, ascensores, puertas, estrobo** | Igual: relés locales |
| **El voceo hablado** (si este sitio tiene bocina) | Es un archivo de audio guardado en el gabinete |
| **El sensor midiendo** | Sigue midiendo cien veces por segundo |
| **El semáforo y todo el panel** | La pantalla la sirve el propio gabinete por la red del edificio |
| **Los botones del panel** (silenciar, cerrar alerta, probar) | Todos son locales |
| **La configuración del sitio** | El gabinete guarda la última configuración firmada en su propio disco y la vuelve a cargar aunque se le corte la luz (`edge/takab_edge/config/store.py:151-198`) |
| **La hora** | El gabinete no depende de internet para saber la hora. El diseño incluye un reloj con batería propia; **no pude verificar en el código que ese reloj esté instalado en este gabinete** — solo consta la lectura del sincronizador de hora (`edge/takab_edge/health/__init__.py:193-196`). Ver §10, hueco H-8 |

### Qué deja de funcionar, o queda esperando

| Deja de funcionar | Qué significa en la práctica |
|---|---|
| **Los avisos a la gente: SMS, correo, notificación al celular, WhatsApp** | **Los manda la nube, no el gabinete.** El gabinete no sabe mandar ni un correo (`api/src/takab_api/notify/orchestrator.py:40-42`; en `edge/` no existe ningún emisor de SMS/correo/push). La sirena sí suena; el mensaje al teléfono del brigadista puede no llegar. **Esto es lo más importante de toda esta sección.** Ver el matiz de abajo |
| **La actuación por acuerdo entre varios edificios (quórum)** | Cuando tres o más estaciones de la red confirman un sismo, la nube manda una orden firmada a los gabinetes. Sin enlace esa orden **no llega** y no hay actuación por esa vía (`edge/takab_edge/dispatch/__init__.py:211-238`). **La alerta oficial SASMEX no depende de esto en absoluto** |
| **La consola web y la app móvil** | Dejan de ver a este gabinete. En la consola central el sitio aparece como `SIN ENLACE` a los 5 minutos sin latido (`api/src/takab_api/settings.py:130-132`) |
| **La configuración nueva** | Si alguien cambia umbrales o equipamiento desde la consola, este gabinete **no se entera hasta que vuelva el enlace**. Sigue con la última configuración que recibió, y el panel lo rotula: `SEGÚN LA ÚLTIMA CONFIG FIRMADA v12 · SIN ENLACE CON LA NUBE` |
| **La subida de evidencia** | Los registros del sismo se quedan guardados en el gabinete esperando. Ver el aviso de abajo |

#### El matiz de los avisos: hay dos formas distintas de "caerse la nube"

No son lo mismo y no dan el mismo resultado. **Desde el panel no puedes distinguirlas**: en los
dos casos verás `SIN ENLACE`.

| Qué se cayó de verdad | ¿Salen los avisos al teléfono? |
|---|---|
| **Se cayó el internet de ESTE edificio**, pero la nube de TAKAB sigue viva | **Puede que sí.** La nube tiene una salvaguarda: si detecta un sismo que alcanza a un sitio al que perdió el enlace, abre un incidente y notifica igual, por si acaso (`api/src/takab_api/incident/fail_open.py:112-166`) |
| **Se cayó la nube entera** de TAKAB | **No sale ninguno.** No hay quien los mande |

**Consecuencia operativa, y es la misma en los dos casos:** cuando veas `SIN ENLACE`,
**no cuentes con que los avisos automáticos salgan.** Avisa tú.

### Qué se acumula mientras tanto

| Se acumula | Dónde y cuánto |
|---|---|
| Mensajes de estado y mediciones | En una cola en el gabinete. Las mediciones rutinarias tienen tope (10 000) y cuando se llena **se tiran las más viejas primero**; los **eventos y los acuses no se tiran nunca** (`edge/takab_edge/cloud/__init__.py:463-493`) |
| Registro sísmico continuo | En el disco del gabinete. Retención configurada: **14 días** (`edge/takab_edge/config/settings.py:139-141`) |
| Evidencia de eventos pendiente de subir | Una lista de "hay que subir esto". El panel te dice cuántos y desde cuándo |

> **Aviso honesto sobre lo que se acumula.** Que la evidencia sobreviva a un **reinicio del
> gabinete** depende de un ajuste que hoy **no lo pone el instalador automáticamente**. El
> panel te lo dice a la cara cuando no sobrevive: en la sección de evidencia aparece
> `COLA NO DURABLE · SE PIERDE AL REINICIAR`. **Si ves esa frase, díselo a soporte:** significa
> que si el gabinete se reinicia con evidencia pendiente, esa evidencia no se sube nunca.
> Ver §10, hueco H-1.

### Qué haces tú cuando cae la nube

1. **Nada urgente.** Respira. El edificio sigue protegido.
2. **NO desconectes, NO reinicies, NO apagues el gabinete.** El gabinete reconecta solo, en
   cuanto vuelva el enlace, sin que nadie toque nada (reintentos automáticos con espera
   creciente hasta 60 segundos entre intentos, `edge/takab_edge/cloud/__init__.py:540-576`).
   **Reiniciarlo es la peor idea posible:** puede tirar la evidencia acumulada.
3. **Avisa por otro medio.** Esto es lo que sí tienes que hacer: como los SMS y correos
   automáticos no salen, **si ocurre un sismo mientras la nube está caída, avisar a los
   brigadistas es tarea humana.** Radio, teléfono, viva voz. Que esté escrito en tu plan de
   emergencia.
4. **Revisa si es el internet del edificio.** Si otras cosas del edificio tampoco tienen
   internet, es la línea, no el gabinete. Avisa a quien lleve la red.
5. **Si pasa de una hora, avisa a soporte TAKAB.** Ellos ya deberían saberlo — la nube detecta
   un gabinete callado en unos 10 minutos (`infra/terraform/modules/observability/main.tf:182-202`)
   — pero un aviso tuyo con la hora exacta ayuda.

### El error que vas a cometer una vez: confundir dos letreros

Son distintos y piden cosas distintas.

| Letrero | Qué se cayó | Gravedad |
|---|---|---|
| `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA` (ámbar, arriba a la derecha) | **El gabinete no habla con la nube.** El edificio sigue protegido | Baja. Es esta sección §5 |
| `SIN CONEXIÓN CON EL GABINETE · REINTENTANDO…` (rojo, arriba en el centro) | **Tu pantalla no habla con el gabinete.** No sabes si el edificio está protegido o no | **Alta.** Ve a §6.1 |

`edge/takab_edge/local_api/index.html:909` y `:858`.

---

## 6 · Diccionario de estados del panel

Cada fila: qué lo dispara, qué significa **en el edificio**, y qué haces.

Columna **urgencia**:
**AHORA** = llama a soporte en este momento ·
**HOY** = anótalo y repórtalo hoy ·
**ANOTAR** = déjalo escrito en la bitácora del turno.

### 6.0 · Las tres palabras que NO significan lo mismo

Esto es lo más fácil de confundir y lo más caro de confundir. El panel distingue tres cosas
distintas a propósito, y cada una pide una acción distinta.

| Palabra en pantalla | Significa | Ejemplo | **Qué haces** |
|---|---|---|---|
| **`S/D`** | **No hay dato.** Nunca se midió, o el módulo que lo mide no está | La temperatura del procesador dice `S/D` | Depende de qué dato sea. Busca la fila concreta abajo |
| **`DATO RETENIDO DESDE 04:12:07 UTC`** | **El dato existe, pero es viejo.** Estás mirando una foto congelada de esa hora | Tu pantalla dejó de recibir del gabinete hace unos segundos | **No creas nada de lo que ves.** Recarga la página. Ver §6.1 |
| **`NO CONTESTA`** | **El módulo que gobierna algo está caído.** No es que el dato falte: es que la pieza no responde | La fila `RELÉS` dice `NO CONTESTA` | **AHORA.** Es lo más grave que puede decir esta pantalla |

**Nunca las colapses mentalmente en "está fallando algo".** `S/D` en la temperatura del
procesador es una molestia. `NO CONTESTA` en los relés significa que **quizá la sirena no
suene.**

Y una regla de color que vale para toda la pantalla:

> **Ámbar = el sistema no sabe. Rojo = el sistema sabe que algo está mal. Verde = medido y
> bueno.** Nunca verás verde sobre un dato que nadie midió.

#### El vocabulario completo — y por qué la consola del SOC dice lo mismo

Las tres palabras de arriba son las que más se confunden, pero no son todas. **El vocabulario
de estado del sistema está escrito en un solo sitio**, `shared/glossary/estados.json`, y de ahí
salen **las dos pantallas**: este panel y la consola web del SOC.

Eso importa para ti aunque no uses la consola. Cuando llames a soporte, **la persona al otro
lado está mirando la consola, no tu panel.** Si tú dices una palabra y su pantalla dice otra
para el mismo hecho, los dos creéis que habláis de cosas distintas — y esa traducción, hecha de
cabeza y bajo presión, es donde se cometen los errores caros. Por eso las dos pantallas usan la
misma palabra siempre que puedan, y **cuando no pueden, es porque las dos no saben lo mismo**.

| Qué pasa | En **este panel** | En la **consola** del SOC | Qué pide |
|---|---|---|---|
| No hay dato: nunca se midió, o el módulo que lo mide no está | `S/D` | `S/D` | Depende del dato. **Nunca se pinta en verde** |
| El dato existe pero es viejo: es una foto congelada | `DATO RETENIDO` | `DATOS RETENIDOS` \* | No creerte nada de lo que ves hasta que refresque |
| El módulo que **gobierna** algo no responde | `NO CONTESTA` | `NO CONTESTA` | **AHORA.** Lo más grave que dice cualquiera de las dos |
| El módulo de relés no está corriendo | `DETENIDO` | — (no puede saberlo) | **AHORA.** Alarma manual del edificio lista |
| El módulo de relés corre pero falló al leerse | `AVERÍA` | — (no puede saberlo) | **AHORA.** Alarma manual del edificio lista |
| El gabinete y la nube no se hablan | `SIN ENLACE` | `SIN ENLACE` | Anotar. **El edificio sigue protegido** (§5) |
| Alguien retiró el gabinete en la consola central | `RETIRADO` | `RETIRADO` | Si no fue intencional, avisar a TAKAB. No caduca solo |
| **Tu pantalla** no habla con el gabinete | `SIN CONEXIÓN CON EL GABINETE` | — (la consola no habla con gabinetes) | **AHORA.** Ver §6.1 — y §5, es el error que todos cometen una vez |
| El gabinete late y todo está en rango | — (no puede saberlo) | `OPERATIVO` | Nada |
| El gabinete late pero algo está fuera de rango | — (no puede saberlo) | `DEGRADADO` | Hoy. La consola nombra las razones |

\* Deuda conocida y declarada: la consola dice `DATOS RETENIDOS` en plural donde este panel dice
`DATO RETENIDO`. Es el **mismo estado**; está fichada en el propio glosario (`divergencias`) y
un test impide que crezca la lista.

**Los guiones de esa tabla no son huecos, son la parte importante.** Donde pone "no puede
saberlo" es literal:

- **La consola no puede decir `DETENIDO` ni `AVERÍA`.** La nube ve a tu gabinete **por el
  latido y nada más**. Un gabinete cuyo módulo de relés está caído **sigue latiendo**: desde la
  nube se ve un gabinete que late. Que la sirena no vaya a sonar **solo lo ve este panel**. Es
  la razón entera por la que este manual existe y por la que vas físicamente al gabinete.
- **Este panel no puede decir `OPERATIVO` ni `DEGRADADO`.** Son veredictos que la nube calcula
  con los umbrales de tu organización. Un gabinete no puede afirmar de sí mismo que la nube lo
  ve bien — **eso fue exactamente el fallo del 14 de julio de 2026: quince horas ciego con la
  consola en `OPERATIVO`.** Este panel dice lo que **mide**, no lo que cree que otro piensa de
  él.

> **Si soporte te dice `OPERATIVO` y tu panel dice `NO CONTESTA` en los relés, no os
> contradecís: los dos tenéis razón y el que manda es el tuyo.** El gabinete late (por eso la
> consola lo ve bien) y a la vez no puede accionar nada (por eso tu panel grita). Ten lista la
> alarma manual del edificio y díselo con esas palabras.

### 6.1 · Conexión entre tu pantalla y el gabinete

Es la píldora del centro-arriba. Habla de **tu navegador**, no del gabinete con la nube.

| Estado | Significa | Urgencia | **Qué haces** |
|---|---|---|---|
| `PANEL EN VIVO` (verde) | Todo lo que ves es de este segundo | — | Nada |
| `CONECTANDO…` (ámbar) | La página acaba de abrir | — | Espera dos segundos |
| `DATO RETENIDO DESDE hh:mm:ss UTC` (ámbar) | **Estás mirando una foto vieja.** El gabinete no contestó los últimos intentos | HOY | Recarga la página. Si vuelve, fue un tropiezo de la red. **Mientras diga esto, no tomes decisiones con lo que ves en pantalla** |
| `SIN CONEXIÓN CON EL GABINETE · REINTENTANDO…` (rojo) | **Tu pantalla no habla con el gabinete.** Puede que el gabinete esté bien y sea tu red, o puede que el gabinete esté apagado | **AHORA** | 1) Comprueba que tu equipo sigue en la red del edificio. 2) Ve físicamente al gabinete y mira si tiene luces. 3) **Avisa a soporte.** Recuerda: aunque tú no lo veas, la rama de hardware de la sirena puede seguir viva |

`edge/takab_edge/local_api/index.html:855-861`.

### 6.2 · Enlace con la nube

| Estado | Significa | Urgencia | **Qué haces** |
|---|---|---|---|
| `ENLACE NUBE · CONECTADO` (verde) | Habla con la nube | — | Nada |
| `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA` (ámbar) | No habla con la nube. **El edificio sigue protegido** | ANOTAR | Toda la §5 |
| `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · N EN COLA` | Igual, y hay N mensajes esperando | ANOTAR | Si N crece durante días, avisa a soporte |

`edge/takab_edge/local_api/index.html:909`.

### 6.3 · Relés: sirena, estrobo, gas, ascensores, puertas

Una tarjeta por actuador instalado. Cada una dice dos cosas distintas:

- **`ACTIVADO` / `REPOSO`** — si el sistema está *pidiendo* protección en ese canal.
- **`ENERGIZADO` / `DESENERGIZADO` · `fail-safe NO/NC/fail_close`** — el estado eléctrico real.

> **No son lo mismo, y en algunos canales son opuestos.** El gas está en `fail_close`: si se
> queda sin corriente, **cierra**. Las puertas están en `NC`: si se quedan sin corriente,
> **liberan**. Eso está bien: es el diseño a prueba de fallos. La línea de arriba
> (`ACTIVADO`/`REPOSO`) es la que te dice si hay protección pedida.

`takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:71-81`;
`edge/takab_edge/local_api/index.html:977-983`.

Si algo va mal con los relés, **aparece una fila extra llamada `RELÉS`**. Cuando todo está
bien, esa fila no existe. Estos son sus estados:

| Fila `RELÉS` dice | Significa **en el edificio** | Urgencia | **Qué haces** |
|---|---|---|---|
| `NO CONTESTA` (rojo) | **El proceso que gobierna los relés no responde. El gabinete no pudo medir si la sirena, el gas o los ascensores están donde deberían.** Puede que la sirena no suene | **AHORA** | **Llama a soporte inmediatamente.** Mientras tanto: da por hecho que la sirena automática podría no sonar. Ten lista la alarma manual del edificio y avisa al personal por radio. La pantalla también nombra un servicio técnico (`takab-gpio`/`takab-edge`): **cópiaselo a soporte tal cual, no intentes tocarlo tú** |
| `DETENIDO` (rojo) | El módulo de relés no está corriendo. **El gabinete NO puede accionar nada** | **AHORA** | Igual que arriba. Alarma manual lista |
| `AVERÍA` (rojo) | El módulo corre pero falló al leer su propio estado | **AHORA** | Igual que arriba |
| `S/D` (rojo) | **No se sabe la causa.** El panel lo trata como la peor causa posible, a propósito | **AHORA** | Igual que arriba |
| `INCOMPLETO` (rojo) + `sin estado de SIRENA, GAS…` | Falta el estado de actuadores que la configuración dice que **sí** están instalados | **AHORA** | Llama a soporte y dile **qué actuadores nombra la frase** |
| `PERFIL S/D` (rojo) | La configuración del sitio no se pudo leer. La lista de abajo puede incluir actuadores que este edificio no tiene | HOY | Avisa a soporte. **No confíes en la lista de actuadores hasta que se resuelva** |
| `SIN ACTUADORES` (ámbar) | Este sitio declara cero actuadores instalados | HOY | Si este edificio **sí** tiene sirena y gas, es un error de configuración: avisa a soporte |

`edge/takab_edge/local_api/index.html:549-561`; causas en
`edge/takab_edge/local_api/__init__.py:664-680`.

### 6.4 · Sensor sísmico y ondas

| Estado | Significa | Urgencia | **Qué haces** |
|---|---|---|---|
| Las cuatro líneas se mueven un poco, sin nota | Normal. El sensor está vivo | — | Nada. **Que las líneas se muevan siempre un poquito es lo correcto** — el suelo nunca está quieto del todo |
| `SIN SEÑAL DEL SENSOR · SIN FEATURES RECIBIDAS` (ámbar) en un carril | **Ese canal no está midiendo, o su último dato tiene más de 5 segundos** | HOY | Si sale en **un** canal: anótalo y repórtalo hoy. Si sale en **los cuatro**: el edificio está sin instrumentación propia. **La alerta oficial SASMEX sigue funcionando** (es otro camino), pero avisa a soporte hoy |
| `SATURACIÓN DEL ADC · EL CANAL ESTÁ TOPADO, NO MIDIENDO` (rojo) | El movimiento se salió de la escala del sensor. **El canal está topado: el valor que muestre es un mínimo, no la medida real** | HOY | Durante un sismo grande esto puede pasar y es información valiosa. **En reposo no debería pasar nunca:** si sale sin sismo, avisa a soporte hoy |
| Un carril con **línea discontinua ámbar** y sin números | Ese canal no ha entregado ni un dato desde que abriste la página | HOY | Igual que `SIN SEÑAL` |
| `SIN CALIBRAR · UNIDADES rel.` (ámbar) sobre las ondas | Los números que ves son **relativos**, no gravedades reales | HOY | Los movimientos se ven, pero **los valores no son comparables con nada**. Avisa a soporte: falta un paso de instalación |
| `SIN SEÑAL DEL SENSOR` en la brújula redonda | Lo mismo que arriba, dicho en la brújula | HOY | Igual |
| `SIN UBICACIÓN PROVISIONADA` (ámbar) en el mapa | Nadie cargó las coordenadas de este edificio. **El sistema no inventa un punto** | HOY | Avisa a soporte: falta un paso de instalación. No afecta a la sirena |

**La barra "proximidad al disparo"** te dice qué tan cerca está el movimiento del umbral.
Debajo hay una frase que conviene leer una vez: *"El piso de ruido en reposo es 0.6–1.1 mg: el
disparo está 60× por encima. En reposo esta barra debe verse vacía — y eso es información."*
Traducción: **si esa barra tiene algo de relleno en un día tranquilo, algo pasa.** Anótalo.

`edge/takab_edge/local_api/index.html:1034-1052` (carriles), `:1053-1083` (proximidad),
`:1862-1865` (brújula), `:387` (ubicación).

> **Por qué "sin señal" y "señal vieja" dicen lo mismo en esta sección, y solo en esta.**
> Una medición de movimiento del suelo de hace más de 5 segundos no vale nada. Por eso el panel
> **borra** el canal en vez de pintarlo viejo. Esto es deliberado y viene de un fallo real: el
> 14 de julio de 2026 el sistema estuvo 15 horas ciego mientras la consola decía OPERATIVO
> porque pintaba valores congelados en verde (`edge/takab_edge/local_api/index.html:864-871`).
> En **todas las demás** secciones de la pantalla, "viejo" y "ausente" se dicen distinto.

### 6.5 · Salud del gabinete

La cabecera dice `DIAGNÓSTICO DE HACE 42 s`. Si pasa de 3 minutos se pone ámbar: el
diagnóstico que estás leyendo ya es viejo.

| Estado | Significa | Urgencia | **Qué haces** |
|---|---|---|---|
| `S/D · SIN DIAGNÓSTICO AÚN` (ámbar) | **El módulo de autodiagnóstico no ha entregado nada.** No es que esté bien: es que no se sabe | HOY | Avisa a soporte |
| `Retraso del sensor` en ámbar (≥2 s) o rojo (≥10 s) | Los datos del sensor llegan tarde | HOY (ámbar) / **AHORA** (rojo) | Con 10 s de retraso, la detección propia va tarde. Avisa a soporte |
| `Pérdida de paquetes` en ámbar (≥1 %) o rojo (≥10 %) | Se están perdiendo datos entre sensor y gabinete | HOY | Suele ser el cable de red entre las dos placas. Avisa a soporte |
| `Huecos del flujo` en ámbar (>0) | Hubo cortes en el flujo del sensor | ANOTAR | Anótalo. Si crece cada día, repórtalo |
| `Reconexiones SeedLink` en ámbar (>5) | El gabinete ha tenido que reconectarse al sensor muchas veces | HOY | Suele ser cable o alimentación del sensor |
| `Contadores SeedLink` → `S/D · sin cliente` (ámbar) | El gabinete no tiene cliente de sensor corriendo | **AHORA** | Sin instrumentación propia. Avisa a soporte |
| `Temperatura del SoC` ámbar (≥70 °C) o rojo (≥80 °C) | El gabinete se está calentando | HOY (ámbar) / **AHORA** (rojo) | **Comprueba que la ventilación del gabinete no esté tapada** y que no le dé el sol. Es lo único de esta lista que puedes arreglar tú |
| `UPS` → `battery · 63 % · 28 min` (ámbar) | **El gabinete está corriendo con batería.** Se fue la corriente | **AHORA** | Verifica el corte de energía del edificio. El número de minutos es la autonomía que queda. **Cuando se agote, el gabinete se apaga** — y con él el panel y la detección propia. La rama de hardware WR-1→sirena depende de su propia alimentación |
| `UPS` → `unknown · …` (ámbar) | No se sabe si está en corriente o en batería | HOY | Avisa a soporte |
| `UPS` → `line · 100 %` (verde) | En corriente, batería llena | — | Nada |
| `Disco usado` ámbar (≥90 %) | El disco del gabinete se está llenando | HOY | Avisa a soporte. Con el disco lleno se deja de guardar evidencia |
| `Certificado mTLS` ámbar (<30 días) | La credencial con la que el gabinete habla con la nube caduca pronto | HOY | Avisa a soporte. **Cuando caduque, el gabinete se queda sin nube** (pero sigue protegiendo) |
| `Desfase de reloj NTP` → `S/D` (ámbar) | No se pudo medir el desfase de hora | ANOTAR | Anótalo |
| `Tonos de voceo` → `N RECHAZADO(S)` (rojo) | Hay archivos de voz que el gabinete rechazó | HOY | **El voceo puede no sonar.** Avisa a soporte |
| `Tonos de voceo` → `alerta · SIN TONO DE PRUEBA` (ámbar) | Hay voz de alerta pero no de prueba | ANOTAR | El botón `PROBAR SIRENA` avisa aparte de esto |

`edge/takab_edge/local_api/index.html:1221-1273`.

### 6.6 · Evidencia del sismo (respaldo a la nube)

Cuando ocurre un evento, el gabinete guarda el registro y lo sube. Esta sección dice cómo va.

| Estado | Significa | Urgencia | **Qué haces** |
|---|---|---|---|
| `SIN EVIDENCIA PENDIENTE` (verde) | Todo subido | — | Nada |
| `N PENDIENTE(S) · RESPALDO EN MARCHA` (ámbar) | Se están subiendo | — | Nada. Vuelve en un rato |
| `BACKFILL EN CURSO · N` / `PIDIENDO PERMISO A LA NUBE · N` (cian) | Subiendo activamente | — | Nada |
| `N EN ESPERA DE ENLACE · LA MÁS VIEJA HACE 3 h` (ámbar) | No hay nube. **Esperar es lo correcto** | ANOTAR | Nada. Se sube solo al volver el enlace. Ver §5 |
| `N ATASCADA(S) DESDE HACE 4 h` (rojo) | **Hay nube y aun así no sube.** Lleva más de una hora atascado | HOY | Avisa a soporte con el número y la antigüedad |
| `N PENDIENTE(S) · EDAD S/D` (ámbar) | Hay pendientes pero no se sabe desde cuándo | ANOTAR | Anótalo |
| `N PENDIENTE(S) ILEGIBLE(S) · M POR SUBIR` (rojo) | Hay archivos rotos. **Esos no se van a subir nunca solos** | HOY | Avisa a soporte. El panel **nombra los ficheros** debajo, precisamente para que se los puedas dictar |
| `SIN PENDIENTES · N EVIDENCIA(S) PERDIDA(S)` (rojo) | **Se perdió evidencia de un evento.** El registro ya no está | HOY | Avisa a soporte. Si fue de un sismo real, díselo: puede tener valor legal o de seguro |
| `S/D · SIN MÓDULO DE RESPALDO` (ámbar) | El módulo de respaldo no está corriendo | HOY | **No se está respaldando nada.** Avisa a soporte |
| Fila `Cola pendiente` → `COLA NO DURABLE · SE PIERDE AL REINICIAR` (ámbar) | Si el gabinete se reinicia, la lista de pendientes se borra | HOY | Avisa a soporte. **Y sobre todo: no reinicies el gabinete** mientras diga esto. Ver §10, hueco H-1 |

`edge/takab_edge/local_api/index.html:1308-1396`.

### 6.7 · Gabinetes secundarios por radio (LoRa)

Solo aparece si este sitio tiene gabinetes secundarios enlazados por radio.

| Estado | Significa | Urgencia | **Qué haces** |
|---|---|---|---|
| `SIN RADIO LORA · MÓDULO DESHABILITADO` | Este sitio no usa radio. Normal si no lo contrataron | — | Nada |
| `SIN GABINETES SECUNDARIOS PROVISIONADOS` | Hay radio, pero nadie dio de alta secundarios | ANOTAR | Si esperabas secundarios, avisa a soporte |
| Un secundario en verde con `-84 dBm · SNR 9.5 · 3.90 V` | Ese secundario está vivo | — | Nada |
| `ENLACE PERDIDO` (rojo) en un secundario | **Ese secundario no da señal.** Lleva más de 4 minutos y medio callado | **AHORA** | **La zona que cubre ese secundario puede estar sin sirena.** Ve a verlo físicamente si puedes; avisa a soporte |
| `SIN CONTACTO AÚN` (gris) | Nunca ha hablado desde que arrancó el principal | HOY | Si debería estar instalado, avisa a soporte |
| `SIN ACK` (rojo) en un secundario durante una alerta | **Se le mandó la alarma y no confirmó haberla recibido** | **AHORA** | Da por hecho que **esa zona no está sonando.** Avísala por radio o en persona |
| `ALARMA PROPAGADA` (ámbar) | Se le mandó la alarma y confirmó | — | Nada |

`edge/takab_edge/local_api/index.html:1183-1219`.

### 6.8 · Sismicidad SSN (el mapa y la lista de sismos)

Esto es **contexto informativo**, no la alerta. Son sismos que el Servicio Sismológico Nacional
ya publicó.

| Estado | Significa | **Qué haces** |
|---|---|---|
| `INSTANTÁNEA DEL CATÁLOGO · hace 2 h · FEED FIRMADO v8` | Catálogo reciente | Nada |
| `CATÁLOGO VIEJO · INSTANTÁNEA DE HACE 4.1 d · UMBRAL 48 h` (ámbar) | Lo que ves tiene más de dos días | **No lo uses para decidir nada.** Anótalo; si dura, avisa a soporte |
| `INSTANTÁNEA DEL CATÁLOGO · EDAD DESCONOCIDA` (ámbar) | No se sabe de cuándo es. **El panel lo trata como viejo** | Igual que arriba |
| `CATÁLOGO NO DISPONIBLE · SIN DATOS EN CACHÉ` (ámbar) | No hay catálogo | Nada urgente. No afecta a la protección |
| `ESTIMACIÓN TEÓRICA · LEY DE ATENUACIÓN SIMPLE — NO ES DATO MEDIDO` (ámbar) | La comparativa de sacudida es un **cálculo aproximado**, no una medición | **No la cites como medición.** Es una referencia visual |

`edge/takab_edge/local_api/index.html:1525-1591`.

### 6.9 · Cabecera y configuración

| Estado | Significa | **Qué haces** |
|---|---|---|
| `config v12` | El gabinete corre la configuración firmada número 12 | Nada |
| `config S/D` (en la cabecera) | No se sabe qué configuración corre | Avísalo hoy |
| `config v0 · defaults` | **Nunca recibió configuración del sitio.** Corre con valores de fábrica | Avisa a soporte: los umbrales de este edificio no están aplicados |
| Franja `DEMO · NO ES ESTADO REAL` | Alguien abrió el panel en modo demostración. **Nada de lo que ves es real** | Quita el `?demo=` de la dirección del navegador. **Nunca dejes un monitor de pared en este modo** |

`edge/takab_edge/local_api/index.html:905-906`, `:212-216`.

---

## 7 · Los botones: qué hacen de verdad

Todos piden el PIN de 6 dígitos. Los marcados **2 clics** hay que pulsarlos dos veces:
el primer clic arma, el segundo ejecuta, y **si tardas más de 5 segundos se desarma solo**.

| Botón | Qué hace de verdad | Cuándo usarlo |
|---|---|---|
| `SILENCIAR AUDIBLES` | Calla la sirena. **Solo aparece si la sirena está sonando** | Cuando la sirena ya cumplió su función y estorba la coordinación. **La alerta sigue viva; solo callas el ruido** |
| `CERRAR ALERTA` · **2 clics** | Libera el enclave: los relés vuelven a reposo | **Solo cuando una persona responsable decida que la emergencia terminó.** Esto reabre el gas y devuelve los ascensores a servicio |
| `PROBAR SIRENA` | Suena 2 segundos | Prueba mensual. **Avisa antes por radio** |
| `PROBAR ACTUADORES` · **2 clics** | Sostiene sirena y estrobo, y da un pulso de verificación a gas, ascensores y puertas leyendo el retorno. **No abre incidente ni manda correos** | Prueba programada. **Avisa antes: se va a mover el gas y los ascensores.** Si entra una alerta real a media prueba, la alerta gana |
| `CALIBRAR BRÚJULA` · **2 clics** | Fija el punto cero de la brújula de ejes | **Solo el técnico, con el gabinete instalado y nivelado.** Si lo pulsas con el gabinete torcido, la brújula queda torcida |
| `MODO PRUEBA WR-1` | Abre una ventana de 120 segundos donde el gabinete **protege igual** pero **no le cuenta nada a la nube** | Solo el técnico, para probar el receptor sin abrir un incidente real ni disparar correos |
| `SALIR DE PRUEBA WR-1` | Cierra esa ventana antes de tiempo | Cuando termine la prueba. Si se te olvida, se cierra sola |
| `SIMULACRO DE VOCEO` | Reproduce el mensaje hablado de simulacro. **No toca ningún relé** | Simulacros. **Solo aparece si este sitio tiene bocina** |

`edge/takab_edge/local_api/index.html:1702-1714`;
`takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:854-876`.

> **Límite honesto de `SILENCIAR AUDIBLES`.** Este edificio puede tener una **rama de hardware
> en paralelo** que conecta el receptor WR-1 directamente a la sirena, para que suene aunque la
> computadora del gabinete esté muerta. Es la protección más importante del sistema —
> y por eso mismo **el botón de silencio no la puede callar** mientras la alerta oficial
> mantenga el contacto cerrado. Si pulsas silenciar y la sirena sigue sonando, **no está
> averiada: es esa rama.** (`takab-docs/RBAC-TAKAB.md:243`;
> `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:862`. Ver §10, hueco H-3.)

### Si un botón no funciona

| Mensaje | Significa | Qué haces |
|---|---|---|
| `ORDEN ACEPTADA · <botón>` (verde) | Se ejecutó | Nada |
| `CAPTURE EL PIN DE 6 DÍGITOS` | Se te olvidó el PIN | Escríbelo y vuelve a pulsar |
| `PIN INCORRECTO` | PIN mal | Vuelve a intentar. **Cuidado: a los 5 fallos se bloquea un minuto** |
| `BLOQUEADO POR INTENTOS · ESPERA 60 s` | Cinco fallos seguidos | Espera un minuto. No es una avería |
| `SIN PIN CONFIGURADO · ACCIONES BLOQUEADAS` | Este gabinete no tiene PIN cargado. **Ningún botón va a funcionar** | Avisa a soporte hoy: falta un paso de instalación |
| `ERROR 409` | El gabinete no podía hacer eso ahora mismo. El caso típico: pulsar `CALIBRAR BRÚJULA` sin señal del sensor | Resuelve la causa (en ese caso, el sensor) y reintenta |
| `ERROR 503` | El gabinete no pudo ejecutar la acción | **No recargues la página ni reinicies nada.** Avisa a soporte y dile qué botón pulsaste |
| `SIN CONEXIÓN CON EL GABINETE` | Tu pantalla no llegó al gabinete. **La orden no se envió** | Ver §6.1 |

`edge/takab_edge/local_api/index.html:1679-1694`;
`edge/takab_edge/local_api/__init__.py:437-462`.

---

## 8 · Qué haces durante y después de un sismo

### Mientras suena

1. **Protégete tú primero.** El sistema ya hizo lo suyo en milisegundos.
2. **No vayas al gabinete.** No hay nada que pulsar durante el sismo.
3. **No uses los ascensores.** Ya bajaron solos.
4. Aplica el protocolo del edificio.

### En los primeros minutos después

1. Abre el panel.
2. **Mira el semáforo.** Si dice `■ EVACUAR / RESGUARDO` o `■ ACCESO RESTRINGIDO`, el
   protocolo sigue vigente.
3. **Mira las tarjetas de relés.** ¿El gas quedó cerrado? ¿Los ascensores abajo?
4. **Mira si hay `SIN ENLACE`.** Si lo hay, **los avisos automáticos a los brigadistas no
   salieron.** Avísalos tú, por radio o teléfono. Ver §5.
5. **Mira si hay `SIN ACK`** en algún gabinete secundario. Esa zona puede no haber sonado.
6. **Anota la hora.** El panel muestra la hora UTC de la alerta debajo del letrero rojo.

### Antes de volver a la normalidad

1. **No pulses `CERRAR ALERTA` por reflejo.** Ese botón reabre el gas y devuelve los
   ascensores a servicio. Púlsalo cuando **una persona responsable** haya decidido que la
   emergencia terminó y que es seguro reabrir el gas.
2. **Revisa la sección de evidencia.** Debe estar subiendo o subida. Si dice
   `EVIDENCIA PERDIDA` o `ATASCADA`, avisa a soporte hoy: ese registro puede hacer falta para
   el seguro o para el dictamen.
3. **Recuerda el límite:** TAKAB da un dictamen operativo preliminar. **El reingreso al
   edificio no lo autoriza este sistema.** Lo autoriza una firma de ingeniería.

---

## 9 · Cada cuánto es "viejo" — tabla de referencia

Cuando el panel dice que algo es viejo, estos son los relojes que usa. Están aquí para que no
tengas que adivinar.

| Cosa | Se considera vieja a partir de | Dónde está |
|---|---|---|
| Un canal del sensor | **5 segundos** | `edge/takab_edge/local_api/__init__.py:61` |
| El autodiagnóstico de salud | **3 minutos** (se pone ámbar) | `edge/takab_edge/local_api/index.html:1224-1226` |
| Una evidencia sin subir teniendo nube | **1 hora** (pasa a `ATASCADA`, rojo) | `edge/takab_edge/backfill/__init__.py:54` |
| Un gabinete secundario por radio | **4 min 30 s** sin latido (`ENLACE PERDIDO`) | `edge/takab_edge/config/settings.py:165-167` |
| El catálogo de sismos del SSN | **48 horas** | `edge/takab_edge/catalog.py:57` |
| Que la consola central marque este sitio `SIN ENLACE` | **5 minutos** sin latido | `api/src/takab_api/settings.py:130-132` |
| Que TAKAB reciba una alarma de gabinete callado | **~10 minutos** | `infra/terraform/modules/observability/main.tf:179-202` |

---

## 10 · Huecos declarados

Lo que este manual **no puede prometerte hoy**, dicho con todas las letras. Un manual que
manda pulsar algo que no existe es peor que uno incompleto.

**H-1 · La evidencia pendiente puede no sobrevivir a un reinicio del gabinete.**
El sistema está diseñado para que sobreviva, pero el ajuste que lo garantiza
(`TAKAB_EDGE_CLOUD_SPOOL_DIR`) **no lo escribe hoy el script de instalación**
(`infra/scripts/provision_gateway.sh:132-133`; ficha abierta `T-2.67.b`,
`takab-docs/TASKS.md:4267-4281`). El panel te lo dice a la cara con
`COLA NO DURABLE · SE PIERDE AL REINICIAR`. **Mientras esa frase esté en pantalla, la
instrucción operativa es: no reinicies el gabinete.**

**H-2 · No hay un teléfono de soporte escrito en este manual.**
La cadena de guardia de TAKAB existe, pero **hoy el único canal que entrega de verdad es el
correo**, y el escalamiento por SMS está prometido y no construido
(`takab-docs/runbooks/RUNBOOK-ses-produccion-y-cadena-oncall.md:455-478`). Rellena a mano la
ficha del principio con un teléfono real. Sin ese dato, todas las veces que este manual dice
"avisa a soporte" son una instrucción incompleta.

**H-3 · La rama de hardware WR-1 → sirena no está verificada físicamente.**
Está diseñada y documentada (`takab-docs/runbooks/RUNBOOK-SPOF-02-ruta-hardware-sirena.md`),
pero su verificación depende de un gate de hardware todavía abierto (gate #3,
`takab-docs/PLAN-MAESTRO-TAKAB.md:79`). **No des por hecho que la sirena suena con el gabinete
muerto hasta que un técnico te enseñe el acta de esa prueba en este edificio.** Anota el
resultado en la ficha.

**H-4 · Botones físicos de silencio y de prueba: el software los soporta, pero no consta que
estén cableados.**
El código escucha dos botones físicos (`edge/takab_edge/config/settings.py:79-80`), pero la
asignación de pines está marcada como provisional hasta el gate #3, y la tabla de hardware
verificado del proyecto **no los lista**
(`takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:59-67`). **Este manual no te
manda pulsar un botón físico.** Si tu gabinete tiene uno, anótalo en la ficha y pide a soporte
que lo verifique.

**H-5 · El registro sísmico continuo de 14 días depende de un ajuste de instalación.**
La retención configurada son 14 días (`edge/takab_edge/config/settings.py:139-141`), pero
**no consta en el repositorio ningún sitio de producción donde se fije la ruta del disco**; sin
ella, el registro se guarda en un directorio temporal que se borra en cada arranque. Pide a
soporte que confirme por escrito, para este edificio, cuántos días de registro hay realmente.

**H-6 · Cuando algo falla, el panel nombra servicios técnicos que un operador no puede tocar.**
Frases como *"revisar takab-edge.service"* o *"revisar takab-gpio/takab-edge"* están dirigidas
al técnico. **Tu acción no es ejecutar nada: es copiar esa frase tal cual y dársela a soporte.**

**H-7 · Este manual no cubre la consola web ni la app móvil.**
Solo cubre el panel del gabinete y la operación en sitio. La única excepción es la tabla de
§6.0, que pone al lado la palabra que usa la consola para **cada estado que tú ves**: no está
ahí para enseñarte a usar la consola, sino porque **quien te contesta el teléfono está mirando
esa pantalla** y los dos tenéis que llamar igual a la misma cosa. El vocabulario de las dos
sale de un solo fichero (`shared/glossary/estados.json`) y lo vigilan sendos tests.

**H-8 · El reloj con batería del gabinete no está verificado en el código.**
La documentación de arquitectura dice que hay un reloj de tiempo real con batería (RTC DS3231)
que mantiene la hora sin internet, con una deriva de unos 0.17 s al día
(`takab-docs/BLUEPRINT-TECNICO-TAKAB.md:121`). **Esa cifra es de hoja de datos del fabricante,
no una medición de este proyecto**, y en el software no hay nada que lea ni configure ese
reloj: solo la lectura del sincronizador de hora
(`edge/takab_edge/health/__init__.py:193-196`). En la práctica esto solo importa para la hora
escrita en los registros después de un corte largo de internet; **no afecta a la sirena**. Pide
a soporte que confirme si este gabinete lleva el reloj instalado.

---

## 11 · Resumen de una página — imprime esto y pégalo

**Si suena la sirena:** protégete. El sistema ya actuó. No hay cuenta regresiva y no la habrá.

**Si el panel dice `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA`:** el edificio **sigue protegido**.
No reinicies nada. **Pero los avisos automáticos a los brigadistas NO están saliendo: avísalos
tú.**

**Si el panel dice `SIN CONEXIÓN CON EL GABINETE`:** es otra cosa y es peor. No sabes en qué
estado está el edificio. Ve al gabinete y llama a soporte.

**Si la fila `RELÉS` dice `NO CONTESTA`, `DETENIDO`, `AVERÍA` o `S/D`:** la sirena podría no
sonar. **Llama a soporte AHORA** y ten lista la alarma manual del edificio.

**Ámbar quiere decir "no lo sé".** No quiere decir "probablemente esté bien".

**`S/D` = no hay dato · `DATO RETENIDO` = el dato es viejo · `NO CONTESTA` = la pieza está
caída.** Tres cosas distintas, tres acciones distintas.

**`CERRAR ALERTA` reabre el gas.** Que lo decida una persona, no el reflejo.

---

*Este manual describe el comportamiento verificado en el código del sistema. Toda afirmación
lleva su referencia `archivo:línea`. Lo que no se pudo verificar está en la §10 como hueco
declarado, no como promesa.*
