# RUNBOOK — SPOF-02: Ruta de hardware paralela WR-1 → sirena

> **Tarea:** T-1.4 (`edge/hw`) · **Depende de:** T-1.3 (`gpio`) · **Prioridad: ALTA**
> **Criterio de aceptación:** con el Raspberry Pi 5 apagado o colgado, el contacto del WR-1
> **sigue disparando la sirena** (relé de potencia en paralelo). Documentado en este runbook.
> **Estado:** diseño y procedimiento **listos**; la **verificación física es hardware-gated**
> (gate #3 — requiere el receptor WR-1, el relé de potencia, la sirena y el arnés reales).
>
> Es **la mitigación de punto único de falla más importante del sistema** (blueprint §4.7,
> SPOF-02). En un sistema donde fallar cuesta vidas, la alerta audible NO puede depender de que
> el software del Pi esté sano.

---

## 1. Problema (SPOF-02)

El Pi 5 es un punto único de falla del camino de vida: si el proceso se cuelga, el kernel se
bloquea o el Pi muere, el **reflejo software SASMEX→sirena** de T-1.3 (`gpio`) deja de accionar
el relé. Sin mitigación, un Pi muerto = sin sirena ante una alerta SASMEX real.

La regla de oro 1 (CLAUDE.md §2) exige que el camino de activación sea determinista y no dependa
de software complejo; esta ruta lleva ese principio a su conclusión: **una ruta puramente
eléctrica, sin CPU, del contacto WR-1 a la sirena.**

## 2. Principio de diseño

El **contacto seco de alerta del WR-1** (salida de relé del receptor SASMEX) energiza —a través
de un **relé de potencia** dimensionado para la sirena— la sirena, **en paralelo** con el relé
que gobierna el Pi (T-1.3). La sirena tiene por tanto **dos fuentes en lógica OR**:

```
  sirena_ON  =  (relé_del_Pi)  OR  (ruta_de_hardware)
```

La ruta de hardware **no tiene CPU, firmware ni lógica programable**: es contacto → relé → sirena,
con alimentación propia respaldada por UPS. Sobrevive a cualquier fallo de software del Pi.

### 2.1 Dos variantes

| | **A · Paralelo puro** | **B · Fallback con watchdog (RECOMENDADA)** |
|---|---|---|
| Comportamiento | El contacto WR-1 SIEMPRE suena la sirena por hardware, en paralelo al Pi. | La ruta de hardware está **inhibida mientras el Pi está sano**; se **habilita sólo si el Pi muere/se cuelga**. |
| Pi sano | Sirena suena por ambas rutas; la de hardware **no es silenciable** por software. | Sólo el Pi gobierna (T-1.3): reflejo <100 ms, **silenciable** por el operador (botón/LAN). |
| Pi muerto | Sirena suena por la ruta de hardware. ✓ | Sirena suena por la ruta de hardware. ✓ |
| Falsa alarma | El operador **no puede callar** la sirena de hardware hasta que el WR-1 libere el contacto. | El operador **sí puede** silenciar (el Pi está vivo y gobierna). |
| Complejidad | Mínima. | Un relé "Pi-vivo" + detector de latido (monoestable retriggerable). |

**Recomendación: variante B.** Preserva la semántica de silencio del operador de T-1.3 (que la
revisión adversarial de T-1.3 confirmó como criterio: el silencio actúa sobre el patrón que
ejecuta el Pi; la rama que NO se puede silenciar es precisamente esta ruta de hardware, y sólo
debe activarse cuando el Pi realmente no puede gobernar). La variante A es aceptable como diseño
más simple donde la no-silenciabilidad sea tolerable o el contacto WR-1 sea un pulso corto (no
latching) — decidir con la semántica real del WR-1 (gate #3, §7).

## 3. Variante B — diseño eléctrico

### 3.1 Detección de "Pi vivo" por **latido**, no por nivel estático

Un nivel estático (GPIO en HIGH = "vivo") sólo detecta **pérdida de energía** del Pi: un Pi
**colgado** puede dejar el pin en HIGH y parecer vivo. Por eso el Pi emite un **latido** (onda
cuadrada ~1 Hz) en un GPIO de keep-alive, y un **monoestable retriggerable** (temporizador
watchdog dedicado tipo TPS3823 / MAX6369, o 74HC123, o 555 en configuración retriggerable) lo
convierte en un nivel "Pi vivo":

- Llegan pulsos → el monoestable se re-dispara → salida "vivo" → **K_wd energizado**.
- Cesan los pulsos (Pi muerto **o colgado**) → el monoestable expira tras `t_wd` (≈2–3 s) →
  salida "muerto" → **K_wd de-energizado**.

> **REQUISITO CRÍTICO — el latido debe probar la liveness del CAMINO DE REFLEJO, no del
> proceso.** El reflejo de T-1.3 es *event-driven* (el `when_pressed` del WR-1 corre en un hilo de
> callback de gpiozero) y todas las transiciones se serializan en un único `RLock`. Un **cuelgue
> parcial** —el hilo del reflejo bloqueado con el lock tomado, mientras otros hilos siguen vivos—
> deja el reflejo muerto pero un latido ingenuo (`while True: toggle; sleep`) seguiría latiendo →
> K_wd energizado → ruta HW inhibida → **sirena muda ante una alerta real**: exactamente lo que
> SPOF-02 debe impedir. Por eso el latido **NO** puede emitirse desde un bucle independiente: cada
> pulso debe condicionarse a **adquirir+liberar el lock del reflejo y observar progreso** (p.ej. un
> contador de reflejo monótono que sólo avanza si el camino SASMEX→relé pudo ejecutarse). Un
> reflejo en deadlock NO debe poder emitir el latido. Implementación y pin (sugerido **BCM 26**,
> documentar en `GpioPins`) se cierran con el hardware (gate #3); mientras no exista, la variante A
> es el fallback.

### 3.2 Lógica del relé de habilitación

`K_wd` (relé DPDT, energizado = Pi vivo) **inhibe** la ruta directa mientras el Pi está sano:

```
  ruta_hardware_habilitada  =  NOT K_wd            (K_wd de-energizado ⇒ Pi muerto ⇒ habilita)
  sirena_ON  =  relé_del_Pi(GPIO)  OR  ( contacto_WR-1  AND  NOT K_wd )
```

**Dirección fail-safe:** si la **propia alimentación de K_wd** falla, K_wd de-energiza →
`NOT K_wd` = verdadero → la ruta de hardware queda **habilitada** (falla hacia *poder* alertar).
Coherente con "en la duda, alertar" en un camino de vida.

### 3.3 Coexistencia con el silencio del operador (T-1.3) y SPOF-07

| Escenario | K_wd | Ruta HW | Quién suena / silencia |
|---|---|---|---|
| Pi sano, sin alerta | energizado | inhibida | nada |
| Pi sano, alerta SASMEX | energizado | inhibida | relé del Pi (reflejo <100 ms); **operador puede silenciar** |
| Pi sano, operador silenció | energizado | inhibida | silenciado ✓ (el Pi vive → ruta HW sigue inhibida) |
| **Pi muerto/colgado, alerta** | de-energizado | **habilitada** | **sirena por hardware**; NO silenciable (el Pi no puede gobernar) — correcto |

Así se resuelve la aparente tensión con SPOF-07 (fail-safe de la sirena = **NO**: una falla del
Pi no la deja sonando): el relé del **Pi** es NO (de-energizado = mudo), y la sirena sólo suena con
el Pi muerto **si además hay un contacto WR-1 asertado** — es decir, ante una alerta real, no por
el mero fallo del Pi.

### 3.4 Diagrama de cableado (variante B)

```
  WR-1 (receptor SASMEX)
   └─ contacto seco de ALERTA ─────────────┐
                                           │            ┌──────────────┐
   Pi 5 GPIO keep-alive (latido ~1Hz) ──▶ [ Monoestable ]──▶ bobina K_wd
                                           │  retrig. t_wd │            │
                                           │            └──────────────┘
                                           │                   │ contacto NC de K_wd
                                           │                   │ (cerrado ⇔ Pi MUERTO)
                                           ▼                   ▼
                                     ┌─────────────────────────────┐
                                     │  Relé de POTENCIA de sirena │◀── Pi GPIO relay_siren (T-1.3, en paralelo)
                                     └───────────────┬─────────────┘
                                                     ▼
                                        SIRENA / ESTROBO  (alimentación respaldada por UPS)
```

- El contacto de **alerta** del WR-1 sólo llega a la bobina del relé de potencia **a través del
  contacto NC de K_wd** (cerrado cuando el Pi está muerto). En paralelo, el `relay_siren` del Pi
  (T-1.3) energiza el mismo relé de potencia por su cuenta.
- El contacto de **prueba periódica** del WR-1 (CIRES, SPOF-03) **NO** debe llegar a esta ruta
  (no debe sonar la sirena); enrutarlo sólo a la entrada de heartbeat del Pi (`gpio`).

## 4. Lista de materiales (BOM) mínima

| Ítem | Nota |
|---|---|
| Relé de potencia de sirena | Contactos rated para el **pico de corriente de la sirena elegida** (coordinar con SPOF-04/UPS); bobina compatible con la fuente respaldada. Diodo/varistor de flyback. |
| Relé K_wd (DPDT) + monoestable/watchdog IC retriggerable | `t_wd` ≈ 2–3 s. Alimentado desde la fuente respaldada, **no** desde el riel del Pi. |
| Fuente respaldada por UPS | Independiente de la alimentación lógica del Pi; dimensionar para sirena (§SPOF-04). |
| Borneras, fusible/PTC, varistores, caja | Separación de bajo voltaje (lógica) y potencia (sirena). |
| Cableado del contacto seco WR-1 (alerta y prueba en pares separados) | Semántica real = gate #3 (§7). |

## 5. Alimentación (SPOF-04)

La ruta de hardware, K_wd, el relé de potencia y la sirena deben alimentarse desde el **riel
respaldado por la UPS**, **nunca** desde la alimentación lógica del Pi. Dimensionar la UPS para el
**pico de corriente de arranque de la sirena** (validar contra la sirena elegida — SPOF-04).
Apagado limpio del Pi al 10% de batería con last-will MQTT no debe cortar esta ruta.

## 6. Procedimiento de verificación (hardware-gated · gate #3)

> **Seguridad:** trabajo con potencia de sirena. Corte de energía, bloqueo/etiquetado, EPP
> auditivo. Verificar separación bajo-voltaje/potencia antes de energizar.

Registrar cada prueba en la tabla del §8.

1. **Pi vivo — camino software (T-1.3).** Con el Pi corriendo `takab-gpio`, asertar el contacto de
   **alerta** del WR-1 (botón de prueba del WR-1 o simulador de contacto en seco). Esperado:
   sirena suena por el relé del Pi, latencia **<100 ms** (medir); el **silencio** del operador
   (botón/LAN) la calla; K_wd energizado → **ruta de hardware inhibida** (verificar con multímetro
   en el contacto NC de K_wd: abierto).
2. **Pi muerto — SPOF-02 (la prueba clave).** Apagar el Pi (o cortar el latido de keep-alive).
   Esperado: el monoestable expira (~`t_wd`), K_wd de-energiza, su contacto NC **cierra** →
   **ruta de hardware habilitada**. Asertar el contacto de alerta del WR-1 → **la sirena suena SIN
   el Pi**. Medir latencia. Confirmar que el software **no** puede silenciarla (el Pi está muerto)
   — comportamiento correcto.
3. **Recuperación (SPOF-02 b) — con alerta NUEVA y con alerta SOSTENIDA.** Reencender el Pi; el
   watchdog de hardware (config §9) lo reinicia **<15 s**; el latido se restablece → K_wd
   re-energiza → ruta de hardware se **inhibe** de nuevo; el Pi retoma el gobierno.
   - **3a. Alerta nueva:** una alerta posterior la maneja el software (silenciable). ✓
   - **3b. Alerta SOSTENIDA a través del reinicio (fail-dangerous).** Mantener el contacto de
     **alerta** del WR-1 **cerrado durante todo el reinicio**. Como el reflejo es *edge-triggered*,
     no habrá flanco nuevo tras el arranque; el software **debe** re-tomar la alerta viva **antes**
     de que la ruta HW se re-inhiba. `gpio._on_start` **lee el nivel del contacto** (`is_pressed`)
     y siembra el reflejo si ya está asertado (T-1.3, corregido). **Verificar que la sirena es
     continuamente audible a través del traspaso HW→software**, sin ventana de silencio. Sin esta
     siembra, la sirena quedaría muda a mitad de una alerta viva al recuperarse el Pi.
4. **Pi colgado — total (no sólo apagado).** Simular un cuelgue total (`kill -STOP` al proceso o
   congelar el latido sin cortar energía). Esperado: idéntico a (2) — el latido cesa, K_wd libera,
   la ruta de hardware se habilita. Valida que se detecta **hang**, no sólo pérdida de energía.
4b. **Pi colgado — PARCIAL (la prueba que el latido ingenuo NO pasaría).** Bloquear SÓLO el camino
   de reflejo (p.ej. mantener tomado el `RLock` desde otro hilo, o bloquear el `relay.on()`) dejando
   vivos los demás hilos. Esperado: como el latido está condicionado a la liveness del reflejo
   (§3.1), **cesa** aunque el proceso siga corriendo → K_wd libera → **ruta de hardware engancha** →
   asertar el contacto de alerta suena la sirena por hardware. Si el latido siguiera (latido
   ingenuo), la sirena quedaría muda: ese es el fallo que este paso debe cazar.
5. **Fallo de alimentación de K_wd.** Cortar la alimentación del propio K_wd. Esperado: K_wd
   de-energiza → ruta de hardware **habilitada** (fail-safe hacia alertar). Restaurar.
6. **Pulso de prueba CIRES (SPOF-03) — con el Pi MUERTO.** La prueba SÓLO es válida con la **ruta
   de hardware HABILITADA** (K_wd de-energizado): con el Pi vivo, K_wd inhibe la ruta y la sirena
   estaría muda *pase lo que pase* → una falsa aprobación que no detectaría un cableado erróneo del
   contacto de prueba en la ruta de hardware. Por eso: **apagar el Pi** (ruta HW habilitada) y
   asertar el contacto de **prueba** del WR-1. Esperado: la sirena **NO** suena (el contacto de
   prueba no está cableado a la ruta de hardware). Repetir opcionalmente con el Pi vivo (el Pi lo
   registra como heartbeat de mantenimiento). Sin la variante Pi-muerto, un contacto de prueba
   mal cableado sonaría la sirena en cada pulso periódico de CIRES tras cualquier muerte del Pi.
7. **Semántica real del WR-1 (gate #3).** Con el receptor real, medir **duración, latching y
   rebote** del contacto de alerta (¿cuánto tiempo suena la sirena de hardware tras un evento?) y
   la **cadencia** de la prueba periódica. Coordinar con CIRES. Ajustar `t_wd` y, si el contacto es
   momentáneo, evaluar un enclavamiento de sirena de N minutos en la ruta de hardware.

## 7. Decisiones abiertas (para Mauricio / CIRES)

- **Variante A vs B** (§2.1): recomendada **B**; A si la no-silenciabilidad es aceptable.
- **Semántica del contacto WR-1** (gate #3): asignación alerta/prueba, duración, latching, rebote
  → fija `t_wd`, el enclavamiento de la sirena de hardware y el cableado de pares.
- **Rating de sirena y dimensionado de UPS** (SPOF-04): pico de corriente de la sirena elegida.
- **Pin de keep-alive** y su emisión por software (`gpio` togglea el latido) — implementar al
  cablear (gate #3).

## 8. Registro de verificación (llenar con hardware)

| # | Prueba | Resultado esperado | Medido | OK/NO | Fecha/inicial |
|---|---|---|---|---|---|
| 1 | Pi vivo → sirena por software, silenciable, <100 ms | — | | | |
| 2 | **Pi muerto → sirena por hardware** | suena sin Pi | | | |
| 3a | Recuperación <15 s, alerta NUEVA la maneja el software | — | | | |
| 3b | **Recuperación con alerta SOSTENIDA: sirena continua en el traspaso HW→SW** | sin silencio | | | |
| 4 | Pi colgado (total) → ruta HW habilitada | suena sin Pi | | | |
| 4b | Cuelgue PARCIAL (reflejo bloqueado, otros hilos vivos) → latido cesa, ruta HW engancha | suena sin Pi | | | |
| 5 | Fallo de K_wd → ruta HW habilitada (fail-safe) | habilitada | | | |
| 6 | Pulso de prueba CIRES **con Pi muerto** → sirena NO suena por HW | no suena | | | |
| 7 | Semántica WR-1 medida (duración/latching/rebote) | — | | | |

## 9. Mitigaciones complementarias de SPOF-02 (b, c, d)

- **(b) Watchdog de hardware BCM2712** — reinicia el Pi si el kernel/systemd se cuelga:
  - `/boot/firmware/config.txt`: `dtparam=watchdog=on`
  - `/etc/systemd/system.conf.d/watchdog.conf`: `RuntimeWatchdogSec=10` · `RebootWatchdogSec=15`
  - Unidad del proceso de vida con reinicio automático: ver `edge/systemd/takab-gpio.service`.
- **(c) Boot desde NVMe/eMMC industrial** — nunca microSD de consumo.
- **(d) Raíz de sólo lectura** (`overlayroot`) + partición de datos `ext4 data=journal`.

> El camino de vida vive en el **proceso mínimo `takab-gpio`** (T-1.3): sin ObsPy/NumPy, arranca
> <1 s, reinicio automático por systemd. Esta ruta de hardware es su **respaldo independiente**
> para el caso en que ni el proceso ni el Pi puedan actuar.

---

*Referencias: `takab-docs/BLUEPRINT-TECNICO-TAKAB.md` §4.7 (SPOF-01…07), `CLAUDE.md` §2 (reglas de
oro), T-1.3 (`edge/takab_edge/gpio`), `takab-docs/TASKS.md` T-1.4. Verificación final: gate #3.*
