# DOCUMENTO DE ENTREGA Y ACEPTACIÓN — TAKAB Ailert

> **Qué es este documento.** Es lo que se firma con el cliente. Describe, con el mismo detalle y
> el mismo tono, **qué hace el sistema y qué no hace**. No es material comercial: es el
> documento al que las dos partes volverán el día que algo no ocurra como alguien esperaba.
>
> **Regla que gobierna todo lo que sigue:** *lo que no está escrito aquí, no está contratado.*
> Y su recíproca, que es la que hace útil al documento: **lo que este documento declara que el
> sistema no hace, no es un defecto — es alcance.**
>
> **Cada afirmación de la sección «qué hace» es rastreable** a una prueba automatizada de la
> [matriz requisito→test](MATRIZ-REQUISITO-TEST.md) o a una línea de código citada. Ninguna
> afirmación de este documento se sostiene sobre una intención.
>
> Documento versión **1.0** · Emitido el **2026-08-08** · Tarea de origen: `T-2.86`.

---

## 0 · Datos de la entrega (rellenar antes de firmar)

Ninguno de estos campos viene rellenado, y no puede venirlo: son propios de cada cliente y de
cada edificio.

| Dato | Valor |
|---|---|
| Cliente (razón social) | |
| Domicilio del inmueble protegido | |
| Nombre del sitio en el sistema | |
| Identificador del gabinete (`gateway_id`) | |
| Número de gabinetes entregados en este sitio | |
| Gabinetes secundarios por radio (LoRa), si los hay | |
| Actuadores efectivamente cableados en este sitio (marcar) | ☐ sirena ☐ estrobo ☐ válvula de gas ☐ ascensores ☐ retenedores de puerta |
| ¿Este sitio contrata **actuación instrumental autónoma** (`instrumental_actuation`)? | ☐ Sí ☐ No — ver §3.2 |
| ¿Este sitio tiene bocina de voceo? | ☐ Sí ☐ No |
| Marco normativo que el **cliente** declara aplicable | *(ver §6.4 — TAKAB no lo respalda)* |
| Fecha de instalación | |
| Fecha de puesta en servicio | |
| Responsable interno del inmueble | |
| Soporte TAKAB — teléfono | *(ver §7, hueco H-2)* |
| Soporte TAKAB — correo | |
| Versión del software entregada (`FW_VERSION` del gabinete) | |
| Versión de la nube desplegada (`/api/health`) | |

---

## 1 · Qué se entrega, en una página

**TAKAB Ailert es un sistema de alertamiento sísmico y continuidad operativa por edificio, con
dos mitades:**

1. **Un gabinete en el inmueble** (el «edge»), con un sensor sísmico, una computadora que decide
   y acciona, y un receptor de la **alerta sísmica oficial mexicana (SASMEX)**. Esta mitad
   **protege sin internet**.
2. **Una plataforma en la nube**, con consola web para el centro de operaciones, app móvil,
   expediente del incidente y coordinación entre edificios. Esta mitad **coordina, no protege**.

**La frase que resume el diseño y que conviene leer dos veces:**

> Si se cae internet, si se cae el proveedor, si se cae la nube entera de TAKAB, **el edificio
> sigue protegido**. Lo que se pierde mientras tanto está enumerado en §3.3, no está escondido.

---

# PARTE I · QUÉ HACE EL SISTEMA

Cada fila lleva su **acreditación**: la fila de la [matriz](MATRIZ-REQUISITO-TEST.md) que la
prueba, o el `archivo:línea` del que sale. Donde dice `SIN COBERTURA`, es una capacidad que
**existe en el código pero ninguna prueba la sostiene** — y está repetida en §8 con su
consecuencia.

## 2 · En el edificio, sin internet (capa edge)

### 2.1 Alerta oficial SASMEX → actuación

| Qué hace | Acreditación |
|---|---|
| Recibe la **alerta sísmica oficial (SASMEX)** por un receptor **WR-1** cableado al gabinete, y acciona por su cuenta: **sirena, estrobo, cierre de válvula de gas, retorno de ascensores a planta baja y liberación de retenedores de puerta** | `RO-1.a`, `RO-2.a` |
| Lo hace **con la nube caída**, y hay pruebas que lo miden con la nube explícitamente apagada — no ausente por casualidad | `RO-1.a` |
| **Ningún estado de la nube desarma ni calla el reflejo**: ni la configuración publicada, ni una ventana de mantenimiento remota | `RO-1.b` |
| El tiempo entre el cierre del contacto y el movimiento de los relés se **mide** y cabe en el presupuesto de **menos de 100 ms** | `RO-1.e` |
| Medición con el **WR-1 real cableado**: **6.65 ms** del contacto al reflejo | `design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md:85`; hito de `T-1.69` |
| Del receptor WR-1 **solo se cablea el Relevador 2** («Alerta Sísmica Oficial»). Las pruebas periódicas y los avisos multi-riesgo viven en el Relevador 1 y no entran al gabinete | `TASKS.md:1684-1690` |
| Cada relé tiene un **estado seguro declarado por canal**: sirena y estrobo `NO` (una falla no los deja sonando), gas `fail_close` (una falla **cierra** el gas), retenedores `NC` (una falla **libera** las puertas) | `ESPECIFICACION-PANEL-GABINETE.md:71-77` |
| Un arranque fallido del gabinete deja los relés **en seguro antes** de soltar el control de los pines | `RO-4.d` |
| Dos procesos no pueden pelearse los relés: la propiedad de los pines es **exclusiva y se grita** | `RO-4.c` |

### 2.2 Detección instrumental propia

