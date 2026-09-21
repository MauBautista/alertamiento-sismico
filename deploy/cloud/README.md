# Runbook · Desplegar la nube TAKAB (T-1.37)

Hasta esta tarea, la "nube" de TAKAB era: DB (EC2 + TimescaleDB), IoT Core, SQS, S3,
Cognito, ECR y KMS. **Cero cómputo.** La API, el consumer de SQS, el motor de incidentes
y la consola corrían en la laptop de Mauricio. Esto los mueve al EC2 que ya existe.

## Por qué así

| Decisión | Motivo |
|---|---|
| Co-locar en el EC2, no ECS Fargate | El entorno dev cabe entero en la máquina que ya sostiene TimescaleDB. Un ALB costaría ~$18/mes por hacer lo que Caddy hace gratis. |
| `t4g.small` → `t4g.medium` | TimescaleDB-HA + API + 2 ingest + motor + notify + comandos + Caddy ≈ **1.6 GiB en reposo**. En 2 GiB, un pico de ingesta hace que el OOM-killer mate al proceso de mayor RSS: **Postgres**. **+$12.26/mes** ⇒ total ~$42–47/mes (budget: $50). |
| Caddy + Let's Encrypt sobre **sslip.io** | TLS real sin Route53 ni dominio propio. `3-14-15-92.sslip.io` resuelve a `3.14.15.92`. |
| **Security group web separado** | Se adjunta a la ENI, no a la instancia. Se puede desconectar (o `serve_enabled=false`) para cerrar el acceso público al instante, sin tocar la DB ni recrear la máquina. |
| Secretos en **tmpfs** | `takab-secrets.service` los materializa de Secrets Manager a `/run/takab/*.env` en cada arranque. Nunca tocan el disco ni git (regla de oro 6). |

### Invariante que no se negocia

La **API** usa el DSN de `takab_app` (RLS **forzada**). Los **workers** usan el de
`takab_ingest` (**BYPASSRLS**, porque escriben filas de todos los tenants: la ingesta no
tiene sesión de usuario). Mezclarlos sería un cruce de tenants silencioso — la API
serviría datos ajenos sin que ninguna política lo detuviera (**regla de oro 5**). Por eso
son dos `env_file` distintos en `docker-compose.yml` y no uno con override.

### Desviaciones honestas

- **T-1.26 ratificó "mismo origen tras CloudFront".** Caddy en el EC2 conserva el
  *invariante* (mismo origen ⇒ sin CORS, y `wss://host/api/ws` sale por la misma regla).
  Cambia el *mecanismo*. CloudFront sigue siendo el destino cuando haya dominio propio.
- **`/dev/token` está apagado en la nube.** `cloud.env` omite
  `TAKAB_API_AUTH_JWKS_JSON`, y `main.create_app` condiciona el router a ese valor: el
  endpoint ni se monta. La nube solo acepta Cognito.
- **La clave HMAC de comandos se resuelve POR GABINETE** (T-1.38): la API y el config
  sync firman con la clave del gateway **destino**, leída en runtime de Secrets Manager
  (`takab/dev/gateway-hmac/<thing>`, campo `hmac_key`, cache 300 s) con el rol de la
  instancia. El secreto HMAC vive **separado** del secreto del certificado: IAM no
  filtra campos JSON y el rol de la nube jamás debe poder leer claves privadas mTLS.
  Sin clave resoluble para un gateway: **fail-closed** (503 en la API; el sync lo salta
  sin quemar versión). Ya no existe `command-hmac.env` ni clave compartida alguna.
- El puerto **80 va abierto al mundo** porque el desafío HTTP-01 de ACME lo exige y sale
  de IPs que no se pueden enumerar. Caddy solo responde el reto ahí y redirige a 443.
- Las URLs de las DLQ **sí se inyectan** (`TAKAB_API_DLQ_URL_*`): los consumidores las
  exigen al arrancar — los REJECT explícitos se envían por URL; el redrive de SQS va por
  ARN y no depende de esto (GAP-1 · T-1.38).
