# Plan · Revisión de la presentación al cliente

> **Ficha:** [`T-7.28`](TASKS.md) · **Dueño:** Mauricio · **Escrito:** 2026-09-22
> **Guía de ejecución:** [`runbooks/GUIA-DEMOSTRACION-POR-ROLES.md`](runbooks/GUIA-DEMOSTRACION-POR-ROLES.md)
> **Qué tiene que pasar y cómo se acredita:** [`runbooks/RUNBOOK-demo-cliente.md`](runbooks/RUNBOOK-demo-cliente.md)
>
> Este documento contesta **una** pregunta: *¿las funciones que vamos a enseñar están
> implementadas y corriendo en la nube?* No es el guion de la demostración ni la guía de
> roles — es la **revisión previa**, con su veredicto por función y su Goal medible.

---

## 1 · El Goal · cómo se mide, y con qué comando

```bash
bash deploy/demo/goal-presentacion.sh
```

**Sale 0 sólo si todo el nivel A está en verde.** Tres niveles que no se mezclan:

| Nivel | Qué es | Quién lo puede medir |
|---|---|---|
| **A** | paridad repo↔nube, censo de conformidad, banderas, consola servida, gabinete | **la máquina, sola** |
| **B** | lo funcional: dictamen, firma, cierre, push, simulacro, catálogo | una **persona con sesión** — aquí sale `NO MEDIDO`, nunca verde |
| **C** | lo que el sistema **no hace** (invariantes y decisiones) | se **imprime** para que nadie lo prometa |

### La comprobación central, y por qué es ésta y no otra

**La API desplegada no publica su OpenAPI**, y es deliberado: `main.py` pone `docs_url`,
`redoc_url` y `openapi_url` a `None` en el perfil público. Pedir `/openapi.json` a la nube
devuelve el **HTML de la consola** (medido). Así que confirmar «la función X está en la
nube» **no se hace sondeando endpoints**: se deriva de la etiqueta.

```bash
TAG=$(curl -s $CONSOLA/api/health | jq -r .build)    # lo que la nube DECLARA que corre
git diff --quiet "$TAG..HEAD" -- $(rutas_que_llegan_a_la_nube)
```

Si ese diff está vacío, **todo lo del repositorio está en la nube** y no hace falta
enumerar función por función. La lista de rutas que viajan se **deriva** de las líneas
`b64 deploy/cloud/…` del propio `deploy.sh` y de las `COPY` de los dos Dockerfile, con
`api/tests` fuera porque ningún Dockerfile la copia.

> **Medido el 2026-09-22:** nube `10a8b3b`, `HEAD` `33cf209`, **diff vacío**.
> Los tres PRs de ese día sólo tocaron tests, documentos y herramientas locales.

---

## 2 · Veredicto por función

Verificado por catorce agentes (siete verificadores y siete refutadores), con las citas
comprobadas una a una contra el código y contra el gabinete y la nube vivos.

| Función | En `main` | En la nube | Se enseña… |
|---|---|---|---|
| **Se mueve el sensor → sale la alerta** | ✅ | ✅ | sin sesión: panel + consola |
| **SASMEX → alerta a los dispositivos** | ✅ | ✅ | con el WR-1 y el Pixel |
| **Dictamen con fotos, mapa, espectrograma** | ✅ | ⚠️ **código sí, DATO no** | con sesión de inspector |
| **«Magnitud» de cómo se sintió** | ⚠️ **parcial por diseño** | ⚠️ parcial | con sesión |
| **Cierre del evento** | ✅ | ✅ | con sesión |
| **Vincular evento de USGS / SSN** | ⚠️ **USGS sí, SSN no** | ❌ **apagado** | requiere encenderlo |
| **Audio / voceo** | ⚠️ **sirena sí, voz no** | — | la sirena suena |
| **Simulacros** | ✅ | ✅ | con sesión |

### Lo que hay detrás de cada ⚠️

**Dictamen · el código está entero y desplegado; el DATO no está.** En la nube hay **cero
snapshots de mapa de sacudida**, y ningún incidente existente puede ya obtener uno: la
consulta de candidatos exige `opened_at` dentro de 6 h y el incidente más nuevo tiene 14 h.
Además **fotos y miniSEED son conjuntos disjuntos**: 8 incidentes con onda y sin una sola
foto, 4 con fotos y sin onda. **No existe hoy un incidente que enseñe las dos cosas
juntas.** Se arregla con una reproducción durante el ensayo, no con código.

**«Magnitud» · hay que decirlo bien o no decirlo.** TAKAB **no calcula magnitud** y no es
un pendiente: es `[INVARIANTE]` del blueprint §14 — medido, cero funciones inversas
PGA→magnitud en todo el repositorio. Tampoco reporta **intensidad macrosísmica (MMI)**, a
propósito, y el papel lo declara. Lo que **sí** existe, construido y desplegado, es la
**intensidad medida en el inmueble**: PGA/PGV pico con su instante y su umbral **con
procedencia**, en la §5 del dictamen, titulada *«INTENSIDAD MEDIDA EN EL INMUEBLE»*. Eso es
exactamente «cómo se sintió aquí», y es más defendible que una magnitud: es una medición
del edificio, no una estimación de un epicentro.

