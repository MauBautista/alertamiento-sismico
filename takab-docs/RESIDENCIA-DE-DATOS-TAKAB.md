# RESIDENCIA DE DATOS — TAKAB Ailert

> **Documento de decisión (T-2.83).** Evalúa migrar la nube de TAKAB de `us-east-2` (Ohio,
> EE. UU.) a `mx-central-1` (México Central). Todas las cifras de este documento están
> **medidas o citadas de fuente primaria**; lo que no se pudo medir está declarado como hueco.
> Ninguna cifra es estimada.
>
> Fecha de la evaluación: **2026-08-08** · Autor: Mauricio Bautista

---

## 1. Recomendación

> ## **NO MIGRAR a `mx-central-1` hoy. Seguir en `us-east-2`.**
>
> **Razón, en una línea: AWS IoT Core no existe en la región de México.** Es el servicio por
> el que entra cada gabinete a la nube (MQTT/mTLS). Sin él no hay producto que migrar.
>
> No es una decisión de coste (México cuesta +5 %, trivial) ni de latencia (México sería
> **48 ms más rápido**, medido — y esa latencia **no está en el camino crítico de
> alertamiento**). Es de disponibilidad de servicio: **la migración hoy no es cara, es
> imposible.**

**Esta recomendación se revisa el día que AWS anuncie IoT Core en `mx-central-1`.** Ver §7,
que fija las condiciones exactas de revisión. Hasta entonces, la respuesta al cliente no es
"no queremos", es "AWS todavía no lo permite, y esto es lo que sí hacemos mientras tanto".

---

## 2. La respuesta corta al cliente

*Redactada para leerse en voz alta, tal cual, en una llamada.*

> «Sus datos están hoy en el centro de datos de Amazon Web Services en Ohio, Estados Unidos.
>
> Le explico por qué y qué implica.
>
> AWS abrió una región en México en enero de 2025, y la evaluamos formalmente. **El servicio
> que conecta los gabinetes sísmicos con nuestra nube —AWS IoT Core— todavía no está
> disponible en la región de México.** Lo verificamos contra la documentación oficial de AWS
> y midiéndolo nosotros mismos: el punto de conexión sencillamente no existe en México. Así
> que hoy no es que hayamos elegido Estados Unidos frente a México; es que México todavía no
> ofrece la pieza central.
>
> Ahora, lo importante: **la ubicación de la nube no afecta a su seguridad durante un sismo.**
> El sistema está diseñado para que la alerta sísmica y la activación de sirena, válvulas de
> gas, ascensores y puertas ocurran **100 % dentro de su edificio**, sin pasar por internet ni
> por la nube. Si se cae el enlace, o se cae Amazon entero, su gabinete sigue detectando y
> sigue actuando. La nube sirve para coordinar entre edificios, para la consola y para el
> expediente posterior — no para salvarle la vida en el segundo cero.
>
> Sobre el marco legal: la ley mexicana de protección de datos **permite** las transferencias
> internacionales cumpliendo sus requisitos, y **no exige** que los datos permanezcan
> físicamente en territorio nacional. Le entregamos por escrito el detalle de qué datos
> personales tratamos, con qué base y con qué controles. Si su institución tiene una política
> interna o una cláusula contractual que sí exija territorio nacional, dígamelo: es una
> conversación distinta y la tenemos con gusto — tenemos identificado exactamente qué haría
> falta y cuánto tardaría.»

**Si el cliente insiste en residencia en México**, la respuesta honesta es: es técnicamente
posible mover *casi todo* (base de datos, S3, consola, colas, identidad) a `mx-central-1`,
pero **la ingesta de los gabinetes seguiría entrando por IoT Core en EE. UU.** mientras AWS no
lo lleve a México — salvo que se sustituya IoT Core por un broker MQTT propio, lo que cambia
el perfil de riesgo del sistema. Ver §7.

---

## 3. Disponibilidad de servicios — esto decide el asunto

### 3.1 Qué usa TAKAB hoy

Inventario tomado de `infra/terraform/` (no de memoria), contando los tipos de recurso
declarados:

| Servicio AWS | Dónde se declara | Para qué |
|---|---|---|
| **AWS IoT Core** | `modules/iot-core/`, `modules/iot-gateway/` (`aws_iot_thing`, `aws_iot_policy`, `aws_iot_certificate`, 3 × `aws_iot_topic_rule`) | **Entrada de cada gabinete** (MQTT/mTLS) y comandos nube→edge |
| Amazon SQS | `modules/messaging/` (2 colas + 2 DLQ) | Desacople de ingesta y backfill |
| Amazon S3 | `modules/storage/` (2 buckets) | miniSEED de eventos, evidencia, dictámenes PDF |
| Amazon Cognito | `modules/identity/` (2 pools, 3 clientes, 2 dominios, grupos) | Auth de consola web y app móvil |
| AWS KMS | `modules/kms/` (3 claves + alias) | Cifrado en reposo |
| Amazon SNS | `modules/push/` (`aws_sns_platform_application` APNS + FCM), `modules/observability/` (topic + suscripción) | **Push móvil** y alarmas de operación |
| Amazon SES v2 | `modules/observability/` (`aws_sesv2_email_identity`) | Correo de notificación |
| Amazon CloudWatch | `modules/observability/` (8 alarmas, log group, metric filter) | Observabilidad y alarma de gabinete mudo |
| Amazon EC2 + EBS + DLM | `modules/database/`, `modules/serve/` | Postgres/TimescaleDB, API y consola, snapshots |
| Secrets Manager, SSM, ECR, IAM, VPC, DynamoDB | varios módulos | Secretos, PITR, imágenes, red, locking de Terraform |

> **Nota de precisión:** el `CLAUDE.md` §3 nombra **ECS Fargate** como capa de cómputo
> objetivo. En el Terraform de hoy **no hay ningún recurso ECS/Fargate**: la API corre sobre
> `aws_instance` (EC2). Para esta decisión da igual —Fargate **sí está** en México (ver 3.2)—
> pero conviene no arrastrar el supuesto.

### 3.2 Qué hay y qué no en `mx-central-1`

