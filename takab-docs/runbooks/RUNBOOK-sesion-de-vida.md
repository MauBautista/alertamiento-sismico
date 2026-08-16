# Runbook · Sesión de vida — `G-01`, `G-02`, `G-04`

> **Ficha:** [`T-2.92`](../TASKS.md) · **Pendiente:** [`PENDIENTES-MAURICIO §3.1`](../PENDIENTES-MAURICIO.md)
> **Dueño:** Mauricio · **Es la tarea que decide si el producto es real.**

---

## ⚠️ Veredicto antes de agendar nada: **esto no es una sesión, son tres cosas distintas**

La ficha agrupa `G-01`, `G-02` y `G-04` como si se cerraran en una visita. **No se puede**, y
conviene saberlo antes de reservar una tarde y descubrirlo con el gabinete delante. Lo verificado
contra el equipo real el **2026-08-16**:

| Gate | Estado real | Qué falta |
|---|---|---|
| **`G-01`** · restart en frío | **SE PUEDE HACER HOY** | nada — 20 minutos |
| **`G-04`** · WR-1 real, <100 ms a sirena | **a medias** | una sirena de verdad; y una transmisión real de CIRES |
| **`G-02`** · sirena con el Pi APAGADO | **NO se puede probar** | **el hardware no existe** — y falta software |

> ### El hallazgo que importa
> **`G-02` no es una prueba pendiente: es una obra pendiente.** La ruta de hardware que hace sonar
> la sirena sin el Pi —relé `K_wd`, monoestable retriggerable, relé de potencia, riel respaldado por
> UPS— **no está construida**, y el **latido de keep-alive** que la gobierna **no está escrito**: no
> hay pin de latido en el mapa de pines (`GpioPins` tiene `wr1_contact`, los dos botones y los cinco
> relés, y ninguno más).
>
> Y es, en palabras de la propia ficha, **«la mitigación más importante del sistema»**: si la sirena
> solo suena cuando el Pi vive, todo el diseño determinista depende de un solo aparato encendido.

---

## Lo que sí está verificado hoy, y no es poco

Medido contra el gabinete `gw-dev-0001` el 2026-08-16:

| | |
|---|---|
| Backend GPIO | **`LGPIOFactory (lgpio)` real** — `TAKAB_EDGE_DEV_MODE=false`, sin caída a sysfs |
| Dueño de los pines | `takab-gpio`, proceso dedicado (traspaso hecho, `D-04`) |
| Relés declarados | `siren`, `strobe` — `reason: ok`, `missing: []` |
| Presupuesto de reflejo | `reflex_budget_s = 0.100` — el umbral de `G-04`, ya cableado en el código |
| Reflejo contacto → relé | **6.65 ms** y **4.16 ms**, medidos con el WR-1 real |

**O sea: la mitad eléctrica de `G-04` ya está medida y pasa con dos órdenes de magnitud de margen.**
Lo que falta de ese gate no es velocidad — es **que haya una sirena al final del cable** y que la
semántica del contacto se observe contra CIRES.

---

# BLOQUE A · `G-01` — restart en frío · **HOY, ~20 minutos**

**Qué demuestra:** que el gabinete se recupera solo de un corte de energía sin que nadie lo toque.
Sin esto, cada apagón es una visita técnica.

### A.0 · Antes de reiniciar — foto del estado

```bash
ssh takab-pi5
systemctl is-active takab-gpio takab-edge
curl -s http://127.0.0.1:8080/api/status | python3 -m json.tool | head -30
```

Anota que ambos digan `active`. Si alguno no lo está, **para**: `G-01` mide la recuperación, no el
arranque desde un estado roto.

### A.1 · El reinicio

```bash
sudo reboot
```

Espera ~60 s y vuelve a entrar (`ssh takab-pi5`).

### A.2 · Las cinco comprobaciones — **todas o no pasa**