| Qué hace | Acreditación |
|---|---|
| Mide el movimiento del suelo con un **Raspberry Shake RS4D**: 4 canales a **100 muestras por segundo** (un geófono vertical + acelerómetro de 3 ejes) | `ESPECIFICACION-PANEL-GABINETE.md:61` |
| Calcula cada segundo PGA, PGV, RMS, STA/LTA y saturación, y clasifica el estado del inmueble en cinco niveles (`normal`, `vigilancia`, `acceso restringido`, `evacuar/resguardo`, `modo manual`) | `BLUEPRINT §4.5` |
| Guarda el **registro sísmico crudo** en el disco del gabinete, con retención configurada de **14 días** | `edge/takab_edge/config/settings.py:139-141` — y ver §7 hueco H-5 |
| Registra **por transición de estado**, no por intervalo: el motor de reglas apunta una vez por cambio de nivel, no una vez por evaluación | `RO-10.a`, `RO-10.b` |
| **Una sola estación NO acciona relés.** Desde la política ratificada el 2026-08-03, la detección instrumental local es **aviso visual** en el panel; se prueba con un sismo simulado completo y los cinco relés siguen sin actuar | `RO-1.f` — ver §3.2 |
| El **opt-in por sitio** (`instrumental_actuation`) restaura la actuación autónoma donde el contrato lo exija, y también está probado | `RO-1.g` |

### 2.3 Pantalla del gabinete (panel LAN)

| Qué hace | Acreditación |
|---|---|
| El gabinete **sirve su propia pantalla** dentro de la red del edificio, sin pasar por internet y sin cargar un solo recurso externo (una prueba rompe el build si aparece un `https://` en el HTML) | `ESPECIFICACION-PANEL-GABINETE.md:50-53`; `edge/tests/test_local_api.py::test_index_has_no_external_resources` |
| Se ve sin usuario ni contraseña; **para tocar botones pide un PIN de 6 dígitos**, con bloqueo de 60 s a los 5 intentos fallidos | `MANUAL-OPERACION-TAKAB.md §2` |
| Botones disponibles: silenciar audibles, cerrar alerta, probar sirena, **probar actuadores** (ejercita gas/ascensores/puertas con lectura de retorno, sin abrir incidente ni notificar), calibrar brújula, modo prueba WR-1, simulacro de voceo | `MANUAL-OPERACION-TAKAB.md §7`; `T-1.67`, `T-1.69` |
| **No pinta un dato viejo como si fuera de ahora**: una medición de más de 5 s se borra en vez de congelarse en verde; el resto de la pantalla rotula la edad | `RO-7.c` |
| **Sin cuenta regresiva y sin magnitud**, y hay un test que falla si aparecen | `INV-T-MINUS.a`, `INV-magnitud.a` |

### 2.4 Cuando cae el enlace

| Qué hace | Acreditación |
|---|---|
| Sigue detectando, accionando y guardando: **el enlace no es prerequisito de nada de lo anterior** | `RO-2.a` |
| **Dos horas sin enlace y al reconectar no se pierde ni se duplica un evento** | `RO-2.b` |
| La cola de mensajes **sobrevive al reinicio del proceso** | `RO-2.c` — y ver §7 hueco H-1 |
| La evidencia del sismo encolada sin enlace **se sube sola al reconectar**, con su huella `sha256` | `RO-2.d` |
| La configuración firmada del sitio **sobrevive a un corte de luz** y se vuelve a verificar al cargarla | `RO-3.e`; `T-2.34` |
| El panel dice `SIN ENLACE — PROTECCIÓN LOCAL ACTIVA` en **ámbar, no en rojo**: es el sistema funcionando como fue diseñado | `MANUAL-OPERACION-TAKAB.md §5` |

## 3 · En la nube

### 3.1 Ingesta y expediente

| Qué hace | Acreditación |
|---|---|
| Cada gabinete entra a la nube con **certificado propio** (mTLS/X.509), por un canal cifrado | `BLUEPRINT §4.6` |
| El mismo evento recorrido dos veces produce **un solo incidente**: la idempotencia está en la base de datos, no solo en el código | `RO-3.a`, `RO-3.b` |
| Abre y gobierna el ciclo de vida del **incidente**, con línea de tiempo, acuse y acciones | `BLUEPRINT §5.3` |
| Guarda **evidencia inmutable**: registro sísmico del evento (miniSEED), fotos de inspección y PDF de dictamen, con puntero en la base y descarga por incidente | `BLUEPRINT §9` |
| Emite un **dictamen operativo preliminar** (`NO HABITAR · INSPECCIÓN` / `HABITAR · MONITOREO` / `OPERACIÓN NORMAL`) con su base y su firma, y las correcciones **insertan una versión nueva, jamás reescriben** | `BLUEPRINT §9`; `T-2.40`, `T-2.41` — límite en §6.1 |
| La prosa generada **rodea al veredicto sin poder tocarlo**: el veredicto del PDF es idéntico con y sin prosa | `RO-1.h` |

### 3.2 Red de estaciones (quórum)

| Qué hace | Acreditación |
|---|---|
| Correlaciona detecciones de **≥3 estaciones** con una ventana de asociación **consciente de la distancia** entre sitios (`\|Δt\| ≤ dist / 6.5 km·s⁻¹ + 3 s`, tope 30 s) | `BLUEPRINT §4.5` |
| Los parámetros están **validados contra 13 sismos con valores oficiales SSN/USGS**, no elegidos a ojo | `PLAN-MAESTRO §3`, gate #2 (`T-1.46`) |
| Al confirmar el quórum, **la nube emite comandos de actuación FIRMADOS** a los gabinetes miembro (HMAC por gabinete + nonce + caducidad + acuse) | `RO-8.a`, `RO-8.b`, `RO-8.f`, `RO-8.i` |
| Una **firma inválida ni ejecuta ni acusa**; un comando **repetido** se rechaza; un comando **viejo** se rechaza aunque su firma sea válida | `RO-8.a`, `RO-8.f`, `RO-8.i` |
| Un comando **sin acuse nunca se reporta como ejecutado**: vence y se marca vencido, y un acuse tardío no lo resucita | `RO-8.h` |
| Hay **límite de tasa por usuario y sitio** sobre la superficie de comandos | `RO-8.d` — y el límite por sitio, sin prueba: §8, `RO-8.e` |

