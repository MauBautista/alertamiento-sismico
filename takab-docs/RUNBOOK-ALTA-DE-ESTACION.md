# RUNBOOK — Alta de una estación nueva (gabinete) y realidad multi-tenant

> **Qué es esto.** El paso a paso reproducible para dar de alta un gabinete nuevo, desde que el
> **Raspberry Pi (cerebro)** está conectado al **Raspberry Shake (sensor)** hasta que la estación
> aparece **calibrada y operativa** en la consola de la nube. Incluye: quién puede hacerlo, de
> dónde sale el "serial" que vincula a la nube, cómo se calibra y de dónde sale la *procedencia*
> de la calibración, y cómo funciona hoy la creación de clientes (tenants) y la visibilidad.
>
> **Estado de referencia:** el único gabinete real hoy es `gw-dev-0001` (los `gw-sim-*` viven
> apagados por diseño). Los valores concretos de ejemplo salen de la calibración real de
> **AM.R4F74** (T-1.41).
>
> **Documentos relacionados:** `takab-docs/BLUEPRINT-TECNICO-TAKAB.md` (§4 fuentes/tiers, §4.5
> quórum), `takab-docs/RBAC-TAKAB.md` (roles), `takab-docs/runbooks/RUNBOOK-demo-fase1-tres-gabinetes.md`
> (demo de quórico con 3 gabinetes), `db/schema.sql` (DDL fuente de verdad).

---

## 0. Panorama — dos placas por gabinete

| Placa | Rol | Quién la toca |
|---|---|---|
| **Raspberry Shake (RS4D)** | **Solo sensor.** Expone SeedLink en **TCP 18000**. 4 canales: `EHZ` (geófono) + `ENZ/ENN/ENE` (acelerómetro MEMS), 100 sps. | **NADIE.** El *Shake OS no se modifica* (regla de oro, `CLAUDE.md §8`, blueprint §P3). El Pi solo **lee**. |
| **Raspberry Pi (cerebro)** | El "gabinete inteligente": lee SeedLink del Shake, recibe SASMEX por GPIO (WR-1), dispara actuadores, corre reglas y sincroniza a la nube. | Aquí instalamos nuestro software (`edge/`). El cerebro real actual es un **Pi 4** (tiene jack 3.5 mm). |

> El orden mental es: **primero el edge (Pi) queda leyendo y protegiendo de forma autónoma**,
> **luego** se conecta a la nube. La nube es para coordinación, no para la seguridad local.

**Un dato central que confunde a todos (léelo antes de seguir):** lo que **vincula el gabinete a
la nube NO es el "serial"** que escribes en el formulario — es el **nombre del IoT thing** (ej.
`gw-dev-0001`) que crea Terraform. El `serial` es solo un texto de inventario. Ver §3.

---

## 1. Requisitos previos

- Pi con acceso SSH (para `gw-dev-0001`: `ssh takab-pi5`, ver memoria de acceso).
- El Shake y el Pi en la **misma LAN**; el Pi puede alcanzar el Shake por IP en el puerto 18000.
- En tu máquina de operación: `aws` CLI con el perfil **`takab-dev`** (SSO), `terraform`, y el
  repo clonado. Región **`us-east-2`**.
- Un usuario de consola con rol **`takab_superadmin`** o **`tenant_admin`** (para registrar la
  estación en la nube — ver §6).

---

## 2. Parte 1 — El sensor (Raspberry Shake): red y código de estación

1. **Conecta el Shake a la red** y anota su **IP** (la que verá el Pi). No cambies nada del Shake OS.
2. **Averigua el código de estación.** El Shake publica su red/estación en SeedLink. La red es
   siempre **`AM`**; la estación es algo como **`R4F74`**. Lo ves en la UI del Shake
   (rs.local / rshake config) o preguntando SeedLink. Lo necesitarás para el `edge.env` (§5) y
   para la calibración (§7).