**Catálogo · USGS está construido y APAGADO en la nube.** `catalog_usgs_enabled` vale
`False` y **ningún fichero lo encendía** — barrido del repositorio entero, no sólo de
`deploy.sh`. Consecuencia medida: la casilla «MAGNITUD (CATÁLOGO)» sale vacía en todos los
incidentes reales y `catalog_consultations` no tiene una sola fila. **Ya está encendido en
`deploy.sh` (este plan lo incluye), pero exige un redespliegue para que llegue.** El SSN
**no se consulta y es deliberado**: la atribución de sus cifras sigue sin cerrar
(`D-06` / `T-2.149` bloqueada) y el dictamen lo declara.

**Audio · la sirena suena; la voz no existe.** No hay **ni una grabación** en el
repositorio, y en este gabinete `audio.enabled=false`. El tono oficial del SASMEX está
**reservado y ausente a propósito**: es de CIRES.

---

## 3 · Las trampas medidas · cada una puede costar la demostración

> Las seis salen de la verificación de hoy, no de la teoría. Cinco no estaban escritas en
> ningún sitio.

**1 · Un golpe de prueba QUEMA el incidente bueno.** Hay **un `event_id` por episodio** y el
episodio no se cierra hasta **90 s de silencio**. Si golpeas la losa para «probar» y al rato
haces el acto 2 de verdad, el segundo golpe **escala el mismo incidente** en vez de abrir
otro — y el teléfono no vuelve a sonar. **Deja 2 minutos limpios antes de cada acto.**

**2 · La consola SOC y el teléfono se contradicen cuando la red corrobora.** El motor de
correlación **no reescribe el `trigger`**, sólo enlaza `event_id` — lo declara el propio
código. El teléfono autoriza por `node_count` y la consola sólo mira el `trigger`, que sigue
diciendo `local_threshold`. Resultado: panel del gabinete **rojo**, teléfono **EVACÚE**,
consola **ámbar «SIN ACTUACIÓN»**. Con una sola estación no se ve; si te preguntan por el
quórum, **no prometas que la consola lo pinta en rojo**.

**3 · El PDF del simulacro desmiente por escrito cualquier promesa de voceo.** `will_sound`
viaja en el acuse hasta el reporte de la nube, que imprime por sitio **«SIN VOCEO — voceo
por audio deshabilitado»**. Es la mejor prueba de honestidad del producto y la trampa más
afilada: lo que prometas en voz alta, el papel que entregas lo niega.

**4 · No hay botón de «cerrar incidente».** La única puerta humana es **clasificar**. Y un
incidente clasificado `real` no cierra sin dictamen firmado o sin esperar las 6 h del TTL.

**5 · El defecto de maquetación de la §14 se dispara en el 100 % de los incidentes con
fotografía**, porque todos los reportes de daño tienen exactamente una foto.

**6 · `FALLBACK_STYLE` sólo entra si el estilo del mapa NUNCA cargó.** Perder los tiles a
media sesión no engancha el respaldo. **Abre la consola antes** y recarga si sale vacía.

---

## 4 · El plan de trabajo, en orden

### Antes del día

1. **Encender el catálogo y redesplegar** — es lo único que falta para que «vincular un
   evento del USGS» sea cierto:
   ```bash
   make cloud-images && make cloud-deploy
   ```
2. **Medir la latencia de la IA** y decidir el tope (cierra `T-7.26`):
   ```bash
   make cloud-medir-latencia-ia
   ```
3. **Usuarios y MFA** — los dos pools, y entrar una vez con cada rol
   (ver `GUIA-DEMOSTRACION-POR-ROLES.md §2`, la trampa de los 401 en ambas direcciones).
4. **Leer la lista «lo que NO debe decirse»** del runbook.

### El mismo día, antes de que entre nadie

```bash
bash deploy/demo/goal-presentacion.sh      # tiene que salir 0
bash deploy/demo/guion.sh --preflight      # 0 ✗
```

Y abrir la consola **antes** que el cliente (trampa 6).

### Durante

```bash
bash deploy/demo/guion.sh --full           # cronometra los cuatro actos
```

### Al terminar

Clasificar como **`reproduccion`**, pegar la tabla de tiempos en el § Registro, y si
firmaste un dictamen, **apuntar la hora: acabas de acreditar el flujo móvil `03`**, el
único de los seis que nunca se ha acreditado.

---

## 5 · Goal de la fase · cuándo se puede decir que está revisada

```bash
set -e; cd "$(git rev-parse --show-toplevel)"

# 1 · lo que se enseña ES lo que corre, y el sistema está sano
bash deploy/demo/goal-presentacion.sh

# 2 · el ensayo entero, dos veces, con tiempos por acto
for i in 1 2; do bash deploy/demo/guion.sh --full || exit 1; done

# 3 · la tabla viva del informe, sin un solo ROJO
sed -n '/conformidad:inicio/,/conformidad:fin/p' takab-docs/INFORME-CONFORMIDAD-DEMO.md |
  grep -qE '^\*\*RESUMEN:\*\*.* 0 ROJO'

# 4 · y el § Registro tiene las DOS corridas, clasificadas `reproduccion`
grep -c 'corrida `' takab-docs/runbooks/RUNBOOK-demo-cliente.md | grep -qE '^[2-9]'
```

**Lo que este Goal NO puede comprobar, y por eso va escrito aparte:** que las frases que se
dicen en voz alta sean ciertas. Eso lo gobierna la lista «lo que NO debe decirse», que se
lee antes de cada demostración y **se actualiza** — cinco de sus trece filas originales
razonaban sobre cosas que ya no eran verdad.