```bash
# 1 y 2 · los dos procesos vivos, sin haber peleado por arrancar
systemctl is-active takab-gpio takab-edge
systemctl show -p NRestarts --value takab-gpio takab-edge

# 3 · backend lgpio REAL, sin caída silenciosa a sysfs/native
sudo journalctl -u takab-gpio -b --no-pager | grep -i "pin factory"

# 4 · alguien sostiene los pines, y es el proceso correcto
sudo journalctl -u takab-gpio -b --no-pager | grep -iE "cerrojo|dueño" | head -5
```

| # | Criterio de aprobado |
|---|---|
| 1 | `takab-gpio` **y** `takab-edge` en `active` |
| 2 | `NRestarts` bajo. **Un número alto = pelea por el cerrojo, no éxito** |
| 3 | dice **`LGPIOFactory (lgpio)`**. Si dijera `native`, `sysfs` o `Mock`, **`G-01` NO pasa** |
| 4 | el cerrojo lo sostiene `takab-gpio` |
| 5 | los relés responden — abajo |

### A.3 · Quinta comprobación: que los relés de verdad se muevan

Abre el panel en un navegador de la LAN: **`http://192.168.3.91:8080`** y pulsa la prueba de
actuadores. El resultado por relé aparece en la tarjeta «Última prueba de actuadores».

> **🔊 ESTO SUENA.** La prueba local de actuación **hace sonar la sirena y destellar el estrobo** —
> no es una alerta real (no publica evento ni abre incidente), pero **es audible**. Avisa a quien
> esté cerca. Si el gabinete estuviera en un edificio con gente, esto va con aviso previo.

**Aprobado si:** cada relé instalado reporta su resultado y la hora del ensayo, y `relays_status`
sigue diciendo `reason: ok`.

### A.4 · Registrar

Marca `G-01` en la tabla de `RUNBOOK-auditoria-cierre.md` con la fecha y la evidencia (pega la
salida del punto 3 — es la que prueba que no hubo degradación silenciosa del backend).

---

# BLOQUE B · `G-04` — lo que se puede medir hoy y lo que no

### B.1 · Medible hoy: el reflejo contacto → relé

Con el **botón de prueba del propio WR-1** (o el modo prueba por LAN, `/api/test-mode`), asertar el
contacto y leer:

```bash
curl -s http://127.0.0.1:8080/api/status | python3 -c "import sys,json;print(json.load(sys.stdin)['latencies'])"
```

`reflex_s` debe quedar **muy por debajo de `reflex_budget_s` (0.100)**. Referencia ya obtenida:
**6.65 ms** y **4.16 ms**.

> **Sale `null` si no ha habido disparo desde el último arranque del proceso.** No es un fallo: es
> que no hay nada que medir todavía.

### B.2 · **No** medible hoy — y son las dos mitades que faltan

1. **`contacto → relé → SIRENA < 100 ms`.** Lo medido llega **al relé, no al altavoz**. Cerrar el
   gate exige una **sirena real sobre un relé de potencia**. Hoy el gabinete saca audio por el
   **jack**, que sirve para voceo pero **no es la sirena** del gate.
2. **Semántica real del WR-1 contra una transmisión de CIRES:** duración del contacto, si engancha
   (*latching*), rebote, y la cadencia del pulso periódico de prueba. **Esto no depende de ti: hay
   que coordinarlo con CIRES o esperar a un evento real.** De aquí sale el valor de `t_wd` del
   Bloque C, así que **conviene arrancarlo ya** aunque el hardware no esté.

---

# BLOQUE C · `G-02` — **es una obra, no una sesión**

**Qué demuestra:** que la sirena suena **con el Pi apagado**. Es el respaldo que impide que todo el
diseño determinista cuelgue de un solo aparato encendido.

> ✅ **Variante decidida el 2026-08-16: (B), fallback con watchdog**
> ([`D-10`](../DECISIONES-MAURICIO.md)). La ruta de hardware queda **inhibida mientras el Pi está
> sano** y engancha sola si muere o se cuelga — así el operador conserva el silencio ante una falsa
> alarma. La lista de abajo **ya incluye** lo que (B) añade sobre (A): el `K_wd` y el monoestable.

### C.1 · Lo que hay que comprar

