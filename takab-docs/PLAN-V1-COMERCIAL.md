# Plan V1-COMERCIAL — de lo que hay a lo que se puede enseñar

> **De dónde sale.** De [`INFORME-V1-COMERCIAL.md`](INFORME-V1-COMERCIAL.md), la auditoría del
> **2026-09-02**. Cada ficha de aquí cierra uno o varios hallazgos numerados de allí.
>
> **Bloque de numeración: `T-5.xx`, y no colisiona con nada.** Verificado antes de escribirlo:
> `TASKS.md` no contiene ni una ocurrencia de `T-5.` ni de `T-6.`; los máximos vivos son
> `T-2.172`, `T-3.16` y `T-4.05`. Las 27 fichas van de `T-5.01` a `T-5.27` y se insertan también
> en `TASKS.md` como bloque propio, con la cabecera de conteo actualizada en el mismo commit.
>
> **Lo que este plan NO hace: duplicar fichas.** Ocho hallazgos del informe caen sobre tareas que
> **ya existen y están abiertas**. Esas no se re-fichan: se citan por su número en §4 y se dejan
> donde están. Abrir una ficha nueva para un trabajo ya fichado es cómo un backlog empieza a
> mentir sobre su propio tamaño.
>
> **Estimación en sesiones de Claude Code**, no en horas. Una sesión = un ciclo completo del
> método (`CLAUDE.md §6`): plan, tests primero, ejecución en bucle hasta verde, y PR.

---

## 1 · La ruta crítica hacia V1-DEMO **no es** la ruta crítica hacia el primer cliente

`TASKS.md §RUTA CRÍTICA` declara la ruta al primer cliente real, y sigue vigente:
`G-04 ∧ G-02 ∧ T-2.89 ∧ T-2.96 ∧ T-2.74 ∧ notificación real`. De esos seis, **el software
controla uno y medio**.

**La ruta a la primera exposición es otra, y esa sí es casi toda nuestra.** Una demo no necesita
que la sirena suene con el gabinete apagado; necesita **no afirmar que lo hace**. No necesita que
el SMS entregue; necesita **no prometerlo**. La diferencia entre las dos rutas es exactamente la
diferencia entre *acreditar* y *no mentir*, y solo la segunda se compra con capacidad de
desarrollo.

```
V1-DEMO  =  T-5.01 ∧ T-5.02 ∧ T-5.03 ∧ T-5.04 ∧ T-5.05
```

Cinco fichas, **las cinco `SOFTWARE`**, **cero humanos con agenda**. Es el hallazgo de
planificación de esta auditoría: lo que hoy impide enseñar el producto **no está bloqueado en
nadie**.

**Reparto honesto del resto.** De las 49 fichas abiertas o parciales que había antes de este
plan, 20 eran `SOFTWARE` puro y 29 tocaban a un humano o a un gate. De las **27 nuevas**, **23
son `SOFTWARE` puro**; de las otras cuatro, 2 llevan además una `DECISIÓN` de producto, 1 un
`GATE-HW` y 1 un `GATE-LEGAL`. El plan no alarga la cola de gates: la mueve entera al lado que sí avanza.

---

## 2 · Las tres tandas

### Tanda 1 — antes de la **primera** exposición · 9 fichas · 13 sesiones

Todo lo que hace que una pantalla afirme algo falso delante de un cliente, más el interruptor que
impide disparar algo real. **Ninguna espera a nadie.**

| Ficha | Qué cierra | Bloqueo | Sesiones |
|---|---|---|---|
| `T-5.01` | El modo demo del panel dispara actuadores reales | `SOFTWARE` | 1 |
| `T-5.02` | No existe modo demostración de sistema | `SOFTWARE` + `DECISIÓN` | 3 |
| `T-5.03` | El banner del SOC llama alerta sísmica a un botón de pánico | `SOFTWARE` | 1 |
| `T-5.04` | La landing vende capacidades no acreditadas | `SOFTWARE` | 1 |
| `T-5.05` | Un gabinete simulado se ve igual que uno real | `SOFTWARE` | 1 |
| `T-5.06` | El runbook de alta rompe la ingesta | `SOFTWARE` | 2 |
| `T-5.07` | El test del deslinde impreso no comprueba nada | `SOFTWARE` | 1 |
| `T-5.08` | El guion de demo sirve para CI, no para enseñar | `SOFTWARE` | 2 |
| `T-5.09` | Cabeceras que declaran un conteo sin test que lo cuente | `SOFTWARE` | 1 |

### Tanda 2 — antes de la **segunda** exposición · 8 fichas · 16 sesiones

Lo que el cliente pide en la primera reunión y hoy no existe.

| Ficha | Qué cierra | Bloqueo | Sesiones |
|---|---|---|---|
| `T-5.10` | No hay máquina de estados de procedencia del evento externo | `SOFTWARE` | 3 |
| `T-5.11` | La correlación con el catálogo es solo temporal | `SOFTWARE` | 1 |
| `T-5.12` | Los falsos positivos son incontables | `SOFTWARE` | 2 |
| `T-5.13` | No hay plantillas de simulacro | `SOFTWARE` | 2 |
| `T-5.14` | El post-simulacro no tiene tiempos ni sale del navegador | `SOFTWARE` | 2 |
| `T-5.15` | El tiempo de acuse no se calcula y los destinatarios no se leen | `SOFTWARE` | 2 |
| `T-5.16` | Umbrales por tipo de inmueble, con rollback | `SOFTWARE` + `DECISIÓN` | 3 |
| `T-5.17` | El sonido del simulacro no se elige ni queda auditado | `SOFTWARE` | 1 |

### Tanda 3 — antes del **primer contrato firmado** · 10 fichas · 12 sesiones

Lo que un cliente institucional revisa antes de firmar, y la higiene que hasta entonces no duele.

| Ficha | Qué cierra | Bloqueo | Sesiones |
|---|---|---|---|
| `T-5.18` | La IA no tiene tope de gasto | `SOFTWARE` | 1 |
| `T-5.19` | Ningún encargado declarado; falta la transferencia internacional | `GATE-LEGAL` + `SOFTWARE` | 1 |
| `T-5.20` | Firmar un dictamen no entra en la bitácora de auditoría | `SOFTWARE` | 1 |
| `T-5.21` | No hay censo de dato viejo en la app móvil | `SOFTWARE` | 2 |
| `T-5.22` | La latencia del reflejo solo existe como prosa | `SOFTWARE` + `GATE-HW` | 1 |
| `T-5.23` | No existe espectrograma en el dictamen técnico | `SOFTWARE` | 2 |
| `T-5.24` | El reloj y la pérdida de paquetes callan cuando deberían gritar | `SOFTWARE` | 1 |
| `T-5.25` | El silencio no alcanza a los gabinetes secundarios | `SOFTWARE` | 1 |
| `T-5.26` | La huella del PDF se imprime a la mitad; la ficha de estación está partida | `SOFTWARE` | 1 |
| `T-5.27` | Faltan dos guardas: catálogo fuera del veredicto, folio fuera del prompt | `SOFTWARE` | 1 |

**Total: 27 fichas · 41 sesiones.**

> **Los tres totales se rehacen, y por eso se dice cómo:** las fichas y las sesiones salen de
> sumar las columnas de las tres tablas de arriba; el reparto por etiqueta sale de contar el
> sufijo del encabezado de cada ficha en §5. Un total tecleado a mano acaba divergiendo —
> este ya divergió una vez mientras se escribía este documento.

---

## 3 · Por qué el corte está donde está

**La tanda 1 no es "lo urgente": es lo que impide enseñar el producto sin mentir.** Las cinco
primeras fichas son la ruta crítica de V1-DEMO. Las cuatro restantes son las que hacen que la
demo se pueda **repetir** y que el material impreso no se contradiga a sí mismo.

**La tanda 2 es lo que el cliente va a preguntar y hoy no tiene respuesta.** "¿De qué sismo fue?"
(`T-5.10`, `T-5.11`), "¿cuántas falsas alarmas tienen?" (`T-5.12`), "¿me deja el reporte del
macrosimulacro?" (`T-5.13`, `T-5.14`), "¿en cuánto acusan mis brigadistas?" (`T-5.15`), "mi
edificio es industrial, no un hospital" (`T-5.16`). Ninguna hace mentir a una pantalla hoy —
por eso no está en la tanda 1— pero cada una es un "no" en una reunión.

**La tanda 3 es lo que se revisa antes de firmar**, más la higiene de superficies que hoy dicen
"bien" cuando quieren decir "no sé". `T-5.18` tiene una precedencia dura y conviene no perderla:
**el tope de gasto tiene que existir antes de encender la IA**, no después, porque lo único que
hoy acota el riesgo es que la perilla está apagada.

---

## 4 · Hallazgos que NO llevan ficha nueva

Ocho hallazgos del informe caen sobre trabajo **ya fichado y abierto**. Se dejan donde están.

| Hallazgo | Ficha existente | Nota |
|---|---|---|
| **H-05** · Si el gabinete muere, la sirena calla | `G-02` en `T-2.92`; decidido en `D-10`, compra sin fecha por `D-16` | `FÍSICO`. Sigue en la ruta crítica al primer cliente, no a la demo. |
| **H-08** · Publicar umbral firmado a hardware nunca se hizo | `G-05` en `T-2.93` | `FÍSICO`. `T-5.16` le entrega el insumo de software; el gate se cierra aparte. |
| **H-09** · SMS, WhatsApp y push no entregan | `T-2.76.a`, `T-2.77.a`, `T-2.97` | Altas administrativas. `PENDIENTES-MAURICIO §4`. |
| **H-11** · Catálogo congelado | `T-2.149` (bloqueada) y `T-2.66.b` (decisión abierta) | La parte nueva —que la magnitud **nunca se escribe**— sí entra, dentro de `T-5.10`. |
| **H-12** · Onda cruda y espectro inalcanzables en producción | `T-3.11.c` | El worker de backfill no está en el compose. `PENDIENTES §2.11`. |
| **H-13** · Sin tiempo de recuperación medido | `T-2.72.a` y `T-2.74` (`G-09`) | Ventana AWS. |
| **H-14** · Uso comercial del catálogo del SSN | segundo bloqueo de `T-2.149`; `T-2.96` | `LEGAL`, gobernado por `D-20`. |
| **H-23** · El fail-open del modo prueba grita por paquete | `T-2.172` | Sigue viva, verificada línea por línea en esta auditoría. |
| **F4** · Shadow-mode de la IA | `T-3.01`, `T-3.02` | La auditoría añade el detalle de **dónde está la costura** y de que la razón del desacuerdo ya se calcula y se tira. |

---

## 5 · Las fichas

Formato exacto de `TASKS.md`. Se insertan al final de ese archivo como **Fase 5.0**.

## Fase 5.0 · V1-DEMO — que nada de lo que se enseña afirme lo que no se acreditó

> **De dónde sale esta fase.** De la auditoría del **2026-09-02**
> ([`INFORME-V1-COMERCIAL.md`](INFORME-V1-COMERCIAL.md), plan en
> [`PLAN-V1-COMERCIAL.md`](PLAN-V1-COMERCIAL.md)). 52 ítems auditados: 10 verdes, 23 amarillos,
> 19 rojos.
>
> **Qué NO es esta fase.** No es "terminar el producto". Es el conjunto mínimo para que TAKAB
> Ailert se pueda **enseñar y vender** sin que una pantalla afirme algo que nadie acreditó. La
> ruta al primer cliente sigue siendo la de §"RUTA CRÍTICA", y sigue estando en manos de humanos
> con agenda. **Esta no**: de sus 27 fichas, 23 son `SOFTWARE` puro.
>
> **La ruta crítica de V1-DEMO son cinco fichas** —`T-5.01`, `T-5.02`, `T-5.03`, `T-5.04`,
> `T-5.05`— y **ninguna espera a nadie**. Es la diferencia entre *acreditar* y *no mentir*: una
> demo no necesita que la sirena suene con el gabinete apagado, necesita **no afirmar que lo
> hace**.

### [x] T-5.01 · En modo demo los botones **mandan órdenes de verdad** — `SOFTWARE` · **CERRADA 2026-09-02**
> **Verificado abriendo el archivo, no leyendo una ficha.** `edge/takab_edge/local_api/index.html`
> — `doAction()` ejecuta `fetch(endpoint, {method:'POST', headers})` **sin comprobar `DEMO`**. El
> único `if (!DEMO)` del flujo se salta el refetch de estado, nada más. Y `renderActions()` pinta
> `PROBAR ACTUADORES` —cuyo propio subtítulo dice *"sostiene sirena+estrobo · pulso en gas,
> ascensores, puertas"*— **incondicionalmente**, además de decidir **qué** botones aparecen a
> partir del estado FALSO de la escena: con `?demo=alerta` salen `SILENCIAR AUDIBLES` y
> `CERRAR ALERTA` porque la escena sintética dice que la sirena suena.
>
> Mientras tanto, arriba, la cinta afirma `DEMO · NO ES ESTADO REAL`.
>
> **Es la familia de defecto que este proyecto ya conoce** —una superficie que dice "bien" cuando
> quiere decir "no sé"— pero llevada un paso más lejos: aquí la superficie dice *"nada de lo que
> ves es real"* al lado de un botón que sí lo es. El servidor tampoco defiende: `?demo=` es un
> parámetro del navegador y los handlers no saben de él.
>
> **Y es el escenario exacto de una exposición comercial**, que es lo que lo pone el primero de
> la lista.
- **Componente:** edge (panel LAN) · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que con `?demo=` puesto ninguna acción alcance al gabinete, y que la pantalla lo
  diga en el propio botón en vez de solo en la cinta.
