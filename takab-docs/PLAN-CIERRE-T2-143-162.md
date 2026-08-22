# Plan · Cerrar las cinco fichas implementables de `T-2.143`…`T-2.162`

> **Creado:** 2026-08-22 · **Rama:** `feat/t2-156-sitio-publico-y-correo-legible`
> **Precede a:** el merge de #80 y #81.

---

## OBJETIVO (medible, y es la condición de parada del loop)

**Las cinco fichas en `[x]`, cada una con su criterio verificado contra el sistema real y no
contra el plan, y todo comiteado en la rama con los siete checks de CI en verde.**

```
T-2.146   latido de keep-alive de SPOF-02
T-2.147   el quórum de pánico notifica
T-2.145   alarmas sin treat_missing_data + la contradicción de dlq_depth
T-2.162   el correo de guardia dice qué hacer y dónde
T-2.143   una baja en Cognito arranca el reloj de la PII
```

**No se marca `[x]` ninguna sin:** test que falle antes y pase después, verificado **rompiendo el
código a propósito**; `ruff` y `terraform fmt/validate` limpios; y `test_docs_consistency` en verde
con el conteo cuadrado.

---

## FUERA DE ALCANCE, y por qué — para que nadie lo lea como olvido

| | Motivo |
|---|---|
| `T-2.149` · ingestor SSN | Bloqueo **legal** vivo (atribución del SSN, aparcado por [`D-20`](DECISIONES-MAURICIO.md#d-20)). El técnico caducó: el feed responde por HTTP |
| `T-2.151` · ARCO por teléfono | Exige decidir **cómo se acredita la titularidad de un número**. Es una pregunta de identidad, no de código, y es de Mauricio |
| `T-2.153` · deriva de migraciones | **Ya resuelta** por la sesión paralela en `feat/cierre-decisiones-d04-d19` (`860650f`) |
| Meta (`§4.2`) y Twilio (`§4.3`) | Excluidos por indicación de Mauricio: **no hay número que vincular todavía** |

---

## ORDEN, y no es arbitrario

Se ataca **de mayor a menor riesgo no mitigado**, no de menor a mayor esfuerzo.

### 1 · `T-2.146` — el latido de keep-alive · **primero porque es riesgo de vida**

Es la mitad de software de `G-02`, «la mitigación más importante del sistema». Hoy **no existe**:
sin él, un Pi colgado deja el edificio sin sirena y nada lo suple.

> ### ⚠️ La trampa que [`D-10`](DECISIONES-MAURICIO.md#d-10) dejó escrita, y que hace peligrosa la
> ### implementación ingenua
> **El latido debe probar la liveness del CAMINO DE REFLEJO, no del proceso.** Un cuelgue parcial
> —el hilo del reflejo bloqueado con el lock tomado, los demás hilos vivos— dejaría el reflejo
> muerto mientras un `while True: toggle` sigue latiendo: `K_wd` energizado, ruta de hardware
> **inhibida**, y **sirena muda ante una alerta real**. Es el fallo que `G-02` existe para impedir,
> reintroducido por su propia mitigación.
>
> Cada pulso debe condicionarse a **adquirir y liberar el lock del reflejo y observar progreso**:
> un contador monótono que solo avanza si el camino SASMEX→relé pudo ejecutarse. Pin sugerido
> **BCM 26**, a declarar en `GpioPins`.

**Se puede escribir y probar sin el hardware** (`D-16` aplazó la BOM): el latido es software y su
test vive en la simulación de GPIO que el edge ya usa.

**Test que decide la ficha:** con el hilo del reflejo bloqueado, el latido **debe cesar**. Si sigue
latiendo, la ficha no está hecha aunque todo lo demás pase.

### 2 · `T-2.147` — el quórum de pánico notifica

`D-05` decidió push solo a tácticos y escalado al SOC sin acuse; `D-11` autorizó abrir incidente
`trigger='manual'` para colgar de él la maquinaria de notificación. Hoy **el voto de pánico no toca
`notify/`**: emite el comando firmado, audita, y ahí acaba.

**Cuidado con dos cosas ya decididas:** un incidente `manual` **no puede presentarse como sísmico**
(el titular sale del `trigger`, lección de `T-2.104`), y **no ordena evacuar a nadie** — solo SASMEX
o ≥3 inmuebles simultáneos.

### 3 · `T-2.145` — las alarmas que no declaran qué hacer sin datos

Incluye la contradicción anotada hoy: `dlq_depth` tiene `treat_missing_data = "breaching"` mientras
su comentario, dos líneas arriba, razona `notBreaching`.

> **Cuál es el correcto hay que DECIDIRLO, no elegir el que calle.** `notBreaching` encaja con el
> comentario (una DLQ vacía e inactiva es lo que se quiere) pero también silencia el caso en que
> SQS deja de publicar **porque algo se rompió**. La disyuntiva ya se resolvió una vez en la alarma
> del gabinete mudo, y allí se eligió **vigilar la ausencia**. La decisión que se tome se escribe
> con su razón en el propio recurso.

### 4 · `T-2.162` — el correo de guardia no dice qué hacer

Recién fichada, y **medida en persona**: quien recibió el aviso acababa de ejecutar el ensayo
entero y aun así preguntó cuál era «el código». El aviso debe llevar **la URL del acuse y el
plazo**.

> **El falso arreglo:** poner la URL en el runbook no lo cierra. El runbook no está abierto a las
> 3 a.m.; el correo sí.

### 5 · `T-2.143` — una baja en Cognito no arranca el reloj de la PII

La menos urgente de las cinco y la que menos superficie toca, así que va al final: si el loop se
queda sin tiempo, es la que menos duele dejar a medias.

---

## MÉTODO POR FICHA — el ciclo, y no se salta ningún paso

1. **Leer la ficha entera** antes de tocar nada. Varias traen decisiones ya tomadas que el código
   debe respetar (`D-05`, `D-10`, `D-11`), y desobedecerlas por no leerlas es el defecto más caro
   de esta sesión.
2. **Test primero**, y que falle **por la razón correcta** — no por un `ImportError`.
3. Implementar.
4. **Romper el código a propósito** y comprobar que el test se pone rojo. *Un test que solo pasa no
   prueba que cace nada* — lección de `T-2.152`, `T-2.154` y `T-2.159`.
5. Suite relevante + `ruff` + `terraform` según toque, **sobre `takab_test_ses`** para no chocar con
   la sesión paralela.
6. Cerrar la ficha con lo medido, cuadrar el conteo, comitear con rutas explícitas.

---

## TRAMPAS DE ESTA SESIÓN, ya pagadas — leerlas antes de empezar

- **`pgrep -c pytest` antes de diagnosticar un rojo.** Dos pytest sobre la misma base dan rojos
  falsos indistinguibles de los reales: hoy fueron 6 de 8.
- **Un aviso en prosa envejece cubriendo media casuística** y se lee como cobertura completa. Pasó
  tres veces hoy. Si algo importa, va en una guarda que falle, no en un párrafo.
- **Dos declaraciones del mismo hecho divergen.** Pasó tres veces hoy. Si un dato ya se declara en
  un sitio, derivarlo — nunca teclearlo otra vez.
- **Verificar desde donde mira el destinatario**, no desde el punto privilegiado. Costó una
  denegación de AWS y un diagnóstico entero.
- **La IP de un log no identifica al actor** cuando el agente y la persona salen por la misma.
- **`make` en segundo plano miente por el código de salida** si el último comando es un `tail`.
  Terminar con `exit $rc`.
- **Comitear con rutas explícitas, nunca `git add -A`:** hay otra sesión en el árbol.
- **Comprobar `git branch --show-current` antes de cada commit:** el otro agente cambia de rama.

---

## CONDICIÓN DE PARADA

El loop termina cuando las cinco están en `[x]` **y** `gh pr checks` da los siete en verde.

**Se detiene y pide ayuda humana** —regla de `CLAUDE.md §6`— si tras **tres iteraciones** un
criterio no pasa. No se inventan rodeos que violen las reglas de oro.
