# Traspaso de sesión — dónde se quedó esto y cómo seguir

> **Qué es este documento.** Lo que una sesión nueva necesita saber para continuar **sin
> reconstruirlo leyendo commits**. No sustituye a `TASKS.md` (qué construir) ni a
> `PENDIENTES-MAURICIO.md` (qué está bloqueado en una persona): es **el estado y el método**.
>
> **Última sesión:** 2026-08-10 → 2026-08-14 · **once lotes, todos por PR con los siete checks.**

---

## 0 · ⚠️ LO PRIMERO: la nube va por detrás del repo (2026-08-23)

```
main:  fc06bd5
nube:  eaeb82a          ← tres commits por detrás
```

**No es un olvido, es una decisión tomada:** el rebuild cuesta ~40 min y lo que falta desplegar no
cambia el comportamiento de hoy. Lo que queda fuera del contenedor es el **guard de `T-2.163`** —el
rechazo del directorio SIMULADO por su nombre—. La reconciliación de bajas **sí funciona y está
verificada en la instancia** (`8 cuentas en el directorio`), porque lo que le faltaba era el entorno
y eso lo arregló terraform, no la imagen.

> **Al siguiente cambio de código: reconstruir y desplegar, y el guard va dentro.** `CLOUD_TAG` sale
> de `git rev-parse --short HEAD`, así que **cualquier commit —hasta uno de solo docs— mueve el tag
> y obliga a reconstruir**. No existe «desplegar solo esto».

**Y la lección que costó ese despliegue:** `T-2.143` se cerró con tests en verde, se desplegó y en
producción **no hacía nada**. Se comprobó `docker run … -c "import reconcile"` → OK, y eso acreditó
lo que no era: el job recibe un `db.env` construido al vuelo con **una sola clave**, así que el
código caía al directorio simulado y abortaba cada noche. **Verificar el código DENTRO del
contenedor no es verificar el ENTORNO desde el que se invoca** — hay que mirar
`/opt/takab/bin/takab-*.sh` y el rol de instancia.

---

## 1 · Estado, en tres cifras

| | |
|---|---|
| **Backlog** | ver la cabecera de `TASKS.md` — el conteo lo verifica un test, así que **es fiable** |
| **Suites** | api ~2500 · web ~1800 · edge 1166 · mobile 491 · demo 22 · terraform 50 |
| **Desplegado** | se le pregunta al sistema, no a un documento: `/api/health` para la nube, `fw_running` en `gateways` para el gabinete |

**`main` está protegido con siete checks obligatorios.** ⚠️ Pero `enforce_admins` está en `false`,
así que **un `git push` directo a `main` FUNCIONA y se salta los siete gates** — no da error, no
avisa. Se comprobó por las malas. **Todo va por rama + PR + `gh pr merge`.**

---

## 2 · El método que funcionó, y por qué

**Subagentes en paralelo sobre UN árbol compartido**, con el integrador (la sesión principal)
haciendo el trabajo que no se puede repartir. La receta, que ya sobrevivió a once lotes:

1. **Dos agentes por lote, no cuatro.** Con cuatro se agotó el límite semanal a mitad de camino y
   murieron los cuatro en fase de exploración. Dos terminan.
2. **Una base de tests por agente** (`takab_test_a`, `_b`…). Dos pytest concurrentes sobre la misma
   base se envenenan.
3. **Ficheros disjuntos declarados como límite duro**, nombrando los del otro agente. Sin eso se
   pisan.
4. **Un solo agente crea migraciones por lote.** Dos en paralelo **bifurcan el árbol de alembic**.
5. **Ningún agente comitea.** El integrador comitea con **rutas explícitas**, nunca `git add -A`.
6. **El contrato y la matriz se regeneran UNA vez, al final**, por el integrador.
7. **Los agentes no ejecutan `terraform apply`.** Escriben código; el `apply` es de Mauricio.

**Lo que hace que esto produzca calidad y no volumen:** en el encargo de cada agente se le dice
**qué puede salir mal**, no solo qué hacer. Las mejores correcciones del ciclo vinieron de agentes
que **midieron en vez de obedecer** — y varias veces contradijeron la ficha, con razón.

---

## 3 · Trampas medidas — leer antes de tocar nada

Estas costaron corridas o despliegues. No están en el código; están aquí.

### Del entorno
- **`make test` se detiene en la primera suite que falla.** Un rojo en api deja web, edge y mobile
  **sin ejecutar**, y el log parece una corrida completa.
- **El código de salida de `make` en segundo plano miente.** Escribir `EXIT=$?` a un fichero.
- **`make drift` no puede pasar con el contrato sin comitear**: compara contra HEAD. Solo es
  significativo **después** del commit.
- **La DB de tests es `takab`/`takab_dev`, NO `postgres`.** Usar la base `takab` da ~12 failed +
  90 errors **falsos**.
- **`tests/ops/test_restore_check.py` renombra roles a nivel de CLÚSTER**, así que no se puede
  verificar una migración contra base limpia mientras la suite corre, **aunque sea otra base**.
- **SSO rancio:** `aws sso login` a secas **no basta** — hace falta `aws sso logout` primero. La
  firma es que **`docker login` a ECR funciona y terraform muere** con `InvalidGrantException`.