- **Criterios de aceptación:**
  - [x] `doAction()` se niega con `DEMO` puesto: no emite `fetch`, y el mensaje de la caja del PIN
        dice por qué (algo como `MODO DEMO · LAS ÓRDENES ESTÁN INHIBIDAS`).
  - [x] `renderActions()` **no pinta** botones de actuación en demo, o los pinta visiblemente
        inertes. La decisión de cuál de las dos se toma en la ficha, se escribe con su razón.
  - [x] Un test que **cuente peticiones**, no que lea prosa: con cada escena de demo, pulsar cada
        botón produce **cero** `fetch` a `api/*`. Que el conteo esperado sea cero se declara en
        voz alta para que el test no pueda pasar por vacuidad.
  - [x] El test cubre las cinco acciones alcanzables desde una escena de demo, enumeradas
        **derivándolas de `renderActions`**, no a mano.
  - [x] Sin `?demo=` nada cambia: los mismos botones siguen mandando sus mismas órdenes (guarda
        anti-prohibir-de-más).
- **Cómo se cerró (2026-09-02).** **Decisión: se PINTAN, inertes** — no se esconden. La razón:
  `?demo=` existe para enseñar cómo se ve el panel en estados que no se pueden reproducir a
  voluntad, y un panel sin sus botones no se parece al real; esconderlos sería mentir en la otra
  dirección. La honestidad es que sigan ahí, con borde discontinuo y el subtítulo
  `INERTE EN DEMO`, y que la orden no salga.
  **Lo que midieron los tests al escribirlos primero, y agranda el hallazgo de la auditoría:**
  el defecto no era un camino teórico — **las doce escenas de demo mandaban entre 2 y 4 órdenes
  reales cada una** al gabinete que las pintaba.
  **Y lo que apareció al arreglarlo:** `doAction` es el **único** camino del panel que hace
  `POST`, en unas 2 400 líneas. Eso convierte la guarda en estructural en vez de disciplinaria,
  y hay un test que lo exige por conteo: un segundo `POST` en otro sitio la esquivaría y sale
  rojo con su número de línea.

