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
- El deploy **siembra la flota dev en la DB de la nube** (`db/seeds/dev_fleet.sql`,
  idempotente) justo después de las migraciones: sin filas en `gateways`/`sensors` la
  ingesta rechazaría todo mensaje del gabinete real por "unknown principal" → DLQ
  (GAP-3 · T-1.38).

---

## Precondiciones

1. Perfil SSO activo: `aws sso login --profile takab-dev`.
2. Conocer tu IP pública: `curl -s ifconfig.me`.
3. Docker con emulación arm64 (el EC2 es Graviton; `make cloud-images` ya construye
   `--platform linux/arm64` SIEMPRE). Una sola vez en un host x86:
   `docker run --privileged --rm tonistiigi/binfmt --install arm64`.
   La etapa node de la consola corre nativa (`$BUILDPLATFORM`): `dist/` no tiene
   arquitectura, solo las capas de Caddy son arm64.

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

Terraform añadirá el `https://<ip>.sslip.io/auth/callback` a los callbacks de Cognito;
el de `localhost:5173` **se conserva**, así que `make dev` local sigue funcionando.

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
