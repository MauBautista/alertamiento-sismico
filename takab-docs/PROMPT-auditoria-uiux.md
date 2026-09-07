# PROMPT — Auditoría UI/UX de las tres superficies y plan de reforma visual

> **Esta es la SESIÓN 1 de una tanda. No se toca código en esta sesión.** Produce dos
> documentos y las fichas del plan. Las mejoras visuales se ejecutan después, **una superficie
> por sesión**, con la plantilla del §9.
>
> **Por qué partido y no todo junto:** auditar, reparar y rediseñar en la misma sesión hace
> imposible saber después qué se encontró, qué se rompió al arreglar y qué se cambió por
> gusto. Este proyecto ya pagó ese precio con superficies que se entregaron sin estilos y
> nadie lo notó (`T-1.72`, `T-1.73`).

---

## 1 · Alcance

Tres superficies, con **licencia de cambio distinta cada una**. Esto es lo primero que hay
que interiorizar:

| Superficie | Dónde vive | Licencia de cambio |
|---|---|---|
| **Consola SOC** | `web/` | **AMPLIA.** Es la superficie comercial. Se puede reestructurar, animar y repensar jerarquías. |
| **App móvil** | `mobile/` | **MEDIA.** Se pule y se anima; los flujos de vida (alerta, pánico, acuse) no se reordenan sin ficha propia. |
| **Panel LAN del gabinete** | `edge/takab_edge/local_api/` | **ESTRECHA.** Se audita contra su especificación. Ver §5. |

---

## 2 · Lee antes de empezar

1. `takab-docs/design/README.md` — qué es referencia y qué es producción.
2. `takab-docs/design/DESIGN-TOKENS-RECONCILIATION.md` — `shared/design-tokens/tokens.json`
   es **fuente única de verdad** con drift gate (`make drift`). Ningún color, tamaño ni
   espaciado nuevo se escribe a mano en un `.css` o un `.tsx`: **entra por el token o no entra**.
3. `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md` y `NOTAS-DE-DISENO.md`.
4. `takab-docs/design/edge-panel/VERIFICACION-T-2-23.md` — las 10 escenas y las 3 densidades.
5. `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md` — las 12 pantallas y los dos perfiles.
6. `takab-docs/RBAC-TAKAB.md` — qué ve cada rol. **Una mejora visual que enseñe de más es un
   fallo de seguridad, no un fallo de diseño.**

Y la red que va a resistirte, para que la uses como aliada y no la desactives:
`web/src/styles/layoutInvariants.test.ts`, `cssContract.test.ts`, `statePrecedenceCensus.test.ts`,
`serverDataCensus.test.ts`, `serverFrameCensus.test.ts`, `consoleImageCensus.test.ts`,
`designTokens.test.ts`, `simulatedRule.test.ts`, `mobile/src/screenStateCensus.test.ts`,
Playwright + `@axe-core/playwright`.

**Si un cambio visual rompe uno de esos tests, el test casi siempre tiene razón.** Antes de
tocarlo, escribe por qué crees que no la tiene.

---

## 3 · Los cinco principios que gobiernan cualquier cambio visual aquí

Se aplican a las tres superficies y no se negocian con argumentos estéticos.

1. **El movimiento nunca es el único portador de estado.** Un color, un texto o un icono debe
   decir lo mismo que dice la animación. Quien tenga `prefers-reduced-motion` activado no
   puede perder información — ya existe `web/src/lib/useReducedMotion.ts`, se usa.
2. **Ninguna animación retrasa la lectura de una alerta.** En el banner de alerta y en la
   pantalla de crisis, el estado final se pinta en el primer frame. Se puede animar la
   *entrada del contenedor*; jamás la aparición del dato.
3. **La animación más valiosa de este producto es la que se DETIENE.** Un pulso de vida que
   late mientras el dato es fresco y se congela cuando envejece convierte el movimiento en
   honestidad. Eso vale más que cualquier transición decorativa, y encaja con el modo de
   fallo que este proyecto lleva un año persiguiendo: la superficie que miente en verde.
4. **Cero peticiones externas en el panel del gabinete.** Sin CDN, sin Google Fonts, sin
   tiles. Ya es así; que siga siéndolo.
5. **Todo valor visual sale del token.** Si hace falta un token nuevo, se añade a
   `tokens.json`, se regenera y se documenta — no se escribe un hex suelto.

---

## 4 · Checklist de auditoría · Consola SOC (`web/`)