### [x] T-5.02 · **Modo demostración de sistema** — `SOFTWARE` + `DECISIÓN` · **CERRADA 2026-09-02**
> Hoy no existe. Nada bloquea push, SMS, WhatsApp, correo, comandos firmados ni apertura de
> incidentes, y ninguna pantalla del SOC ni de la app lo declararía si existiera. Lo que hay son
> tres cosas parciales que no lo son: el `?demo=` del panel (que es un reproductor de escenas —
> ver `T-5.01`), el modo demo del SOC que **se retiró a propósito**
> (`web/src/styles/soc.css:787`: *"una consola de operación real no lleva controles de
> demostración"*, y la razón sigue siendo buena), y el estado `simulated` de notificaciones, que
> es **derivado de la ausencia de credenciales** y por tanto **desaparece justo en el entorno
> donde se haría la demo**.
>
> **Sin esto, cada exposición es un riesgo de disparar algo real o de enseñar datos falsos sin
> etiquetar.** Con las credenciales de notificación puestas —que es lo que se busca— el riesgo
> deja de ser teórico.
>
> **Lo que hay que decidir antes de construir**, y por eso la ficha lleva `DECISIÓN`: (a) el
> alcance del modo, ¿por tenant, por sesión o por despliegue?; (b) quién puede encenderlo y
> apagarlo; (c) si un incidente **real** que entra con el modo puesto lo apaga solo —que es la
> lectura coherente con *"lo real gana"* de los simulacros— o si el modo lo impide y grita.
- **Componente:** api + web + mobile + edge · **Depende de:** T-5.01 · **Prioridad: MÁXIMA**
- **Objetivo:** un estado explícito, visible y auditado, en el que el sistema no despierta a
  nadie, no cierra un relé y lo anuncia en las tres superficies.
- **Criterios de aceptación:**
  - [x] Decisión escrita en `DECISIONES-MAURICIO.md` **con su razón** antes de la primera línea de
        código, cubriendo los tres puntos de arriba.
  - [x] Con el modo activo: cero entregas por cualquier canal, cero comandos firmados emitidos,
        cero relés movidos. Cada intento **deja fila en `audit_log`** con el motivo — un modo que
        bloquea en silencio es otra superficie muda.
  - [x] Las tres superficies lo declaran de forma inconfundible y **distinta del simulacro**: el
        ámbar ya significa "simulacro sonando" y los dos no pueden confundirse.
  - [x] Encender y apagar el modo queda auditado con actor y hora.
  - [x] El bloqueo se **deriva** del registro de proveedores y de la superficie única de comandos,
        no de una lista de canales escrita a mano — un canal nuevo tiene que quedar bloqueado
        solo.
  - [x] Test de no-vacuidad: con el modo apagado, los mismos escenarios sí entregan y sí comandan.
- **Cómo se cerró (2026-09-02), y DOS criterios cambiaron al construirlos.** Las tres decisiones
  están en [`D-27`](DECISIONES-MAURICIO.md#d-27), escritas antes de la primera línea de código:
  **por cliente y con vencimiento** (máx. 8 h, el techo en el CHECK de la tabla y no en el
  código); **lo enciende el dueño de la plataforma, lo apaga él o el administrador del cliente**
  —asimétrico: difícil de volver inseguro, fácil de volver seguro—; y **lo real lo apaga**, con la
  lectura contraria rechazada sin discusión: un modo capaz de suprimir una alerta real no es un
  dispositivo de seguridad.
- **Lo que cambió (1): «cero entregas por cualquier canal» era más ancho de lo que puede ser.**
  Lo destapó un test. Como *cualquier* incidente apaga el modo antes de planificar sus avisos, el
  modo **no puede suprimir la cascada de un incidente nuevo** — y eso es correcto, no una
  limitación: si pudiera, un quórum de pánico de ocupantes reales quedaría callado. Lo que el modo
  sí suprime, y era lo importante, son los **comandos firmados** (simulacros, prueba de actuadores,
  actuación por quórum): los actos del que demuestra. La puerta de notificación se queda como
  **respaldo que no debería dispararse nunca**, y se refuerza con la otra mitad que ese mismo test
  obligó a escribir: **con un incidente abierto no se entra en el modo**. Con las dos reglas
  juntas, el modo y un evento vivo **no pueden coexistir**.
- **Lo que cambió (2): son DOS superficies, no tres, y el panel queda fuera a propósito.** La
  consola y la app lo declaran. El panel del gabinete **no**, y la razón está en `D-27`: meterlo
  exigiría que el modo viajara al gabinete, y cada dato nuevo que viaja hacia allí es superficie
  nueva hacia el camino de vida — que es justo lo que este modo no puede tocar. Además está
  medido: el seed de producción deja el conjunto de reglas sin clave `edge`, así que hoy el config
  sync no empuja nada al gabinete real; construirlo sería entorno preparado para un mensaje que
  nadie recibe. El panel no promete entrega de notificaciones: su silencio no es una mentira.
- **El bloqueo es derivado de verdad:** la puerta de notificación va **antes** de preguntar por el
  proveedor, así que ni siquiera consulta el registro — cubre hasta un canal sin proveedor
  cableado, y un canal sexto queda bloqueado el día que nazca. La de comandos vive en el embudo
  único que firma, así que simulacros y quórum la heredan sin duplicar la superficie sensible.
- **Y el color no es un detalle:** cian con borde discontinuo, **no ámbar**. En esa consola el
  ámbar ya significa «simulacro en curso» y «dato retenido», y un tercer significado en el mismo
  color vacía los tres. El discontinuo es el idioma compartido de las tres fichas de demostración
  —`T-5.01` (botones inertes), `T-5.02` y `T-5.05` (datos de demo)—: «esto no es real».

### [x] T-5.03 · El banner del SOC llama **alerta sísmica** a un botón de pánico — `SOFTWARE` · **CERRADA 2026-09-02**
> `web/src/features/console/ConsolePage.tsx:129` elige el incidente a destacar **solo por
> `severity === "critical"`**, y `AlertBanner.tsx` lleva **dos** textos escritos a fuego:
> `ALERTA SÍSMICA · PROTÉJASE` (`:23`) y `EDGE · RS4D · REGLAS LOCALES EJECUTADAS · ● AUTO`
> (`:39-41`). **Ninguno mira el `trigger`.**
>
> Ante un quórum de pánico —que abre incidente `trigger='manual'` con severidad crítica por
> `D-11`— el SOC afirma dos cosas falsas a la vez: que hubo una alerta sísmica, y que la ejecutó
> el sensor. La app móvil, para **el mismo incidente**, pinta `NO ES UNA ALERTA SÍSMICA`
> (`mobile/src/features/alarm/BuildingAlarmView.tsx:66`) y el push dice `ALARMA DEL INMUEBLE`.
> Lo mismo ocurre con el umbral instrumental, que la política de solo-aviso degradó y que el SOC
> sigue pintando como alerta porque su tier mapea a severidad crítica.
>
> **Es el defecto que ya se corrigió en móvil, reintroducido en el SOC**, y la lección de
> entonces vuelve a aplicar tal cual: *un componente presentacional puede llevar una mentira a
> fuego que ninguna prueba de la lógica alcanza*. La corrección de móvil vive en
> `mobile/src/features/alert/source.ts` y es el modelo a copiar: el titular **se deriva** de la
> fuente.
- **Componente:** web · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que el titular y la atribución del banner salgan del `trigger`, y que ninguna
  superficie pueda volver a divergir sin que un test lo diga.
- **Criterios de aceptación:**
  - [x] El titular y la línea de atribución se derivan del `trigger` del incidente, con las cuatro
        fuentes cubiertas por igualdad (no un `default` que absorba lo desconocido).
  - [x] Un `trigger` nuevo que nadie mapeó **no cae a "alerta sísmica"**: sale rotulado como
        desconocido y el build lo nombra.
  - [x] **Un test cross-superficie**: para cada `trigger`, el titular del SOC, el de la app y el
        del panel del gabinete son coherentes entre sí. Es el test que hoy no existe y que habría
        cazado esto.
  - [x] El glosario compartido de estados **incorpora el móvil** —hoy solo cubre panel y consola—
        y el eje de titulares de alerta, no solo el vocabulario de estado.
  - [x] La divergencia ya declarada en el glosario (`DATO RETENIDO` / `DATOS RETENIDOS`) se cierra
        o se re-declara con su razón.
- **Cómo se cerró (2026-09-02).** El titular y la atribución salen de
  `web/src/features/console/alertHeadline.ts`, espejo consciente del módulo del móvil, y los
  literales viven en `shared/glossary/estados.json` → `titulares_de_alerta`, con las tres
  superficies. El censo cruzado de `edge/tests/test_glosario_de_estados.py` ata ese eje al
  **CHECK de `incidents.trigger` por IGUALDAD**: el quinto trigger que alguien añada sale rojo
  con su nombre hasta que se decida cómo se llama en las tres pantallas. Se saboteó a propósito
  para comprobar que no pasa por vacuidad.
  **Tres cosas aparecieron al hacerlo.** (1) La prueba del invariante estaba escrita ALREDEDOR
  del defecto: su fixture traía `trigger: "local_threshold"` y aun así esperaba «PROTÉJASE»; se
  le puso el trigger que le corresponde y se conservó el nombre del test, que es el ancla de
  `INV-magnitud.a` en la matriz. (2) **El móvil tenía la misma grieta en su caso por defecto** —
  un trigger no mapeado titulaba «ALERTA SÍSMICA»—, corregida en las dos superficies.
  (3) **La divergencia se RE-DECLARA, no se cierra, y se encareció mientras estaba declarada:**
  donde T-2.137 midió diez aserciones en ocho ficheros, hoy son **veinticuatro en doce**. Sigue
  siendo un lote propio, y ahora se sabe que es más grande. Su `arreglo` ya no lista los ficheros:
  manda re-derivarlos, porque la lista anterior nació desactualizada.

### [x] T-5.04 · El perímetro de claims de la landing cubre **cifras**, no **capacidades** — `SOFTWARE` · **CERRADA 2026-09-02**
> `landing/tests/contenido.test.mjs:58` defiende un perímetro real y bien pensado: prohíbe cifras
> medidas y prohíbe citar normas. **No prohíbe afirmar una capacidad que nadie acreditó**, y por
> eso pasó en verde lo siguiente, hoy publicado:
>
> - *"acciona sirena, estrobo, **gas, ascensores y puertas** del inmueble"* — ningún gabinete
>   tiene esos tres canales cableados; el gabinete de referencia reporta **dos** relés. El
>   controlador que los haría está en la lista de materiales marcado **"Opcional"**, y
>   `ENTREGA-Y-ACEPTACION-TAKAB.md:214` dice que su driver es *"un extra no acreditado con
>   equipo"*.
> - *"**respaldo de energía**"* entre lo que se instala — el gabinete vivo reporta
>   `ups_status: "unknown"` y `battery_pct: null`.
>
> **Es exactamente el fallo que el propio repositorio ya cazó una vez** —el checklist de gas y
> puertas en verde sin gas ni puertas— reaparecido en la superficie más pública que tiene el
> proyecto. La landing es por lo demás notablemente honesta (su columna "No hace" es mejor que la
> de casi cualquier competidor), y eso hace más fácil, no más difícil, corregir la otra columna.
- **Componente:** landing · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que el sitio público no afirme en presente una capacidad cuyo gate está abierto,
  y que un test lo impida en adelante.
- **Criterios de aceptación:**
  - [x] Las dos afirmaciones se reformulan sin perder la venta: el alcance de diseño se dice como
        alcance de diseño y la acreditación por inmueble se dice como tal. La columna "No hace"
        **no se toca**: ya es correcta.
  - [x] El perímetro del test gana una regla de **capacidades**: una lista de afirmaciones que
        exigen un gate cerrado, **derivada** del censo de gates de
        `MATRIZ-REQUISITO-TEST.md`, no tecleada. Con el gate abierto, la afirmación en presente
        pone el test en rojo.
  - [x] La regla nombra el gate concreto en el mensaje de fallo, para que quien la dispare sepa
        qué haría falta para poder decirlo.
  - [x] Guarda anti-prohibir-de-más: las afirmaciones que **sí** están acreditadas (operar sin
        internet, evidencia inmutable, aislamiento entre clientes, sin cuenta atrás) siguen
        pasando.
- **Cómo se cerró (2026-09-02).** El perímetro gana **una regla de capacidades derivada del
  registro §10 del runbook de auditoría** — que es donde los gates se marcan presencialmente— y
  no de una lista de gates tecleada: `Object.keys(CAPACIDADES_GATEADAS)` se compara **por
  igualdad** contra los diez del registro, así que un gate nuevo obliga a decidir qué
  afirmaciones dependen de él antes de poder seguir. Lo editorial —qué frase cuelga de qué
  gate— va escrito con su nombre; lo que no puede quedar a juicio es **olvidarse** de un gate.
  **Detalle que costó una corrida:** el registro tiene una fila (`G-01`) con **una columna
  menos** que las otras nueve, así que el parseo va por CONTENIDO y no por posición — un índice
  fijo daría «abierto» a un gate acreditado, y equivocarse en esa dirección es lo caro.
  **Y una corrección al propio informe:** «respaldo de energía» **se queda**. Está en la lista de
  materiales y es lo que se instala; lo que faltaba no era quitarlo sino decir que también se
  acredita en el inmueble, y ahora lo dice.

### [x] T-5.05 · Un gabinete **simulado** se ve igual que uno real — `SOFTWARE` · **CERRADA 2026-09-02**
> La separación entre lo simulado y lo real vive en el seed (`db/seeds/sim_fleet.sql`, con su
> aviso en mayúsculas de que jamás se aplica al entorno desplegado) y en el despliegue
> (`deploy/cloud/deploy.sh` solo siembra el de producción). **No vive en la pantalla**, que es
> justo donde se hace la demo.
>
> No hay columna que marque lo simulado ni marca visual en el mapa ni en la flota: lo único que
> delata a un sitio sim es que se llama *"Sitio Sim 001 Puebla"*. Misma píldora de estado, mismo
> medidor de respaldo, mismo color. En `make soc-local` un prospecto ve 21 sitios y 5 gabinetes
> con idéntico aspecto, de los cuales **20 y 4 no existen**.
>
> **El patrón visual ya está resuelto en el otro extremo del sistema:** el panel del gabinete
> pinta su cinta `DEMO · NO ES ESTADO REAL` y el manual de operación advierte de no dejar un
> monitor de pared así. La consola no tiene equivalente.
- **Componente:** web + api · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que un sitio o gabinete de demostración sea inconfundible en el mapa y en la
  flota, sin ensuciar la consola de producción.
- **Criterios de aceptación:**
  - [x] La marca se **deriva** de un hecho del dato (prefijo del código/serial, o columna
        explícita), decidido y escrito en la ficha con su razón. Si es columna, migración
        idempotente y con dueño correcto.
  - [x] El mapa y la ficha de flota rotulan lo simulado de forma legible a distancia, y el rótulo
        **no se confunde** con el ámbar de simulacro ni con el de dato viejo.
  - [x] Test: con la flota mixta, todo lo sim sale marcado y **nada real sale marcado** — las dos
        mitades, comparadas por igualdad.
  - [x] Con cero sitios sim (el caso de producción) la interfaz es idéntica a hoy: la marca no
        reserva espacio ni cambia el diseño.
- **Cómo se cerró (2026-09-02).** **Decisión: la marca se deriva del PREFIJO del código/serial,
  no de una columna nueva.** La razón: la convención ya existe, está documentada en la cabecera
  del propio seed y ya la defiende un test; una columna sería una **segunda verdad** sobre el
  mismo hecho, y las dos podrían divergir. Los patrones van **anclados** (`^site-sim-\d+$`) a
  propósito: un `includes("sim")` marcaría de demostración un edificio real llamado
  `site-simon-01`, y equivocarse en esa dirección —rotular de demo un inmueble con gente
  dentro— es peor que no rotular nada. Hay un test para ese caso exacto.
  **Lo que hizo falta en el servidor:** el contrato del mapa no publicaba el código, solo el
  nombre, así que la consola no tenía con qué distinguir. Ahora publica `code` —un **hecho**—
  y no un `demo: bool`: decidir qué se rotula es de la presentación, y meter la política del
  seed en el contrato la duplicaría.
  **El color, que no es un detalle:** el rótulo va **gris con borde discontinuo, no ámbar**. En
  esta consola el ámbar ya significa «simulacro en curso» y «dato retenido»; un tercer
  significado en el mismo color vacía los tres. El discontinuo es el mismo lenguaje que
  `T-5.01` le dio a los botones inertes del panel: «esto no es real».

### [ ] T-5.06 · El runbook de alta de estación **rompe la ingesta** — `SOFTWARE`
> `RUNBOOK-ALTA-DE-ESTACION.md:122-124` manda escribir en el archivo de entorno del gabinete:
> `TAKAB_EDGE_TENANT_ID=<uuid del tenant>`, `TAKAB_EDGE_SITE_ID=<uuid del sitio>`,
> `TAKAB_EDGE_GATEWAY_ID=<uuid del gateway>`.
>
> **La ingesta espera lo contrario, y lo dice en su propia cabecera**
> (`api/src/takab_api/ingest/handlers.py:9-13`): los identificadores que viajan en el payload son
> los **códigos y seriales legibles**, no UUIDs. Y `:126` rechaza el resto:
> `gateway mismatch: payload=… registro=…` → la cola de descarte.
>
> **Y lo peor del paso:** `infra/scripts/provision_gateway.sh:163` ya había escrito el valor
> correcto (el nombre del dispositivo). El runbook, en el paso siguiente, manda **sobrescribirlo**.
> Resultado: una estación aprovisionada, con su certificado, conectada por mTLS — y **muda en la
> nube**, sin que ninguna pantalla explique por qué.
>
> **Hay seis divergencias más**, todas del mismo origen (el runbook lleva desde el 2026-07-30 sin
> tocarse mientras el contrato de alta cambió tres veces): manda un campo que hoy da 422;
> documenta como inexistentes el alta de clientes y los permisos de visibilidad, que llevan meses
> en producción; **omite el paso de instalar el software del edge** y el de publicar la versión;
> omite el equipamiento del sitio, con lo que la consola pinta cinco actuadores en un gabinete que
> tiene dos; y omite el conjunto de reglas, con lo que la estación nueva nunca entra al
> sincronizado firmado.
- **Componente:** takab-docs + api (tests) · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que el runbook vuelva a describir lo que hace el código, y que dejar de hacerlo
  ponga el build en rojo.
- **Criterios de aceptación:**
  - [ ] Las siete divergencias corregidas, cada una citando el archivo y la línea del código que
        manda.
  - [ ] Añadidos los pasos que faltan: instalación del software del edge, publicación de la
        versión, equipamiento explícito del sitio y conjunto de reglas con la clave del edge.
  - [ ] **Un test que ancle el runbook al código**, no a otra prosa: las variables de identidad
        que el runbook manda escribir se comparan contra las que el aprovisionador escribe y
        contra las que la ingesta acepta. Si las tres dejan de coincidir, rojo con las tres
        citadas.
  - [ ] El test cubre también el cuerpo del alta de gabinete: un campo que el esquema prohíbe y el
        runbook manda, sale nombrado.
  - [ ] Nota en el runbook sobre por qué el aprovisionador ya lo deja bien y no hay que tocarlo.

### [ ] T-5.07 · El test del **deslinde impreso** no comprueba nada — `SOFTWARE`
> `api/tests/dictamen/test_pdf.py:190-195`, entero:
>
>     assert DISCLAIMER.startswith("Dictamen operativo PRELIMINAR")
>     for variant in ("technical", "executive"):
>         assert render(model(), variant).startswith(b"%PDF")
>
> Comprueba (a) que una constante empiece por una cadena y (b) que el archivo sea un PDF.
> **Borrar la llamada que imprime el deslinde dejaría el test en verde.** Y lo mismo vale para los
> otros cinco avisos del documento —el de intensidad macrosísmica, el de sin calibración, el de la
> envolvente, el del centroide y el del croquis—: ninguno tiene una prueba que verifique su
> presencia en el documento.
>
> **El deslinde impreso es lo que protege al proyecto en una reunión comercial**, y es la única
> pieza del PDF cuya desaparición nadie notaría hasta que hiciera falta.
>
> **El propio repositorio ya sabe hacerlo bien:**
> `api/tests/dictamen/test_compliance_section.py::test_las_etiquetas_cambian_los_BYTES_del_pdf`
> es exactamente el patrón que falta aquí.
- **Componente:** api (tests) · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que quitar un deslinde del documento ponga la suite en rojo nombrándolo.
- **Criterios de aceptación:**
  - [ ] Los seis avisos se verifican **sobre el documento generado**, no sobre la constante.
  - [ ] La lista de avisos a verificar se **deriva** del módulo que los declara, no se teclea: uno
        nuevo entra solo al censo.
  - [ ] Guarda de no-vacuidad: el test declara en voz alta cuántos avisos espera, y cero no es un
        número aceptable.
  - [ ] Cada aviso se comprueba en la variante o variantes donde debe salir, y se comprueba que
        **no** sale donde no debe (el aviso de asistencia automatizada, sin prosa generada).

### [ ] T-5.08 · El guion de demo sirve para CI, **no para enseñar** — `SOFTWARE`
> `demo/` es sólido en lo que hace: se levanta desde cero con dos comandos, monta tres
> supervisores reales, el consumidor real y el motor de incidentes real, y está **bien aislado de
> producción** con tres guardias que se defienden solos (host real de la conexión, exclusividad de
> la base, y un seed que declara que jamás se aplica a la nube).
>
> Pero está construido para **acreditar criterios**, no para contar una historia: imprime marcas
> de verificación en terminal, trunca entre escenas y sale con código de error. Y le faltan tres
> cosas para una exposición: **no ejercita simulacros** (cero coincidencias de la palabra en todo
> `demo/*.py`), **no rotula los datos como simulados** —al contrario, el modo interactivo usa la
> identidad de desarrollo a propósito para que *"la consola local se vea igual que la
> desplegada"*—, y el aislamiento de notificaciones es **implícito**: descansa en que el script no
> lanza el worker, no en un interruptor.
- **Componente:** demo · **Depende de:** T-5.02, T-5.05 · **Prioridad: ALTA**
- **Objetivo:** un guion recorrible de principio a fin delante de un cliente, con los datos
  etiquetados y sin posibilidad de tocar nada real.
- **Criterios de aceptación:**
  - [ ] Escena de **simulacro** completa: agenda, armado, disparo humano, acuse por sitio y
        reporte, en las tres superficies.
  - [ ] El guion corre con el modo demostración de `T-5.02` puesto, y **falla ruidosamente** si no
        lo está.
  - [ ] Los datos del guion usan la identidad simulada y la marca visual de `T-5.05`.
  - [ ] Un documento corto de recorrido —qué se enseña, en qué orden, qué NO se toca— que cite
        las frases de `INFORME-V1-COMERCIAL.md §3`.
  - [ ] El aislamiento de notificaciones deja de ser implícito: se **impone**, y hay un test que
        lo comprueba.

### [ ] T-5.09 · Cabeceras que declaran un conteo **sin test que lo cuente** — `SOFTWARE`
> `TASKS.md` tiene el suyo desde T-2.61, y por eso su cabecera es fiable. Los otros dos censos del
> proyecto no lo tienen, y **los dos ya divergieron**:
>
> - `DECISIONES-MAURICIO.md:15` declara **23 decisiones** y última actualización **2026-08-22**.
>   El archivo tiene **26** y la última es del **2026-08-30**. Tres decisiones son invisibles para
>   quien lea la cabecera — y la bitácora existe precisamente para poder revocar con conocimiento.
> - `TRASPASO-SESION.md §0` abre con un bloque en negrita que fija la deriva de despliegue en
>   **"tres commits"** sobre un commit que hoy está **103 por detrás** de `main`. La deriva real es
>   de 13 (nube) y 25 (gabinete). Es el archivo que se manda leer al empezar una sesión.
>
> Ninguno de los 28 tests de consistencia documental los mira. **Es la doctrina que el propio
> repositorio predica, sin aplicar a dos de sus tres censos:** *un censo que enumera a mano acaba
> divergiendo*.
- **Componente:** api (tests) + takab-docs · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que ninguna cabecera de un documento de gobierno pueda declarar un número que el
  archivo desmiente.
- **Criterios de aceptación:**
  - [ ] Test que cuenta las decisiones de la bitácora (filas del índice y anclas de sección, que
        además tienen que coincidir entre sí) y exige que cuadren con su cabecera.
  - [ ] Test que comprueba que la fecha de última actualización declarada **no es anterior** a la
        fecha de la última decisión del archivo.
  - [ ] El bloque de deriva de despliegue del traspaso deja de fijar un número: **se le pregunta
        al sistema** (o se declara con la fecha de la medición y un test que exija que el commit
        citado exista y esté a la distancia declarada).
  - [ ] Las dos cabeceras corregidas en el mismo commit que sus tests.
  - [ ] El mensaje de fallo dice **cómo** rehacer el conteo, como ya hace el de `TASKS.md`.

### [ ] T-5.10 · **Procedencia del evento externo**: cinco estados, tres superficies — `SOFTWARE`
> Hoy no existe ninguna máquina de estados de procedencia. Lo que hay son dos enumeraciones de
> presentación (`EpicenterKind`, la banda de magnitud) y un campo `source` con tres valores
> efectivos. Y `reference_earthquakes` no lleva **ni hora de consulta, ni bandera de
> preliminar/revisado, ni identificador estable del proveedor**: solo una clave que nos inventamos
> nosotros, la fuente y una cita textual libre.
>
> Peor: `seismic_events.magnitude` **nunca se escribe con un valor**. El único INSERT del sistema
> pone `NULL` literal, así que la rama del catálogo en la consola es **inalcanzable en
> producción** y el SOC siempre ve "sin catálogo". El enriquecimiento post-hoc que documenta el
> esquema **no existe como código**.
>
> **El estado que más falta es el de sin correlación**, y no es un adorno: su ausencia convierte
> un "no sé" en una pantalla vacía que el operador lee como "no pasó nada".
>
> **Esto no roza el invariante de la cuenta atrás, lo cumple.** Lo que aquel prohíbe es una cifra
> **derivada por nosotros** del contacto seco. Una cifra de fuente externa citada, con su hora de
> consulta y su estado, es literalmente lo que el invariante contempla como *"fuente nueva y
> citable"*. La regla que esta ficha impone es: **con procedencia, o no se pinta**.
- **Componente:** api + web + mobile + edge · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que toda cifra sísmica que no midió nuestro instrumento se pinte con su fuente, su
  hora de consulta y su estado de confirmación — o no se pinte.
- **Criterios de aceptación:**
  - [ ] Cinco estados en el contrato compartido, **con el mismo nombre en las tres superficies**:
        sin dato externo, consultando, preliminar, confirmado, sin correlación.
  - [ ] El texto de la consulta dice **"consultando"**, nunca *"estimando"*: nosotros no
        estimamos, preguntamos. Anclado por test.
  - [ ] `reference_earthquakes` gana hora de consulta, estado de revisión e identificador del
        proveedor; migración idempotente, con el dueño correcto.
  - [ ] Ninguna superficie pinta magnitud, epicentro, profundidad u hora de origen **sin** su
        fuente y su hora de consulta al lado. Test por superficie que lo verifique sobre el árbol
        renderizado.
  - [ ] El estado de sin correlación **se pinta**: hay un texto para él y un test que lo exige.
  - [ ] Se declara qué pasa hoy con la magnitud que nunca se escribe: o se escribe con su
        procedencia, o el campo se retira y la interfaz deja de tener una rama inalcanzable.

### [ ] T-5.11 · La correlación con el catálogo es **solo temporal** — `SOFTWARE`
> `api/src/takab_api/forensics/__init__.py:52` fija `CATALOG_WINDOW_S = 120.0` y la consulta toma
> el evento más cercano en el tiempo dentro de esa ventana. **No hay distancia máxima. No hay
> magnitud mínima. No hay filtro geográfico.** La distancia se calcula **después** del acierto,
> solo para describirlo, y nunca para rechazar. En la ruta del receptor —que es la normal— no hay
> epicentro propio que comparar, y el PDF imprime *"sin epicentro propio que comparar"*.
>
> Hoy el riesgo está acotado por accidente: son 13 filas mexicanas de 1985 a 2022. **Con el feed
> vivo de `T-2.149` se vuelve grave**: un sismo de cualquier parte del mundo ocurrido dentro de
> ±120 s del contacto se imprimirá en un dictamen firmado bajo el rótulo *"contraste con
> catálogo"*, con su magnitud y su lugar. Y el sistema no tiene forma de decir *"hay un evento en
> el catálogo pero no es el nuestro"*.
- **Componente:** api · **Depende de:** T-5.10 · **Prioridad: ALTA**
- **Objetivo:** que el criterio de identidad entre el evento del catálogo y el que disparó el
  gabinete sea explícito, defendible y capaz de decir que no encontró nada compatible.
- **Criterios de aceptación:**
  - [ ] Criterio explícito y configurable: ventana temporal, radio máximo epicentro↔sitio y
        magnitud mínima coherente con la distancia, cada uno con su razón escrita.
  - [ ] En la ruta sin epicentro propio, el acierto **no se presenta como contraste**: se declara
        no verificable, con su texto propio.
  - [ ] Un evento fuera de radio, o de magnitud incoherente con la distancia, **no casa** — y el
        resultado es el estado de sin correlación de `T-5.10`, no un hueco.
  - [ ] Test con un caso realista de sismo lejano dentro de la ventana temporal: hoy casaría; con
        la ficha, no.

### [x] T-5.12 · **Contar falsos positivos** — `SOFTWARE` · **CERRADA 2026-09-02**
> Hoy no hay forma de contarlos, ni siquiera a mano sobre la base. `incidents.state` admite
> `open|acked|in_review|closed` y **nada más**: no hay columna de clasificación, ni de descarte,
> ni de motivo de cierre. Cerrar un incidente **no pide ni admite una razón**, y el estado
> intermedio de revisión no desemboca en ningún veredicto registrable. No existe endpoint de
> agregados ni vista que los cuente.
>
> **Es la métrica que decide si el cliente renueva** — y la ironía está documentada en el propio
> código: la app explica que el documento de entrega *"deslinda expresamente los falsos positivos
> de SASMEX"*. El sistema **se deslinda de una tasa que no mide**.
>
> Lo único adyacente que ya está bien: los simulacros viven en tabla propia, así que al menos los
> ensayos no contaminan el conteo.
- **Componente:** api + web · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que cerrar un incidente registre **qué fue**, y que la tasa se pueda leer sin
  abrir la base.
- **Criterios de aceptación:**
  - [x] Clasificación al cierre con un catálogo cerrado y corto, decidido en la ficha: real,
        falso positivo, prueba/mantenimiento, indeterminado. **Indeterminado no es el default
        silencioso**: se elige y se declara.
  - [x] La clasificación queda auditada con actor y hora, y **no se puede reescribir**: una
        corrección inserta, no sustituye, como ya hace la cadena de dictámenes.
  - [x] Endpoint de agregados por tenant y ventana, con la tasa y el desglose, respetando el
        aislamiento entre clientes.
  - [x] La consola lo muestra, y **declara cuántos incidentes están sin clasificar** en vez de
        excluirlos del denominador — un porcentaje calculado sobre lo clasificado, con lo no
        clasificado escondido, es peor que no tener el número.
  - [x] Los simulacros siguen fuera del conteo, con test.
- **Cómo se cerró (2026-09-02).** Tabla propia `incident_classifications` (migración `0055`),
  **append-only con las dos capas** que ya usa la cadena de dictámenes: `REVOKE UPDATE, DELETE`
  **y** el trigger `forbid_update_delete()`. Corregir **INSERTA** una fila que apunta a la
  anterior por `supersedes_id`; la vigente es la que nadie sustituye. `GET /classification-stats`
  da la tasa por ventana, y `api/src/takab_api/incident/classification.py` fija el conjunto
  `EN_LA_TASA` **excluyendo `prueba`** — los simulacros ya vivían en tabla aparte, pero un
  incidente marcado a mano como prueba también tenía que salir del denominador.
  **Dos decisiones que no estaban en la ficha y sí en el código.**
  (1) **La tasa devuelve `null`, no `0`, cuando nadie ha clasificado nada.** Un cero afirmaría
  que no hubo falsos positivos; lo que pasa es que nadie miró. La consola lo pinta `S/D` y dice
  por qué, y hay test de que jamás sale `0.0 %` desde el vacío.
  (2) **Los sin clasificar viajan junto al porcentaje, siempre** (`4 DE 10 SIN CLASIFICAR`): la
  agregación los conserva en el total en vez de filtrarlos, porque un porcentaje sobre lo
  clasificado, con lo no clasificado escondido, es una muestra sesgada por quién tuvo tiempo.
  **Y una divergencia que apareció al hacerlo, ajena a esta ficha:** el espejo de la matriz RBAC
  en `web/src/test-utils/meFixtures.ts` **lleva 16 celdas divergentes** de
  `api/src/takab_api/auth/matrix.py` (cctv ×9, privacidad ×4, `read_audit`, `checkin_submit`,
  `panic_vote`). Aquí se corrigieron **solo las dos de `classify_incident`**; las otras dieciséis
  siguen abiertas y **nada las vigila** — el fichero pide a mano que se le actualice. Es el patrón
  que `TRASPASO-SESION.md §4` ya nombró: *un censo que enumera a mano acaba divergiendo*. Se
  deriva en tres líneas comparando los dos por igualdad; no se hizo aquí porque volver verde esas
  dieciséis celdas cambia qué botones ven seis roles en las suites existentes, y eso es un lote
  propio, no un apéndice de esta ficha. **Fichado como `T-5.28`**, con la tabla de las dieciséis
  y con lo que de verdad hay que mirar al cerrarla: nueve de ellas apagan los paneles de CCTV en
  toda la suite de web, así que la divergencia no relaja una aserción — **borra la población**.

### [ ] T-5.13 · **Plantillas de simulacro** guardadas y editables — `SOFTWARE`
> No existen: ni tabla, ni campo en el cuerpo del alta, ni endpoint, ni interfaz. El alta de un
> simulacro tiene exactamente cinco campos y ninguno es una plantilla. Lo más cercano —ejecutar
> una agenda ya creada— **la consume**, así que no se puede reutilizar.
>
> Para el macrosimulacro de septiembre hay que teclear los sitios, la duración y la nota a mano,
> cada vez. Es fricción operativa en el caso de uso más visible que tiene el producto.
- **Componente:** api + web · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que un simulacro recurrente se defina una vez y se lance en dos clics.
- **Criterios de aceptación:**
  - [ ] Plantilla con nombre, conjunto de sitios, duración y nota; CRUD completo con el mismo rol
        que hoy puede disparar un simulacro.
  - [ ] Crear un simulacro desde una plantilla **copia** sus valores; editar la plantilla después
        no reescribe simulacros ya ejecutados.
  - [ ] Una plantilla cuyos sitios ya no existen o están retirados **lo dice al usarla**, en vez
        de lanzar contra un conjunto silenciosamente más pequeño.
  - [ ] Aislamiento entre clientes: una plantilla es de su tenant, con test de cruce.

### [x] T-5.14 · El **post-simulacro** no tiene tiempos ni sale del navegador — `SOFTWARE` · **CERRADA 2026-09-02**
> Lo que hay está bien hecho: el acuse por sitio se deriva por unión con la tabla de comandos, y
> distingue honestamente *sin gabinete comandable* de *sin acuse* — dos cosas que colapsar sería
> mentir. Faltan las dos que el cliente pide:
>
> - **El tiempo.** No existe latencia de acuse por sitio en ninguna capa: ni el esquema de salida
>   ni la interfaz exponen el instante del acuse ni su diferencia contra el arranque. El dato
>   clave de un post-simulacro —*"la torre B tardó 4 min 12 s"*— **no existe**.
> - **La salida.** No hay PDF ni CSV: cero referencias a simulacros en los routers de exportación
>   y de reportes. El propio código llama a esto *"la evidencia de cumplimiento que se le entrega
>   a Protección Civil"*, y hoy se entrega **mirando una pantalla**.
- **Componente:** api + web · **Depende de:** ~~T-5.13~~ **nada** · **Prioridad: MEDIA**
  > **Corregido al ejecutarla.** La dependencia declarada era **editorial, no técnica**: se
  > escribió porque las dos fichas hablan de simulacros y quedaban juntas en el plan. Nada del
  > reporte toca las plantillas — el reporte lee `drills` + `commands`, que existen desde
  > T-2.48, y T-5.13 crea una tabla nueva que el reporte no consulta. Se cerró **sin** T-5.13.
- **Objetivo:** un documento que el cliente pueda enseñarle a Protección Civil.
- **Criterios de aceptación:**
  - [x] Instante del acuse por sitio persistido y expuesto, con su diferencia contra el arranque
        del simulacro.
  - [x] El tiempo se declara **por sitio y agregado**, y los sitios sin acuse no se cuentan como
        cero: salen aparte.
  - [x] Exportación del reporte con las mismas propiedades que el dictamen: determinista,
        hasheada, registrada como evidencia y auditada.
  - [x] El documento distingue las tres categorías (acusó / no acusó / no tenía gabinete) y dice
        cuántos sitios hay en cada una.
- **Cómo se cerró (2026-09-02).** `commands` gana `acked_at` (migración `0055`) y `DrillSiteOut`
  lo expone junto a `ack_latency_s`; `POST /drills/{id}/report` renderiza el PDF con el mismo
  camino que el dictamen —determinista, hasheado, inscrito en `evidence_objects` (que gana
  `drill_id`) y auditado—. La consola pinta `+M:SS · sello UTC` por sitio y la `MEDIANA` en el
  resumen.
  **La decisión que gobierna la ficha entera: quien no acusó NO entra como cero.** `null` viaja
  intacto del SQL al píxel, en las cuatro capas, y cada una tiene su test: la latencia del que no
  acusó es `None`, la mediana de un simulacro sin acuses es `None`, el resumen dice `MEDIANA S/D`
  y **la fila del que no acusó no pinta nada** —ni `+0:00` ni un guion—, porque los dos se leen
  como *respondió al instante*, que es lo contrario del hecho. Un cero además arrastraría la
  mediana hacia abajo justo en el simulacro que peor salió.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **El discriminador de agenda es `scheduled_at`, no `started_at`.** El guard que impide
  exportar una agenda —un documento que afirmaría cero de cero— se escribió primero sobre
  `started_at`, que la fila de agenda **también** lleva. Se caza con test.
  (2) **`evidence_objects` se declara ANTES que `drills` en `db/schema.sql`**, así que la FK
  inline reventaba una carga limpia; va como `ALTER TABLE` después del bloque de `drills`.
  (3) **Generar va con `drill_start`, no con `export`**, copiando la separación que ya existe
  entre `generate_report` y `export` en el dictamen: **generar inscribe una evidencia inmutable**
  del tenant, y `gov_operator` —que existe para recogerla— la descarga después por la ruta de
  evidencia de siempre. El reporte se registra con `drill_id`, así que le llega.

### [x] T-5.15 · **Cadena de acuse**: cuánto tardó y quién recibió — `SOFTWARE` · **CERRADA 2026-09-02**
> Tres de las cuatro preguntas se contestan hoy: quién acusó (con fila en el timeline y verbo en
> la bitácora), quién no respondió (el pase de lista distingue *sin reporte* y ofrece notificar a
> los que faltan), y en qué zona. Faltan dos, y las dos son de perito:
>
> - **"¿En cuánto tiempo?"** — el sistema **sí** calcula y almacena una latencia, pero es la de
>   **despacho** de la notificación, no la del acuse. El acuse escribe su fila con el sello de la
>   transacción y **nunca lee el instante de apertura**; la bitácora del SOC imprime sellos
>   absolutos sin columna de transcurrido. El número es derivable restando a mano; nadie lo hace.
> - **"¿Quién recibió la alerta?"** — la tabla donde vive el destinatario y la confirmación de
>   entrega **no se lee desde ningún router de consulta**. Es contestable en la base y no por la
>   API ni por ninguna pantalla.
- **Componente:** api + web · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que una revisión post-incidente se pueda hacer sin abrir la base.
- **Criterios de aceptación:**
  - [x] Latencia de acuse calculada y expuesta, con la misma honestidad que la de despacho: quien
        no acusó no tiene latencia, y eso **no es un cero**.
  - [x] Endpoint de lectura de los envíos de un incidente: canal, destinatario (con el mismo
        criterio de mínimo dato que el resto), estado y confirmación de entrega.
  - [x] La bitácora del incidente muestra el transcurrido junto al sello absoluto.
  - [x] Aislamiento entre clientes con test de cruce, y el envío simulado se distingue del
        entregado, como ya hace la tabla.
- **Cómo se cerró (2026-09-02).**
  **La latencia del acuse** la escribe ahora la propia fila (`incidents_ack.py`), calculada **en
  SQL y en el mismo statement que la inserta**: así el `now()` del que sale la cifra es
  exactamente el `now()` del `ts` de la fila. Restarlo en Python daba un número plausible y falso
  en cuanto los relojes difieren un segundo. Va con la misma clave (`latency_s`) y el mismo `t0`
  (`incidents.opened_at`) que la de despacho de `notify_sent`, así que las dos se comparan sin
  traducir nada.
  **`GET /incidents/{id}/notifications`** lee lo que `notification_jobs` guardaba desde la `0040`
  y no leía nadie. Devuelve **dos latencias separadas y NO sumadas**: `dispatch_latency_s` (de la
  apertura a que el proveedor aceptó) y `delivery_latency_s` (de ahí a la confirmación). El
  segundo tramo **no depende de TAKAB** —son los tres minutos del operador móvil—, y presentarlos
  sumados se los cargaría a la plataforma. `delivered` sale de `delivered_at IS NOT NULL` **y de
  nada más**: `sent` es «el proveedor lo aceptó» y `simulated` «no había proveedor», y ninguno de
  los dos afirma que un humano lo tenga en la mano.
  **El destinatario se reduce en `notify/destino.py`, con allowlist por FORMA** — la misma
  doctrina de `narrative/redact.py`, y por el mismo motivo: con una denylist, el canal que se
  añada mañana trae un `target` que nadie previó y sale entero, con el teléfono dentro. Lo que no
  encaja **no sale y se declara** (`unrecognised`), porque un hueco se leería como «no había
  destinatario».
  **Tres cosas que aparecieron al hacerlo.**
  (1) **La URL de un webhook ES la credencial.** Un `https://…/services/T0/B0/xoxb…` autoriza a
  publicar a cualquiera que lo lea; devolver `target` en crudo habría sido una fuga de secreto por
  una pantalla de consola. Sale **el host y nada más**, con test de que la ruta no aparece.
  (2) **El prefijo de país no se deduce del largo.** La primera versión del enmascarado lo dedujo,
  acertaba con México y mentía con `+1` y con `+351`. Un prefijo inventado en una pantalla de
  evidencia es peor que un dígito menos: **se enmascara todo menos la cola**.
  (3) **`gov_ack_incident` no dejaba fila en la bitácora** (migración `0056`). Escribía solo
  `audit_log`, así que un incidente acusado por Protección Civil salía `acked` en la consola **con
  la bitácora sin un solo acuse**: la pantalla que existe para reconstruir lo ocurrido contradecía
  al estado que tenía al lado. No es un hueco, es una contradicción — y ninguna de las dos vías
  del acuse tenía test de que su fila existiera.
  (4) **El SLA no se cumple por no intentarlo.** El veredicto de plazo comparaba `sent_at <=
  deadline_at`, así que el job encolado hace media hora con plazo de 60 s **y sin enviar** salía
  sin veredicto y sin aviso: el incumplimiento más grave era el único silencioso. Se compara
  contra `sent_at` si salió y contra **ahora** si no, y el `null` queda para lo único que lo
  merece — el canal que no tenía plazo.

### [x] T-5.16 · **Umbrales por tipo de inmueble**, con rollback — `SOFTWARE` + `DECISIÓN` · **CERRADA 2026-09-02**
> `BLUEPRINT §4.5` declara tres bandas de referencia: hospitales 0.040–0.060 g, industriales
> 0.080–0.120 g, corporativos 0.100–0.150 g. **Ninguna está implementada.** `building_type` es
> texto libre sin catálogo ni restricción, y **nadie lo consulta** para resolver umbrales: los
> alcances son tenant, sitio y sensor. El propio código lo declara en la consola.
>
> Consecuencia física: el default del edge está documentado como *"Default = hospital"*, así que
> **toda la flota corre la banda de hospital**. Un industrial dado de alta hoy avisa dos veces por
> debajo de su banda.
>
> Y falta el **rollback**, que el blueprint exige por nombre (*"versionada y reversible"*) y que
> `G-05` pide explícitamente. El versionado y el conflicto por versión base están bien resueltos y
> con test; el histórico está en la base. Lo que no hay es forma de volver a una versión: hay que
> teclear los valores viejos y crear una nueva.
>
> **Lo que hay que decidir:** si la tipología es un catálogo cerrado con bandas por defecto, o una
> etiqueta que solo sugiere. La primera opción cambia el comportamiento de una estación con solo
> cambiarle el tipo, y eso **no puede pasar sin publicar y firmar**.
- **Componente:** api + web + db + edge · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el umbral de un edificio corresponda a lo que ese edificio es, y que volver
  atrás sea un clic, no un dictado.
- **Criterios de aceptación:**
  - [x] Decisión escrita **con su razón** sobre si la tipología resuelve umbrales o solo los
        sugiere.
  - [x] Catálogo cerrado de tipos, con las tres bandas del blueprint como valores de referencia
        **derivados de un solo sitio**, no copiados en tres archivos.
  - [x] Cambiar el tipo de un sitio **nunca** cambia por sí solo lo que corre en el gabinete: hace
        falta publicar, y la publicación va firmada como hoy.
  - [x] Rollback a una versión anterior del conjunto de reglas, como operación explícita que
        **crea una versión nueva** declarando a cuál vuelve — nunca reescribiendo el histórico.
  - [x] El rollback queda auditado y respeta el conflicto por versión base.
  - [x] Test de que el default del edge deja de ser silenciosamente el de hospital: sin banda
        resuelta, el gabinete **lo declara** en vez de suponerla.
- **Cómo se cerró (2026-09-02).**
  **La decisión es `D-28`: la tipología SUGIERE, no resuelve.** La razón que la sostiene, y que
  conviene no perder: *el tipo se edita desde una pantalla de captura*. Quien abre el formulario
  de una estación va normalmente a corregir una dirección; si el tipo resolviera el umbral, ese
  guardado —administrativo, sin firma y sin publicación— **re-armaría el edificio a otra
  sensibilidad**. Es un cambio de actuación por un acto de captura, y choca con las reglas de oro
  1 y 8. Se prueba **midiendo**: `test_cambiar_el_TIPO_no_toca_el_rule_set_activo` compara el
  rule_set activo antes y después de cambiar el tipo, en vez de fiarse de un comentario.
  **El catálogo vive en `shared/schemas/tipologia_umbral.json`** y de ahí derivan, por igualdad y
  en los dos sentidos, la validación de la API, el `CHECK` de `sites.building_type` y el
  desplegable de la consola — y las tres bandas se leen **del propio blueprint** con una expresión
  regular, así que retocar una cifra en un sitio y no en el otro sale rojo con el número que
  cambió.
  **El rollback** (`POST /rule-sets/{id}/rollback`) crea una versión **más**, nunca una menos:
  `rolled_back_to` declara a cuál vuelve, queda auditado con las dos versiones y respeta el
  conflicto por versión base igual que el PUT.
  **Cinco cosas que aparecieron al hacerlo.**
  (1) **Los tipos que el producto atiende y para los que NADIE publicó banda** —universidad,
  gobierno, otro— la llevan en `null` **con su razón escrita**. Prestarles la de hospital habría
  sido repetir el defecto que abre la ficha en vez de cerrarlo.
  (2) **El rollback NO resucita un secreto rotado.** El `config` guarda el `secret` del webhook, y
  una versión vieja lo trae; puede haberse rotado justamente porque se filtró. Se restauran los
  valores de entonces con las credenciales de AHORA, reutilizando `redact_config` + `merge_secrets`
  en vez de escribir una tercera regla de secretos.
  (3) **El panel trataba «cualquier cosa que no sea `sin_resolver`» como banda publicada**, así
  que un origen desconocido se leía como decidido — un fallback pintado de `ok`. Son **tres**
  estados, y el tercero se declara. Lo cazó el censo de render del panel: mutar el campo no
  cambiaba un pixel porque todas las mutaciones caían en la misma rama.
  (4) **El origen se pinta SIEMPRE**, no solo cuando es malo: que la advertencia falte no puede
  ser la única señal de que la banda sí se eligió.
  (5) **`serverDataCensus` obligó a sacar el campo de tipología a componente propio.** Dentro del
  formulario era dato de servidor sin los cuatro estados: con la consulta caída, un desplegable
  con solo «SIN CLASIFICAR» se lee como «no hay tipos», que es lo contrario de «no se pudieron
  leer».
  **Lo que la migración `0057` hace con lo escrito antes:** `building_type` era texto libre. Se
  normaliza lo reconocible y lo que no encaja pasa a `otro` **dejando el texto original en
  `audit_log`** — perder la captura de alguien en silencio para que cuadre un `CHECK` es lo que
  prohíbe la regla de oro 11.

### [x] T-5.17 · El **sonido del simulacro** no se elige ni queda auditado — `SOFTWARE` · **CERRADA 2026-09-02**
> El selector de audio que la nube empuja cubre **dos ranuras** —sirena y tono de prueba— y el
> voceo de simulacro **no está entre ellas**: sale de un ajuste local cuyo valor por defecto es
> vacío, configurable solo tocando el archivo de entorno de cada gabinete.
>
> Y la auditabilidad tiene un hueco: el sha256 se registra **al arrancar**, no al sonar. Al
> reproducir solo se escribe la ruta en el journal local, y el botón del panel deja rastro en un
> anillo **en memoria** que no pasa por el libro de actuaciones. Si alguien pregunta qué sonó el
> 19 de septiembre en la torre B, la única respuesta está en el journal de ese gabinete.
>
> **La propiedad que hay que conservar al añadir el selector** ya está bien resuelta en el
> catálogo y no se toca: la nube elige **por identificador de catálogo**, nunca por binario ni
> ruta absoluta —ese canal va firmado a un aparato que toca gas y puertas—; un identificador
> desconocido **conserva el tono anterior** en vez de caer a otro; y el tono oficial sigue
> reservado y ausente por su gate legal.
- **Componente:** edge + api · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que se pueda elegir el sonido del simulacro desde la nube y que quede constancia
  de qué sonó exactamente.
- **Criterios de aceptación:**
  - [x] El perfil de audio gana la ranura del voceo de simulacro, con las mismas reglas que las
        dos existentes.
  - [x] El sha256 del asset **viaja en el acuse** del arranque del simulacro y queda persistido
        junto al acuse por sitio, no solo en el journal.
  - [x] El botón del panel deja constancia persistida, no en un anillo en memoria.
  - [x] Un identificador desconocido conserva el tono anterior y **lo declara**; el tono oficial
        sigue ausente del catálogo.
  - [x] Test que recorra los tres caminos: identificador válido, desconocido y reservado.
- **Cómo se cerró (2026-09-02).**
  **La ranura** `audio.simulacro` sigue las tres reglas de las otras dos, y no por copia: el bucle
  de `apply_audio_profile` recorre las tres con el mismo código, así que la cuarta que alguien
  añada hereda las reglas o no entra. El voceo de simulacro deja además de leerse de `settings` en
  cada reproducción y pasa a ser **estado del módulo**, que es lo que permite que la nube lo
  elija; el valor inicial sigue siendo el asset local del sitio.
  **El sha256 se calcula de lo que va a sonar, en el instante de sonar**, y no del asset que se
  enumeró al arrancar. La diferencia no es teórica: entre el arranque y el simulacro puede haber
  entrado una config firmada que cambió el tono, y el hash que se registraba hasta hoy podía no
  ser el del sonido que salió por la bocina. Viaja en `results.audio` del acuse —campo que ya
  existía en el contrato, así que **no se abre superficie nueva hacia el gabinete**—, se persiste
  con el acuse por sitio, se expone en `DrillSiteOut.audio` y se cita en el PDF del reporte.
  **El botón del panel** escribe en la bitácora local (`ActuationLedger`), con causa propia
  `lan_drill_voice` y con el asset y su huella en el detalle: «se voceó» sin decir qué se voceó no
  responde a un perito. Antes solo quedaba en la `deque` de `_actions`, que un reinicio borra.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **Un id RESERVADO y uno inventado acababan indistinguibles.** Los dos conservan el tono
  anterior —eso está bien—, pero un tecleo y una infracción de licencia no son el mismo hecho. El
  reporte de flota gana `reserved` con la razón, para poder decir «el tono oficial de SASMEX es de
  CIRES» en vez de un «desconocido» opaco.
  (2) **`audio: null` y «no había módulo de audio» eran lo mismo para quien lee el reporte al día
  siguiente.** Ahora la evidencia **nunca es `None`**: declara la razón, porque el voceo es
  advisory y un simulacro sin él es legítimo —el banner y el registro viven igual—.
  (3) **Y un tercer estado en el documento: «NO REPORTADO».** Un gabinete con firmware anterior no
  trae el campo, y colapsarlo con «SIN VOCEO» afirmaría un silencio que nadie midió.
  **Lo que NO se cierra aquí, y conviene no leer de más:** el catálogo gana un **tono**
  (`takab-simulacro-v1`), no el mensaje hablado. El voceo grabado sigue siendo un asset local y su
  gate de hardware sigue abierto — `RUNBOOK-gate-hw-movil-y-voceo.md §C.2` pide dos grabaciones
  **distinguibles a oído** y nadie las ha hecho. El tono está construido para no confundirse con
  la sirena (carillón de tres pulsos con dos segundos de silencio: el patrón de la megafonía, no
  el de una alarma), es reproducible con `edge/scripts/gen_simulacro.py` como los otros dos, y hay
  test de que los tres binarios del catálogo son **distintos entre sí** — dos ids apuntando al
  mismo WAV sonarían igual aunque el catálogo dijera lo contrario.

### [x] T-5.18 · La IA **no tiene tope de gasto** — `SOFTWARE` · **CERRADA 2026-09-03**
> Hay contabilidad por llamada (el coste se lee de la respuesta del proveedor y se escribe en la
> bitácora) y techo de tokens por llamada. **No hay cuota, ni contador acumulado, ni corte, ni por
> tenant ni por mes.** Y el endpoint que la invocaría **no tiene límite de frecuencia**: la única
> puerta es de rol. Un usuario autenticado puede reexportar el mismo incidente sin límite.
>
> Es la categoría que OWASP llama consumo de recursos sin restricción, y está en el blueprint.
> **Hoy el riesgo está acotado solo por que la perilla está apagada** — lo que significa que el
> tope tiene que aterrizar **antes** del shadow-mode, no después.
- **Componente:** api · **Depende de:** nada · **Prioridad: ALTA (precede a `T-3.01`)**
- **Objetivo:** que encender la IA no pueda costar más de lo que alguien decidió.
- **Criterios de aceptación:**
  - [x] Tope por tenant y por mes, configurable, con valor por defecto conservador.
  - [x] Contador acumulado persistido; alcanzado el tope, **el proveedor cae al determinista** y
        lo declara — nunca falla la exportación, que es una superficie de vida.
  - [x] El corte queda auditado, y el acercarse al tope también (una fila, no una por petición).
  - [x] Límite de frecuencia en la exportación de reportes, por usuario y por sitio, con el mismo
        patrón de dos techos que ya usan los comandos.
  - [x] Test de que con la perilla apagada nada de esto cambia el comportamiento actual.
- **Cómo se cerró (2026-09-03).**
  **Tabla `ai_spend`** (migración `0058`), una fila por `(tenant, mes UTC)`. Es un **contador, no
  evidencia**: por eso se actualiza en sitio y `takab_app` tiene UPDATE, al revés que casi todo lo
  demás del esquema. Lo que sí es evidencia —cuánto costó cada llamada, cuándo se avisó y cuándo se
  cortó— sigue en `audit_log`, que es append-only y exento de poda. El tope por defecto son **5 USD
  al mes**, deliberadamente conservador: el defecto de una cuota no puede ser «el que no molesta».
  **Agotada la cuota, la exportación SALE IGUAL** con texto determinista y lo declara en el PDF. Es
  la decisión que gobierna la ficha: el dictamen es una superficie de vida —alguien lo usa para
  decidir si un edificio se ocupa— y un 429 ahí convertiría un tope de gasto en una **negación de
  evidencia**. La prosa de IA rodea al veredicto y el veredicto no la necesita.
  **El freno de la exportación** son los dos techos de los comandos: el del usuario y el del
  **edificio** (`RO-8.e`: dos operadores coordinados agotan el segundo sin que ninguno rebase el
  suyo). Se cuenta desde `audit_log`, que ya registra cada exportación y no se poda nunca — sin
  tabla nueva ni contador que se pueda perder —, y el rechazo llega **antes de renderizar**:
  rechazar después de haber gastado el PDF y la llamada de IA no protegería de nada.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **La auditoría del corte no escribía nunca.** La primera versión auditaba desde el router
  releyendo el estado, y `leer_estado` **consume** la transición al sellar `blocked_at`: la
  segunda lectura ya la veía consumida. Quien sella el hecho tiene que escribirlo, así que la fila
  se mudó al módulo de cuota. Lo cazó escribir el test, no leer el código.
  (2) **`cap = 0` significa SIN TOPE, no «tope cero»**, y está declarado: es la lectura
  conservadora del ajuste ausente. Quien quiera cortar del todo apaga `openrouter_enabled`, que es
  el interruptor que ya existía.
  (3) **El tope se puede rebasar por UNA llamada, y se declara en vez de disimularse.** El coste
  solo se conoce al volver del proveedor, así que la secuencia honesta es leer → decidir → llamar →
  sumar. Reservar un estimado antes habría sido cobrar por lo que no se sabe; el desbordamiento
  máximo es una llamada, acotado a su vez por el techo de tokens que ya existía. Hay test de que
  el gasto real queda escrito **sin recortarlo al tope**.
  **Y el criterio que protege el estado de hoy:** con la perilla apagada no se cobra ni una
  llamada. `build_narrative` no toca la cuota cuando el proveedor no sale a la red — cobrarle al
  determinista llenaría el contador de ceros y el `calls` de mentiras sobre cuántas veces se salió
  a la red. Apagar la perilla **no es una degradación** y sigue sin marcar el PDF.

### [x] T-5.19 · El aviso de la plataforma no nombra a **un solo encargado** — `GATE-LEGAL` + `SOFTWARE` · **CERRADA 2026-09-03** *(la mitad de software; el texto revisado sigue esperando a `D-20`)*
> Siete terceros tocan o tocarán datos personales: AWS, Twilio, Meta, el servicio de
> notificaciones de Apple, el de Google, la cadena de compilación del móvil, y el webhook del
> propio cliente. **Ninguno está declarado.** Y el aviso **no menciona la transferencia
> internacional**: los datos viven en Ohio. El párrafo más cercano —*"SUS DATOS NO CRUZAN A OTRA
> ORGANIZACIÓN"*— habla del aislamiento entre clientes y es fácil de leer como una negación de
> ello.
>
> **El atenuante es real y hay que decirlo:** el aviso **se autodeclara provisional dentro del
> propio texto**, ese párrafo entra en la huella que sella el consentimiento, y el motor re-pide
> consentimiento al cambiar el texto. A nadie se le está diciendo algo falso; se le está diciendo
> nada. El mecanismo es definitivo; el texto no.
>
> **Choca con `D-20` y gana `D-20`:** la consulta legal espera a que un cliente la pida. Esta
> ficha **no la reabre**. Lo que sí hace es dejar el trabajo de costura listo para el día que
> llegue el texto revisado, y anotar el hecho nuevo: `D-23` y `D-07` descansan **las dos** sobre
> la calificación de que TAKAB es encargado y no responsable, y esa calificación solo está
> afirmada en un texto que se declara sin revisar.
- **Componente:** api + takab-docs · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el día que llegue el texto revisado no falte nada de software, y que mientras
  tanto el inventario de encargados exista y esté al día.
- **Criterios de aceptación:**
  - [x] Inventario de encargados en un documento propio, **derivado** de los proveedores que el
        código construye y de los recursos de infraestructura que tocan datos personales, no
        tecleado. Un proveedor nuevo entra solo.
  - [x] Test que compare el inventario contra los proveedores registrados: uno que no esté
        declarado pone el build en rojo nombrándolo.
  - [x] El aviso gana los dos huecos que hoy no tiene —encargados y transferencia— como
        **marcadores de posición explícitos**, dentro del texto provisional y por tanto dentro de
        la huella.
  - [x] Anotado en `PENDIENTES-MAURICIO §4.1` que la calificación de encargado sostiene `D-23` y
        `D-07`, para que la consulta legal la traiga en su lista.
- **Cómo se cerró (2026-09-03).**
  **Esta ficha NO reabre `D-20`**, y conviene leerlo así: la consulta jurídica sigue esperando a
  que un cliente la pida. Lo que se cerró es el trabajo de costura, para que el día que llegue el
  texto revisado no falte nada de software.
  **`takab-docs/ENCARGADOS-TAKAB.md` se GENERA** de `privacy/encargados.py` — un documento
  tecleado a mano dura hasta el primer proveedor nuevo, y el día que se queda corto **nadie se
  entera**: no hay pantalla que falle. Dos censos lo comparan por igualdad contra el código:
  (a) las **clases proveedoras** del paquete `notify` que salen a un tercero, derivadas del árbol
  de sintaxis y no importando los módulos —`twilio`, `whatsapp` y `push` se importan tarde a
  propósito, y un censo que exigiera importarlos sería un censo de lo que se pudo importar hoy—;
  (b) los **servicios de AWS** que aparecen en `infra/terraform`, cada uno clasificado como
  «guarda datos personales» o no, **con su razón en los dos casos**.
  **El aviso gana los dos párrafos** que le faltaban, dentro del texto provisional y por tanto
  dentro de la huella: eso significa que quien ya consintió **vuelve a ver el aviso**, porque el
  motor re-pide consentimiento al cambiar el texto. Los dos se declaran como **MARCADOR DE
  POSICIÓN**: afirmar una lista completa de encargados sobre un texto sin revisión jurídica sería
  peor que el hueco que había.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **El censo encontró dos clases que yo no había declarado** —`WhatsAppTemplateProvider` y
  `SimulatedPushProvider`—, y una de las dos era el proveedor REAL de WhatsApp: yo había declarado
  un `WhatsAppProvider` que no existe. Es exactamente el defecto que el censo existe para cazar, y
  lo cazó en su primera ejecución sobre su propio autor.
  (2) **El párrafo «SUS DATOS NO CRUZAN A OTRA ORGANIZACIÓN» se retituló.** Hablaba del
  aislamiento entre clientes, y junto a un aviso que callaba a siete encargados se leía como que
  nadie más los toca. Ahora dice de qué habla y remite al párrafo siguiente. Hay test de que la
  frase vieja no vuelve.
  (3) **El webhook del cliente se declara igual, con su matiz escrito**: ahí el destino lo elige el
  RESPONSABLE y no TAKAB, y su país es «desconocido: lo determina el cliente». Omitirlo por ese
  matiz habría sido exactamente el hueco que abre la ficha.
  **Y el hecho nuevo que se anotó para la consulta:** `D-23` y `D-07` descansan **las dos** sobre
  la calificación de que TAKAB es *encargado* y no *responsable*, y esa calificación solo está
  afirmada en un texto que se declara sin revisar. Si no se sostiene, las dos decisiones cambian
  de dueño y no de detalle.

### [x] T-5.20 · Firmar un dictamen **no entra en la bitácora de auditoría** — `SOFTWARE` · **CERRADA 2026-09-03**
> Firmar escribe la fila del dictamen —con quién firmó, en una tabla que no admite reescritura— y,
> **solo si el veredicto es habitable**, una acción en el timeline del incidente. **No escribe en
> `audit_log`.** El censo tiene 72 verbos, incluidos leer un dictamen y solicitarlo; no el de
> firmarlo.
>
> El hecho no se pierde. Pero el sitio donde un perito, un seguro o una auditoría van a buscar
> *"quién firmó qué y cuándo"* es la bitácora, y **el acto de mayor peso legal del sistema no está
> ahí**. Si además el veredicto firmado no es habitable, tampoco deja acción en el timeline.
- **Componente:** api · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el acto más importante del sistema aparezca donde se busca.
- **Criterios de aceptación:**
  - [x] Verbo propio en la bitácora al firmar, con el incidente como objeto y el veredicto en el
        detalle.
  - [x] La fila se escribe **también** cuando el veredicto no es habitable.
  - [x] Un test de censo que exija que **toda transición de estado con peso legal** deje verbo:
        derivado, no una lista a mano, para que el siguiente entre solo.
  - [x] La bitácora sigue siendo escritor único: la fila entra por el módulo de auditoría, como el
        contract-test existente exige.
- **Cómo se cerró (2026-09-03).**
  `dictamen_signed`, con el incidente como objeto y en el `meta` el veredicto, si es habitable, el
  identificador del dictamen y **a quién sustituye** — la cadena se reconstruye desde la bitácora
  sin tener que leer la tabla de dictámenes. La llamada va **antes** del `if` de habitabilidad y no
  dentro, que es lo que dejaba al peor caso sin rastro en ninguno de los dos sitios: ni bitácora
  (no escribía nunca) ni timeline (solo si era habitable). Y es justo el veredicto que más pesa:
  `no_inhabit_inspect` deja a gente fuera de su casa hasta que alguien inspeccione.
  **El censo es el entregable, no el arreglo.** Arreglar la firma habría tardado diez minutos y
  habría dejado el hueco abierto para el siguiente acto, así que
  `tests/contracts/test_evidencia_deja_verbo.py` deriva **las dos poblaciones**: las tablas
  append-only salen de `db/schema.sql` contando los triggers cuya función es
  `forbid_update_delete()` —es el propio esquema el que declara qué es evidencia— y los
  manejadores salen del árbol de sintaxis de `routers/`. La exigencia se comprueba **dentro de la
  función**: un `audit_async` en el manejador de al lado no audita este acto.
  **Y la lista de excepciones quedó VACÍA**, que era el mejor resultado posible: de los doce
  manejadores que escriben evidencia, once ya dejaban verbo y el que no se arregló en vez de
  declararse excepción. El vacío tiene su propio test — una lista de excepciones que puede crecer
  sola no es una excepción.
  **Lo que costó y conviene no repetir: este censo se quedó CIEGO DOS VECES mientras se
  escribía**, y las dos veces pasó en verde justo sobre el defecto que venía a cazar. La primera,
  por leer solo las asignaciones `NOMBRE = "INSERT INTO …"` y no el SQL que los módulos de
  `queries` construyen **dentro de funciones**: veía cuatro manejadores de los doce. La segunda,
  por buscar `alias.nombre` cuando los módulos de `queries` se importan con alias
  (`from … import dictamens as q`): con la primera corregida seguía sin ver `sign_dictamen`. Un
  censo se prueba **contra el defecto que ya sabes que existe**; si no lo encuentra, el censo está
  roto, no el código.

### [x] T-5.21 · No hay **censo de dato viejo** en la app móvil — `SOFTWARE` · **CERRADA 2026-09-03**
> La consola está resuelta y bien: un censo derivado del árbol obliga al componente siguiente a
> tener su prueba de los cuatro estados o a aparecer en una lista de deuda comparada **por
> igualdad**. Fuera de la consola es muestreo.
>
> En móvil el componente de marco existe y está probado, pero **no hay censo**: tres archivos usan
> el envoltorio que conoce la frescura y **seis consultan al servidor sin él**. Y hay un caso
> concreto: la lista del pase de vida solo declara el dato viejo **si el refetch está fallando**,
> así que un pase de lista de hace diez minutos con red sana **se pinta como fresco**.
>
> Es justo la pantalla que se enseña en una demo, y justo el fallo que la regla de oro 7 existe
> para impedir.
- **Componente:** mobile · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que en el teléfono ningún número se pinte como vivo sin poder demostrarlo.
- **Criterios de aceptación:**
  - [x] Censo derivado equivalente al de la consola: quién posee dato de servidor se deriva de los
        transportes, y se cruza contra quién tiene la prueba de los cuatro estados.
        **Ya existía** (`T-2.111`); lo que faltaba, y es lo que se hizo, es el censo sobre la
        SEMÁNTICA de la frescura.
  - [x] Comparación **por igualdad** contra la deuda declarada: la pantalla siguiente escribe su
        prueba o entra en una lista a la vista.
  - [x] El caso del pase de vida corregido: la edad se declara siempre, no solo cuando falla el
        refetch.
  - [x] Guarda anti-vacuidad: el censo declara cuántas pantallas espera y cero no vale.
- **PRIMERO, LA CORRECCIÓN DE LA FICHA.** Su premisa era **falsa**: «en móvil no hay censo» — y
  sí lo había, `mobile/src/screenStateCensus.test.ts`, de `T-2.111`, derivado del sistema de
  ficheros de `expo-router` y con sus cuatro listas de deuda vacías. Existía en el commit sobre el
  que se hizo la auditoría (`df13599`), así que el hallazgo estaba mal. Lo mismo el conteo «tres
  usan el envoltorio y seis consultan sin él»: los seis que consultan y **renderizan** usan el
  marco; los otros son hooks y observadores, que no pintan nada.
- **Y AHORA LO QUE SÍ ERA CIERTO, que resultó ser mucho peor.** La tercera viñeta —«el pase de
  vida solo declara el dato viejo si el refetch está fallando»— era exacta, y no era un caso: era
  **el significado de `stale` en toda la app**. `useAlertState` lo calculaba como
  `isError && data !== undefined` y **siete pantallas lo heredaban**; `lista.tsx` y `dictamen.tsx`
  hacían lo propio con `failureCount > 0`; `AccountScreen` y `camera.tsx`, con `isError`. **Nueve
  superficies**: con red sana y un `mobile_state` de hace diez minutos, todas esas señales valen
  `false` y la pantalla afirma frescura.
  La peor de las nueve no es el pase de lista: es `camera.tsx`. Su frescura acaba **horneada en el
  píxel** de una fotografía forense y entra en el sha256, así que un «METADATOS RETENIDOS» que
  solo aparecía al fallar la consulta dejaba fotos con metadatos de hace diez minutos **sin marca
  ninguna** — y esa foto va a un dictamen.
- **Cómo se cerró (2026-09-03).**
  `src/ui/useStaleSince.ts`: la edad sale del **reloj**, y el umbral **del intervalo de poll de
  cada pantalla** — «viejo» no es una cantidad de segundos, es «ya deberíamos haber refrescado y
  no lo hicimos». Tres pollos perdidos: uno es jitter, tres son un patrón. Una pantalla que
  consulta cada 5 s y otra cada 30 envejecen a ritmos distintos, y un umbral fijo mentiría en una
  de las dos. El hook trae reloj propio: sin el tic, un dato fresco al montar seguiría pintándose
  fresco para siempre.
  **El censo gana TRES reglas nuevas**, y las tres salieron de encontrarse el defecto en tres
  formas distintas: la expresión del marco, la propiedad que un hook DEVUELVE, y una **constante
  local** con nombre de frescura (`camera.tsx` pasaba el nombre de la constante al marco y la
  señal de fallo quedaba un salto más atrás). Las dos primeras nacieron ciegas y hubo que
  corregirlas: la del productor iba dentro del bucle de rutas y el defecto vivía en `features/`;
  la del marco, lo mismo, y por eso `AccountScreen` lo encontré leyendo y no el censo.
  **Y once fixtures pasaron de un epoch clavado en 2027 a contar desde `Date.now()`.** Desde que
  la frescura sale del reloj, un `dataUpdatedAt` en el futuro sale «fresco» y el estado `stale`
  dejaba de materializarse. La razón por la que un instante futuro **sí** debe salir fresco está
  escrita en el módulo: `dataUpdatedAt` lo pone react-query con el reloj del propio dispositivo,
  el mismo que da el «ahora», así que en campo no puede haber desfase — un valor futuro solo
  aparece en un test que clava un epoch. Con él, ocho tests que simulaban «viejo» **haciendo
  fallar la consulta** estaban probando el defecto; ahora prueban el tiempo.

### [~] T-5.22 · La latencia del reflejo **solo existe como prosa** — `SOFTWARE` + `GATE-HW` · **SOFTWARE CERRADO 2026-09-03 · espera `GATE-HW`**
> Es la cifra de venta más citada del producto, medida dos veces con hardware real: **6.65 ms el
> 2026-07-14** y **4.16 ms en frío el 2026-07-31**. Y su evidencia primaria son **ocho documentos
> con el número escrito a mano**. No hay journal, ni acta, ni captura del estado del gabinete, ni
> fixture. Un cliente que pida la evidencia recibe un archivo de texto.
>
> Además el guardián de esa latencia **reporta el mejor de cinco intentos**, no un percentil, tras
> haber fallado aproximadamente una de cada ocho corridas en integración continua. Y en el
> gabinete vivo el campo de latencia del reflejo está en nulo: la medición no está viva, es
> histórica.
>
> **El p95 del tramo hacia la consola tampoco se midió nunca**: lo que se vende como *"medido 214
> ms"* es una sola observación, y una cita de percentil del tablero apunta a una línea que no lo
> contiene.
- **Componente:** edge + takab-docs · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que la cifra que se vende tenga detrás un artefacto y no una frase.
- **Criterios de aceptación:**
  - [x] La medición del reflejo se persiste como artefacto reproducible en el gabinete (captura
        fechada del estado, o registro dedicado), no solo como línea de journal.
  - [x] Los ~~ocho~~ **nueve** documentos citan **una fuente**, no nueve copias del número.
  - [x] Donde se declara un percentil, o se mide o se dice que es una observación única. La cita
        rota del tablero se corrige o se retira.
  - [ ] `GATE-HW`: la siguiente sesión presencial captura la evidencia con el procedimiento nuevo.
        **Es lo único que queda, y no lo cierra el software** — ver
        [`MEDICIONES-TAKAB.md`](MEDICIONES-TAKAB.md) §2 y el runbook §B.1.bis.
- **Cómo se cerró la mitad de software (2026-09-03).**
  **El acta** (`edge/takab_edge/audit/reflejo.py`): cada flanco del WR-1 deja una línea fechada
  con la latencia que midió el dueño de los pines **y el estado de los cinco canales en ese
  instante**. Eso es lo que convierte el número en evidencia: no «tardó 4 ms», sino «tardó 4 ms
  **y estos relés quedaron así**», que es algo que alguien puede discutir.
  **La escribe el SUPERVISOR, no el dueño de los pines**, y no es un detalle: el reflejo vive
  entero dentro de un proceso que es mínimo y auditable a propósito (regla de oro 4), y meterle
  un fichero dentro sería pagar el acta con el camino de vida. El módulo de auditoría ya dejaba
  escrito que registrar el reflejo «es tarea aparte»; **esta era esa tarea**. El acta es advisory
  de punta a punta: si el disco falla se cuenta y se sigue.
  **`MEDICIONES-TAKAB.md` es la fuente única**, y `api/tests/test_mediciones.py` la sostiene con
  una regla que no es «prohibido repetir la cifra» —hay documentos que **deben** citarla— sino
  **«quien la cite tiene que enlazar aquí»**. El día que el número cambie, un `git grep` del
  enlace da la lista exacta de quién hay que revisar; hoy esa lista no existía.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **No eran ocho documentos: eran NUEVE.** El barrido encontró uno más que el informe
  (`PLAN-MAESTRO-TAKAB.md`, con el `214 ms`). Es la diferencia entre contar a mano y derivar.
  (2) **El `214 ms` se vendía como medición y se citaba como si fuera el percentil.** No lo es:
  es **una observación**, y el `p95 < 2 s` que el blueprint declara **nunca se ha medido**. Las
  tres cifras quedan rotuladas como observaciones únicas allí donde se citan.
  (3) **Y las dos cifras del reflejo se tomaron ANTES de que el acta existiera**, así que **no
  tienen artefacto** — y la tabla lo dice con todas las letras en su columna «Artefacto:
  ninguno». Cerrar la ficha entera habría exigido borrar esa fila; dejarla es lo que hace que
  `GATE-HW` siga significando algo.
  **Lo que NO se tocó, y por qué:** el guardián de CI (`test_e2e.py`) sigue reportando el mejor de
  cinco intentos. El informe lo listaba como defecto y **no lo es**: `T-2.170` lo razona como
  tolerancia **al instrumento** —un runner compartido mide código + planificación, y el ruido
  solo suma—, publica la serie completa también en verde y avisa cuando hizo falta reintentar.
  Además mide **pines simulados**: no acredita nada del hardware y ahora el documento lo dice.

### [x] T-5.23 · No existe **espectrograma** en el dictamen técnico — `SOFTWARE` · **CERRADA 2026-09-03**
> Confirmado abriendo el código: lo que hay es **un solo espectro de amplitud** de la ventana
> entera, con resta de continua y ventana de Hann. Cero coincidencias de transformada por ventanas
> en todo el árbol.
>
> **Para un cliente no técnico no aporta**: es una figura que exige formación y compite con el
> croquis y el semáforo, que son lo que decide. **Para el pericial sí**: separar la llegada de las
> dos ondas y ver si el edificio respondió en su periodo fundamental es exactamente lo que un
> espectro global promedia y esconde.
>
> Por eso va en la tanda tres, y **detrás** de que la onda cruda llegue a existir en la nube
> (`T-3.11.c`): sin registro archivado no hay nada que transformar.
- **Componente:** api · **Depende de:** T-3.11.c *(para el DATO, no para el código — ver abajo)* ·
  **Prioridad: BAJA**
- **Objetivo:** una figura tiempo-frecuencia en el documento pericial, con la misma honestidad que
  el resto.
- **Criterios de aceptación:**
  - [x] Espectrograma del canal dominante, con sus ejes rotulados y su ventana declarada.
  - [x] Sin registro archivado, **el mismo texto de ausencia** que ya usa la sección de onda cruda:
        no un hueco.
  - [x] El PDF sigue siendo determinista: mismo modelo, mismos bytes.
  - [x] La figura **no promete** una escala que no existe, como ya vigila la guarda del mapa.
- **La dependencia SE VERIFICÓ, y es real — pero no bloquea el código.** `T-3.11.c` se lee como
  «el worker de CCTV», y suena a que no tiene nada que ver. Sí lo tiene:
  `api/src/takab_api/backfill/objects.py` es **el único productor** de la fila de evidencia
  `kind='miniseed'`, y ése es el worker que no está en el compose de la nube. O sea que en
  producción **hoy no hay miniSEED archivado que transformar**, y la figura tomará siempre el
  camino de la ausencia hasta que `T-3.11.c` se despliegue. La ficha ya lo anticipaba en su
  criterio 2, y por eso el código se puede cerrar: está construido para declarar el hueco.
- **Cómo se cerró (2026-09-03).**
  `dictamen/espectrograma.py`: transformada por ventanas de Hann con solape del 50 % sobre el
  **mismo canal dominante** que el espectro y la duración — dos figuras del mismo dictamen que
  describieran trazas distintas serían una trampa para quien las compare, que es la razón que ya
  dejó escrita `T-3.14`.
  **La prueba que justifica la figura entera** es `test_SEPARA_en_el_tiempo_dos_frecuencias_que_el
  _espectro_global_promedia`: media traza a 5 Hz y media a 20 Hz. El espectro global las vería a
  las dos y no diría cuándo; el espectrograma tiene que enseñar 5 Hz al principio y 20 al final.
  Si eso falla, la figura no aporta nada y sobra.
  **Cuatro decisiones que llevan su razón escrita.**
  (1) **La escala es RELATIVA y la leyenda lo dice.** El crudo llega en cuentas del ADC y la
  calibración instrumental sigue pendiente: una barra con unidades prometería una calibración que
  nadie hizo. Es la misma guarda que vigila el mapa de sacudida.
  (2) **La continua se resta POR VENTANA.** El crudo del RS4D trae millones de cuentas de DC —el
  hallazgo de `T-2.25`—, y sin restarla cada ventana sale aplanada. Hay test con 3.77 M de cuentas
  encima.
  (3) **Una traza muerta devuelve ceros, no una figura encendida.** Normalizar dividiendo por cero
  pintaría ruido como si fuera señal: de las dos mentiras posibles, es la cara.
  (4) **Un registro largo se diezma tomando columnas equiespaciadas, no truncando.** Truncar
  dejaría fuera la coda, que es media pregunta de un peritaje.
  **Y la leyenda se extrajo a función pura** para poder probarla: el flujo de contenido de un PDF
  va comprimido, así que un test que buscara el rótulo en los bytes acabaría probando `fpdf2` en
  vez del enunciado. Junto a ella, una guarda anti-vacuidad que compara el MISMO documento con y
  sin figura — «el ejecutivo pesa menos que el técnico» habría pasado en verde aunque no se
  dibujara nada.

### [ ] T-5.24 · El reloj y la pérdida de paquetes **callan cuando deberían gritar** — `SOFTWARE`
> Dos huecos de la misma familia, los dos en el eje de "salud del sistema":
>
> - **El reloj.** El desfase se mide de verdad con el demonio de reloj, viaja, se persiste y
>   degrada el estado del sitio en la consola. Pero el panel del gabinete **lo pinta siempre en
>   verde**: no usa el ayudante de umbrales que todas las filas vecinas sí usan, así que un desfase
>   de cinco segundos se ve igual que uno de tres milisegundos. Y **ninguna de las 13 alarmas de la
>   nube es de reloj**: se ve solo si alguien está mirando la pantalla. Sin hora confiable, ninguna
>   evidencia sirve.
> - **La pérdida de paquetes.** Viaja a la nube y **se descarta a propósito** en la ingesta, con la
>   razón escrita. Consecuencia: el centro de operaciones **no puede ver la pérdida de paquetes de
>   ningún gabinete**; para diagnosticar un enlace degradado hay que ir al sitio o abrir el panel
>   por red local.
- **Componente:** edge + api + infra · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que las dos señales que dicen si la evidencia vale se puedan ver y despierten a
  alguien.
- **Criterios de aceptación:**
  - [ ] El panel usa el mismo ayudante de umbrales que sus filas vecinas para el desfase de reloj.
  - [ ] Alarma de desfase en la nube, con el mismo criterio que las demás: vigila la **ausencia**
        además del valor, y publica su cero para no quedarse muda.
  - [ ] La pérdida de paquetes gana columna y llega al centro de operaciones, o se declara por
        escrito **por qué** sigue siendo local — pero no las dos cosas a la vez.
  - [ ] Test de que el gabinete sin dato de reloj **lo declara** en vez de pintarse en verde.

### [ ] T-5.25 · El silencio **no alcanza a los gabinetes secundarios** — `SOFTWARE`
> El silencio del operador está bien resuelto en el gabinete que lo recibe: corta la sirena, corta
> el voceo, deja el estrobo, no toca gas ni puertas, y una alarma nueva vuelve a sonar. Doce tests
> lo defienden.
>
> Pero en un sitio con varios gabinetes, el principal propaga la activación a los secundarios por
> radio y **solo el cierre de alerta propaga la orden inversa**. El silencio no. El operador calla
> el suyo y **el edificio sigue sonando**.
>
> Es el mismo riesgo de credibilidad que motivó la decisión de la ruta de hardware: una sirena que
> nadie puede callar durante una falsa alarma quema la obediencia a la siguiente alerta.
- **Componente:** edge · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que silenciar signifique lo mismo en todo el inmueble.
- **Criterios de aceptación:**
  - [ ] El silencio se propaga a los nodos secundarios, y **solo** el silencio: la protección no
        audible de cada nodo no se toca.
  - [ ] Un nodo que no confirma **se declara** en el panel: silenciar cuatro de cinco no es
        silenciar.
  - [ ] Una alarma nueva vuelve a sonar en todos, como ya ocurre en el principal.
  - [ ] Test con dos nodos que mida el estado eléctrico de ambos, no la orden enviada.

### [ ] T-5.26 · La huella del PDF se imprime **a la mitad**, y la ficha de estación está partida — `SOFTWARE`
> Dos defectos de superficie que se arreglan juntos porque los dos son "el dato está y no se ve":
>
> - **La huella.** La cadena de custodia imprime el sha256 truncado a **32 de 64** caracteres,
>   mientras la portada del mismo documento instruye verificarlo con la herramienta estándar. Con
>   medio hash no se puede. (El hash de contenido de la portada sí va entero; es el de cada objeto
>   de evidencia el que se corta.) Además el documento ejecutivo **no lleva huella de contenido**:
>   el que lee quien decide no trae con qué verificarse.
> - **La ficha de estación.** Modelo, versión de firmware, serial y estado del respaldo eléctrico
>   **no están en el contrato del mapa**; para verlos hay que abandonar la consola e ir a Flota,
>   que en una demo es un salto de pantalla en el peor momento. Y el panel del propio gabinete no
>   muestra su serial ni el código de estación del sensor, así que quien está de pie delante no
>   puede correlacionarlo con la consola sin abrir el archivo de entorno.
- **Componente:** api + web + edge · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que un dato que el sistema ya tiene no se pierda en el último centímetro.
- **Criterios de aceptación:**
  - [ ] La cadena de custodia imprime el hash completo, o la portada deja de instruir verificarlo
        — no las dos cosas.
  - [ ] El documento ejecutivo lleva su huella de contenido.
  - [ ] La ficha del mapa gana los campos de identidad de hardware, con el mismo criterio honesto
        que ya usa el medidor de respaldo: sin dato, lo dice.
  - [ ] El panel del gabinete declara su serial y el código de estación del sensor.
  - [ ] Los PDF siguen siendo deterministas.

### [ ] T-5.27 · Las **dos guardas que faltan** — `SOFTWARE`
> Dos propiedades que hoy se cumplen **por construcción** y que nada impediría romper mañana:
>
> - **La cifra externa fuera del veredicto.** El desacoplamiento es genuino y estructural: el tipo
>   de entrada del veredicto tiene siete campos y **ninguno admite** magnitud ni catálogo, y el
>   módulo no importa nada de forense. Pero los catorce tests del motor afirman lo que la regla
>   **sí** hace; **ninguno afirma que el catálogo no la mueve**. Añadir el campo mañana no pondría
>   nada en rojo. Con `T-5.10` y `T-5.11` entrando, esta guarda deja de ser opcional.
> - **El folio fuera del prompt.** La lista blanca de lo que sale hacia el proveedor de prosa es
>   real y no deja pasar **ni un dato personal**: ni notas de ocupantes, ni coordenadas, ni
>   firmante, ni identificador de dispositivo. Pero el folio —que viaja entero— contiene el código
>   del sitio y los ocho primeros hex del identificador del incidente, y el docstring del módulo
>   afirma que ese identificador **nunca sale**. Y el test que lo defendería **borra el folio antes
>   de afirmar**. Es un identificador estable y correlacionable entre dictámenes, no un dato
>   personal — pero la lista blanca dice una cosa y hace otra.
- **Componente:** api (tests) · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que las dos propiedades dejen de depender de que nadie las rompa.
- **Criterios de aceptación:**
  - [ ] Contract-test que fije por **igualdad** los campos de la entrada del veredicto, y que
        prohíba por barrido del árbol de sintaxis que el motor de reglas o el del dictamen importen
        el módulo forense o el esquema del catálogo.
  - [ ] Se decide y se escribe qué hacer con el folio: o el prompt recibe un folio recortado, o el
        docstring deja de afirmar lo que no cumple. **Lo que no puede quedarse es el test que
        esquiva el caso.**
  - [ ] El test del identificador deja de borrar el folio antes de afirmar.
  - [ ] Guarda de no-vacuidad en ambos: cada uno declara cuántos elementos espera.