### De las suites
- **⚠️ La que más veces se cobró a un agente, incluso avisado:** importar de `@takab/sdk` **en el
  cuerpo de un módulo** que alcance a `IncidentTimeline` tumba `useFleet.test.tsx` y
  `useSiteRelays.test.tsx` **a «0 test», en silencio** — el conteo de **ficheros** baja y **no sale
  ni una marca de fallo**. Hacerlo perezoso, y **mirar el conteo de ficheros**, no el de tests.
- **`expo-router` barre `mobile/src/app/**` con `require.context`**: un `*.test.tsx` ahí dentro
  **rompe el bundle** y la app deja de compilar sin que nada se ponga rojo.
- **Un test que compara conjuntos puede pasar por VACUIDAD.** Pasó dos veces este ciclo, una en el
  test que cerraba justo ese defecto. Si puede estar vacío, **que lo declare en voz alta**.
- **El arnés de un test no debe inferir su propio estado de una vista del servidor**
  (`pg_stat_activity` y similares): puede no reflejar lo que acaba de montar. **Que el arnés
  confirme que se montó.**
- **Una guardia textual del tipo `"x" not in fuente` se pone ROJA con solo nombrar `x` en el
  comentario que documenta la decisión.** Le pasó al test de `T-2.136`. Las guardias deben mirar
  **comportamiento** (`SHOW …` sobre la conexión real), no prosa. Y si una guardia analiza código,
  **que quite comentarios y docstrings antes**: un `;` dentro de un docblock dejó fuera del
  análisis justo al caso que buscaba, y pasó en verde sin haberlo mirado.

### De las migraciones y la nube
- **Verde en local ≠ verde en producción, y esto pasó DOS veces:**
  - Ceder el dueño de una función en `db/schema.sql` **mata la 0001** (`SET ROLE takab_migrator`
    no es miembro de `takab_ingest`).
  - La `0001` termina con `GRANT … ON ALL TABLES … TO takab_app`, así que **en base nueva un rol
    sale con permisos que en base existente no tiene**. Con PII eso es grave: se descubrió que
    `takab_app` tenía SELECT sobre una tabla de **hashes de credencial** solo en la nube.
- **`has_table_privilege` devuelve `false` con un grant de COLUMNA.** Por eso un verificador puede
  dar cinco `PASS` sobre una base donde se puede reescribir un check-in de vida.
- **Un permiso IAM que falta no da error: da una conducta silenciosamente peor.** Pasó con las
  reglas IoT y con `sqs:ChangeMessageVisibility`.

---

## 4 · La doctrina que este ciclo destiló

Casi todos los defectos graves del ciclo fueron **la misma familia**: *una superficie que dice
«bien» cuando lo que quiere decir es «no sé»*. Se cerraron **siete**:

| Dónde decía verde | Lo que pasaba de verdad |
|---|---|
| checklist BMS: gas, ascensores, puertas | se pintaba **la última orden**, no el estado del relé |
| `DAMAGE PEOPLE AT RISK` con `kind:'ok'` | personas atrapadas, en verde y en inglés |
| `NOTIFY_NO_RECIPIENTS` | nadie recibió la notificación |
| alarma del inmueble | se inferían cosas que el acuse ya sabía |
| «● LIVE» con el SOC mudo | el hub llevaba minutos sin repartir |
| imagen de consola | llevaba semanas sin poder construirse |
| verificador de restore | cinco `PASS` sobre una base rota |

**La regla que sale de ahí, y que conviene aplicar a lo que quede:** un fallback no puede ser
`ok`. Un estado sin clasificar **pide que alguien lo mire**. Y todo censo que enumere a mano
**acaba divergiendo**: hay que **derivarlo del productor** y hacer que **nombre lo que no sabe
resolver** en vez de callarlo.

---

## 5 · Por dónde seguir

**Software abierto:** ver `TASKS.md`, que está al día. Las candidatas naturales al arrancar:
`T-2.143` (la baja hecha en Cognito no arranca el reloj de la PII), `T-2.84.e`, `T-2.72.a`, y las
tres `[~]` que esperan gates (`T-2.67.c`, `T-2.86.a`, `T-2.99`).

**Lo que NO avanza con software**, y por tanto no se debe usar para medir progreso: todo
`PENDIENTES-MAURICIO.md`. **Dos de esos puntos son de plazo externo** (§4.1 marco normativo, §4.2
alta de WhatsApp) y llevan **toda la sesión sin arrancar**: cada día ahí se suma al final del
proyecto y **ningún lote lo compensa**.

**Y la frase que sigue siendo cierta desde la Fase 1:** *«meter más tareas de software en la ruta
crítica no la acorta ni un día. Lo que la acorta es una tarde con el radio, el relé y un
cronómetro»* (`TASKS.md § RUTA CRÍTICA`). `G-04` sigue abierto.

> **⚠️ `npm run lint` NO incluye prettier.** El job `web` de CI corre además
> `npm run format:check`, así que una PR puede salir verde en local con `lint` +
> `typecheck` + `vitest` + `build` y **roja en CI por formato**. Medido el
> 2026-08-24 con una sola línea mal indentada en `meFixtures.ts`. La verificación
> local de web son CINCO comandos, no cuatro.

