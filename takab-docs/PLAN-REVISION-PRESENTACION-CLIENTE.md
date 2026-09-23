# Plan · Revisión de la presentación al cliente

> **Ficha:** [`T-7.28`](TASKS.md) · **Dueño:** Mauricio · **Escrito:** 2026-09-22
> · **Revisado contra lo medido el 2026-09-22 por la tarde** (ver §2 y §4: dos de sus pasos
> se ejecutaron ese mismo día y el documento los seguía pidiendo)
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

> **Medido el 2026-09-22 por la tarde:** nube `f63b38b`, `HEAD` `db6684c`, **diff vacío** en
> las rutas que viajan. Lo que cambió después del despliegue son `api/tests/`, `deploy/demo/`
> y `takab-docs/`, y ninguna de las tres entra en las imágenes.
>
> ⚠️ **Esta nota nació rancia y conviene saber por qué.** Hasta esta revisión decía «nube
> `10a8b3b`, `HEAD` `33cf209`» — las dos etiquetas del **2026-09-21** — bajo la fecha de hoy,
> así que quien la leyera no podía distinguir que estaba vieja. Un SHA tecleado a mano envejece
> sin avisar, y ésta es justo la nota sobre la que descansa todo el §1. **La fuente que no puede
> diverger es la fila que el censo genera solo**, `| build de la nube | 🟢 VERDE |
> /api/health.build=… == HEAD |`, en [`INFORME-CONFORMIDAD-DEMO.md`](INFORME-CONFORMIDAD-DEMO.md):
> se regenera entera en cada corrida. Si las dos se contradicen, gana el censo.

---

## 2 · Veredicto por función

Verificado por catorce agentes (siete verificadores y siete refutadores), con las citas
comprobadas una a una contra el código y contra el gabinete y la nube vivos.

| Función | En `main` | En la nube | Se enseña… |
|---|---|---|---|
| **Se mueve el sensor → sale la alerta** | ✅ | ✅ | sin sesión: panel + consola |
| **SASMEX → alerta a los dispositivos** | ✅ | ✅ | con el WR-1 y el Pixel |
| **Dictamen con fotos, mapa, espectrograma** | ✅ | ⚠️ **código sí, DATO no** | con sesión de inspector |
| **Redacción asistida del informe (IA)** | ✅ | ✅ **encendida** desde `f63b38b` | con sesión — **y hay que decir que la foto sale de México** |
| **«Magnitud» de cómo se sintió** | ⚠️ **parcial por diseño** | ⚠️ parcial | con sesión |
| **Cierre del evento** | ✅ | ✅ | con sesión |
| **Vincular evento de USGS / SSN** | ⚠️ **USGS sí, SSN no** | ✅ **encendido** el 2026-09-22 | con sesión: la casilla del catálogo en el dictamen |
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

**Catálogo · encendido y desplegado el 2026-09-22 — y esta revisión lo encontró APAGADO, que
es lo que lo salvó.** Cuando se escribió este plan, `catalog_usgs_enabled` valía `False` y
**ningún fichero del repositorio lo encendía** — barrido entero, no sólo de `deploy.sh`—, así
que lo que `T-7.25` construyó no se habría podido enseñar. Con la bandera apagada se midieron
también las consecuencias: la casilla «MAGNITUD (CATÁLOGO)» salía vacía en todos los incidentes
reales y `catalog_consultations` no tenía una sola fila. **La bandera y la tabla dejaron de ser
verdad esa misma tarde; la casilla vacía NO, y ésa es la que importa delante del cliente.** Con
su medición cada una, porque ninguna se puede dar por buena de memoria:

- el encendido entró en `3fb22a6` y viajó con el despliegue de `f63b38b`, y la instancia trae
  `TAKAB_API_CATALOG_USGS_ENABLED=true` — fila 🟢 del censo generado a las 17:18:52Z;
- `catalog_consultations` tiene **dos filas, y son los dos incidentes del ensayo de hoy**:
  `d5af54e5` a las 18:07:55Z y `b420daaa` a las 19:14:14Z, fuente `USGS`, **un intento** cada
  uno, contestados (leído por SSM contra la base de la nube el 2026-09-22). La consulta **se
  dispara sola y de verdad**;
