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

> **GOTCHA CRÍTICO (de T-1.41):** `provision_gateway.sh` **SOBRESCRIBE** `/etc/takab/edge.env` y
> solo escribe **tres** líneas — `TAKAB_EDGE_HMAC_KEY`, `TAKAB_EDGE_MQTT_ENDPOINT`,
> `TAKAB_EDGE_LOCAL_API_PIN` — más los certs. **El resto del `edge.env` (identidad, SeedLink,
> rutas de cert, calibración) se AGREGA después** (§5, §7). Si vuelves a correr `provision`,
> **borra** esos añadidos: re-aplica la identidad, SeedLink y calibración tras cada re-provision.

---

## 5. Parte 4 — Completar el `edge.env` del gabinete

`provision` dejó los secretos. Ahora **agrega** (append) los bloques restantes a
`/etc/takab/edge.env` en el Pi. Todas las variables llevan prefijo `TAKAB_EDGE_`; los campos
anidados usan doble guion bajo `__` (`edge/takab_edge/config/settings.py`).

```dotenv
# --- (ya lo puso provision_gateway.sh) ---
# TAKAB_EDGE_HMAC_KEY=...
# TAKAB_EDGE_MQTT_ENDPOINT=...
# TAKAB_EDGE_LOCAL_API_PIN=...

# --- Identidad (multi-tenant) --- deben COINCIDIR con lo que registres en la nube (§6)
TAKAB_EDGE_TENANT_ID=<uuid del tenant/cliente>
TAKAB_EDGE_SITE_ID=<uuid del sitio>
TAKAB_EDGE_GATEWAY_ID=<uuid del gateway>
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
```

El servicio `systemd` (`edge/systemd/takab-edge.service`) ya fuerza `TAKAB_EDGE_DEV_MODE=false`,
lee `EnvironmentFile=/etc/takab/edge.env` y corre con `WorkingDirectory=/var/lib/takab`
(obligatorio: lgpio escribe su FIFO ahí). Reinicia el servicio tras editar el `edge.env`:
```bash
sudo systemctl restart takab-edge.service && systemctl status takab-edge.service
```

---

## 6. Parte 5 — Registrar la estación en la nube (API)

Una "estación" en la nube = **un sitio (`site`) + un gateway + uno o más sensores**. Se crean en
**este orden** (cada uno hereda el `tenant_id` del anterior):

1. **`POST /sites`** — el edificio/ubicación.
   Campos: `code`, `name`, `lat`, `lon`, `timezone`, `criticality`, `address`, `building_type`.
   - Un rol **interno** (superadmin/support) **debe nombrar `tenant_id`** explícitamente; un
     `tenant_admin` queda forzado a su propio tenant (`api/src/takab_api/routers/_common.py`).
   - `lat/lon` importan: la nube calcula el quórum por **distancia real** entre sitios (§8).
2. **`POST /fleet/gateways`** — el Pi. Campos: `site_id`, `serial`, `fw_version`,
   **`iot_thing`** (= el thing de Terraform; ponlo aquí para que deje de estar "PENDIENTE DE
   APROVISIONAR"), `has_wr1`, `installed_at`. **No** lleva `tenant_id` (lo hereda del sitio).
3. **`POST /sensors`** — el RS4D. Campos: `site_id`, `gateway_id`, `kind` (`ground`/`structural`),
   `model`, `serial`, `channels` (default `{EHZ,ENZ,ENN,ENE}`), `sample_rate` (100), `mount`,
   `lat/lon`, y **`calibration_source`** (déjalo vacío hasta §7).

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

> **Estado actual (antes de T-1.72):** **no hay** endpoint ni botón para crear clientes. Se hace
> por **SQL** en la DB. T-1.72 traerá el alta de clientes desde la consola (superadmin).

**Crear un cliente (tenant) hoy** — vía seed/migración SQL (patrón `db/seeds/prod_fleet.sql`),
aplicada como superusuario/`takab_migrator`:
```sql
INSERT INTO tenants (code, name, vertical, plan_code, isolation_mode, status)
VALUES ('hospital-central', 'Hospital Central Puebla', 'salud', 'mvp', 'logical', 'active');
```
Campos (`db/schema.sql:68-78`): `code` (único), `name`, `vertical`, `plan_code`,
`isolation_mode` (`logical`/`dedicated`), `visibility` (`private`/`gov_shared`), `status`.

**Asignarle estaciones** = crear sus `sites`/`gateways`/`sensores` **bajo ese `tenant_id`** (§6).
Todo hereda el tenant del sitio; el superadmin **nombra el `tenant_id`** al crear el sitio. Una
estación **no se puede mover** a otro tenant (los routers bloquean el cruce con 403).

---

## 10. Visibilidad ACTUAL — quién ve qué

> **Estado actual (antes de T-1.73):** la visibilidad es **fija por rol**, no configurable. T-1.73
> traerá la visibilidad **configurable** por el superadmin (ver que existen / ver datos, de un
> cliente o de todos).

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

1. [ ] Shake en red; anota IP y código de estación `AM.Rxxxx` (no tocar Shake OS).
2. [ ] Terraform: agrega el thing a `gateway_fleet` → `apply`.
3. [ ] `provision_gateway.sh <thing> <ssh_host>` → certs + secretos en el Pi; guarda el PIN.
4. [ ] **Agrega** identidad + SeedLink + rutas de cert al `edge.env` (append; no re-provisiones).
5. [ ] Nube: `POST /sites` → `POST /fleet/gateways` (con `iot_thing`) → `POST /sensors`
       (rol `manage_fleet`).
6. [ ] Calibra: sensibilidades al `edge.env` (append) **+** `PUT /sensors` `calibration_source`.
7. [ ] Reinicia `takab-edge.service`; verifica flota, heartbeat, reposo 0.6–1.1 mg, unidades `g`.
8. [ ] (Cliente nuevo) crea el tenant por SQL y cuelga sus sitios/gateways/sensores del `tenant_id`.