3. Verifica que el Shake sirve datos: desde el Pi, el edge se conectará a `IP_DEL_SHAKE:18000`.

---

## 3. Parte 2 — Identidad del gabinete: "serial" vs "iot_thing"

Hay **dos identificadores distintos**. No los confundas:

| Identificador | Qué es | De dónde sale | Para qué sirve |
|---|---|---|---|
| **`iot_thing`** (ej. `gw-dev-0001`) | La **identidad mTLS/MQTT** del gabinete en AWS IoT Core (es el `client_id`). | **Lo crea Terraform** (§4). No lo inventa la API. | **Es lo que vincula el gabinete a la nube.** |
| **`serial`** | Un texto de **inventario** ÚNICO y libre. | **Tú lo defines** (convención propia). Puedes usar el serial de hardware del Pi: en el Pi corre `cat /proc/cpuinfo` y toma la línea `Serial`. | Rastreo físico/activos. **NO** es la credencial de nube. |

> En el formulario de la consola el campo dice **"SERIAL DEL GABINETE"**, pero el campo que de
> verdad sincroniza con la nube es **`iot_thing`** (`web/src/features/fleet/HardwareForm.tsx`,
> columnas `db/schema.sql:117` serial vs `:119` iot_thing). Un gateway con `serial` pero **sin**
> `iot_thing` aparece como **"PENDIENTE DE APROVISIONAR"** — existe en el inventario pero no
> puede hablar con la nube todavía.

---

## 4. Parte 3 — Aprovisionar la identidad de nube (Terraform + provision)

Esto crea el *thing* IoT, su certificado mTLS y su clave HMAC de comandos, y baja todo al Pi.

> ⚠️ **`terraform apply` y las acciones IAM las corre Mauricio** (el clasificador de esta sesión
> las niega). Los comandos van con el prefijo `!` en el prompt cuando haga falta ejecutarlos aquí.

1. **Agrega el nuevo thing a la flota** en `infra/terraform/envs/dev/variables.tf` (variable
   `gateway_fleet`, hoy `["gw-dev-0001", "gw-sim-0001"…]`). Añade el nombre nuevo, p.ej.
   `"gw-hospital-0001"`. Si ese gabinete debe **paginar a un humano** cuando se caiga, agrégalo
   también a `paged_gateways` (solo gateways reales; los sim no).
2. **Aplica Terraform** (crea `aws_iot_thing` + `aws_iot_certificate` + el secreto HMAC en Secrets
   Manager, módulo `infra/terraform/modules/iot-gateway/`):
   ```bash
   terraform -chdir=infra/terraform/envs/dev apply
   ```
3. **Baja las credenciales al Pi** con el script de aprovisionamiento
   (`infra/scripts/provision_gateway.sh`):
   ```bash
   # instala en el Pi por SSH: /etc/takab/certs/{cert,key,ca}.pem + /etc/takab/edge.env + PIN
   infra/scripts/provision_gateway.sh gw-hospital-0001 <ssh_host_del_pi>
   # sin ssh_host: escribe ./certs-gw-hospital-0001/ para copiar tú a mano
   ```
   El script imprime **UNA vez** el **PIN del panel LAN** (6 dígitos): entrégalo al responsable
   del edificio; sin él, las acciones del panel local quedan 403 (fail-closed).

