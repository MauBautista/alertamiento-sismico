# RUNBOOK · Redespliegue de la nube a Fase 2 (2026-07-26)

> **Punto de partida: la nube corre código del 2026-07-14 (tag `9d16056`, alembic `0016`).**
> Desde ahí hay 82 commits y **4 migraciones sin aplicar** (`0017_visibility_grants`,
> `0018_mobile_core`, `0019_push_endpoints`, `0020_checkin_notify`): toda la Fase 1.10 y toda la
> API móvil de Fase 2 están en `main` pero **no están vivas**. El síntoma con el que se descubrió
> fue un 401 en el login del móvil.
>
> Este runbook es la secuencia para ponerla al día. No inventa pasos: consolida los guard-rails
> que ya estaban dispersos en `deploy/cloud/README.md`, el Makefile y la memoria de despliegues
> anteriores.

---

## 0. Cómo leer esto

- Cada paso dice **quién** lo corre. Los pasos AWS los corre Mauricio (el clasificador los niega
  en sesión asistida): en Claude Code, prefijo `!`.
- **[PARA]** = si ves eso, detente y diagnostica. No sigas "a ver si jala".
- El orden importa: las migraciones corren **antes** de cambiar la API, y el acceso de red se
  arregla **antes** de cualquier `terraform apply`.

---

## 1. Precondiciones (verificables sin AWS)

```bash
git status --short                  # limpio (cotizacion/ está gitignored desde 2026-07-26)
git log origin/main..main           # vacío: no hay commits locales sin subir
gh run list --branch main -L 1      # DEBE estar verde
make lint && make test && make drift
```

**[PARA] si CI está rojo.** Es la regla A-1 de la auditoría: no se despliega desde un árbol que
no pasa sus propios gates. (Main estuvo rojo del 2026-07-18 al 2026-07-26 por el timeout de
`mobile/src/features/panel/panel.test.tsx`; se arregló subiendo `testTimeout` a 20 s.)

---

## 2. Acceso: sesión AWS e IP dinámica

```bash
aws sso login --profile takab-dev                       # el token expira solo
AWS_PROFILE=takab-dev make cloud-allow-my-ip MODE=--status   # ¿mi IP está permitida?
AWS_PROFILE=takab-dev make cloud-allow-my-ip                 # ábrela + limpia reglas manuales
```

La IP doméstica es **dinámica**: cuando rota, la consola deja de responder con **timeout** (no
403 — el paquete muere en el SG `takab-dev-web`, que acota el 443 a /32). Cada arreglo manual
por CLI deja una regla **fuera de Terraform** que hará fallar el siguiente `apply` por duplicada.
`allow_my_ip.sh` revoca esas reglas y reabre el acceso con la IP actual; distingue las reglas de
Terraform por su descripción canónica (`Consola SOC (HTTPS) desde <cidr>`).

---

## 3. Terraform — solo si hay que tocar infraestructura

Para un redeploy de **código** no hace falta. Es necesario si cambias SES/push/SG/instancia.

```bash
AWS_PROFILE=takab-dev make cloud-allow-my-ip MODE=--revoke   # limpia manuales ANTES del apply
cd infra/terraform/envs/dev
terraform plan
```

- **[PARA] si el plan dice `aws_eip.web[0] will be destroyed`.** Faltan las variables:
  `serve_enabled=true` y `web_allowed_cidrs`. Un apply así deja la consola **fuera de internet** y
  al volver lo hace con **otra IP**, que además hay que re-autorizar en las callback URLs de
  Cognito. En esta máquina `local.auto.tfvars` (gitignored) ya las fija; desde CI u otra máquina,
  no.
- **[PARA] si el plan cambia `instance_type`.** Eso **para la instancia**: la DB cae varios
  minutos y los gabinetes acumulan spool. Es una decisión, no un efecto colateral.
- Tras el apply, verifica que tu IP siga en `web_allowed_cidrs` o perderás la consola.

---