- El deploy **siembra SOLO la flota real en la DB de la nube** (`db/seeds/prod_fleet.sql`,
  idempotente) justo después de las migraciones: sin filas en `gateways`/`sensors` la
  ingesta rechazaría todo mensaje del gabinete real por "unknown principal" → DLQ
  (GAP-3 · T-1.38). La flota sim (`db/seeds/sim_fleet.sql`) es EXCLUSIVA de entornos
  locales: aplicarla aquí desharía la purga de datos sim de T-1.47.

---

## Precondiciones

0. **Deploy SOLO desde `main` pusheado con CI verde** (regla A-1 de la auditoría de
   cierre). Verificar antes de tocar nada: `git status` limpio sobre `main`,
   `git log origin/main..main` vacío y los checks del último commit en verde
   (`gh run list --branch main -L 1`). Lo que se despliega debe ser EXACTAMENTE lo
   que el repositorio y el CI vieron — nunca un árbol local con cambios sin subir.
1. Perfil SSO activo: `aws sso login --profile takab-dev`.
2. Conocer tu IP pública: `curl -s ifconfig.me`.
3. Docker con emulación arm64 (el EC2 es Graviton; `make cloud-images` ya construye
   `--platform linux/arm64` SIEMPRE). Una sola vez en un host x86:
   `docker run --privileged --rm tonistiigi/binfmt --install arm64`.
   La etapa node de la consola corre nativa (`$BUILDPLATFORM`): `dist/` no tiene
   arquitectura, solo las capas de Caddy son arm64.
4. **[T-7.26] El secreto de OpenRouter y su permiso, antes de desplegar.** Desde
   T-7.26 el despliegue exporta `TAKAB_API_OPENROUTER_ENABLED=true`, así que la capa
   narrativa del dictamen sale a la red de pago. La clave **no viaja en `cloud.env`**
   — está en `PROHIBIDOS_EN_PRODUCCION` —: el proceso la resuelve en runtime con el
   rol de la instancia, igual que la clave HMAC de comandos.

   **4.1 y 4.2 son independientes entre sí**, y conviene decirlo porque este mismo
   párrafo afirmó lo contrario hasta el 2026-09-21. Medido: el permiso es un ARN
   construido por interpolación de un `local`, no hay ningún
   `data "aws_secretsmanager_secret"` en el terraform, así que el `apply` sale igual
   de limpio antes que después de crear el secreto. **El orden que sí importa es que
   las dos van antes de `make cloud-deploy`** — y ese ya no depende de la memoria de
   nadie: sin el `apply`, `deploy.sh` aborta al resolver `openrouter_secret_id`
   (`tf_obligatorio`, en vez de escribir el identificador vacío y salir 0 como hacía
   hasta esta ficha); sin el secreto, `make cloud-conformidad` lo dice en ROJO en la
   pieza «secreto de la capa narrativa».

   ```bash
   # 4.1 · crear el secreto (una vez; el valor jamás entra en git ni en el estado
   #       de terraform, por eso lo crea una persona y no el IaC)
   aws secretsmanager create-secret --profile takab-dev --region us-east-2 \
     --name takab/dev/openrouter \
     --description 'Clave de OpenRouter para la capa narrativa del dictamen (T-7.26)' \
     --secret-string '{"api_key":"sk-or-v1-..."}'

   # 4.2 · conceder la LECTURA a la instancia. Sin este apply el despliegue
   #       "enciende" la IA y la nube sigue escribiendo prosa determinista:
   #       GetSecretValue responde AccessDenied y resolve_api_key degrada.
   make cloud-apply   # NO `terraform apply` a pelo: el target trae las dos guardas
                      # de T-2.171 (rama y local.auto.tfvars)

   # 4.3 · comprobarlo con la misma herramienta que lo vigila a diario: la pieza
   #       «secreto de la capa narrativa» mide que el secreto EXISTA y que el rol
   #       de la instancia lo alcance (deriva el rol de la instancia; no teclea
   #       ningún nombre). VERDE es la respuesta buena.
   make cloud-conformidad
   ```

   La pieza tiene **tres** respuestas y no dos: VERDE (lo midió y está), ROJO (lo midió
   y NO está, con la orden que lo arregla) y **NO MEDIDO** (no pudo preguntarlo —SSO
   caducado, un perfil sin permiso para leer IAM, la región equivocada— y entonces lo
   dice en vez de acusar). Un NO MEDIDO tampoco es un aprobado: cuenta como fallo del
   censo salvo `--permitir-no-medido`, que lo saca del código de salida pero no lo
   pinta de verde. Hasta el 2026-09-21 ese tercer caso salía como ROJO y con la receta
   del segundo (`make cloud-apply`, que no arregla unas credenciales caducadas): un
   censo que acusa de lo que no comprobó enseña al operador a ignorar el rojo.

   El nombre `takab/dev/openrouter` del paso 4.1 tiene que ser el de
   `local.openrouter_secret_id` (`infra/terraform/envs/dev/main.tf`): es el que
   construye el ARN del permiso y el que `deploy.sh` exporta. Y el campo del JSON es
   `api_key` y no otro: es el que lee `resolve_api_key`
   (`api/src/takab_api/narrative/openrouter.py`). Un secreto con otro nombre, o con
   otro nombre de campo, resuelve a cadena vacía y degrada. Las dos coincidencias las
   vigila `infra/scripts/tests/test_censo_banderas.sh`, que las compara contra sus
   fuentes en vez de fiarse de que este párrafo siga siendo verdad.