> **GOTCHA (histórico, CORREGIDO en PRs #13/#14):** `provision_gateway.sh` **sobrescribía**
> `/etc/takab/edge.env` con solo sus claves gestionadas, borrando identidad, SeedLink y
> calibración. Desde entonces hace un **merge idempotente** (`infra/scripts/merge_env.py`, con
> tests en CI): actualiza SOLO lo que gobierna — identidad, `DEV_MODE`, HMAC, endpoint, PIN y,
> si pasas `--site-lat/--site-lon` (T-2.20), las coordenadas — y **conserva todo lo demás**,
> con respaldo fechado previo en el dispositivo. Re-correr `provision` ya es seguro.

---

## 5. Parte 4 — Completar el `edge.env` del gabinete

`provision` dejó los secretos. Ahora **agrega** (append) los bloques restantes a
`/etc/takab/edge.env` en el Pi.

> ### ⚠️ La identidad son CÓDIGOS, no UUIDs — y el gateway ya está puesto
>
> Lo que el gabinete manda en cada payload es lo que la ingesta compara contra el registro, y
> **compara códigos y seriales legibles, no UUIDs**
> (`api/src/takab_api/ingest/handlers.py:8-16`):
>
> | Lo que viaja en el payload | Contra qué se compara | Ejemplo |
> |---|---|---|
> | `payload.tenant_id`  | `tenants.code`     | `hospital-central` |
> | `payload.site_id`    | `sites.code`       | `hospital-central-torre-a` |
> | `payload.gateway_id` | `gateways.serial` (= `iot_thing`) | `gw-hospital-0001` |
>
> Si no coinciden, `_identity_reject` (`handlers.py:118-131`) devuelve
> `gateway mismatch: payload=… registro=…` y **el mensaje se va a la cola de descarte**. El
> gabinete queda aprovisionado, con su certificado, conectado por mTLS… y **mudo en la nube**,
> sin que ninguna pantalla explique por qué.
>
> **`TAKAB_EDGE_GATEWAY_ID` ya lo dejó bien `provision_gateway.sh:163`**, que escribe ahí el
> *thing name*. **No lo sobrescribas**: hasta el 2026-09-04 este runbook mandaba pisarlo con un
> UUID, que es exactamente lo que rompe la ingesta. Si lo has hecho, bórralo del `edge.env` y
> vuelve a correr `provision_gateway.sh` (es idempotente y `merge_env.py` conserva lo demás).
>
> **Por qué el aprovisionador ya lo deja bien y no hay que tocarlo:** `provision_gateway.sh`
> recibe el *thing name* como primer argumento —el mismo que Terraform creó y el mismo que va en
> `iot_thing`— y lo escribe tal cual en su **bloque gestionado**
> (`printf 'TAKAB_EDGE_GATEWAY_ID=%s…' "$THING" … >"$TMP/edge.env.managed"`). No hay conversión,
> ni UUID, ni un paso intermedio donde perderlo: **es la misma cadena que la ingesta espera**.
> Ese bloque se reescribe en cada corrida y `merge_env.py` conserva lo que tú añadiste, así que
> re-aprovisionar es seguro y **corrige** el `edge.env` si alguien lo pisó.
>
> Que estas tres fuentes —runbook, aprovisionador e ingesta— sigan diciendo lo mismo lo comprueba
> `api/tests/test_runbook_alta_de_estacion.py`, y si dejan de coincidir el build se pone rojo
> nombrando las tres. Todas las variables llevan prefijo `TAKAB_EDGE_`; los campos
anidados usan doble guion bajo `__` (`edge/takab_edge/config/settings.py`).

```dotenv
# --- (ya lo puso provision_gateway.sh) ---
# TAKAB_EDGE_HMAC_KEY=...
# TAKAB_EDGE_MQTT_ENDPOINT=...
# TAKAB_EDGE_LOCAL_API_PIN=...

# --- Identidad (multi-tenant) --- CÓDIGOS LEGIBLES, NUNCA UUIDs (ver el aviso de abajo)
TAKAB_EDGE_TENANT_ID=hospital-central         # = tenants.code
TAKAB_EDGE_SITE_ID=hospital-central-torre-a   # = sites.code
# TAKAB_EDGE_GATEWAY_ID=gw-hospital-0001      # YA LO ESCRIBIÓ provision_gateway.sh — NO LO TOQUES
TAKAB_EDGE_IOT_THING=gw-hospital-0001        # = el thing de Terraform (client_id MQTT)
TAKAB_EDGE_STATION=R4F74                       # código de estación del Shake
TAKAB_EDGE_SITE_NAME=Hospital Central Puebla   # rótulo del panel LAN

# --- SeedLink (Raspberry Shake) ---
TAKAB_EDGE_SEEDLINK_HOST=192.168.x.y           # IP del Shake en la LAN
TAKAB_EDGE_SEEDLINK_PORT=18000
TAKAB_EDGE_SEEDLINK_NETWORK=AM
TAKAB_EDGE_SEEDLINK_STATION=R4F74
TAKAB_EDGE_SEEDLINK_LOCATION=00
# canales por defecto EHZ,ENZ,ENN,ENE (no hace falta setearlos salvo excepción)

# --- Cloud (mTLS a IoT Core) --- rutas donde provision instaló los certs
TAKAB_EDGE_MQTT_CERT_PATH=/etc/takab/certs/cert.pem
TAKAB_EDGE_MQTT_KEY_PATH=/etc/takab/certs/key.pem
TAKAB_EDGE_MQTT_CA_PATH=/etc/takab/certs/ca.pem

# --- Calibración (se llena en §7; hasta entonces PGA/PGV son RELATIVOS) ---
# TAKAB_EDGE_SIGNAL__VEL_SENSITIVITY_MS_PER_COUNT=...
# TAKAB_EDGE_SIGNAL__ACCEL_SENSITIVITY_MS2_PER_COUNT=...

# --- Ubicación del sitio (T-2.20; habilita el mapa del panel LAN) ---
# Mismas coordenadas que registres en `POST /sites` (§6). Sin ellas el panel
# muestra "SIN UBICACIÓN PROVISIONADA" (jamás inventa un punto). También puedes
# dejarlas desde el aprovisionamiento: provision_gateway.sh ... --site-lat 19.0433 --site-lon -98.1980
TAKAB_EDGE_SITE_LAT=19.0433
TAKAB_EDGE_SITE_LON=-98.1980
# Vecinas de la red (informativas; el quórum vive en la NUBE y JAMÁS gatea la
# sirena local): JSON en una línea, opcional.
# TAKAB_EDGE_NEIGHBORS=[{"code":"AM.R0001","lat":19.10,"lon":-98.30,"distance_km":17.0}]
```

El servicio `systemd` (`edge/systemd/takab-edge.service`) ya fuerza `TAKAB_EDGE_DEV_MODE=false`,
lee `EnvironmentFile=/etc/takab/edge.env` y corre con `WorkingDirectory=/var/lib/takab`
(obligatorio: lgpio escribe su FIFO ahí). Reinicia el servicio tras editar el `edge.env`:
```bash
sudo systemctl restart takab-edge.service && systemctl status takab-edge.service
```

---

## 5.bis Parte 4.5 — Instalar el software del edge

**Este paso faltaba en el runbook** (hasta el 2026-09-04): `provision_gateway.sh` deja
identidad, certificados y secretos, pero **no copia el código**. Un gabinete aprovisionado sin
esto no tiene nada que arrancar.

```bash
deploy/edge/deploy.sh <ssh_host>            # p.ej. takab-pi5
```

Qué hace (`deploy/edge/deploy.sh`): rsync a una **release nueva** que nadie apunta todavía →
pre-vuelo `compileall` → `uv sync` con los extras dentro de esa release → **gate de imports**
(`takab_edge.supervisor` + `takab_edge.gpio.__main__`, con `lgpio` y `awsiot`) → unidades
systemd → repunte del symlink. Si algo falla antes del repunte, **el gabinete no se toca**.

- La primera vez migra el layout a A/B y exige `--ventana-de-mantenimiento` (ver
  `RUNBOOK-sesion-de-vida.md`; `G-01` gatea esa ventana).
- Escribe el `FW_VERSION` de la release. Ese valor es el que el gabinete **declara** en su
  heartbeat y el que hay que publicar en el paso siguiente — **por igualdad**.

---

## 5.ter Parte 4.6 — Publicar la versión en el registro de releases

**También faltaba.** Sin este paso la flota entera sale **`SIN REFERENCIA`**: se sabe qué corre
cada gabinete, no si eso es lo actual (`api/src/takab_api/routers/fleet.py:372-386`).

```bash
POST /fleet/releases   { "version": "<el FW_VERSION exacto que escribió deploy.sh>" }
```

- **Solo `takab_superadmin`** (`_PUBLISH_RELEASE_ROLES`). No tiene acción de matriz propia a
  propósito: no hay botón, es superficie de herramienta/CI.
- La comparación con lo que declara el aparato es **por igualdad**, así que un espacio de más
  deja `DESCONOCIDA` a toda la flota que corra ese código.
- Republicar la misma versión da **409**: la tabla es append-only.

---

## 6. Parte 5 — Registrar la estación en la nube (API)

Una "estación" en la nube = **un sitio (`site`) + un gateway + uno o más sensores**. Se crean en
**este orden** (cada uno hereda el `tenant_id` del anterior):

> Los tres cuerpos rechazan claves desconocidas (`extra="forbid"`), así que un campo de más da
> **422** y no un aviso: las listas de abajo son EXACTAS y las ancla
> `api/tests/test_runbook_alta_de_estacion.py` contra los esquemas.

1. **`POST /sites`** — el edificio/ubicación (`api/src/takab_api/schemas/sites.py::SiteCreate`).
   Campos: `tenant_id`, `code`, `name`, `lat`, `lon`, `timezone`, `criticality`, `address`,
   `building_type`.
   - Un rol **interno** (superadmin/support) **debe nombrar `tenant_id`** explícitamente; un
     `tenant_admin` queda forzado a su propio tenant (`api/src/takab_api/routers/_common.py`).
   - `lat/lon` importan: la nube calcula el quórum por **distancia real** entre sitios (§8).
   - `building_type` **sugiere** umbrales por tipología, no los impone (`T-5.16`, `D-28`).
2. **`POST /fleet/gateways`** — el Pi (`schemas/fleet.py::GatewayCreate`).
   Campos: `site_id`, `serial`, `iot_thing`, `has_wr1`, `equipment`, `installed_at`.
   - **`iot_thing`** = el thing de Terraform. Ponlo aquí para que el gabinete deje de estar
     "PENDIENTE DE APROVISIONAR".
   - **No lleva `tenant_id`**: lo hereda del sitio, y la RLS lo valida.
   - **No lleva `fw_version`, y mandarlo da 422.** Es deliberado: la versión la **DECLARA el
     gabinete** en su heartbeat (`T-1.74`), no el formulario. Este runbook lo mandaba hasta el
     2026-09-04.
   - **`equipment`** son los cinco actuadores REALMENTE instalados
     (`siren`/`strobe`/`gas_valve`/`elevator`/`door_retainer`, `schemas/fleet.py::
     EquipmentProfile`). El default es **todo `true`**, así que omitirlo hace que la consola
     pinte cinco actuadores en un gabinete que quizá tiene dos. Decláralo siempre:
     `"equipment": {"siren": true, "strobe": true, "gas_valve": false, "elevator": false,
     "door_retainer": false}`.
3. **`POST /sensors`** — el RS4D (`schemas/sensors.py::SensorCreate`). Campos: `site_id`,
   `gateway_id`, `zone_id`, `kind` (`ground`/`structural`), `model`, `serial`, `channels`
   (default `{EHZ,ENZ,ENN,ENE}`), `sample_rate` (100), `mount`, `lat`, `lon`, y
   **`calibration_source`** (déjalo vacío hasta §7).
   - El `serial` del sensor es el **código de estación** (`R4F74`): la ingesta compara
     `Feature1s.station` contra `sensors.serial` (`handlers.py:8-16`). Si no cuadra, las
     features del gabinete se descartan aunque todo lo demás esté bien.

Puedes hacerlo desde la **consola web** (Flota → alta de sitio/gateway/sensor,
`web/src/features/fleet/`) o por API directa.

### ¿Quién puede registrar estaciones?

La acción se llama **`manage_fleet`** y la tienen **solo**:

| Rol | ¿Puede dar de alta estaciones? |
|---|---|
| `takab_superadmin` | ✅ (en cualquier tenant; debe nombrar el `tenant_id`) |
| `tenant_admin` | ✅ (solo en **su** tenant) |
| `takab_support` | ❌ (lee la flota, no la mueve) |
| `soc_operator`, `gov_operator`, resto | ❌ (solo lectura) |

Fuente: `api/src/takab_api/auth/matrix.py` (`ROLE_ACTION_MATRIX[...]["manage_fleet"]`), reforzado
por RLS en `db/schema.sql`.

---

## 6.bis Parte 5.5 — Conjunto de reglas: sin esto la estación no se sincroniza

**Faltaba en el runbook.** Un gabinete sin `rule_set` aplicable **nunca entra al sincronizado
firmado**: no recibe umbrales, ni equipamiento, ni catálogo — el doc firmado que el edge espera
sencillamente no se produce para él.

```bash
PUT  /rule-sets                       # crea la versión activa del alcance (version+1)
POST /rule-sets/{rule_set_id}/publish # 202: marca la intención de sincronizar al edge
```

- **Alcance**: `scope_type` `tenant` o `site`. Un `rule_set` de **tenant** cubre a toda estación
  nueva de ese cliente — si el cliente ya tiene uno, **esta estación ya está cubierta y no hace
  falta crear otro**. Uno de **sitio** manda sobre el de tenant.
- **El `config` DEBE traer la clave `edge`.** Un `rule_set` sin ella no se sincroniza, y es a
  propósito (`T-1.7`): lo que viaja al gabinete es ese subárbol, firmado.
- El alcance tiene que pertenecer al tenant del token, o 403/404
  (`api/src/takab_api/routers/rule_sets.py:64-78`).
- Verifica en el panel LAN del gabinete que `config_version` deja de ser `v0 · defaults`.

---

## 7. Parte 6 — Calibración y **procedencia**

La consola muestra esta frase en la pestaña de hardware:

> *"Sin procedencia, el PGA/PGV del sitio se presenta en unidades relativas. No hay casilla de
> 'calibrado': hay que nombrar de dónde sale la respuesta instrumental."*

**Qué significa.** No existe un *checkbox* "calibrado" que puedas marcar. En la DB,
`calibrated := (sensors.calibration_source IS NOT NULL)` (`db/schema.sql:142-146`). Es decir: **te
declaras calibrado nombrando la fuente de la respuesta instrumental**, no marcando una casilla que
podría mentir. Mientras `calibration_source` sea `NULL`, el edge usa sensibilidades *placeholder*
y la consola pinta **unidades relativas (`rel.`)** con el badge **"SIN CALIBRAR"**.

**Qué es la "procedencia" y de dónde sale.** Es el **nombre de la respuesta instrumental** del
sensor, p.ej. `stationxml:AM.R4F74`. Sale del **StationXML / RESP del propio Raspberry Shake**,
que obtienes del servicio **FDSN** de la red `AM`. De ahí sacas las **sensibilidades reales**
(counts→físico) por canal. Ejemplo con ObsPy (cliente registrado `RASPISHAKE`):

```python
from obspy.clients.fdsn import Client
inv = Client("RASPISHAKE").get_stations(
    network="AM", station="R4F74", level="response")
# de la respuesta (Scale / overall sensitivity) obtienes, por canal:
#   EHZ (geófono/velocidad)  -> counts por (m/s)
#   EN* (MEMS/aceleración)   -> counts por (m/s^2)
# la sensibilidad que va al edge es el INVERSO: (unidad física) por count.
```

La calibración se aplica en **dos lugares** (ambos, o la consola seguirá diciendo "SIN CALIBRAR"):

1. **En el edge** — sensibilidades reales al `edge.env` del Pi. Se **AGREGAN** (append idempotente,
   nunca re-corriendo `provision`, que sobreescribe el archivo):
   ```dotenv
   TAKAB_EDGE_SIGNAL__VEL_SENSITIVITY_MS_PER_COUNT=2.5021894e-9    # ejemplo real R4F74 (EHZ)
   TAKAB_EDGE_SIGNAL__ACCEL_SENSITIVITY_MS2_PER_COUNT=2.6007802e-6  # ejemplo real R4F74 (EN*)
   ```
   (Valores de ejemplo tomados del StationXML FDSN de AM.R4F74, constantes en todas las épocas —
   T-1.41.) Reinicia `takab-edge.service`.
2. **En la nube** — declara la fuente en el sensor:
   ```
   PUT /sensors/{sensor_id}   body: { "calibration_source": "stationxml:AM.R4F74" }
   ```
   (requiere `manage_fleet`; `api/src/takab_api/routers/sensors.py`).

**Validación (cómo sabes que quedó bien).** Con el edificio **en reposo**, los canales MEMS deben
reportar el **piso de ruido del RS4D ≈ 0.6–1.1 mg**. Si ves eso y la consola ya muestra `g`/`cm/s`
(sin el badge), la calibración es coherente. Una excitación real de AM.R4F74 llegó a **0.567 g en
ENZ** — físicamente consistente con el piso de reposo (T-1.41). Ojo con la caveat de honestidad
que quedó registrada: *"sensibilidad plana @5 Hz, sin deconvolución de respuesta completa"*.

---

## 8. Parte 7 — Verificación end-to-end del alta

- [ ] `systemctl status takab-edge.service` → activo; el log muestra conexión SeedLink al Shake y
      lag bajo (no "dato congelado" — regla de oro 7).
- [ ] En la consola, la estación aparece en **Flota** y en el **mapa** en sus coordenadas.
- [ ] `device_health` reporta heartbeat (rtt MQTT, lag SeedLink, cert).
- [ ] Tras calibrar (§7): la consola muestra **`g`/`cm/s`** (sin "SIN CALIBRAR") para ese sitio.
- [ ] (Opcional, con hardware) prueba LOCAL de actuación desde el panel LAN (T-1.67) sin alertar a
      la nube; y modo prueba del WR-1 (T-1.69) para ejercitar sin generar incidente.
- [ ] **Quórum:** el "3 estaciones al mismo tiempo" se evalúa **en la nube** correlacionando por
      **distancia real** (`|Δt| ≤ dist/v_P + margen`, blueprint §4.5), **entre estaciones y aún
      entre tenants distintos** (las ondas no respetan fronteras de cliente). No dispara hasta que
      haya **≥3 estaciones reales**. La corroboración por estaciones se verá en la consola a partir
      de **T-1.71**. *La actuación local de cada edificio NO espera al quórum* (regla de oro:
      seguridad local autónoma).

---

## 9. Multi-tenant HOY — crear clientes y asignarles estaciones

> **Corregido el 2026-09-04.** Este párrafo decía que «no hay endpoint ni botón para crear
> clientes» y mandaba hacerlo por SQL a mano. `T-1.72` cerró el **2026-07-15**: el alta de
> clientes es API y consola desde entonces.

**Crear un cliente (tenant)** — `POST /tenants`, acción `manage_tenants`, **solo
`takab_superadmin`** (`api/src/takab_api/routers/tenants.py:53`). También desde la consola.

Campos (`db/schema.sql`, tabla `tenants`): `code` (único), `name`, `vertical`, `plan_code`,
`isolation_mode` (`logical`/`dedicated`), `visibility` (`private`/`gov_shared`), `status`.

> **El SQL a mano ya no es el camino** y tiene un precio que no se ve: saltarse el endpoint
> también se salta la fila de `audit_log` que deja el alta, y con ella la evidencia de quién dio
> de alta a ese cliente y cuándo.

**Asignarle estaciones** = crear sus `sites`/`gateways`/`sensores` **bajo ese `tenant_id`** (§6).
Todo hereda el tenant del sitio; el superadmin **nombra el `tenant_id`** al crear el sitio. Una
estación **no se puede mover** a otro tenant (los routers bloquean el cruce con 403).

---

## 10. Visibilidad ACTUAL — quién ve qué

> **Corregido el 2026-09-04.** Este párrafo decía que la visibilidad era «fija por rol, no
> configurable». `T-1.73` cerró el **2026-07-15**: hay concesiones explícitas desde entonces —
> `POST /visibility-grants` y `DELETE /visibility-grants/{id}`, acción `manage_visibility`, solo
> `takab_superadmin` (`api/src/takab_api/routers/visibility.py:45-84`).
>
> La tabla de abajo sigue describiendo el **default por rol**, que es lo que rige mientras no
> haya una concesión; una concesión lo AMPLÍA, nunca lo recorta.

| Quién | Ve qué (metadatos **y** datos) | ¿Configurable? |
|---|---|---|
| `takab_superadmin` / `takab_support` | **Todo** (todos los clientes), siempre. | No (fijo por rol). |
| `tenant_admin`, `soc_operator`, … | **Solo lo de su propio cliente**, siempre. | No. |
| `gov_operator` (Protección Civil) | Lo suyo **+** clientes marcados `visibility='gov_shared'` (solo lectura). | Sí, pero es un flag por-tenant en la DB, solo gov. |

Mecanismo: **Row-Level Security** default-deny + `FORCE` en toda tabla de negocio
(`db/schema.sql`, helpers `app_tenant_id()`, `app_is_takab_internal()`, `app_gov_can_see()`
`:490-511`; políticas `:517-702`). Los **datos** (waveform/métricas) siguen la **misma frontera
de tenant** que los metadatos, aislados por las vistas `*_secure` (por el conflicto TimescaleDB+RLS).

---

## Apéndice — checklist rápido de alta

0. [ ] (Cliente nuevo) `POST /tenants` — superadmin, acción `manage_tenants` (§9).
1. [ ] Shake en red; anota IP y código de estación `AM.Rxxxx` (no tocar Shake OS).
2. [ ] Terraform: agrega el thing a `gateway_fleet` → `apply`.
3. [ ] `provision_gateway.sh <thing> <ssh_host>` → certs + secretos en el Pi; guarda el PIN.
4. [ ] **Agrega** identidad + SeedLink + rutas de cert al `edge.env` (append; no re-provisiones).
       **La identidad son CÓDIGOS, no UUIDs**, y `TAKAB_EDGE_GATEWAY_ID` ya está puesto: **no lo
       toques** (§5).
5. [ ] `deploy/edge/deploy.sh <ssh_host>` — instala el software del edge (§5.bis).
6. [ ] `POST /fleet/releases` con el `FW_VERSION` EXACTO que escribió el paso anterior (§5.ter).
7. [ ] Nube: `POST /sites` → `POST /fleet/gateways` (con `iot_thing` y **`equipment`**, **sin
       `fw_version`**) → `POST /sensors` (rol `manage_fleet`, §6).
8. [ ] `rule_set` aplicable al sitio o a su tenant, con clave `edge`, y **publicado** (§6.bis).
       Sin esto la estación no entra al sincronizado firmado.
9. [ ] Calibra: sensibilidades al `edge.env` (append) **+** `PUT /sensors` `calibration_source`.
10. [ ] Reinicia `takab-edge.service`; verifica flota, heartbeat, reposo 0.6–1.1 mg, unidades `g`,
        y que el panel LAN deje de decir `v0 · defaults`.