## 4. Imágenes (arm64 obligatorio)

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64   # se pierde al reiniciar el host
AWS_PROFILE=takab-dev make cloud-images
```

El EC2 es **Graviton**: una imagen x86 se sube sin quejarse y truena al arrancar el contenedor.
`CLOUD_TAG` es `git rev-parse --short HEAD`, así que el tag de la imagen **es** el commit.

---

## 5. Deploy

```bash
AWS_PROFILE=takab-dev make cloud-deploy
```

Qué hace (`deploy/cloud/deploy.sh`, todo por `aws ssm send-command`; no hay SSH):

1. Aborta si `console_public_host` está vacío (aplica con `-var serve_enabled=true`).
2. Sobrescribe `/etc/takab/cloud.env` y `/etc/takab/deploy.env` — config **no** secreta; los
   secretos los materializa `takab-secrets.service` en tmpfs.
3. Abre una ventana de privilegios (`GRANT takab_ingest TO takab_migrator; GRANT CREATE ON SCHEMA
   public`), corre **`alembic upgrade head`** en un contenedor efímero y **revoca siempre**,
   incluso si la migración falla.
4. **Si la migración falla, aborta sin tocar la API.** Correcto: mejor vieja y viva que a medias.
5. Seeds idempotentes (`prod_fleet.sql`, `reference_earthquakes.sql`). **Nunca `sim_fleet.sql`**:
   desharía la purga de T-1.47.
6. `systemctl restart takab-cloud.service` → corte de segundos en los 7 contenedores.

> **Trampa histórica de migraciones:** en local migras como superusuario, en la nube como
> `takab_migrator`. Una migración verde en local puede ser **imposible** en la nube. Las 0017-0020
> ya se escribieron con ese patrón (`_UP_PREEXISTING_AS_CONNECTION_USER`), pero si una falla, el
> mensaje de permisos es la primera pista.

---

## 6. Verificación

```bash
curl -s https://<console_public_host>/api/health     # {"status":"ok","build":"<SHA>"}
```

**El `build` debe ser el SHA que acabas de desplegar.** Antes de 2026-07-26 `/health` respondía
`{"status":"ok"}` a secas y no había forma de saber qué corría sin entrar por SSM — por eso el
retraso de 82 commits pasó inadvertido.

```bash
make db-tunnel                                       # y en otra terminal:
psql "postgresql://…@localhost:5434/takab" -c "SELECT version_num FROM alembic_version;"   # 0020
```

Además: la consola carga; los gabinetes drenan su spool (`queued` bajando); el openapi vivo ya
expone `push-tokens`, `enrollment`, `checkins`, `mobile-state` y `manual-activation-votes`.

---

## 7. Semillas para el E2E móvil (GATE-HW)

```bash
AWS_PROFILE=takab-dev make cloud-mobile-users                     # occupant + brigadista + código
AWS_PROFILE=takab-dev make cloud-staging-incident PHASE=crisis    # incidente controlado
AWS_PROFILE=takab-dev make cloud-staging-incident PHASE=status    # confirma la fase derivada
```

Detalle de fases, precondiciones de los 5 flujos Maestro y el contrato de derivación de `phase`:
`RUNBOOK-cierre-fase2.md §3/§4` y `mobile/.maestro/README.md`.

---

## 8. Si algo sale mal

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La consola da **timeout** | tu IP rotó | `make cloud-allow-my-ip` (§2) |
| `apply` falla por regla duplicada | regla manual de SG | `make cloud-allow-my-ip MODE=--revoke` |
| Deploy aborta en la migración | DDL imposible como `takab_migrator` | la API sigue en la versión vieja; arregla la migración, no la base |
| Contenedor no arranca | imagen x86 en Graviton | rehaz `make cloud-images` con binfmt arm64 |
| `/api/health` sin `build` | imagen anterior a 2026-07-26 | el deploy no tomó; revisa el tag en `/etc/takab/deploy.env` |
| El gabinete no publica tras el deploy | enlace MQTT del edge | mira `journalctl -u takab-edge` en el Pi; el spool es idempotente, no se pierde nada |