Cada ítem: veredicto **VERDE / AMARILLO / ROJO**, evidencia `ruta:línea`, y una línea de razón.

### 4.1 · Inventario y flujos

- [ ] **W1** · Mapa de rutas: enumera todas las pantallas (`app/routes.tsx`), qué rol las ve y
      cuáles están huérfanas (alcanzables sin entrada en la navegación, o con entrada y sin
      contenido real).
- [ ] **W2** · Recorre los **flujos completos**, no las pantallas sueltas. Como mínimo:
      llegada de alerta → triage → detalle de incidente → dictamen → firma → exportación;
      alta de cliente → alta de sitio → alta de gabinete → verlo en el mapa;
      programar simulacro → dispararlo → ver acuses → reporte.
      Para cada uno: **cuántos clics, cuántas pantallas, dónde se pierde el contexto.**
- [ ] **W3** · **Botones que no hacen nada** o que hacen menos de lo que su etiqueta promete.
      Este proyecto tiene regla de "sin stubs silenciosos": verifica que se cumple hoy.
- [ ] **W4** · Estados vacíos, de carga y de error en **cada** pantalla. Un vacío sin
      explicación es indistinguible de un fallo.
- [ ] **W5** · Precedencia de estados: alerta real > simulacro > mantenimiento > normal.
      ¿Se respeta visualmente en todas las pantallas o solo donde hay test?

### 4.2 · Jerarquía visual y estética

- [ ] **W6** · **Jerarquía tipográfica**: ¿el dato más importante de cada pantalla es el más
      grande? Señala las pantallas donde el ruido compite con la señal.
- [ ] **W7** · Densidad: la consola es para operadores y densidad alta está bien, pero
      identifica dónde la densidad se volvió amontonamiento.
- [ ] **W8** · Consistencia: mismos componentes para mismas funciones. Enumera las
      divergencias (tres estilos de tarjeta, dos estilos de tabla, etc.).
- [ ] **W9** · Color: ¿el semáforo operativo es inequívoco? ¿Hay algún estado que dependa
      solo del color? **Contraste AA como mínimo** — usa axe.
- [ ] **W10** · La **primera pantalla que ve un cliente en una demo**. Descríbela y di
      honestamente si vende. Es el ítem más comercial de esta lista.
- [ ] **W11** · Marca: logo, tipografía y color de TAKAB, coherentes y presentes sin invadir.

### 4.3 · Movimiento

- [ ] **W12** · Inventario de lo que ya se mueve hoy y con qué propósito.
- [ ] **W13** · Dónde **falta** movimiento y aportaría: llegada de un incidente nuevo a la
      cola, transición de tier, latido de frescura de dato (principio 3), progreso de una
      exportación, confirmación de una acción firmada.
- [ ] **W14** · Dónde **sobra** o sobraría: cualquier cosa en el camino de lectura de una
      alerta.
- [ ] **W15** · `prefers-reduced-motion`: cobertura real, no solo que el hook exista.

### 4.4 · Autenticación y arranque

> **Restricción dura.** El login es **Hosted UI de Cognito con OIDC `code` + PKCE**
> (`web/src/auth/userManager.ts`), sesión en `sessionStorage`, renovación silenciosa, y
> constancia de MFA exigida en el camino de comando de actuadores (`api/.../auth/mfa.py`,
> regla de oro 8). **NO se propone sustituirlo por un formulario propio.** Reimplementar los
> retos de MFA a mano, con `T-2.87` abierto y exposiciones encima, es riesgo sin beneficio.

- [ ] **W16** · Qué ve exactamente un usuario desde que abre la URL hasta que ve datos.
      Cronometra los pasos y nombra cada pantalla intermedia.
- [ ] **W17** · **Personalización del Hosted UI de Cognito**: qué permite hoy la
      configuración (logo, CSS de marca, textos) y qué haría falta para que la pantalla de
      login se vea TAKAB y no genérica de AWS. Esto es lo que sí se va a cambiar.
- [ ] **W18** · La pantalla **anterior** al redirect: ¿hay una landing de la consola con
      marca y botón de entrar, o se salta directo? Evalúa si conviene tenerla.
- [ ] **W19** · Retorno del redirect: el momento entre callback y primer render. ¿Hay
      esqueleto, o pantalla en blanco?
- [ ] **W20** · `DegradedSessionScreen` y expiración de sesión: ¿qué le dice al usuario y qué
      puede hacer? Auditar también el logout.
