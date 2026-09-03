# Mediciones — la fuente única de las cifras que se citan

> **Si una cifra medida aparece en otro documento, ese documento tiene que enlazar aquí.**
> Lo exige un test (`api/tests/test_mediciones.py`), y la razón es la de `T-5.22`: la cifra
> más citada del producto estaba **replicada a mano en ocho documentos** y su evidencia era
> una frase. Ocho copias no son una fuente: son ocho sitios donde el número puede
> desactualizarse por separado y nadie se entera.

## 1 · Qué distingue una medición de una promesa

Tres columnas y ninguna es adorno:

- **Cuántas observaciones.** Una sola observación **no es un percentil**, y llamarla p95 es
  inventarse una distribución que nadie midió. Aquí se dice cuántas hubo.
- **Con qué se midió.** El hardware real y el simulador no acreditan lo mismo. Una medición
  sobre pines simulados vale para detectar regresiones y **no vale para vender**.
- **Dónde está el artefacto.** Si la respuesta es «en un documento», entonces no hay
  evidencia: hay una afirmación.

## 2 · El camino de vida — contacto SASMEX → relé

| Qué | Valor | Cuándo | Observaciones | Instrumento | Artefacto |
|---|---|---|---|---|---|
| Contacto WR-1 → reflejo (sirena + estrobo) | **6.65 ms** | 2026-07-14 | **una** | WR-1 real cableado al Pi 4 | ⚠️ **ninguno** — anterior al acta (`T-5.22`) |
| Contacto WR-1 → reflejo, en frío | **4.16 ms** | 2026-07-31 | **una** | WR-1 real cableado al Pi 4 | ⚠️ **ninguno** — anterior al acta |
| Presupuesto declarado del camino | **< 100 ms** | — | — | `BLUEPRINT §4.3` | es un objetivo, no una medición |

**Cómo leer esto sin exagerarlo.** Las dos cifras son **observaciones únicas**, tomadas con el
receptor real, y su margen contra el presupuesto es de dos órdenes de magnitud. Eso es una
señal fuerte — y aun así **no son un p95**: para declarar un percentil hacen falta muchas, y
todavía no las hay.

**Desde `T-5.22` el gabinete levanta acta.** Cada flanco del WR-1 escribe una línea fechada en
`<directorio de bitácora>/reflejo.jsonl` con la latencia que midió el dueño de los pines **y el
estado de los cinco canales en ese instante** — que es lo que convierte el número en algo
discutible. El acta sobrevive al reinicio, distingue el pulso de prueba de CIRES del flanco
real, y publica **el peor caso además del mejor**: publicar solo el mejor es cómo una cifra de
venta deja de describir al producto.

> **`GATE-HW` · lo que falta y no lo cierra el software.** Las dos cifras de arriba se tomaron
> **antes** de que existiera el acta, así que no tienen artefacto. La siguiente sesión
> presencial tiene que **volver a medir con el procedimiento nuevo** y adjuntar el
> `reflejo.jsonl` resultante. Procedimiento en
> [`runbooks/RUNBOOK-sesion-de-vida.md`](runbooks/RUNBOOK-sesion-de-vida.md).

## 3 · El camino de la consola — incidente escrito → pintado en pantalla

| Qué | Valor | Cuándo | Observaciones | Instrumento | Artefacto |
|---|---|---|---|---|---|
| Commit del incidente → frame en la consola | **214 ms** | Fase 1.7 | **una** | E2E vivo contra la nube desplegada | ⚠️ **ninguno** |

**Esto no es un percentil y no debe citarse como tal.** Es **una observación**. El
`BLUEPRINT §4.5` declara un objetivo de `p95 < 2 s` para este camino y **ese percentil nunca se
ha medido**: lo único que hay es este número suelto, muy por debajo del objetivo. Decir
«medido 214 ms» es correcto; decir «p95 214 ms» sería falso.

## 4 · Lo que se mide en cada corrida de CI, y por qué no es lo mismo

`edge/tests/test_e2e.py::test_latencia_contacto_wr1_a_los_cinco_reles_bajo_presupuesto` mide el
camino entero **sobre pines simulados**, y su veredicto es el **mejor de cinco intentos**. Eso
está declarado y razonado en `T-2.170`: no es tolerancia al presupuesto —que sigue en 100 ms y
no se mueve— sino **al instrumento**. Un runner compartido mide *código + planificación*, y el
ruido de planificación solo suma; si el código se degradó, ni el mejor intento llega.

La serie completa se publica siempre, también en verde, y una corrida que necesitó reintentos
lo dice con un warning: **un instrumento que pide reintentos merece una mirada**, y callarlo es
cómo se normaliza el ruido hasta que tapa una degradación de verdad.

**Lo que ese test NO acredita:** nada sobre el hardware. Son pines simulados. Para la cifra que
se vende, las únicas fuentes son la tabla de la §2 — y su artefacto, cuando `GATE-HW` lo
produzca.