| Servicio | ¿En `mx-central-1`? | Fuente primaria |
|---|---|---|
| **AWS IoT Core** | **NO** | 4 fuentes independientes — ver 3.3 |
| AWS IoT Device Management / Device Defender / Greengrass / SiteWise | **NO** | Tabla regional AWS; `greengrass.mx-central-1` y `iotwireless.mx-central-1` = NXDOMAIN |
| **Amazon SES** | **NO** | [Endpoints SES](https://docs.aws.amazon.com/general/latest/gr/ses.html) — la tabla no incluye `mx-central-1`; las 4 variantes de endpoint dan NXDOMAIN |
| **SNS mobile push** (APNS/FCM) | **NO** (evidencia fuerte) | El fichero de precios de SNS de `mx-central-1` tiene 17 SKUs y **ninguno** de push móvil; en `us-east-2` existen. Ver §5 y §8 |
| Amazon Cognito (user pools + identity pools) | **SÍ** | [Endpoints Cognito](https://docs.aws.amazon.com/general/latest/gr/cognito_identity.html) — fila `Mexico (Central) \| mx-central-1 \| cognito-idp.mx-central-1.amazonaws.com` |
| AWS Fargate (ECS Linux) | **SÍ** | [Regiones Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate-Regions.html) — fila `Mexico (Central) \| mx-central-1` |
| SQS, S3, KMS, CloudWatch (+Logs), EC2, EBS, Secrets Manager, SSM, ECR, ECS, DynamoDB, RDS, CloudFront, Route 53, ACM, IAM | **SÍ** | Tabla regional AWS + sonda de endpoint propia (todos responden con error propio del servicio, no NXDOMAIN) |
| SNS (tópicos, colas, correo, HTTP) | **SÍ** | Tabla regional + `sns.mx-central-1` responde `<UnknownOperationException/>` |
| AWS End User Messaging (SMS/voz/social) | **SÍ** | `sms-voice.mx-central-1` y `social-messaging.mx-central-1` resuelven |

En total, `mx-central-1` tiene **121** servicios frente a **185** en `us-east-2`; **64**
servicios presentes en Ohio no están en México. La lista completa de los 64 se puede
regenerar con el script de §8.3.

### 3.3 El hallazgo decisivo: IoT Core no está en México

Es la única afirmación de la que depende toda la recomendación, así que está verificada
**cuatro veces, por vías independientes**:

1. **Documentación canónica de AWS.**
   [AWS IoT Core endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
   lista **25 regiones** en las tablas de *Control Plane* y *Data Plane*. `mx-central-1`
   **no aparece en ninguna**.
2. **DNS, plano de control.** `iot.mx-central-1.amazonaws.com` → **NXDOMAIN en 40/40
   intentos**, mientras `iot.us-east-2.amazonaws.com` resolvió las 40 veces.
3. **DNS, plano de datos (la ruta real del gabinete).**
   `data-ats.iot.mx-central-1.amazonaws.com` → **NXDOMAIN**;
   `data-ats.iot.us-east-2.amazonaws.com` → resuelve y acepta conexión en el puerto 8883.
4. **API pública de precios de AWS.** El `region_index.json` de la oferta `AWSIoT` lista
   **25 regiones** y `mx-central-1` no está entre ellas — AWS ni siquiera publica una tarifa
   de IoT Core para México. Reproducible con el script de §8.3.

**Consecuencia arquitectónica.** IoT Core no es un adorno: es el punto de entrada MQTT/mTLS de
cada gabinete, el emisor de los comandos firmados nube→gateway (regla de oro 8) y el sustrato
de las 3 `aws_iot_topic_rule` que alimentan SQS. Migrar la nube a México **sin** IoT Core
obligaría a una de estas dos cosas:

- **(a)** Dejar la ingesta en `us-east-2` y mover el resto a México. Resultado: los datos de
  telemetría **siguen atravesando EE. UU.**, con lo que la residencia que el cliente pidió no
  se consigue de verdad. Además duplica la superficie de operación en dos regiones.
- **(b)** Sustituir IoT Core por un **broker MQTT propio** (p. ej. Mosquitto/EMQX sobre EC2 en
  México). Es viable, pero traslada a TAKAB la responsabilidad de alta disponibilidad,
  rotación de certificados X.509, autorización por tópico y escalado — hoy delegadas en un
  servicio gestionado. **Eso es un cambio de perfil de riesgo en el camino que trae los datos
  de un sistema donde fallar cuesta vidas, y no se hace para ahorrar 48 ms que no están en el
  camino crítico.**

Ninguna de las dos justifica la migración hoy.

> **Dato de contexto, no promesa:** AWS **sí sigue expandiendo** IoT Core a regiones nuevas —
> [Europa (España) y Asia-Pacífico (Malasia) en julio de 2025](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-iot-region-expansion/)
> e [Israel (Tel Aviv) y Europa (Milán) en abril de 2026](https://aws.amazon.com/about-aws/whats-new/2026/04/aws-iot-israel-tel-aviv-europe-milan/).
> Que México llegue es plausible. **No hay ningún anuncio de AWS que lo comprometa**, y este
> documento no lo supone. Es exactamente la condición de revisión de §7.

---

## 4. Latencia — medida desde México, no citada

### 4.1 Qué se midió y cómo

Medido el **2026-08-08** desde la máquina de desarrollo de TAKAB, sobre una **conexión
doméstica en México** — el mismo tipo de enlace que tendría un gabinete en un edificio
mexicano.

Se comprobó primero que **no hay proxy** (`env | grep -i proxy` vacío) y que cada endpoint
resuelve a **IPs regionales distintas** (`s3.mx-central-1` → `16.12.72.1`;
`s3.us-east-2` → `52.219.102.89`), de modo que las diferencias no son un artefacto de caché
ni de un intermediario.

**Método A — `curl`, 40 repeticiones por endpoint, intercaladas** (`/tmp/takab_lat.sh`):

```bash
curl -s -o /dev/null --no-keepalive \
  -w "%{time_namelookup},%{time_connect},%{time_appconnect},%{time_starttransfer},%{http_code}" \
  "https://$endpoint/"
```

> ### ⚠️ Cómo leer estos números — los contadores de `curl` son ACUMULATIVOS
>
> Esto importa, porque si no se dice, **quien reproduzca el comando obtiene cifras distintas
> de las publicadas y con razón desconfía de todo el documento.**
>
> `curl` mide **desde el inicio de la petición**, no por tramos. Es decir:
> `time_connect` **ya incluye** `time_namelookup` (el DNS), y `time_appconnect` **ya incluye**
> `time_connect`. Ejemplo real de esta medición sobre `s3.mx-central-1`:
> `time_namelookup = 48.4 ms`, `time_connect = 60.2 ms` → **el round-trip TCP real fue
> 60.2 − 48.4 = 11.9 ms**.
>
> **Este documento publica los TRAMOS, no los acumulados:**
> - **`TCP` = `time_connect − time_namelookup`** → el round-trip de red puro.
> - **`TLS` = `time_appconnect − time_connect`** → solo el handshake.
> - **`TTFB` = `time_starttransfer`** → este sí **es acumulado** (contiene DNS + TCP + TLS +
>   respuesta), y se publica tal cual sale de `curl`.
>
> **Por qué se resta el DNS:** el tiempo de resolución lo pone el *resolver local*, no la
> región de AWS. En esta misma tanda osciló entre **15.2 ms** (`sqs.mx-central-1`) y **48.4 ms**
> (`s3.mx-central-1`) según el estado de la caché — ruido que no dice nada sobre dónde está el
> centro de datos. Dejarlo dentro **contaminaría la comparación**, que es justo lo que se
> quiere medir. La tabla de §4.2 publica **ambas columnas** para que la reproducción cuadre.

**Método B — `socket.connect()` en Python, 30 repeticiones, con el DNS resuelto *fuera* del
cronómetro** (`/tmp/takab_sock_lat.py`). Es el **control cruzado del método A**: al no medir
DNS en absoluto, no hay nada que restar, y su resultado debe coincidir con la columna `TCP` de
A. Incluye además el **puerto 8883 (MQTT/mTLS)**, que es la ruta real del gabinete.

### 4.2 Resultados

**Método A — 40 repeticiones por endpoint, medianas en ms.** Las dos primeras columnas son lo
que **imprime `curl`** (acumulado, reproducible tal cual); las tres últimas son los **tramos**
derivados de ellas:

| Endpoint | n | `time_namelookup` (DNS) | `time_connect` (acum.) | **TCP** = conn − DNS | p10 | p90 | **TLS** = appconn − conn | TTFB (acum.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `s3.mx-central-1.amazonaws.com` | 40 | 48.4 | 60.2 | **11.9** | 11.1 | 12.3 | 30.1 | 95.9 |
| `s3.us-east-2.amazonaws.com` | 40 | 46.9 | 106.4 | **59.5** | 58.7 | 60.5 | 70.2 | 231.4 |
| `sqs.mx-central-1.amazonaws.com` | 40 | 15.2 | 27.8 | **12.3** | 11.7 | 12.7 | 29.7 | 70.2 |
| `sqs.us-east-2.amazonaws.com` | 40 | 48.2 | 109.1 | **59.9** | 59.0 | 61.5 | 70.2 | 234.3 |
| `iot.us-east-2.amazonaws.com` | 40 | 17.1 | 77.0 | 59.7 | 58.9 | 60.6 | 70.1 | 206.8 |
| `iot.mx-central-1.amazonaws.com` | **0** | — | — | — | — | — | — | **40/40 sin conexión: NXDOMAIN** |

> **Comprobación aritmética** (para quien quiera auditar la tabla sin reejecutar nada):
> `60.2 − 48.4 = 11.8` ≈ **11.9**, y `106.4 − 46.9 = 59.5` ✓. Las pequeñas diferencias en el
> último decimal son porque **cada columna es la mediana de su propia serie**, no la resta de
> dos medianas. El cálculo exacto —restar por muestra y *luego* tomar la mediana— está en el
> script de §8.3, comando (4).

**Método B — `connect()` TCP puro (ms), 30 repeticiones, DNS excluido por construcción:**

| Objetivo | n | mediana | p10 | p90 | min | max |
|---|---:|---:|---:|---:|---:|---:|
| `data-ats.iot.us-east-2.amazonaws.com:8883` *(ruta real del gabinete)* | 30 | **60.5** | 59.6 | 107.8 | 59.1 | 145.9 |
| `s3.us-east-2.amazonaws.com:443` | 30 | 59.5 | 58.4 | 162.4 | 57.7 | 168.7 |
| `s3.mx-central-1.amazonaws.com:443` | 30 | **12.1** | 11.4 | 14.8 | 11.1 | 21.4 |
| `sqs.mx-central-1.amazonaws.com:443` | 30 | 12.4 | 11.2 | 13.4 | 10.9 | 126.0 |

**Los dos métodos coinciden**: ~12 ms a México frente a ~60 ms a Ohio. La dispersión de México
es además más estrecha (p10–p90 de 1.2 ms frente a 1.8 ms en Ohio por el método A).

### 4.3 Qué prueban y qué NO prueban estos números

**Prueban:** que desde una conexión doméstica mexicana, el round-trip a la región de México es
**unos 48 ms menor** que a Ohio, de forma consistente y con poca varianza. Como el gabinete
publica por MQTT desde México, es un proxy razonable de lo que vería el edge.

**NO prueban, y no debe afirmarse:**

- **No** miden latencia *entre servicios dentro de* AWS (API↔RDS, SQS↔consumidor). Eso exige
  desplegar en la región y no se hizo.
- **No** miden rendimiento, throughput ni disponibilidad de `mx-central-1`. Un round-trip
  corto no dice nada sobre si la región aguanta carga.
- **No** son representativos de otras conexiones: se midieron desde **un solo enlace
  doméstico**, en **una sola franja horaria**, en **un solo día**. Otro ISP, otro estado de la
  república u otra hora pueden dar otra cosa.
- **No** miden latencia de extremo a extremo de la aplicación. `TTFB` incluye el tiempo de
  respuesta de un endpoint público a una petición no firmada; no es una operación real.

### 4.4 Cuánto importa de verdad esta latencia

**Poco, y conviene decirlo sin inflarlo.** Por las reglas de oro 1 y 2 del proyecto:

- **El camino crítico de alertamiento no toca la nube.** SASMEX → WR-1 → GPIO → relé ocurre
  íntegramente dentro del gabinete. El reflejo físico está medido en campo en **6.65 ms**
  (Fase 1.9) y el WR-1 en **4.16 ms** (Fase 2.1). Frente a eso, 48 ms de nube **no aparecen en
  la ecuación**: no están en el camino.
- **El edge opera sin nube.** Si el enlace cae, el gabinete sigue detectando, accionando y
  almacenando. La latencia a la nube no puede degradar la seguridad local porque la seguridad
  local no depende de la nube.

**Dónde sí se notarían los 48 ms**, honestamente:

1. **Quórum colaborativo** (≥3 estaciones correlacionadas en la nube). Menos latencia de subida
   adelanta la confirmación. Pero el quórum **jamás gatea el camino SASMEX**, y su ventana de
   asociación se rige por la física de la propagación (`|Δt| ≤ dist/v_P + margen`, blueprint
   §4.5), del orden de **segundos** a 90–110 km. **48 ms es ruido frente a esa ventana.**
2. **Comandos firmados nube→gateway.** Llegarían ~48 ms antes. Relevante y real, pero de nuevo
   pequeño frente al presupuesto de tiempo de una actuación por quórum.
3. **Consola SOC y app móvil.** Es donde más se notaría en *percepción*: cada round-trip de la
   API y cada mensaje del WebSocket ahorraría ~48 ms. Se nota al usarla; no cambia ninguna
   decisión de seguridad.

**Conclusión de la sección:** la latencia es un argumento **a favor** de México, es **real y
está medida** — y aun así **no es suficiente**, porque el servicio que hace falta no está. Si
IoT Core llegara a México, este apartado pasaría de "irrelevante para la decisión" a "una razón
más para migrar".

---

## 5. Coste

### 5.1 Base de consumo declarada — leer antes que la tabla

**El consumo real de TAKAB hoy es de desarrollo.** La cuenta `dev` (634882473845) tiene un
**budget de 50 USD** (`infra/terraform/envs/dev/budget.tf`) y sostiene un solo gabinete
(`gw-dev-0001`). Sobre esa base, un +5 % es **del orden de 2–3 USD al mes**: no es una
conversación.

Sobre una flota comercial sí lo sería, pero **no tenemos esa factura todavía**, así que este
documento **no proyecta un total**. Extrapolar un coste de flota a partir de un entorno de
desarrollo produciría exactamente el tipo de cifra inventada que este documento evita. Lo que
sí se puede afirmar con solidez es el **patrón de precio unitario**, que es estable y no
depende del volumen.

### 5.2 Precios unitarios publicados — MX vs Ohio

Todas las cifras salen de la **API pública de precios de AWS** (Price List Bulk API, sin
credenciales). Las páginas web de precios de AWS **no** sirvieron: cargan las tablas por
JavaScript y el `WebFetch` devuelve la página sin celdas — se declara explícitamente en §8.

| Concepto | `mx-central-1` | `us-east-2` | Δ |
|---|---:|---:|---:|
| EC2 `t3.medium` Linux on-demand | $0.0437 /h | $0.0416 /h | **+5.05 %** |
| EC2 `m7g.large` Linux on-demand | $0.0857 /h | $0.0816 /h | **+5.02 %** |
| EBS gp3 almacenamiento | $0.084 /GB-mes | $0.080 /GB-mes | **+5.00 %** |
| EBS gp3 IOPS aprovisionadas | $0.0053 /IOPS-mes | $0.0050 /IOPS-mes | +6.00 % |
| **S3 Standard, primeros 50 TB** | **$0.024150 /GB-mes** | **$0.023000 /GB-mes** | **+5.00 %** |
| SQS cola estándar (tier 1) | $0.42 /millón | $0.40 /millón | **+5.00 %** |
| SNS peticiones API | $0.525 /millón | $0.50 /millón | **+5.00 %** |
| SNS correo | $2.10 /100 000 | $2.00 /100 000 | +5.00 % |
| **Cognito MAU** (tier 1, 0–50 k) | $0.0055 /MAU | $0.0055 /MAU | **0 %** |
| Cognito Essentials / Plus MAU | $0.015 / $0.020 | $0.015 / $0.020 | 0 % |
| **KMS clave gestionada** | $1.00 /clave-mes | $1.00 /clave-mes | **0 %** |
| KMS peticiones | $0.03 /10 000 | $0.03 /10 000 | 0 % |
| **CloudWatch métrica personalizada** | $0.30 /métrica-mes | $0.30 /métrica-mes | **0 %** |
| CloudWatch Logs ingeridos | $0.50 /GB | $0.50 /GB | 0 % |
| **Salida a internet, primeros 10 TB** | $0.09 /GB | $0.09 /GB | **0 %** |
| **AWS IoT Core** | **sin tarifa publicada** | — | **no comparable** |
| **SNS mobile push** | **sin SKU en el price list** | $0.50 /millón | **no comparable** |

**El patrón es nítido y fácil de explicar a un cliente:** México cobra **exactamente +5 %**
sobre Ohio en todo lo que consume **infraestructura regional** (cómputo, disco, objetos,
colas, peticiones), y **paridad exacta (0 %)** en servicios de control, identidad y
observabilidad (Cognito, KMS, CloudWatch) y en la **salida a internet**.

**Coste no es el motivo para no migrar.** Un +5 % sobre infraestructura es perfectamente
absorbible y sería un argumento comercial razonable si la migración fuera posible.

### 5.3 Verificación independiente

Las dos cifras de las que más depende el argumento se **re-verificaron por separado** contra
la API de precios (`/tmp/takab_verify_price.py`), sin reutilizar el resultado previo:

- `AWSIoT/current/region_index.json` → **25 regiones, `mx-central-1` ausente, `us-east-2`
  presente**.
- S3 Standard 0–50 TB → MX `0.0241500000` USD/GB-Mo (sku `S3X8W88Y5FFCKV5C`) vs Ohio
  `0.0230000000` USD/GB-Mo (sku `YPGKVRB2EKTVDJDT`) = **+5.00 % exacto**.

Ficheros de precios consultados (fecha de publicación de AWS): EC2 `20260806171752`,
S3 `20260807185915`, SQS `20250828200713`, SNS `20260211000229`, KMS `20250828153913`,
CloudWatch `20260806201840`, Cognito `20260622204707`, DataTransfer `20260720184645`.

---

## 6. Marco legal

> **Advertencia previa, vinculante para el uso de esta sección.** Esto es **reporte
> documental**, no opinión jurídica. Aquí se transcribe lo que dicen las fuentes oficiales
> citadas, con su artículo y su URL. **Nadie en TAKAB es abogado.** Lo que necesita
> confirmación profesional está listado en §6.7 y debe confirmarse **antes** de responder por
> escrito a un cliente que invoque una obligación legal.
>
> Esta sección se escribe con la disciplina que impuso el incidente `[ANALISIS-00]` del
> blueprint §9: la cita "NOM-003-SCT" que sostenía un requisito resultó ser una norma de
> **transporte de residuos peligrosos** que no aplicaba. Por eso aquí **cada norma se verificó
> descargando su texto oficial**, no citándola de memoria.

### 6.1 La pregunta que hace el cliente, y la respuesta

**¿La ley mexicana obliga a que los datos personales se queden físicamente en México?**

> ## **No. Ninguna de las dos leyes aplicables impone residencia territorial.**

Lo comprobamos **nosotros mismos**: se descargó el PDF oficial de la LFPDPPP vigente desde la
Cámara de Diputados y se barrió el texto completo. La palabra **`territorio` aparece exactamente
dos veces**, y ninguna impone localización:

- **Art. 1** — *"…es de orden público y de observancia general en todo el **territorio
  nacional**…"* → ámbito de aplicación de la ley, no ubicación de servidores.
- **Art. 2, fr. XX** — *"Transferencia: Toda comunicación de datos personales **dentro o fuera
  del territorio mexicano**, realizada a persona distinta de la titular, del responsable o de
  la persona encargada del tratamiento."* → contempla expresamente la salida del país como
  algo lícito y regulado.

La palabra **`nube` aparece 0 veces** en la ley (el cómputo en la nube se regula en el
Reglamento — ver 6.4).

### 6.2 Qué ley rige hoy (agosto de 2026)

Hubo un cambio de marco reciente y conviene tenerlo bien:

| | |
|---|---|
| **Ley vigente** | **Ley Federal de Protección de Datos Personales en Posesión de los Particulares** — *nueva ley*, DOF **20 de marzo de 2025**, en vigor al día siguiente. Última reforma **DOF 14-11-2025** |
| **Qué abrogó** | La LFPDPPP de **05-07-2010** y la LGPDPPSO de **26-01-2017** (Transitorio Segundo, fr. I y IV) |
| **Por qué cambió** | Reforma constitucional de **simplificación orgánica**, DOF **20-12-2024**, que **extinguió el INAI** |
| **Autoridad hoy** | **Secretaría Anticorrupción y Buen Gobierno** (art. 2, fr. XV; atribuciones en el art. 39) |

Verificado en el encabezado oficial del PDF de la Cámara de Diputados:
*"Nueva Ley publicada en el Diario Oficial de la Federación el 20 de marzo de 2025 — TEXTO
VIGENTE — Última reforma publicada DOF 14-11-2025."* El término `Anticorrupción` aparece 13
veces en el articulado.

**Consecuencia práctica:** cualquier documento comercial de TAKAB que todavía cite la LFPDPPP
de 2010 o al INAI está desactualizado y hay que corregirlo.

### 6.3 Transferencias internacionales — permitidas, con condiciones

**El punto más importante para TAKAB, y conviene entenderlo bien: AWS es un *encargado*, no un
*tercero*.** El art. 2, fr. XX define transferencia como comunicación a persona *"distinta de
la titular, del responsable o **de la persona encargada** del tratamiento"*. Un proveedor de
infraestructura que trata datos **bajo instrucciones de TAKAB** queda **excluido de la
definición de transferencia**, y por tanto fuera del régimen del Capítulo V. El art. 35 lo
repite: obliga respecto de *"terceros nacionales o extranjeros, **distintos de la persona
encargada**"*.

**Esta calificación es la que sostiene el análisis de bajo riesgo, y es justamente la que un
abogado debe confirmar** (§6.7, punto 2).

Cuando **sí** hay transferencia a un tercero, la ley la permite:

- **Art. 35, 2.º párrafo** — el aviso de privacidad *"contendrá una cláusula en la que se
  indique si la persona titular acepta o no la transferencia de sus datos"*, y el receptor
  *"asumirá las mismas obligaciones que correspondan al responsable que transfirió los datos"*.
- **Art. 36** — enumera **siete supuestos** en que la transferencia (nacional **o
  internacional**) procede **sin consentimiento**. Dos son directamente relevantes para TAKAB:
  **fr. II** (prevención o diagnóstico médico, asistencia sanitaria, tratamiento médico o
  gestión de servicios sanitarios) y **fr. VII** (mantenimiento o cumplimiento de una relación
  jurídica entre el responsable y la persona titular).

**No se encontró** en la ley: lista de países adecuados, autorización previa, registro de
transferencias, ni cláusulas contractuales tipo obligatorias.

### 6.4 Cómputo en la nube — permitido, con lista de diligencia

El **Reglamento de la LFPDPPP (DOF 21-12-2011), art. 52** regula expresamente el *"Tratamiento
de datos personales en el denominado cómputo en la nube"* y **no contiene ningún requisito
territorial**. Impone una lista de diligencia sobre el proveedor (políticas afines a la Ley,
transparentar subcontrataciones, no asumir titularidad de la información, confidencialidad,
supresión al concluir el servicio, impedir accesos no autorizados o informar al responsable si
media requerimiento fundado de autoridad) y cierra: *"En cualquier caso, el responsable no
podrá adherirse a servicios que no garanticen la debida protección de los datos personales."*

> ⚠️ **Cabo suelto declarado.** Ese Reglamento es de la ley **abrogada** de 2010. La Cámara de
> Diputados lo sigue publicando como "TEXTO VIGENTE" y la nueva ley define "Reglamento" en su
> art. 2, fr. XIII, pero **no se pudo verificar si se expidió un Reglamento nuevo**, que el
> Transitorio Décimo Segundo ordenaba en 90 días naturales. **Es el punto legal más abierto de
> este documento** — ver §6.7, punto 1.

### 6.5 Si el cliente es del sector público (hospital, universidad o dependencia)

Aplica la **Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados**
(LGPDPPSO), también DOF **20 de marzo de 2025**, última reforma 14-11-2025. Su art. 3, fr.
XXVII cubre *"cualquier autoridad, entidad, órgano y organismo de los poderes ejecutivo,
legislativo y judicial, órganos autónomos… en el ámbito federal, estatal y municipal"* — es
decir, Protección Civil, hospitales públicos y universidades públicas.

**El artículo decisivo es el 62**, verificado literalmente en el PDF oficial:

> *"Artículo 62. El responsable sólo podrá transferir o hacer remisión de datos personales
> **fuera del territorio nacional** cuando el tercero receptor o la persona encargada **se
> obligue a proteger los datos personales** conforme a los principios y deberes que establece
> la presente Ley y las disposiciones que resulten aplicables en la materia."*

**Léase con cuidado: es una condición de garantía, no una prohibición territorial.** Permite
expresamente sacar datos del país si el receptor se obliga a protegerlos. Complementan el
art. 60 (toda transferencia se formaliza mediante cláusulas contractuales o instrumento
jurídico equivalente) y los **arts. 57 y 58**, que **autorizan expresamente el cómputo en la
nube** siempre que el proveedor garantice políticas equivalentes — **sin condición
territorial**.

**Diferencia práctica real frente al sector privado:** el sector público **sí exige
formalización contractual expresa** y **compromiso vinculante del receptor extranjero**. Es un
entregable concreto: TAKAB debería tener listo un **convenio/DPA** que satisfaga los arts. 60
y 62 **antes** de la primera venta a una institución pública.

### 6.6 Requisitos sectoriales: uno es mito, el otro es real pero no es prohibición

**Salud — NOM-024-SSA3: el requisito de residencia NO existe.** La
**NOM-024-SSA3-2012** (*Sistemas de información de registro electrónico para la salud*, DOF
**30-11-2012**, vigente) se descargó del DOF y se barrió su texto completo:

| Término | Coincidencias | Qué son |
|---|---:|---|
| `nube` | **0** | — |
| `ubicaci` | **0** | — |
| `servidor` | **0** | — |
| `fuera del país` | **0** | — |
| `territorio` | 3 | Todas de **ámbito de aplicación** |
| `residencia` | 3 | Todas del **domicilio del paciente** (claves INEGI) |

**No hay un solo requisito de alojamiento territorial.** Si un cliente hospitalario invoca la
NOM-024 para exigir datos en México, está invocando algo que la norma no dice. *(Nótese el
paralelismo con el caso NOM-003-SCT del blueprint §9: una norma citada de memoria que, leída,
no decía lo que se le atribuía.)*

**Contratación pública federal — aquí sí hay algo real, pero es *preferencia*, no obligación.**
El **ACUERDO de políticas TIC de la APF (DOF 06-09-2021)** dice, literalmente:

- **Art. 2, ap. A, fr. XLIV** — define Servicios en la Nube como los *"que se encuentren
  localizados **fuera o dentro** del territorio nacional"*. **La definición misma admite el
  extranjero.**
- **Art. 3, fr. V** — *"**Privilegiar** el alojamiento de la información en territorio
  nacional…"*
- **Art. 46** — *"…podrán contratarse servicios de Centros de Datos a terceros, **procurando**
  que la información se aloje en territorio nacional. En casos específicos, podrá requerirse la
  contratación de Servicios en la Nube Pública, en este supuesto, deberán aportarse datos que
  justifiquen la contratación, dentro del **Estudio de Factibilidad**."*
- **Art. 69** — *"…como **priorizar** su alojamiento en territorio nacional."*

**Los verbos son *privilegiar*, *procurar* y *priorizar* — no *deberá alojarse en*.** Y el
art. 46 prevé **expresamente** la ruta de nube pública con justificación en el Estudio de
Factibilidad. Además, el ACUERDO **obliga a la dependencia compradora, no a TAKAB** — aunque en
la práctica se traslada por contrato y puede aparecer en bases de licitación.

Dos verificaciones adicionales descartan un endurecimiento: el **Contrato Marco de Servicios de
Nube Pública 2024** no contiene cláusula de residencia, y la **Política General de
Ciberseguridad de la APF (DOF 17-12-2025)** no menciona "territorio nacional".

> **Este es, en la práctica, el riesgo comercial real** — no un riesgo de cumplimiento. En una
> licitación federal puede aparecer el art. 3 fr. V o el art. 69 como criterio. La vía prevista
> por la propia norma para justificar `us-east-2` es el **Estudio de Factibilidad del art. 46**.

### 6.7 Qué necesita confirmación de un abogado — **antes de responder por escrito**

1. **Vigencia del Reglamento de 2011 y de su art. 52**, y si existe Reglamento nuevo de la
   LFPDPPP 2025. **Es el punto más importante**: es la norma que gobierna directamente el uso
   de nube en el sector privado.
2. **La calificación de AWS como "persona encargada" y no como "tercero".** Todo el análisis de
   bajo riesgo del sector privado (§6.3) depende de ella. Matiz relevante: **la nueva LFPDPPP
   eliminó la palabra "remisión"**, que sí sobrevive en la LGPDPPSO (art. 3 fr. XXIV y art. 65);
   el régimen del encargado en el sector privado quedó definido **por exclusión**, no por
   artículo propio.
3. **Redacción de la cláusula de transferencia del aviso de privacidad** (art. 35, 2.º párrafo),
   y si conviene apoyarse en el art. 36 fr. VII o fr. II para clientes hospitalarios. *Enlaza
   con T-2.79 (aviso de privacidad versionado).*
4. **Instrumento contractual para el sector público** que satisfaga los arts. 60 y 62 de la
   LGPDPPSO. **Entregable concreto y anterior a la primera venta pública.**
5. **Cómo responder en licitaciones** que invoquen el ACUERDO de 2021, y si el Estudio de
   Factibilidad del art. 46 es la vía adecuada para justificar `us-east-2`.
6. **Leyes estatales de datos personales** — cada entidad federativa tiene la suya para sujetos
   obligados locales. **No se revisaron.** Un hospital o universidad **estatal** puede estar
   sujeto a reglas locales adicionales.
7. **Alcance de la reforma DOF 14-11-2025** (se confirmó que existe y que tocó el art. 4; no se
   auditó el decreto completo) y **criterios emitidos por la Secretaría** desde marzo de 2025.

### 6.8 Cómo se verificaron estas citas

Las afirmaciones decisivas **no se tomaron de una búsqueda web**: se descargó el texto oficial
y se barrió programáticamente (`/tmp/takab_legal_verify.py`):

```bash
curl -sL -o LFPDPPP.pdf  https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf
curl -sL -o LGPDPPSO.pdf https://www.diputados.gob.mx/LeyesBiblio/pdf/LGPDPPSO.pdf
pdftotext LFPDPPP.pdf - | grep -ic territorio    # -> 2, ambas de ambito de aplicacion
pdftotext LFPDPPP.pdf - | grep -ic nube          # -> 0
pdftotext LGPDPPSO.pdf - | grep -A2 'Artículo 62'
```

**Fuentes primarias:**

- LFPDPPP vigente — https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf
- LGPDPPSO vigente — https://www.diputados.gob.mx/LeyesBiblio/pdf/LGPDPPSO.pdf
- Reglamento de la LFPDPPP (2011) — https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LFPDPPP.pdf
- DECRETO DOF 20-03-2025 (expide las tres leyes) — https://www.dof.gob.mx/nota_detalle.php?codigo=5752569&fecha=20/03/2025
- Reforma constitucional de simplificación orgánica, DOF 20-12-2024 — https://www.dof.gob.mx/nota_detalle.php?codigo=5745905&fecha=20/12/2024
- NOM-024-SSA3-2012, DOF 30-11-2012 — https://dof.gob.mx/nota_detalle.php?codigo=5280847&fecha=30/11/2012
- Vigencia de la NOM-024 (Secretaría de Economía) — https://platiica.economia.gob.mx/normalizacion/nom-024-ssa3-2012/
- ACUERDO de políticas TIC de la APF, DOF 06-09-2021 — https://dof.gob.mx/nota_detalle.php?codigo=5628885&fecha=06/09/2021
- Política General de Ciberseguridad de la APF, DOF 17-12-2025 — https://dof.gob.mx/nota_detalle.php?codigo=5776454&fecha=17/12/2025

---

## 7. Qué haría falta para cambiar la recomendación

Un documento de decisión que no dice bajo qué condiciones se revisa se convierte en dogma.
Estas son las condiciones, en orden de peso:

| # | Disparador | Qué habría que hacer | ¿Cambia la recomendación? |
|---|---|---|---|
| **1** | **AWS anuncia IoT Core en `mx-central-1`** | Rehacer §3 y §4; estimar el esfuerzo de migración con coste real de flota | **Sí — es el disparador principal.** Con IoT Core en México, la latencia medida (−48 ms) y el +5 % de coste hacen la migración **defendible y probablemente deseable** |
| **2** | Un cliente exige residencia en México **por contrato o política interna** | Evaluar la opción (a) de §3.3 (ingesta en EE. UU., datos en reposo en México) y decir con claridad qué residencia se consigue y cuál no | Puede justificar una **migración parcial** para ese tenant. **No** cambia la recomendación general |
| **3** | Cambia la ley y aparece una obligación real de localización | Revisar §6 con abogado y replanificar | Sí, y con urgencia |
| **4** | AWS lleva **SES** y **SNS mobile push** a `mx-central-1` | Elimina dos dependencias residuales en EE. UU. | No por sí solo; es **condición necesaria** para que la migración de (1) sea *completa* |
| **5** | El coste de flota real hace que el +5 % pese | Recalcular con la factura real, no con la de desarrollo | Empujaría **en contra** de migrar, no a favor |

**Revisión programada:** re-ejecutar el script de §8.3 (es barato y no necesita credenciales)
**cada seis meses**, o inmediatamente si un cliente pregunta. Si el `region_index.json` de
`AWSIoT` empieza a incluir `mx-central-1`, este documento queda obsoleto y hay que rehacerlo.

---

## 8. Qué NO se pudo medir, y por qué

Declarado explícitamente. Un hueco declarado vale más que un número inventado.

### 8.1 Huecos de medición

1. **Latencia intra-AWS en `mx-central-1`** (API↔base de datos, SQS↔consumidor). Requiere
   desplegar recursos reales en la región. **No se hizo**: exige `terraform apply`, credenciales
   y gasto. Es la medición que faltaría antes de una migración real.
2. **Rendimiento y disponibilidad de `mx-central-1`.** No se midió throughput, ni IOPS reales,
   ni comportamiento bajo carga. Un RTT corto no dice nada de esto.
3. **Latencia desde el gabinete real** (`gw-dev-0001`, Pi 4 en sitio). Todo se midió desde la
   máquina de desarrollo. Medirlo desde el Pi daría el número operativamente correcto; no se
   hizo para no tocar un gabinete en servicio.
4. **Coste total de la flota comercial.** No existe todavía esa factura (§5.1). **No se
   proyecta.**
5. **Coste y duración de la migración en sí** (traslado de datos, re-emisión de certificados
   X.509 de los gabinetes, corte de servicio, re-registro de dispositivos). No se estimó
   porque el bloqueante de §3.3 lo hace ocioso.
6. **Precios en MXN e impuestos locales (IVA).** El price list de AWS solo publica USD.
7. **Variación por ISP, región del país y hora del día.** Un solo enlace, un solo día.

### 8.2 Citas que NO se pudieron verificar

Se listan porque callarlas sería el error que este proyecto ya cometió dos veces.

1. **`SNS mobile push` en `mx-central-1`: NO VERIFICADO por vía documental.** La evidencia es
   **fuerte pero indirecta** — el fichero de precios de SNS de México contiene 17 SKUs y
   ninguno de push móvil (no hay `APNS`, `GCM`, `ADM`, `WNS`, `MACOS`, `BAIDU`, `MPNS`),
   mientras `us-east-2` sí los tiene. No se encontró **ninguna página de AWS** que enumere las
   regiones soportadas para mobile push: el `WebFetch` a
   `docs.aws.amazon.com/sns/latest/dg/sns-push-notification-regions.html` no devolvió lista de
   regiones. **La ausencia en el price list es evidencia fuerte, no una declaración formal de
   AWS.** Antes de apoyar una decisión en esto, confirmar con soporte de AWS.
2. **La tabla oficial "AWS Services by Region" no se pudo leer directamente.**
   `aws.amazon.com/about-aws/global-infrastructure/regional-product-services/` renderiza la
   tabla por JavaScript y devuelve la página sin datos. Se usó el JSON que la alimenta
   (`api.regional-table.region-services.aws.a2z.com/index.json`), **que trae su propio
   descargo de AWS**: *"This file is intended for use only on aws.amazon.com. We do not
   guarantee its availability or accuracy."*
3. **Ese JSON contiene al menos un error comprobado.** Declara **SES disponible en
   `mx-central-1`**, y es **falso**: la doc canónica de endpoints de SES no lista `mx-central-1`,
   y las cuatro variantes de endpoint (`email.mx-central-1.amazonaws.com`,
   `email.mx-central-1.api.aws`, `email-smtp.mx-central-1.amazonaws.com`,
   `ses.mx-central-1.amazonaws.com`) dan **NXDOMAIN**, mientras `email.us-east-2.api.aws`
   resuelve. La confusión probable es con **AWS End User Messaging**, que sí está en México.
   **Por eso este documento trata ese JSON como orientativo y apoya toda afirmación decisoria
   en la doc de endpoints y en sondas propias.** Su `source:version` es además `20251113`.
4. **Páginas web de precios de AWS**: `aws.amazon.com/{ec2,s3,sns}/pricing/` no devolvieron
   tablas por región (JavaScript). **El 100 % de las cifras de §5 viene de la API de precios**,
   no de las páginas web.
5. **No hay ningún anuncio de AWS sobre IoT Core en México**, ni a favor ni en contra. La
   ausencia de anuncio **no es** una promesa de que llegue. No se supone nada.
6. **Huecos legales.** Los siete puntos de §6.7 están **sin confirmar por un abogado**, y el
   más abierto es la **vigencia del Reglamento de 2011** (§6.4). Además **no se revisó ninguna
   ley estatal** de protección de datos, ni regulación de infraestructura crítica que pudiera
   aplicar si TAKAB llegara a clasificarse como tal. **Nada de §6 debe presentarse a un cliente
   como dictamen jurídico.**
7. **No se consultó documentación contractual de AWS** (compromisos de residencia, DPA, adenda
   de transferencias). La sección legal se apoya **solo en la ley mexicana**. Si un cliente
   pide los compromisos contractuales de AWS, hay que obtenerlos de AWS, no inferirlos.

### 8.3 Cómo reproducir todo esto

Ningún paso necesita credenciales de AWS ni toca la base de datos.

```bash
# (1) ¿Existe el endpoint del servicio en la región?  NXDOMAIN = no existe.
#     Ojo: el `|| echo` NO funciona aquí (el estado de salida lo da awk, que sí
#     tiene éxito); hay que capturar en variable y usar la expansión por defecto.
for svc in iot cognito-idp email sqs sns s3 kms ecs; do
  for reg in mx-central-1 us-east-2; do
    ip=$(getent hosts "$svc.$reg.amazonaws.com" | head -1 | awk '{print $1}')
    printf '%s.%s -> %s\n' "$svc" "$reg" "${ip:-NXDOMAIN}"
  done
done

# (2) Plano de datos de IoT (la ruta real del gabinete)
getent hosts data-ats.iot.mx-central-1.amazonaws.com   # NXDOMAIN
getent hosts data-ats.iot.us-east-2.amazonaws.com      # resuelve

# (3) ¿Tiene AWS tarifa de IoT Core para México?
curl -s https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSIoT/current/region_index.json \
  | python3 -c 'import json,sys; r=json.load(sys.stdin)["regions"]; \
      print(len(r),"regiones; mx-central-1:", "mx-central-1" in r)'

# (4) Latencia: round-trip TCP puro, con el DNS RESTADO (columna "TCP" de §4.2).
#     DOS trampas, las dos verificadas en esta máquina:
#       a) time_connect de curl es ACUMULATIVO e incluye el DNS -> hay que restarlo,
#          o se publican ~60 ms para México en vez de ~12 ms (ver el aviso de §4.1).
#       b) LC_ALL=C es OBLIGATORIO: con configuración regional es_MX, awk toma la coma
#          como separador decimal, lee "0.0484" como 0 y la resta sale 0.0 ms.
export LC_ALL=C
for e in s3.mx-central-1 s3.us-east-2; do
  for i in $(seq 1 10); do
    curl -s -o /dev/null --no-keepalive \
      -w "%{time_namelookup} %{time_connect}\n" "https://$e.amazonaws.com/"
  done \
    | awk '{printf "%.1f\n", ($2-$1)*1000}' \
    | sort -n \
    | awk -v e="$e" '{v[NR]=$1}
        END{m = (NR%2) ? v[(NR+1)/2] : (v[NR/2]+v[NR/2+1])/2;
            printf "%-16s n=%d  TCP mediana = %.1f ms\n", e, NR, m}'
done
```

**Comprobado el 2026-08-08**, este bloque (4) devolvió con n=10:

```
s3.mx-central-1  n=10  TCP mediana = 11.4 ms
s3.us-east-2     n=10  TCP mediana = 59.5 ms
```

frente a los **11.9** y **59.5** ms publicados en §4.2 con n=40. **La reproducción cuadra**;
la diferencia de medio milisegundo en México es la varianza esperable de una muestra cuatro
veces menor.

```bash
# (5) Los 64 servicios que están en Ohio y no en México (las cifras de §3.2).
#     OJO: este JSON es orientativo y tiene errores comprobados — ver 8.2.3.
curl -s https://api.regional-table.region-services.aws.a2z.com/index.json \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
def svcs(r): return {p["attributes"]["aws:serviceName"]
                     for p in d["prices"] if p["attributes"].get("aws:region")==r}
mx, ue2 = svcs("mx-central-1"), svcs("us-east-2")
print(f"mx-central-1: {len(mx)} servicios | us-east-2: {len(ue2)}")
falta = sorted(ue2-mx)
print(f"ausentes en MX: {len(falta)}")
for s in falta:
    if "IoT" in s or "Email" in s: print("  *", s)
'
```

**Comprobado el 2026-08-08**, devolvió `mx-central-1: 121 servicios | us-east-2: 185`,
`ausentes en MX: 64`, y entre los ausentes los cinco de la familia IoT (`Core`,
`Device Defender`, `Device Management`, `Greengrass`, `SiteWise`) — **las mismas cifras que
publica §3.2**.

---

## 9. Fuentes

**Documentación oficial de AWS (primaria):**

- AWS IoT Core endpoints and quotas — https://docs.aws.amazon.com/general/latest/gr/iot-core.html
- Amazon Cognito endpoints and quotas — https://docs.aws.amazon.com/general/latest/gr/cognito_identity.html
- Amazon SES endpoints and quotas — https://docs.aws.amazon.com/general/latest/gr/ses.html
- Regiones soportadas por AWS Fargate (ECS) — https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate-Regions.html
- «Now open — AWS Mexico (Central) Region» (lanzamiento, 3 AZ, código `mx-central-1`) — https://aws.amazon.com/blogs/aws/now-open-aws-mexico-central-region/
- Expansión de AWS IoT a España y Malasia (jul-2025) — https://aws.amazon.com/about-aws/whats-new/2025/07/aws-iot-region-expansion/
- Expansión de AWS IoT a Tel Aviv y Milán (abr-2026) — https://aws.amazon.com/about-aws/whats-new/2026/04/aws-iot-israel-tel-aviv-europe-milan/
- AWS Price List Bulk API — https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json
- Tabla de servicios por región (fuente JSON, **con reservas** — ver 8.2.3) — https://api.regional-table.region-services.aws.a2z.com/index.json

**Mediciones propias (2026-08-08):** `/tmp/takab_lat.sh` + `/tmp/takab_lat_raw.csv` (240
muestras), `/tmp/takab_sock_lat.py` (120 muestras), `/tmp/takab_verify_price.py`.
Reproducibles con §8.3.

**Fuentes internas:** `infra/terraform/` (inventario de servicios),
`infra/terraform/envs/dev/providers.tf` (región actual `us-east-2`),
`infra/terraform/envs/dev/budget.tf` (budget de 50 USD),
`takab-docs/BLUEPRINT-TECNICO-TAKAB.md` §4.5 y §9, `CLAUDE.md` §2 (reglas de oro 1, 2 y 11).
