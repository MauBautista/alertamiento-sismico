# Plan · Cerrar las fichas implementables de `T-2.143`…`T-2.162`

> **Creado:** 2026-08-22 · **Rama:** `feat/t2-156-sitio-publico-y-correo-legible`
> **Precede a:** el merge de #80 y #81.

---

## OBJETIVO (medible, y es la condición de parada del loop)

**Las CUATRO fichas en `[x]`, cada una con su criterio verificado contra el sistema real y no
contra el plan, y todo comiteado en la rama con los siete checks de CI en verde.**

```
T-2.162   el correo de guardia dice qué hacer y dónde
T-2.145   alarmas sin treat_missing_data + la contradicción de dlq_depth
T-2.151   ARCO por teléfono, ya con D-23 decidida
T-2.143   una baja en Cognito arranca el reloj de la PII
```

*(`T-2.146` y `T-2.147` salieron del objetivo en la primera iteración: ver la corrección de abajo.)*

**No se marca `[x]` ninguna sin:** test que falle antes y pase después, verificado **rompiendo el
código a propósito**; `ruff` y `terraform fmt/validate` limpios; y `test_docs_consistency` en verde
con el conteo cuadrado.

---

## FUERA DE ALCANCE, y por qué — para que nadie lo lea como olvido

| | Motivo |
|---|---|
| `T-2.149` · ingestor SSN | Bloqueo **legal** vivo (atribución del SSN, aparcado por [`D-20`](DECISIONES-MAURICIO.md#d-20)). El técnico caducó: el feed responde por HTTP |
| ~~`T-2.151` · ARCO por teléfono~~ | **ENTRA EN ALCANCE (2026-08-22)**: la decisión que faltaba está tomada — [`D-23`](DECISIONES-MAURICIO.md#d-23), la titularidad la acredita el cliente institucional |
| `T-2.153` · deriva de migraciones | **Ya resuelta** por la sesión paralela en `feat/cierre-decisiones-d04-d19` (`860650f`) |
| Meta (`§4.2`) y Twilio (`§4.3`) | Excluidos por indicación de Mauricio: **no hay número que vincular todavía** |

---

## ⚠️ CORRECCIÓN (2026-08-22, primera iteración del loop) — el plan se escribió sobre un resumen viejo

**`T-2.146` y `T-2.147` NO están abiertas.** Sus cabeceras dicen `[ ]` y sus criterios dicen otra
cosa:

| Ficha | Criterios | Lo único abierto |
|---|---|---|
| `T-2.146` | **7 hechos, 1 abierto** | `DIFERIDO` — pintar el latido en el panel |
| `T-2.147` | **18 hechos, 1 abierto** | `DIFERIDO` — el botón en la app |

El latido de `SPOF-02` **está escrito desde el 2026-08-16**, con su test negativo verificado contra
sí mismo (se parcheó el sondeo para simular un latido ingenuo y el test falló con el mensaje
correcto). Y el quórum de pánico **sí notifica**.

**De dónde salió el error:** el plan puso `T-2.146` primero *«porque es riesgo de vida, y hoy no
existe»*, citando `PENDIENTES §3.1`, que dice «el latido de keep-alive no está escrito». **Esa
línea está caducada.** Se planificó sobre el resumen y no sobre la ficha — el mismo defecto que
esta sesión ya cazó tres veces en otras formas.

**Y el orden se cae con la premisa.** Lo que queda de `T-2.146` no es riesgo de vida: es pintar en
un panel el estado de un hardware **que no existe en ningún gabinete**. Es el punto de MENOR valor
del lote, no el mayor.

### Alcance real: TRES fichas abiertas, más dos diferidos con razón escrita

**Se cierran:** `T-2.145`, `T-2.162`, `T-2.143`.

**Los dos `DIFERIDO` NO se fuerzan**, y no por pereza:

- `T-2.146` · el panel. Su nota dice que añadir el campo a `status()` **obliga a pintarlo** —lo caza
  `test_panel_render_census`— y que **dónde** lo gobierna `ESPECIFICACION-PANEL-GABINETE.md`.
  *«Inventar un elemento del camino de vida sin leer su spec es peor que no pintarlo.»* Y no bloquea
  el cableado: el dato ya viaja por las dos costuras.
- `T-2.147` · el botón en la app. Mismo razonamiento, en `ESPECIFICACION-APP-MOVIL.md`.

**Ninguna de las dos se marca `[x]`**: tienen trabajo real pendiente, declarado y con su razón. Lo
que se corrige es **el orden del plan y la expectativa**, no el estado de las fichas.

---

## ORDEN de las tres que quedan

Se ataca **de mayor a menor riesgo no mitigado**. Tras la corrección de arriba, el lote ya no
contiene nada de riesgo de vida: lo que queda son tres formas distintas de que un aviso no llegue
o no se entienda.

### 1 · `T-2.162` — el correo de guardia no dice qué hacer

**Primero, porque es el único defecto del lote que se midió sobre una persona.** Quien recibió el
aviso acababa de ejecutar el ensayo entero —acuñó la credencial, abrió la página, acusó un aviso
veinte minutos antes— y aun así preguntó cuál era «el código». El correo no menciona el acuse ni su
URL.

El aviso debe llevar **qué hacer, dónde y con cuánto plazo**.

> **El falso arreglo:** poner la URL en el runbook no lo cierra. El runbook no está abierto a las
> 3 a.m.; el correo sí.

### 2 · `T-2.145` — las alarmas que no declaran qué hacer sin datos

Tres alarmas sin `treat_missing_data` declarado, más la contradicción anotada hoy: `dlq_depth`
tiene `breaching` mientras su comentario, dos líneas arriba, razona `notBreaching`.

> **Cuál es el correcto hay que DECIDIRLO, no elegir el que calle.** `notBreaching` encaja con el
> comentario (una DLQ vacía e inactiva es lo que se quiere) pero también silencia el caso en que
> SQS deja de publicar **porque algo se rompió**. La disyuntiva ya se resolvió una vez en la alarma
> del gabinete mudo, y allí se eligió **vigilar la ausencia**. La decisión se escribe con su razón
> en el propio recurso.

Va segunda porque toca `modules/observability`, que esta sesión acaba de cambiar dos veces —umbral
del backup base e historial de SES—: conviene hacerlo con el módulo fresco en la cabeza.

### 3 · `T-2.151` — ARCO por teléfono, con `D-23` ya decidida

La decisión que la bloqueaba está tomada: **la titularidad la acredita el cliente institucional**.
Queda cablear `forget_msisdn()` al flujo, con dos guardas que la decisión impone y que valen más
que el cableado:

> **La respuesta no puede ser un oráculo de existencia.** A quien no acredita se le contesta lo
> mismo **siempre** — un «no encontrado» frente a un «borrado» convertiría el endpoint en un
> buscador de personas. Test que compare las dos respuestas byte a byte.
>
> **Y sin acreditación no se ejecuta:** borrar el consentimiento de un tercero destruiría la prueba
> de su base legal, que es lo que `D-07` construyó el cripto-borrado para preservar.

### 4 · `T-2.143` — una baja en Cognito no arranca el reloj de la PII

La que menos superficie toca y la única que no es de avisos, así que va al final: si el loop se
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

## ✅ RESULTADO (2026-08-22) — las cuatro cerradas

| Ficha | Lo que resultó ser, cuando se abrió |
|---|---|
| `T-2.162` | Cerrada antes del loop |
| `T-2.145` | **No era ruido: era MUDEZ.** `iot_rule_errors` llevaba **14 días clavada en ALARMA** (una sola transición en toda su vida, el 2026-08-08 09:39 CST) porque su metric filter no publica nada sin errores. Como SNS solo notifica transiciones, un error real de enrutado IoT **no habría mandado un correo**. Las tres pasan a `notBreaching`. Colateral: la descripción de `ec2_cpu` prometía 15 min y la config exigía 25; y el censo contaba las aserciones **comentadas** como cobertura |
| `T-2.151` | **Un endpoint y no dos.** Diferir la ejecución obligaría a guardar el índice del número en una tabla append-only, donde sobreviviría al borrado que lo motivó. `affected` constante = no hay oráculo de existencia. La acreditación vive en la RLS, medida con una constancia real pero de otra clase |
| `T-2.143` | Reconciliación dentro del job que ya corre solo; `--sin-reconciliar` **apaga**, no enciende. Lo difícil no era dar de baja: era **negarse con una lectura a medias** — directorio caído, paginación sin fin, pool vacío |

### Lo que enseñó romper el código a propósito

Doce sabotajes. **Cuatro no mordieron**, y esos fueron los que valieron:

1. Dos parches pegaron en la ocurrencia equivocada del texto buscado y **nunca tocaron el código
   bajo prueba** (`proof_ref=body.proof_ref` sale dos veces; el segundo era el mío). Un sabotaje
   que no se comprueba que muerde vale lo mismo que no haberlo hecho.
2. Un `grep` de veredicto no casaba **por los códigos de color** de pytest: tres sabotajes
   parecieron no producir evidencia cuando lo que fallaba era el lector.
3. Una aserción buscaba la palabra «directorio», que sale en **los dos** motivos de aborto.
   Tercera vez en la sesión del defecto `"5 min"` ⊂ `"15 min"`.
4. Un `ON CONFLICT DO NOTHING` era **inalcanzable** desde el flujo: un cinturón que nunca se
   abrocha. Se prueba ahora ejecutando la sentencia a mano.

Y **dos correcciones vinieron del esquema, no del código**: `user_profiles.user_sub` es PK global
(un sub pertenece a un solo cliente, así que el test que sembraba el mismo en dos tenants pasaba
por vacuidad), y toda fila del padrón nace de un token verificado — o sea de alguien que **tuvo**
cuenta, que es lo que hace exacto el `via = 'account_deleted'`.

### Pendiente de una mano humana

`terraform apply` del módulo `observability`: **hasta que se aplique, `iot_rule_errors` sigue muda
en la nube.** Plan medido: 5 cambios en sitio, 0 destroy.

---

## CONDICIÓN DE PARADA

El loop termina cuando las cinco están en `[x]` **y** `gh pr checks` da los siete en verde.

**Se detiene y pide ayuda humana** —regla de `CLAUDE.md §6`— si tras **tres iteraciones** un
criterio no pasa. No se inventan rodeos que violen las reglas de oro.