### 3.3 Consola SOC, app móvil y avisos

| Qué hace | Acreditación |
|---|---|
| Consola web con **monitoreo en vivo** (mapa, incidentes, detalle de sitio), **flota de gabinetes**, **triage/historial**, **auditoría** y **administración multi-tenant** | `T-2.35…T-2.57` |
| El dato viaja en vivo por WebSocket nativo: medido **214 ms** desde que el incidente se escribe hasta que la pantalla lo pinta | `BLUEPRINT §5.5` |
| **La consola rotula el dato viejo en vez de pintarlo como fresco**, y los indicadores dicen `S/D` cuando no hay dato, nunca cero | `RO-7.b`, `RO-7.e` |
| App móvil para ocupantes y brigadistas: alerta, check-in de vida, inspección de campo con fotos y firma, **cola offline cifrada**, y reenvío idempotente al recuperar señal | `RO-3.c`, `RO-7.d`; `T-2.00…T-2.14` |
| Activación manual: el rol `occupant` necesita **quórum de dos ocupantes en 30 s**; los roles operativos activan individualmente | `BLUEPRINT §8`; `RBAC-TAKAB.md §4.1` |
| **10 roles** con permisos separados. `gov_operator` (Protección Civil) es **solo lectura + acuse**: no opera actuadores | `RBAC-TAKAB.md`; `BLUEPRINT §8` |
| Cascada de notificación con **webhook firmado (HMAC)** y **correo**; un canal **simulado jamás se marca como enviado** — se marca `simulated` y se ve como tal en la consola | `T-2.75` — **límite en §6.3: hoy solo webhook y correo entregan de verdad** |
| Simulacro programado con historial y acuse, **rotulado como no-real en todo el recorrido**; una alerta real aborta el simulacro | `T-2.48`, `T-2.49` |
| Ventanas de mantenimiento que **silencian alarmas de operación, jamás la actuación** — anclado por una prueba que mide relés, no afirmaciones | `T-2.71` — límite en §6.3 |

### 3.4 Aislamiento entre clientes y datos personales

| Qué hace | Acreditación |
|---|---|
| **Un cliente no ve los datos de otro**, y no por convención: lo impone la base de datos (RLS default-deny). Una lectura cruzada devuelve cero filas; una escritura cruzada es rechazada | `RO-5.b`, `RO-5.c`, `RO-5.d` |
| Lo mismo comprobado **con un token real por HTTP**, no solo en la base | `RO-5.e` |
| **Aviso de privacidad versionado**: el consentimiento guarda qué versión aceptó cada persona y cuándo; cambiar el aviso no reescribe consentimientos anteriores | `T-2.79` |
| **Derechos ARCO por anonimización**: se anonimiza al titular **sin perder una sola fila**, y el hecho sobrevive — un check-in anonimizado sigue contando para el incidente | `RO-11.c`, `RO-11.d` |
| **La retención no puede podar la evidencia**: una regla que intente borrar filas de una tabla protegida se rechaza **antes** de borrar nada, y ni saltándose esa guarda lo permite la base | `RO-11.a`, `RO-11.b` |
| Respaldo continuo con **RPO declarado de 900 s, derivado de la configuración de la alarma** y no tecleado, más un ensayo de restauración que **mide su propio tiempo de recuperación** | `T-2.72`, `T-2.73` — límite en §6.3 |

---

# PARTE II · QUÉ NO HACE EL SISTEMA

Esta parte tiene el mismo peso contractual que la anterior. Se divide en cuatro cosas
**que no son lo mismo**:

- **§4 · Nunca lo va a hacer** (invariantes). Prohibiciones permanentes. No se pueden pedir.
- **§5 · No lo hace hoy y podría construirse** (diferidos y funciones abiertas).
- **§6 · No lo hace hoy porque falta algo fuera del software** (gates físicos, humanos, legales
  y de terceros).
- **§7–§8 · Lo hace pero nadie lo ha probado** (huecos declarados del manual y de la matriz).

## 4 · Los invariantes — alcance contratado en negativo

> Estas seis cosas **no se van a construir**. No son funciones pospuestas: son prohibiciones
> permanentes del diseño, y una tarea futura que proponga cualquiera de ellas **se rechaza sin
> discusión** (`TASKS.md`, sección «INVARIANTES»; `BLUEPRINT §14`).
>
> **La diferencia importa en un contrato:** un diferido se puede pedir después y presupuestar;
> un invariante **no llegará nunca**, y el cliente tiene derecho a saberlo antes de firmar.
> Cada uno lleva su razón en una línea.

| # | El sistema NUNCA va a… | Por qué, en una línea |
|---|---|---|
| **I-1** | **Mostrar una cuenta regresiva** («faltan 15 segundos») | El receptor entrega **un sí o un no**, y nada más. El número tendría que inventarlo el software — y de ese número depende si alguien corre o se protege. **Quien espere ese número, va a esperar para siempre.** |
| **I-2** | **Mostrar la magnitud** del sismo en el momento de la alerta | Por lo mismo: el contacto seco no transporta magnitud. El letrero dice exactamente `ALERTA SÍSMICA · PROTÉJASE`. Si algún día llegan datos enriquecidos de CIRES/SSN, serán una **fuente nueva y citable**, no una interpolación nuestra. |
| **I-3** | **Meter inteligencia artificial en el disparo** | La alerta tiene que ocurrir igual el día que el modelo se equivoque, el proveedor no conteste o la factura se acabe. El disparo lo decide un circuito determinista que siempre hace lo mismo con la misma entrada. La IA podrá asesorar y priorizar; **jamás vetar ni disparar**. Y la garantía es de construcción, no de promesa: el objeto que la IA produce **no tiene campo donde poner un veredicto**, y una prueba lo defiende. |
| **I-4** | **Subir la señal sísmica cruda en continuo a la nube** | Ese flujo satura el mismo enlace por el que tiene que salir el aviso cuando de verdad tiembla. El registro crudo sube **solo en eventos confirmados**. No es ahorro: es mantener el enlace disponible para lo único que importa. |
| **I-5** | **Modificar el sistema del sensor (Shake OS)** | El sensor es equipo de un tercero. Un sensor modificado por nosotros es un sensor cuyo comportamiento **ya no podemos acreditar ante nadie** —ni ante el cliente, ni ante un seguro, ni ante un perito—. Nuestro código vive en la computadora del gabinete. |
| **I-6** | **Usar el flujo UDP del sensor en producción** | El protocolo que usamos (SeedLink) sabe reanudar por número de secuencia y **puede demostrar que no perdió un paquete**. UDP no puede demostrar nada, y aquí la diferencia entre «no se perdió» y «creemos que no se perdió» es el expediente de un sismo. |