## Secuencia

### 1. Subir la instancia y publicar la consola

> ⚠️ **Esto para la instancia.** La DB cae unos minutos y el gabinete `gw-dev-0001`
> acumula spool (lo drenará al reconectar — acreditado en el hito de Fase 1). Hazlo en
> una ventana en la que puedas mirar.

```bash
cd infra/terraform/envs/dev
terraform apply \
  -var 'serve_enabled=true' \
  -var 'web_allowed_cidrs=["TU.IP.PU.BL/32"]'
```

`instance_type` ya tiene `t4g.medium` como default committeado.

> ⚠️ **Los dos `-var` NO son opcionales.** `terraform apply` a secas usa el default
> `serve_enabled=false` y **destruye la IP elástica y el SG web**: la consola desaparece
> de internet (y vuelve con OTRA IP, que además hay que re-autorizar en Cognito). Si el
> plan dice `aws_eip.web[0] will be destroyed`, te faltan las variables.

Terraform añadirá el `https://<ip>.sslip.io/auth/callback` a los callbacks de Cognito;
el de `localhost:5173` **se conserva**, así que `make dev` local sigue funcionando.

**Correo (T-1.62).** El envío por SES necesita DOS cosas independientes, y tener una sin
la otra falla en silencio:
1. **Permiso IAM** — lo da este `apply` (Sid `WorkerSesSend`). Sin él: `AccessDenied` y el
   job de notificación muere. Los avisos de CloudWatch **seguirían llegando** (los manda
   SNS, con permiso propio): no sirven para dar por bueno el correo de la app.
2. **Identidad verificada** — el `apply` la CREA pero no la verifica. Hay que clicar el
   correo de AWS (`aws ses verify-email-identity --email-address <correo>` lo reenvía; el
   link caduca en 24 h) y confirmar con `aws sesv2 get-email-identity`. La cuenta está en
   **sandbox**: remitente **y** destinatario deben ser identidades verificadas.

### 2. Construir y subir las imágenes

```bash
make cloud-images
```

Construye `takab/cloud` (API + workers, una imagen y muchos commands) y `takab/console`
(Vite build + Caddy). Etiquetadas con el SHA corto de HEAD.

### 3. Desplegar

```bash
make cloud-deploy
```

Por SSM (no hay SSH): copia el compose y las unidades systemd, materializa los secretos a
tmpfs, **corre las migraciones como `takab_migrator`**, **siembra la flota dev**
(idempotente, superusuario por socket local del contenedor de la DB) y levanta la
topología. Idempotente de punta a punta.

### 4. Verificar

```bash
curl -sf https://<host>/api/health          # {"status":"ok"}
curl -sI  https://<host>/ | head -1         # 200, con certificado válido
```

Y en el navegador: entrar por Cognito, ver el mapa con los sitios, abrir `/fleet` y crear
una estación.

### 5. Medir la latencia de la capa narrativa (T-7.26)