- pero las dos salieron `sin_correlacion`, con la razón escrita: *«la fuente no publicó ningún
  evento en la ventana consultada»* — que es lo correcto, porque golpear una losa en Puebla no
  produce un evento en el catálogo del USGS. **Así que la casilla de magnitud del catálogo sigue
  saliendo vacía**, y ya no por una bandera apagada sino porque no hay con qué casar.

Lo que se puede enseñar, entonces, es que **el sistema pregunta a la fuente oficial y anota qué
contestó**, incluido el «no había nada». Lo que no se puede prometer es que le ponga magnitud al
sismo del cliente: para eso hace falta un sismo que el USGS publique.

El **SSN no se consulta, y es deliberado**: la atribución de sus cifras sigue sin cerrar
(`D-06` / `T-2.149` bloqueada) y el dictamen lo declara.

**IA · la redacción asistida está ENCENDIDA en la nube, y eso obliga a decir una frase.** Hasta
esta revisión no tenía fila en esta tabla, siendo la función que más cambió el 2026-09-22 y la
única que manda un dato del cliente fuera. Medido en la instancia:
`TAKAB_API_OPENROUTER_ENABLED=true` y `TAKAB_API_OPENROUTER_MODEL=google/gemini-2.5-flash-lite`
—**22× más barato** que el `anthropic/claude-sonnet-5` anterior, que además devolvía el
contenido vacío y por eso la capa llevaba desde el 2026-09-21 encendida sin redactar un
párrafo—. El tope es de **30 s** por [`D-37`](DECISIONES-MAURICIO.md#d-37), y ese número sale
de una medición, no de una estimación: con seis fotografías el p50 fue de 13 686 ms. **Es
fail-open**: si el proveedor no contesta, el informe sale con prosa determinista y lo
**declara** en el pie (`NARRATIVA DEGRADADA · <razón>`), así que un plantón no tumba la
demostración pero sí se lee en el papel que se entrega. Y lo que no puede quedarse sin decir:
**la fotografía del daño sale de México** hacia el proveedor del modelo. Sale **sin el sello**
—la franja con la hora, la ubicación y el identificador del operador se tapa antes de enviarla,
y el nombre y el teléfono no viajan—, y la app se lo dice al brigadista en la pantalla donde
dispara; pero sale. El runbook le dedica **tres filas nuevas** en «lo que NO debe decirse», con
la frase exacta con la que se cuenta; la más afilada es que *«las fotos del brigadista se quedan
aquí»* es **falso** desde `T-7.26`/`T-7.27`.

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

> ⚠️ **Los dos primeros pasos de esta lista se hicieron el 2026-09-22 y quedan aquí en
> pretérito, no borrados, para que nadie los repita:**
>
> · **Encender el catálogo y redesplegar** — hecho. El encendido entró en `3fb22a6` y llegó a
> la nube con `f63b38b`. Repetir `make cloud-images && make cloud-deploy` «por si acaso» no es
> gratis: gasta ~40 min de la ventana del día y mueve la nube sin motivo, con el diff de las
> rutas que viajan vacío.
>
> · **Medir la latencia de la IA** — hecha con `make cloud-medir-latencia-ia` contra la nube
> desplegada. El tope sube de 8 s a 30 s y el modelo pasa a `google/gemini-2.5-flash-lite`:
> está razonado en [`D-37`](DECISIONES-MAURICIO.md#d-37) con la tabla de latencias. `T-7.26`
> quedó en `[x]` ese mismo día, así que **este plan era el único sitio del repositorio donde
> seguía apareciendo abierta**.

1. **Usuarios y MFA** — los dos pools, y entrar una vez con cada rol
   (ver `GUIA-DEMOSTRACION-POR-ROLES.md §2`, la trampa de los 401 en ambas direcciones).
2. **Leer la lista «lo que NO debe decirse»** del runbook — incluidas las **tres filas de la
   IA**, que son nuevas y las únicas que hablan de un dato que sale del país.
3. **Dejar clasificados los incidentes que abrió el ensayo 1** (ver «Al terminar»): el
   2026-09-22 quedaron **dos** en `in_review` y sin clasificar.

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

**Clasificar como `reproduccion` los incidentes que abrió la corrida — son DOS, no uno.** Una
corrida completa abre el aviso instrumental del acto 2 (`local_threshold`) **y** el pulso del
acto 3 (`sasmex`). Medido el 2026-09-22 contra la base de la nube, el ensayo 1 dejó
`d5af54e5-…` (acto 2, `watch`, 18:04:53Z) y `b420daaa-…` (acto 3, `critical`, 18:14:14Z), los
dos en `in_review` y con **cero filas** de clasificación — y el § Registro nombraba **sólo el
segundo** hasta que se corrigió esa misma tarde, que es exactamente cómo se pierde uno: nadie
echa de menos un incidente que el guion nunca nombró. El TTL de revisión (6 h) los cierra solos con causa `review_ttl`: clasificarlos
después sigue funcionando —la tabla es append-only— pero se pierde la traza de que lo cerró
**una persona**, y hasta entonces cuentan como sismos reales en las métricas del sitio, que es
exactamente lo que `D-33` separó en fases para evitar. **La lista no te la da el guion: sácala
de la cola del sitio en la consola.**

Después, pegar la tabla de tiempos en el § Registro y anotar allí **qué incidentes quedaron
clasificados**: es lo único que mira la comprobación 4 del Goal de la fase, y por eso una
corrida sin esa anotación no cuenta como corrida acreditada.

Y si firmaste un dictamen, **apunta la hora**. El flujo móvil `03-dictamen-liberacion` ya no es
el que nunca se ha acreditado: se acreditó **por primera vez el 2026-09-22** en la corrida
`20260922T180248Z` (no cargaba porque llevaba un `timeout:` dentro de un `assertVisible` y
Maestro rechazaba el fichero entero). Lo que aporta firmar delante del cliente es la
**re-acreditación**, que no es poco — pero prometerlo como estreno es envejecer al revés otra vez.

---

## 5 · Goal de la fase · cuándo se puede decir que está revisada

```bash
set -e; cd "$(git rev-parse --show-toplevel)"

# 1 · lo que se enseña ES lo que corre, y el sistema está sano.
#     Con la sesión de AWS caída sale 1: sin SSM el censo anota cada bandera AMARILLO y su
#     bloque A4 las pinta de rojo. Un censo ciego NO puede aprobar este Goal.
bash deploy/demo/goal-presentacion.sh

# 2 · el guion se puede conducir HOY. Sólo lee y es repetible, así que el Goal se puede
#     volver a correr para comprobar que la fase sigue cerrada. Las dos corridas de
#     `--full` NO se re-hacen aquí: exigen el WR-1, el gabinete, el Pixel y una persona,
#     y quien las acredita es el § Registro en la comprobación 4.
bash deploy/demo/guion.sh --preflight

# 3 · la tabla viva del informe. «0 ROJO» a secas NO sirve: cuando no se puede leer la
#     instancia, `conformidad.sh` anota AMARILLO —no ROJO—, así que una corrida CIEGA
#     («6 VERDE · 8 AMARILLO · 0 ROJO · 5 NO MEDIDO», que es lo que sale con el SSO
#     rancio) cumplía el grep anterior con trece piezas sin mirar. Un fallback no puede
#     ser «ok».
bloque=$(sed -n '/conformidad:inicio/,/conformidad:fin/p' takab-docs/INFORME-CONFORMIDAD-DEMO.md)
grep -qE '^\*\*RESUMEN:\*\*.* 0 ROJO ·' <<<"$bloque"
#     no-vacuidad: si el formato del bloque cambia, el barrido de abajo pasaría VACÍO
test "$(grep -cE '^\| .+ \| (🟢|🟡|🔴|⚪) ' <<<"$bloque")" -ge 15
#     toda pieza que no esté en VERDE, NOMBRADA aquí con SU veredicto. Tolerar por número
#     deja entrar cualquier pieza nueva; tolerar por pieza+veredicto obliga a mirarla, y no
#     confunde «no se midió» con «se midió y salió amarillo». Las dos excepciones y por qué:
#       · «APK del Pixel · NO MEDIDO» exige el teléfono por USB, y este Goal se corre sin él;
#       · «build de la nube · AMARILLO» es el caso «la nube va por detrás pero SOLO en
#         documentos» — si hubiera cambiado algo que la nube ejecuta, `conformidad.sh` lo
#         anota ROJO, y el ROJO ya lo tumba la línea de arriba. Exigirle VERDE obligaría a
#         redesplegar por un commit de documentos, que es lo que `T-7.01` acaba de quitar.
no_verde=$(awk -F'|' '$3 ~ /(AMARILLO|ROJO|NO MEDIDO)/ {
             gsub(/^ +| +$/, "", $2); gsub(/^ +| +$/, "", $3); sub(/^[^A-Z]+/, "", $3)
             print $2 " · " $3 }' <<<"$bloque")
sin_tolerar=$(grep -vxF -e 'APK del Pixel · NO MEDIDO' -e 'build de la nube · AMARILLO' \
                <<<"$no_verde" | grep -v '^$') || true
[ -z "$sin_tolerar" ]
#     y que la medida sea de ESTE código: el bloque se autodata con el HEAD que lo generó,
#     y entre aquél y HEAD no puede haber cambiado nada que la nube ejecute. Se compara
#     contra las rutas que viajan, no contra HEAD a secas: un commit de documentos NO
#     invalida el censo ni obliga a redesplegar.
sello=$(sed -n 's/.*HEAD `\([0-9a-f]\{7,\}\)`.*/\1/p' <<<"$bloque" | head -1)
. <(sed -n '/^rutas_que_llegan_a_la_nube()/,/^}$/p' deploy/cloud/conformidad.sh)
git diff --quiet "$sello..HEAD" -- $(rutas_que_llegan_a_la_nube)

# 4 · el § Registro tiene las DOS corridas Y ninguna deja un incidente sin clasificar.
#     El grep anterior —`grep -c 'corrida \`' … | grep -qE '^[2-9]'`— contaba líneas del
#     fichero ENTERO (también las de fuera del Registro), nunca buscaba la palabra
#     `reproduccion` pese a prometerla en su comentario, y era FALSO para 10 corridas o más.
reg=$(sed -n '/^## Registro/,$p' takab-docs/runbooks/RUNBOOK-demo-cliente.md)
test "$(grep -c 'corrida `' <<<"$reg")" -ge 2
if grep -E '^### Ensayo ' <<<"$reg" | grep -qi 'PENDIENTE'; then
  echo "una de las corridas del § Registro sigue en PENDIENTE"; exit 1
fi
if grep -qiE 'sin clasificar|pendiente de esta corrida' <<<"$reg"; then
  echo "el § Registro declara incidentes sin clasificar: clasifícalos en la consola"; exit 1
fi
```

**Por qué la 4 mide por REGISTRO y no por base de datos.** La verdad de si un incidente quedó
clasificado está en la nube, y leerla exige sesión — nivel B, que en este Goal nunca se pinta
de verde. Así que lo que se comprueba es la **declaración**: el § Registro nombra la corrida
por su identificador y dice qué incidentes clasificó. Por eso «Pendiente … clasificar» y «sin
clasificar» tiran el Goal: mientras esa frase exista, el propio documento está diciendo que la
corrida no terminó.

**Lo que este Goal NO puede comprobar, y por eso va escrito aparte:** que las frases que se
dicen en voz alta sean ciertas. Eso lo gobierna la lista «lo que NO debe decirse», que se
lee antes de cada demostración y **se actualiza**, porque varias de sus filas razonan sobre
cosas que dejaron de ser verdad al cerrarse F1…F6.

> **Y ese «varias» no es vaguedad: es la corrección del 2026-09-22.** Este documento decía
> «cinco de sus trece filas» y el runbook decía lo mismo, los dos tecleados a mano y los dos
> mal: la tabla tenía ya SEIS filas. Cerraba en trece porque la resta cuadraba con el otro
> número escrito a mano, que es exactamente cómo un censo enumerado a mano se sostiene
> mientras diverge. El runbook las enumera ahora una por una; aquí no se repite la cuenta,
> porque repetirla es lo que la hizo viajar.