- [ ] **W21** · Login de `dev-token`: **verifica que no puede aparecer en producción** y que
      un test lo defiende. Un atajo de desarrollo visible en una demo es un hallazgo ALTA.
- [ ] **W22** · Cuando llegue `console_scope_enforced` (`T-2.89`), ¿qué cambia visualmente?
      Anticípalo: no queremos descubrirlo el día del apply.

---

## 5 · Checklist de auditoría · Panel LAN del gabinete

> **Licencia ESTRECHA, y conviene entender por qué antes de proponer nada.** Esta pantalla
> se lee a 5 metros durante un sismo, corre en el mismo Pi 4 que ejecuta la ruta
> determinista, y sus decisiones de diseño están escritas y justificadas. **El trabajo aquí
> es verificar que el código cumple su propia especificación**, no reimaginarla.
>
> **Prohibido en esta superficie:** animaciones decorativas, transiciones en el banner de
> alerta, cualquier dependencia de red externa, cualquier cosa que compita por CPU con la
> detección, y `localStorage` (el PIN vive en memoria, a propósito).

- [ ] **E1** · Las **10 escenas** de `VERIFICACION-T-2-23.md` (`?demo=<escena>`): recórrelas y
      di cuáles se ven como especifica el documento y cuáles no.
- [ ] **E2** · Las **3 densidades** (`?mode=muro|consola|campo`) contra los breakpoints
      declarados: CAMPO `<1024`, CONSOLA `1024–1919` con mínimo real 1280, MURO manual.
- [ ] **E3** · Honestidad de dato: `S/D`, `<0.001 g`, edad del diagnóstico, `sin_senal` que no
      dibuja línea plana, `SIN ENLACE` en ámbar y no en rojo. Verifica **cada una**.
- [ ] **E4** · Los tres estados por relé (lógico / eléctrico / fail-safe) y que en `fail_close`
      y `NC` se ven correctamente opuestos.
- [ ] **E5** · Precedencia de banners: alerta real tapa todo; el banner de MODO PRUEBA WR-1
      permanece visible bajo alerta real.
- [ ] **E6** · Cero cuenta regresiva, cero magnitud preliminar, cero `localStorage`.
- [ ] **E7** · Tipografía empaquetada: Geist y el subconjunto de JetBrains Mono se sirven del
      Pi, con caída declarada. Sin peticiones externas.
- [ ] **E8** · Legibilidad a distancia en MURO: tier a 72 px, relés a 28 px, sin acciones,
      sin PIN.
- [ ] **E9** · **Único movimiento admisible aquí**, y solo si se propone con justificación:
      el latido de frescura del principio 3. Evalúa si aporta y qué cuesta en CPU.
- [ ] **E10** · Coste de render medido en el Pi real, o declarado como no medido. **No
      inventes la cifra.**

---

## 6 · Checklist de auditoría · App móvil

- [ ] **M1** · Las 12 pantallas de la especificación contra lo construido en
      `mobile/src/features/`: cuáles existen, cuáles divergen, cuáles faltan.
- [ ] **M2** · Los dos perfiles (Ocupante y Brigada): ¿la diferencia se nota al abrir la app?
- [ ] **M3** · `screenStateCensus.test.ts`: qué estados cubre y cuáles no.
- [ ] **M4** · Flujo de alerta real de punta a punta: push → apertura → qué se ve en el primer
      segundo → acuse. **Cronometra los toques hasta acusar.**
- [ ] **M5** · Flujo de simulacro: ¿es **inconfundible** con una alerta real? Este es el ítem
      de seguridad de esta sección.
- [ ] **M6** · Modo offline: qué se ve, qué se puede hacer, cómo se anuncia la cola pendiente.
- [ ] **M7** · Movimiento: `react-native-reanimated` está disponible. Inventario de lo que se
      mueve, y dónde aportaría — con el principio 2 vigente en la pantalla de alerta.
- [ ] **M8** · Objetivos táctiles ≥ 44 px, contraste, y uso con una sola mano en la pantalla
      de pánico.
- [ ] **M9** · Paridad de tokens con la web (`@takab/design-tokens`): ¿alguna divergencia?

---

## 7 · Simulacros — revisión transversal de las tres superficies

> Se audita como un solo flujo porque el riesgo vive en la costura entre superficies.