**Consecuencia práctica y honesta de I-1 e I-2:** durante una alerta, la pantalla dice
`ALERTA SÍSMICA · PROTÉJASE`, el sitio, el identificador del evento y el PGA máximo medido.
Nada más.

> **Matiz añadido el 2026-09-02 (`T-5.03`), y es una precisión, no un cambio de alcance.** Ese
> titular es el de la **alerta oficial** —el contacto del receptor SASMEX—, que es la única fuente
> que puede llevarse ese nombre. Las otras tres se titulan según lo que son: el umbral de una sola
> estación dice `AVISO SÍSMICO`, porque la política ratificada le prohíbe actuar; el quórum de red
> dice que lo confirmó la red; y una activación manual dice que fue manual. Lo que **no** cambia es
> lo que este apartado promete: en ninguna de las cuatro hay cuenta atrás ni magnitud. Si su plan de emergencia, su capacitación o su material interno prometen una cuenta
atrás, **hay que corregirlos antes de la puesta en servicio**.

## 5 · Lo que no hace hoy y sí podría construirse

| El sistema no… | Estado |
|---|---|
| **Mapa de intensidad areal («mini-ShakeMap»)** | **Diferido** — es la única viñeta de `BLUEPRINT §14` que una tarea futura puede derogar (`T-3.09`). Hoy la consola **no pinta bandas de intensidad ni una leyenda que prometa una escala inexistente**, y hay una prueba que lo impide (`DIF-shakemap.a`). |
| **Intensidad MMI, aceleración espectral (Sa) o deriva de entrepiso** | No construidos (`T-3.06`…`T-3.08`). La deriva de entrepiso, además, **exige dos sensores por edificio**: con uno solo el número sería una invención. |
| **Verificación por cámaras (CCTV/ONVIF) y conteo de aforo** | No construido (`Fase 3.2`). Aparece en el material de producto como visión; **no está en esta entrega**. |
| **Feed en vivo de CIRES/SSN como fuente de eventos** | No contratado ni integrado (`T-3.13`, gate #8 abierto). El catálogo del SSN que muestra el panel es **contexto posterior**, no la alerta. |
| **Exportación masiva por lote (ZIP)** | **Decisión vigente: no tenerlo** (`T-3.16`). La descarga objeto por objeto deja huella auditable por descarga; un paquete masivo la borra. |
| **BACnet/IP real contra el sistema del edificio** | La interfaz existe y el adaptador está escrito, pero **el driver real es un extra no acreditado con equipo**: hoy la actuación es por **relés secos locales**, que es la decisión ratificada (gate #4). Integrar BACnet con el BMS del inmueble es alcance adicional, con su propia acreditación. |
| **Actualización remota de la flota con canary y rollback** | Bloqueada (`T-2.70`), por la razón de §6.2. |

## 6 · Lo que no hace hoy porque falta algo fuera del software

Esta sección es la que más se malinterpreta y la que más caro sale callar.

### 6.1 Límites de responsabilidad — léase completa

| Límite | Qué significa |
|---|---|
| **TAKAB no genera la alerta sísmica oficial.** | SASMEX es un servicio de CIRES. TAKAB **recibe** su señal con un receptor WR-1 y actúa en consecuencia. La cobertura, la latencia, la disponibilidad y los falsos negativos del servicio oficial **no son responsabilidad de TAKAB**. |
| **El dictamen es operativo y preliminar.** | **No sustituye la evaluación estructural formal ni autoriza el reingreso al inmueble.** El reingreso lo autoriza una firma de ingeniería. Esto es límite de responsabilidad, no letra pequeña. |
| **El sistema no decide entre evacuar y resguardarse.** | Eleva el nivel medido y lo muestra. **Cuál de los dos protocolos aplica lo fija el plan de emergencia del inmueble**, que es del cliente. |
| **El sistema no reemplaza al plan de emergencia, ni a la brigada, ni a los simulacros.** | Es instrumentación y automatismo. Sin plan y sin personal entrenado, la sirena suena en un edificio que no sabe qué hacer. |
| **El aviso a las personas puede no salir cuando el aviso más falta.** | La sirena es local y suena. **Los SMS, correos, notificaciones al teléfono y WhatsApp los manda la nube**: sin enlace no salen (§6.3). Cuando el panel diga `SIN ENLACE`, **avisar a los brigadistas es tarea humana**, y así tiene que estar escrito en el plan del edificio. |

### 6.2 Gates físicos — lo que no se acredita sin manos en el equipo

Diez verificaciones **no las puede cerrar ningún software**: piden hardware en sitio o una
ventana en la nube. Están **enumeradas a propósito** para que este documento no dé la impresión
de que ya no queda nada por acreditar presencialmente
([matriz, sección «Gates físicos y de despliegue»](MATRIZ-REQUISITO-TEST.md); registro llenable
en `runbooks/RUNBOOK-auditoria-cierre.md §10`).

| Gate | Qué falta acreditar | Qué significa para el cliente | Fecha / firma |
|---|---|---|---|
| **G-01** | Reinicio en frío del gabinete con todo armado | Que tras un corte de luz el gabinete vuelva solo y con el control real de los relés | |
| **G-02** | **La sirena suena con el gabinete APAGADO** (ruta eléctrica en paralelo) | **La mitigación más importante del sistema.** Hasta acreditarla, no dé por hecho que la sirena suena si la computadora muere | |
| **G-03** | 24 h de flujo continuo del sensor + apagón físico del sensor | Que la instrumentación aguanta operación continua y se recupera sin huecos | |
| **G-04** | **Radio WR-1 con transmisión SASMEX real (o prueba CIRES) y la cadena física completa contacto→relé→sirena bajo 100 ms** | Hoy está medido el tramo **contacto→reflejo (6.65 ms)** con el receptor real cableado. **Los relés de potencia, la sirena, la válvula y los ascensores no están cableados en la unidad de referencia: están en MOCK.** Este gate lleva abierto desde el hito de Fase 1 | |
| **G-05** | Publicación de configuración firmada desde la consola a un gabinete físico, con rollback | Que un cambio de umbrales hecho en la consola llega, se aplica y se puede revertir | |
| **G-06** | Simulacro completo en sitio real con **cascada de notificación real** | Que el aviso llega a personas de verdad, cronometrado | |
| **G-07** | Reenvío de un comando capturado contra el gabinete físico | Que el rechazo anti-repetición funciona en el equipo, no solo en pruebas | |
| **G-08** | Prueba de carga a la escala objetivo de flota | Que el sistema aguanta el número de edificios contratados | |
| **G-09** | **Restauración real del respaldo, con el tiempo de recuperación medido contra la nube** | El respaldo está construido y ensayado localmente; **contra la infraestructura real todavía no se ha ejecutado** | |
| **G-10** | Panel LAN + PIN + MFA verificados en el equipo real y contra el directorio de usuarios real | Que el control de acceso del panel y de la consola se comporta como está escrito | |

**Y un gate que no es de hardware pero pesa igual — el criterio 4 de `T-2.70.a`:**

> **Separar el proceso que toca la sirena del proceso que hace todo lo demás cuesta un ciclo
> eléctrico del gas y de los retenedores de puerta.** Está medido: mover al dueño de los pines
> cuesta exactamente dos transiciones por pin, **el gas se cierra y las puertas se sueltan**.
> La causa está verificada contra el código instalado (`LGPIOPin.close()` devuelve la línea a
> entrada al liberarla), y **es imposible de evitar en software**. Las dos salidas son: una
> **ventana de mantenimiento con el edificio avisado, una sola vez**; o **hardware**
> (enclavamiento de relé o un pull-up que sostenga la bobina), que **cambia el perfil de falla
> segura** — un gabinete colgado dejaría de cerrar el gas por sí solo. **Eso no se decide desde
> el software: se decide con el cliente.** La ficha lo declara imposible en vez de fingirlo
> (`TASKS.md:4382-4395`).

### 6.3 Terceros y despliegue — qué está construido pero todavía no entrega

| Función | Estado real hoy | Qué falta |
|---|---|---|
| **Aviso por SMS** | **Nadie recibe un SMS.** El código está completo y probado; sin credenciales el canal se declara `simulated` y **nunca se marca como enviado** | Alta de la cuenta y del número mexicano (`T-2.76.a`). Advertencia documentada del proveedor: la entrega doméstica en México por *long code* es *best-effort and may be unreliable* |
| **Aviso por WhatsApp** | **No entrega.** La plantilla está versionada y sellada en el repositorio, pero **nadie la ha sometido a Meta**: sin plantilla aprobada el canal se declara simulado él solo | Alta del WhatsApp Business Account y aprobación de plantilla (`T-2.77.a`) |
| **Notificación al teléfono (push)** | **No entrega.** La infraestructura existe; sin credenciales de tienda el canal cae a simulado | Credenciales APNs/FCM reales (`T-2.97`) |
| **Correo** | **Entrega, pero solo a direcciones verificadas**: el servicio está en modo restringido (*sandbox*) y **no hay dominio propio** — la consola vive hoy en una dirección genérica sin Route 53 | Salida de sandbox con DKIM/SPF de dominio real (`T-2.78`, `T-2.78.b`) |
| **Webhook firmado** | **Entrega hoy.** Es, junto con el correo a direcciones verificadas, **el único canal que hoy avisa de verdad** | — |
| **Tono SASMEX en la app y en el voceo** | **No se usa el tono oficial.** Usarlo sin licencia no es un detalle estético: es el sonido que la población ya asocia a evacuar | Licencia con CIRES (`T-2.97`) |
| **Voceo hablado en el gabinete** | El motor existe y hay un tono de sirena sintetizado; **los dos mensajes reales no están grabados** y el hardware de audio no está montado ni probado presencialmente | `T-2.95` |
| **Alcance por sitio dentro de un mismo cliente** | **No impuesto en producción.** El aislamiento **entre clientes** sí lo impone la base de datos (§3.4). Lo que hoy no se impone es que un operador de un cliente vea **solo sus sitios**: la perilla está apagada (`api/src/takab_api/settings.py · console_scope_enforced`). **Es la única brecha multi-tenant viva** | `T-2.89`, con secuencia obligada: revisar quién quedaría fuera, asignar alcance, y **entonces** encender |
| **Gestión de usuarios desde la consola** | Corre **simulada** en producción: grita en cada escritura, no finge, pero **no crea usuarios reales** | `T-2.87` |
| **Ventanas de mantenimiento** | El núcleo está completo y el silencio de alarmas **está apagado por defecto a propósito** (con él apagado la ventana declara `0/N SILENCIADAS`, que es honesto). Falta la pantalla para **abrirlas** desde la consola | `T-2.71` |
| **Actualización remota de flota** | Bloqueada por el gate de §6.2 | `T-2.70`, `T-2.70.a` |
| **Restauración del respaldo** | Ensayada localmente con su tiempo medido; **contra la nube real, nunca ejecutada** | `T-2.74` (gate `G-09`), bloqueada por `T-2.73.a` |

### 6.4 Dónde viven los datos, y el marco legal

**Los datos están hoy en el centro de datos de AWS en Ohio, Estados Unidos (`us-east-2`).**
Se evaluó formalmente migrarlos a la región de México y **la recomendación es no migrar hoy**,
por una razón que no es de precio ni de velocidad: **el servicio por el que entra cada gabinete
a la nube (AWS IoT Core) no existe todavía en la región de México** — verificado contra cuatro
fuentes independientes y re-derivado por un auditor. El detalle completo, con el guion para
leérselo al cliente en voz alta, está en [`RESIDENCIA-DE-DATOS-TAKAB.md`](RESIDENCIA-DE-DATOS-TAKAB.md).

> **La ubicación de la nube no afecta a la protección durante un sismo:** la alerta y la
> actuación ocurren dentro del edificio, sin pasar por internet.

**Sobre el marco normativo — y esto es un límite, no un trámite:**

> El sistema **no declara por su cuenta ninguna norma como cumplida**. La regla operativa de
> TAKAB —auditoría, evidencia de incidentes y dictámenes **inmutables y jamás podados por
> retención**— es **requisito propio de TAKAB**, está construida y está probada (`RO-11`).
>
> **Lo que falta es el marco citable.** La cita antigua «NOM-003-SCT» **era una norma de
> transporte** (etiquetado de materiales peligrosos) y **no aplicaba**; se retiró del proyecto.
> Los candidatos reales —Ley General de Protección Civil, reglamentos estatales y municipales,
> términos de referencia del propio contrato, normativa local de revisión estructural
> post-sismo— **los define el cliente con su abogado** (`BLUEPRINT §9`; gate `T-2.96`).
>
> **El sistema muestra el marco que el cliente declara, con su deslinde: TAKAB no lo respalda.**
> Las etiquetas de cumplimiento se cargan por cliente y, **vacías, no muestran nada normativo**
> (`T-2.82`). Un sistema que enseña una norma que nadie verificó es peor que uno que no enseña
> ninguna.

## 7 · Los ocho huecos del manual de operación

El [manual de operación](MANUAL-OPERACION-TAKAB.md) que se entrega con el sistema **declara ocho
cosas que hoy no puede prometer**. Se repiten aquí porque forman parte de lo entregado:

| # | Hueco | Qué implica para el cliente |
|---|---|---|
| **H-1** | La evidencia pendiente de subir **puede no sobrevivir a un reinicio del gabinete** | El sistema está diseñado para que sobreviva, pero el ajuste que lo garantiza **no lo escribe hoy el instalador automáticamente**. El panel lo dice a la cara: `COLA NO DURABLE · SE PIERDE AL REINICIAR`. **Mientras esa frase esté en pantalla: no reiniciar el gabinete** |
| **H-2** | **No hay un teléfono de soporte escrito** | La cadena de guardia existe, pero **hoy el único canal que entrega de verdad es el correo** y el escalamiento por SMS está prometido y no construido. El manual dice **«avisa a soporte» 36 veces** (y menciona «soporte» 52 en total; medido el 2026-08-23, no estimado): **sin ese teléfono, son instrucciones incompletas.** Rellenar en §0 |
| **H-3** | La **rama de hardware WR-1 → sirena no está verificada físicamente** | Está diseñada y documentada. **No dar por hecho que la sirena suena con el gabinete muerto** hasta que exista el acta de esa prueba en este edificio (gate `G-02`) |
| **H-4** | **Botones físicos de silencio y de prueba: el software los soporta, no consta que estén cableados** | El manual no manda pulsar ningún botón físico. Si este gabinete tiene uno, anotarlo y pedir verificación |
| **H-5** | Los **14 días de registro sísmico dependen de un ajuste de instalación** | Sin la ruta de disco fijada, el registro se guarda en un directorio temporal que se borra al arrancar. **Pedir confirmación por escrito, para este edificio, de cuántos días de registro hay realmente** |
| **H-6** | Cuando algo falla, el panel **nombra servicios técnicos que un operador no puede tocar** | La acción del operador es **copiar la frase tal cual y dársela a soporte**, no ejecutar nada |
| **H-7** | El manual **cubre el panel del gabinete y la operación en sitio**; no cubre la consola web ni la app móvil | La capacitación de consola y app es aparte |
| **H-8** | El **reloj con batería del gabinete no está verificado en el código** | Solo importa para la hora escrita en los registros tras un corte largo de internet. **No afecta a la sirena.** Pedir confirmación de si este gabinete lo lleva instalado |

## 8 · Los dieciocho huecos de la matriz — lo que funciona sin que nadie lo pruebe

La **[matriz requisito→test](MATRIZ-REQUISITO-TEST.md)** es el documento de trazabilidad de esta
entrega. Es **generada, no escrita a mano**: la produce una prueba automatizada a partir de las
reglas del proyecto, y **si un test citado desaparece, la matriz deja de poder generarse**.

| Matriz — resumen | Cantidad |
|---|---:|
| Requisitos derivados | **17** |
| Afirmaciones verificables | **66** |
| **Cubiertas** por al menos una prueba viva, que no se salta y que bloquea el merge | **48** |
| **`SIN COBERTURA`** | **18** |
| Gates físicos / de despliegue que ningún software cierra (§6.2) | **10** |

> **Su principio rector, y la razón por la que se entrega entera:** *una matriz sin huecos es una
> matriz que miente — el valor está justo en los huecos.* Aquí están los 18, en lenguaje de
> cliente, ordenados por gravedad. **Ninguno se suaviza.**

### 8.1 Los tres peores

| # | Hueco | Qué significa | Cierra |
|---|---|---|---|
| 1 | **Nada impide hoy el streaming crudo continuo** (`RO-9.a`, `RO-9.b`, `INV-streaming.a`) | El invariante I-4 está escrito en tres documentos y **no lo sostiene ni una prueba**. Añadir hoy un publicador continuo de señal cruda **no rompería un solo test**, y la violación se descubriría **en la factura**. La compuerta que sube evidencia solo en eventos confirmados existe en el código; lo que nadie prueba es la palabra «solo» | `T-2.84.a` |
| 2 | **El segundo factor (MFA) no tiene una sola línea de prueba en ninguna capa** (`RO-8.c`) | Sobre la superficie que **abre válvulas de gas**, la regla del proyecto dice «sin excepción». Hoy la aplicación **no comprueba** la constancia de MFA: lo delega a la configuración del directorio de usuarios, y ese módulo es **el único sin prueba de infraestructura**, así que una desviación de esa configuración **no la detectaría nadie**. Es el hueco más grave de la matriz | `T-2.84.b` |
| 3 | **El proceso mínimo que se prueba no es el que corre de fábrica** (`RO-1.d`, `RO-4.f`) | La regla dice que la sirena, el gas y las puertas los toca un proceso mínimo y auditable. Ese proceso **existe, está probado y arranca en menos de un segundo** — pero **no es el que arranca por defecto**: el valor de fábrica deja los pines en manos del supervisor de 16 módulos, y solo un archivo de configuración fuera del repositorio lo corrige. **El estado de fábrica es el que la regla prohíbe** | `T-2.70.a` |

### 8.2 Los otros doce

| Hueco | Qué significa |
|---|---|
| **Una actuación con el enlace caído no deja rastro auditable en ninguna parte** (`RO-4.e`) | El acuse del actuador lleva canal, acción, evento, éxito y latencia — **no lleva quién lo ordenó**, y el gabinete no escribe bitácora propia. El único registro de auditoría vive en la nube. Es decir: **el caso para el que existe el gabinete es justamente el que no queda auditado** |
| **La bitácora de comandos registra lo que salió bien y calla lo que se intentó** (`RO-8.g`, `RO-8.k`) | Un comando repetido por un atacante se **rechaza** pero **no se apunta**; una denegación (403/409/429) tampoco. Quien investigue un incidente en la bitácora **no verá los intentos** |
| **El límite de tasa por sitio no lo prueba nadie** (`RO-8.e`) | Está implementado; lo que se prueba es el límite por usuario. Dos operadores coordinados agotarían el presupuesto del sitio sin que ninguna prueba lo viera |
| **Una tabla de negocio nueva sin identificador de cliente sería invisible** (`RO-5.a`) | La comprobación cruza el catálogo en la dirección contraria: exige aislamiento a las tablas **que ya tienen** el identificador. Una tabla nueva que naciera sin él **no entraría en el censo, luego no se le exigiría aislamiento**. El punto ciego se cierra solo |
| **El alcance por sitio no se impone en producción** (`RO-5.g`) | Ver §6.3. Y hay algo peor que el hueco: **dos pruebas fijan hoy la conducta NO impuesta**, así que encender la perilla pondrá la suite en rojo. Quien ejecute `T-2.89` tiene que contar con eso |
| **No existe barrido de secretos en el repositorio** (`RO-6.a`) | Ni prueba, ni paso de integración continua, ni herramienta. La regla «nada de secretos en el código» se sostiene hoy **solo sobre la disciplina de quien escribe** — la clase de garantía que este proyecto no acepta en ninguna otra regla |
| **Un ajuste que falte en producción cae en silencio al valor de desarrollo** (`RO-6.c`) | No hay validación de arranque: los valores por defecto **son credenciales de desarrollo**. Lo que sí está cubierto es el cierre por endpoint de dos secretos concretos, que devuelven error en vez de servir |
| **Nada obliga al componente número 28 a manejar los cuatro estados de pantalla** (`RO-7.a`; ficha `T-2.84.c`) | Medido: **27 componentes** usan el envoltorio que impone los estados, **14** tienen la prueba, y **al menos 12 pintan dato de servidor fuera de él**. La regla «nunca pintar un dato viejo como fresco» se cumple **por muestreo, no por sistema** — y ese fue exactamente el bug de julio, con la consola diciendo OPERATIVO durante 15 horas de ceguera |
| **La tabla de evaluaciones de regla no tiene guarda contra el registro por intervalo** (`RO-10.d`) | Hoy la regla se cumple **por ausencia de código**: nadie escribe en esa tabla. El día que se escriba el ingestor, nada avisará si escribe por intervalo |
| **La prohibición de IA cubre el proceso que dispara, no el motor que decide el nivel** (`INV-IA.b`) | La lista blanca de dependencias existe solo para el proceso de los relés. El código que decide el nivel —y que, con el opt-in de actuación instrumental, **dispara**— no tiene una equivalente. Es hueco de alcance, no de intención: el mecanismo ya está escrito y le falta el segundo objetivo |
| **«No se toca el Shake OS» no lo comprueba ningún test** (`INV-shakeos.a`) | Aparece en cinco documentos y en cero pruebas. El riesgo es de **garantía con el proveedor**, y el aviso llegaría en el sitio del cliente |

*(Los 18 se cuentan por **afirmación** de la matriz, no por fila de estas tablas: **§8.1 agrupa
seis** —`RO-9.a`, `RO-9.b`, `INV-streaming.a`, `RO-8.c`, `RO-1.d`, `RO-4.f`— y **§8.2, doce**.)*

### 8.3 Lo que la matriz declara que NO garantiza

Tres reservas, escritas por la propia matriz, que se heredan a este documento:

1. **La semántica la decide un humano.** El generador comprueba que la prueba exista, que no se
   salte y que la corra un trabajo que bloquea el merge. Que además **demuestre** lo que su fila
   dice, no lo comprueba nadie automáticamente.
2. **La descomposición en afirmaciones es un juicio editorial.** Una afirmación que nadie escribió
   **no aparece como hueco**.
3. **`CUBIERTO` no dice «bien cubierto».** Dice que hay al menos una prueba viva. Un requisito con
   una prueba superficial sale igual de verde que uno con quince.

---

# PARTE III · CONDICIONES DE LA ENTREGA

## 9 · Obligaciones del cliente

El sistema no funciona sin estas cinco cosas, y ninguna es responsabilidad de TAKAB:

1. **Red cableada (Ethernet) para el gabinete.** El Wi-Fi integrado está prohibido por latencia y
   pérdida (`BLUEPRINT §4.1`).
2. **Energía y espacio.** Alimentación estable para el gabinete y su respaldo; ventilación no
   obstruida y sin sol directo (la temperatura del procesador es lo único de la lista de
   diagnóstico que el operador puede arreglar por sí mismo).
3. **Cableado de actuadores por personal calificado**, según el estado seguro declarado por canal
   (§2.1). El sistema **acciona** el gas, los ascensores y las puertas: la instalación eléctrica
   y la conformidad de esos equipos son del inmueble.
4. **Plan de emergencia propio, personal capacitado y simulacros.** El sistema no decide entre
   evacuar y resguardarse, y **cuando el enlace se cae, avisar a los brigadistas es tarea humana**
   (§6.1).
5. **Custodia del PIN del panel y de los accesos.** El PIN se entrega una sola vez, el día de la
   instalación, al responsable del inmueble.

## 10 · Protocolo de aceptación

La aceptación se firma **por sitio**, y solo cuando estas casillas estén marcadas con evidencia:

- [ ] **Instalación física verificada**: sensor, computadora, receptor WR-1 (Relevador 2 al pin
      declarado), respaldo eléctrico y actuadores cableados según §0.
- [ ] **Gates físicos del §6.2 ejecutados**, o **declarados por escrito como no aplicables a este
      sitio, con su razón** — un gate sin marcar y sin razón es un gate que se olvidó, no un gate
      que se decidió.
- [ ] **`G-02` acreditado o su ausencia aceptada por escrito** (la sirena con el gabinete
      apagado). Es la mitigación más importante del sistema.
- [ ] **`G-04` acreditado**: cadena contacto → relé → sirena medida bajo 100 ms con equipo real.
- [ ] **Prueba de actuadores ejecutada presencialmente** desde el panel, con el edificio avisado,
      y el resultado por relé anotado.
- [ ] **Ficha del manual de operación rellenada** (`MANUAL-OPERACION-TAKAB.md`), incluido el
      **teléfono de soporte** (hueco H-2), e impresa junto al gabinete y en caseta.
- [ ] **Capacitación entregada** al personal de vigilancia y a la brigada, con lista de asistencia.
- [ ] **Marco normativo declarado por el cliente** y cargado en el sistema, con el deslinde de
      §6.4 firmado.
- [ ] **Aviso de privacidad del cliente** revisado y su versión cargada.
- [ ] **Canales de notificación contratados y verificados**: el cliente conoce y acepta cuáles
      entregan hoy y cuáles no (§6.3).
- [ ] **Las secciones §4 (invariantes), §6 (límites) y §8 (huecos) leídas y firmadas** por quien
      firma este documento.

**Criterio de cierre del proyecto** (`TASKS.md`, DoD del proyecto), citado tal cual porque es el
mismo que gobierna esta entrega:

> *Un cliente con un edificio protegido, un operador que sabe operarlo, un respaldo que se ha
> restaurado de verdad, una cadena de vida medida en hardware real, y un documento firmado que
> dice exactamente qué hace y qué no hace el sistema.*

## 11 · Documentos que forman parte de esta entrega

| Documento | Qué contiene |
|---|---|
| [`MANUAL-OPERACION-TAKAB.md`](MANUAL-OPERACION-TAKAB.md) | Manual del operador del inmueble: estados, botones, qué hacer cuando cae la nube, y **8 huecos declarados** (§7) |
| [`MATRIZ-REQUISITO-TEST.md`](MATRIZ-REQUISITO-TEST.md) | Trazabilidad requisito → prueba, **generada**, con los **18 huecos** (§8) y los **10 gates** (§6.2) |
| [`RESIDENCIA-DE-DATOS-TAKAB.md`](RESIDENCIA-DE-DATOS-TAKAB.md) | Dónde viven los datos y por qué; la respuesta al cliente que pregunta (§6.4) |
| [`BLUEPRINT-TECNICO-TAKAB.md`](BLUEPRINT-TECNICO-TAKAB.md) | Arquitectura canónica; **§14** contiene los invariantes de §4 |
| [`RBAC-TAKAB.md`](RBAC-TAKAB.md) | Los 10 roles y qué puede hacer cada uno |
| [`RUNBOOK-ALTA-DE-ESTACION.md`](RUNBOOK-ALTA-DE-ESTACION.md) | Procedimiento de alta de una estación |
| `runbooks/RUNBOOK-SPOF-02-ruta-hardware-sirena.md` | Diseño y verificación de la sirena con el gabinete muerto (`G-02`) |
| `runbooks/RUNBOOK-auditoria-cierre.md §10` | Registro llenable de los 10 gates físicos |

## 12 · Cambios a este documento

Este documento **se re-emite completo**, con número de versión y fecha, cada vez que:

- un gate del §6.2 se cierra o se declara no aplicable;
- un hueco del §7 o del §8 se cierra;
- un canal del §6.3 pasa a entregar de verdad;
- se contrata alcance de §5.

**Los invariantes del §4 no cambian con una re-emisión.** Cambiarlos exige derogar la viñeta
correspondiente por su nombre, en el documento canónico, con la razón escrita — y hay una prueba
automatizada que impide derogarlos en bloque.

---

## 13 · Firmas

Al firmar, las dos partes declaran haber leído **la Parte II completa** —invariantes, límites,
gates abiertos y huecos declarados— y no solo la Parte I.

| | Por el cliente | Por TAKAB |
|---|---|---|
| Nombre | | |
| Cargo | | |
| Firma | | |
| Fecha | | |

**Testigo / responsable técnico del inmueble**

| Nombre | Cargo | Firma | Fecha |
|---|---|---|---|
| | | | |

---

*Este documento no promete ninguna capacidad que no pueda rastrearse a una prueba automatizada
o a una línea de código citada. Lo que no se pudo sostener está en la Parte II como límite
declarado, no omitido.*