| Ítem | Nota |
|---|---|
| **Relé de potencia de sirena** | contactos para el **pico de arranque** de la sirena elegida; diodo/varistor de flyback |
| **Relé `K_wd` (DPDT)** + **monoestable retriggerable** | `t_wd` ≈ 2–3 s. TPS3823 / MAX6369 / 74HC123 / 555 retriggerable |
| **Fuente respaldada por UPS** | **independiente del riel lógico del Pi**; dimensionada para el pico de la sirena |
| **Sirena** | la de verdad; su rating fija los dos puntos anteriores |
| Borneras, fusible/PTC, varistores, caja | separación física bajo-voltaje / potencia |

> **La regla de alimentación que no se negocia:** la ruta de hardware, `K_wd`, el relé de potencia y
> la sirena van al **riel respaldado por UPS**, **nunca** al del Pi. Si cuelgan del Pi, la ruta que
> existe para sobrevivir a la muerte del Pi muere con él.

### C.2 · Lo que hay que escribir (software, es mío)

El **latido de keep-alive**. Y no es un `while True: toggle`:

> **El latido debe probar la liveness del CAMINO DE REFLEJO, no del proceso.** Un cuelgue parcial
> —el hilo del reflejo bloqueado con el lock tomado, los demás vivos— dejaría el reflejo muerto
> mientras un latido ingenuo sigue latiendo: `K_wd` energizado, ruta de hardware **inhibida**, y
> **sirena muda ante una alerta real**. Que es exactamente lo que `G-02` existe para impedir.
>
> Cada pulso debe condicionarse a **adquirir y liberar el lock del reflejo y observar progreso**
> (un contador monótono que solo avanza si el camino SASMEX→relé pudo ejecutarse). Pin sugerido:
> **BCM 26**, a declarar en `GpioPins`.

### C.3 · Las pruebas, cuando exista

Están escritas paso a paso en el **§6 de
[`RUNBOOK-SPOF-02-ruta-hardware-sirena.md`](RUNBOOK-SPOF-02-ruta-hardware-sirena.md)**, con su
tabla de registro en el §8. Las tres que más fácilmente se dan por buenas sin serlo:

- **3b · alerta SOSTENIDA a través del reinicio.** El reflejo es *edge-triggered*: si el contacto ya
  está cerrado cuando el Pi arranca, no hay flanco nuevo. Hay que **ver que la sirena no se calla**
  en el traspaso hardware→software.
- **4b · cuelgue PARCIAL.** Bloquear solo el camino de reflejo. Es la prueba que un latido ingenuo
  **no pasaría**, y por eso es la que valida el diseño de C.2.
- **6 · pulso de prueba de CIRES con el Pi MUERTO.** Con el Pi vivo, `K_wd` inhibe la ruta y la
  sirena estaría muda *pase lo que pase* — una falsa aprobación que no detectaría un contacto de
  prueba mal cableado. Solo vale con la ruta de hardware **habilitada**.

---

## Orden recomendado

1. **Hoy:** Bloque A (`G-01`). Veinte minutos, cero compras.
2. **Esta semana:** abrir la conversación con **CIRES** (Bloque B.2) — es plazo externo, como §4.1
   y §4.2, y de ahí sale el `t_wd` del Bloque C.
3. ✅ **Variante decidida** — (B), `D-10`. **La lista de C.1 ya se puede comprar.**
4. **Comprar y montar**, y solo entonces la sesión de `G-02` + el cierre de `G-04`.

> **Nota sobre el orden 2↔4:** se puede comprar antes de tener la medición de CIRES. Lo único que
> esa medición ajusta es el **`t_wd`** del monoestable (2–3 s es el rango de partida) y, si el
> contacto resultara ser un pulso muy corto, si conviene un **enclavamiento de N minutos** en la
> ruta de hardware. Ninguna de las dos cosas cambia qué piezas comprar.

## Registro

| Gate | Fecha | Evidencia | OK |
|---|---|---|---|
| `G-01` restart en frío | | | |
| `G-04` reflejo contacto→relé | | 6.65 ms / 4.16 ms (previo) | |
| `G-04` contacto→relé→sirena <100 ms | | | |
| `G-04` semántica WR-1 vs CIRES | | | |
| `G-02` sirena con Pi apagado | | | |