- [ ] **S1** · Lo que hay hoy: `api/src/takab_api/routers/drills.py` (agenda, disparo, paro,
      cancelación, acuse por sitio, `from_scheduled`, `commandable`) y
      `edge/takab_edge/drill/` (observador puro, "lo real gana", aborto visible).
      **Enumera qué hace hoy antes de proponer nada.**
- [ ] **S2** · La distinción visual simulacro / alerta real en **las tres superficies a la
      vez**. Si en alguna se parecen, es hallazgo ALTA.
- [ ] **S3** · La animación diferenciada por superficie que se pidió: propón una que sea
      inequívoca **por forma y color, no solo por movimiento** (principio 1).
- [ ] **S4** · El banner de "simulacro armado" (agenda) frente al de "simulacro en curso":
      ¿se distinguen?
- [ ] **S5** · Qué ve el operador cuando un sismo real aborta un simulacro. Es el momento más
      delicado del producto y probablemente el menos probado visualmente.
- [ ] **S6** · Pantalla de resultados post-simulacro: quién acusó, en cuánto, quién no.
      Evalúa si es presentable ante Protección Civil.

---

## 8 · Entregables de esta sesión

### 8.1 · `takab-docs/design/INFORME-UIUX.md`

- Tabla con un renglón por ítem (`W1`…`S6`): veredicto, evidencia, razón.
- **Hallazgos numerados** `U-01`, `U-02`… con severidad. ALTA = una pantalla que miente, un
  simulacro confundible con alerta real, una fuga de alcance por rol, o un atajo de
  desarrollo visible.
- **Sección "Lo que se ve mal en una demo"**: concreto y por pantalla. Es la sección que
  Mauricio lee antes de una exposición.
- **Inventario de movimiento**: lo que hay, lo que falta, lo que sobra.

### 8.2 · `takab-docs/design/PLAN-REFORMA-VISUAL.md`

- Fichas en el formato de `TASKS.md`, **agrupadas por superficie y por sesión de ejecución**.
  Una sesión no mezcla superficies.
- Cada ficha declara: qué tests de censo va a tocar, si necesita token nuevo, y si cambia
  algo que un test defiende hoy.
- **Tres tandas por prioridad:** (1) lo que impide presentar, (2) lo que mejora la venta,
  (3) lo que es gusto. Sé honesto en la clasificación — casi todo lo estético cae en la 3, y
  eso está bien.
- **Lo que se decide NO hacer, con su razón.** Un plan de rediseño sin lista de descartes es
  una lista de deseos.

---

## 9 · Plantilla para las sesiones de ejecución (SESIÓN 2 en adelante)

> Copia esto por cada ficha del plan. **Una superficie por sesión, una ficha por sesión.**

```
Ejecuta <T-x.xx> de takab-docs/design/PLAN-REFORMA-VISUAL.md.

Antes de escribir código:
- Lee la ficha completa y su sección del INFORME-UIUX.
- Confirma que ningún valor nuevo va fuera de shared/design-tokens/tokens.json.
- Enumera qué tests de censo pueden romperse y por qué.

Reglas de la sesión:
- Los cinco principios del §3 del prompt de auditoría siguen vigentes.
- Si un test de censo se pone rojo, NO lo modifiques sin escribir antes por qué
  el test se equivoca. En la duda, gana el test.
- Captura antes y después de cada pantalla tocada.
- make lint && make test && make drift en verde antes del PR.
- Rama + PR con los siete checks. Nada de push directo a main.
- Commits de Mauricio, Conventional Commits, sin footers de IA.
```

---

## 10 · Prohibiciones de la sesión de auditoría

1. **No modificar código.** `git status` limpio salvo los dos documentos.
2. **No sustituir el login de Cognito** por un formulario propio.
3. **No rediseñar el panel del gabinete**; auditarlo contra su especificación.
4. **No desactivar ni relajar un test de censo** para que algo pase.
5. **No escribir un color, tamaño o espaciado fuera de los tokens** en las propuestas.
6. **No proponer animación en el camino de lectura de una alerta.**
7. **No inventar mediciones de rendimiento.** "No medido" es una respuesta válida.

---

## 11 · Criterio de un buen informe

Un informe con todo en VERDE y sin hallazgos es un informe mal hecho. La consola creció
durante 26 tareas de reforma (`Ciclo Nube 2.2`) y eso deja costuras: componentes duplicados,
estados que solo existen en una pantalla, pantallas que se entregaron antes de que hubiera
token para ellas. **Encuéntralas.** Si algo se ve demasiado terminado, ábrelo y ejercítalo
antes de creerle.