`openrouter_timeout_s` vale **8.0 s** y ese número no se inventa: se mide contra el
proveedor real, con el modelo que el despliegue tiene puesto y desde la instancia, que
es la que paga la red. Hay una medición tras cada cambio de modelo.

```bash
make cloud-medir-latencia-ia                                   # 5 rondas × 2 brazos
make cloud-medir-latencia-ia MEDICION_FLAGS="--rondas 10 --crudo"
```

**Sólo lee**: no escribe en la base, no sube nada a S3, no genera PDF, no toca la
configuración de la instancia ni reinicia nada. **Sí gasta**: son llamadas reales al
modelo y se cobran (con los valores por defecto, 10 generaciones y 10 lecturas de
catálogo). No imprime la clave —se resuelve con el rol de la instancia y no sale del
proceso— ni la prosa que devuelve el modelo.

Tres cosas que el script hace a propósito y conviene no deshacer:

1. **Mide con un tope ALTO propio** (`--tope-medicion`, 90 s), que vive sólo dentro del
   proceso de medición. No se puede medir a través del guardia que se está validando:
   con el tope de producción puesto, toda llamada más lenta que 8 s deja de ser una
   latencia y pasa a ser una degradación con `latency_ms = None`, o sea que se borra
   exactamente la cola que se quiere ver. La conclusión sería «nunca pasa de 8 s»:
   cierta por construcción y falsa en el mundo.
2. **Cuenta el catálogo aparte.** `build_narrative` pregunta SIEMPRE si el modelo admite
   imágenes (`D-32`), también en un incidente sin fotos, y eso es un `GET /models` que
   se recuerda por proceso: la primera exportación después de cada despliegue lo paga
   entero, **bajo el mismo tope**. Son dos viajes, no uno.
3. **Una llamada que no volvió no entra en la muestra.** De un plantón se sabe que tardó
   más que el tope de medición, no cuánto; promediarlo convertiría nuestro propio techo
   en «la latencia medida». Si hay alguno, el script se niega a proponer un tope y dice
   qué hacer antes de volver a preguntar.

## Cerrar el acceso público

```bash
terraform apply -var 'serve_enabled=false'
```

Quita la IP elástica y el SG web. La DB, IoT Core y el gabinete siguen intactos: el
gabinete nunca habló con la consola, habla con IoT Core por MQTT/mTLS.

## Diagnóstico

```bash
# sesión en la instancia
aws ssm start-session --profile takab-dev --target "$(terraform -chdir=infra/terraform/envs/dev output -raw db_instance_id)"

sudo docker compose -f /opt/takab/cloud/docker-compose.yml --env-file /etc/takab/deploy.env ps
sudo docker compose -f /opt/takab/cloud/docker-compose.yml --env-file /etc/takab/deploy.env logs -f api
sudo systemctl status takab-secrets takab-cloud
free -m   # headroom de RAM; el motivo de subir a t4g.medium
```

Si Caddy no consigue certificado: revisa que el 80 esté abierto al mundo en el SG web y
que `<ip>.sslip.io` resuelva a la IP elástica (`dig +short <ip>.sslip.io`).

## Usuarios de consola (perfiles por rol)

```bash
AWS_PROFILE=takab-dev make cloud-users          # los 6 roles web
AWS_PROFILE=takab-dev make cloud-users ROLES="inspector soc_operator"
```

Crea/actualiza un usuario Cognito por rol (`<tu-correo>+<rol>@…`, plus-addressing: todos
caen en tu bandeja), lo mete en **su grupo** —sin el grupo `claims.py` rechaza el token con
`role not in groups` (401) aunque el `custom:role` esté bien— y guarda las contraseñas en
Secrets Manager (`takab/dev/console/users`), imprimiéndolas una vez.

**Cero filas en la base:** el rol de consola vive en el TOKEN, no hay tabla `users`. El pool
exige **MFA TOTP**, así que cada perfil enrola su authenticator en el primer login.

> El panel "LOGIN DEV" **no existe en la nube** y no debe existir: `/dev/token` forja claims
> arbitrarios. La API solo lo monta con `TAKAB_API_AUTH_JWKS_JSON` (dev). Si algún día vuelve
> a aparecer en producción, es que el build volvió a colar un `web/.env` (ver `.dockerignore`).
