.PHONY: dev down lint test test-db fmt drift build verify api web edge mobile db install db-tunnel \
        cloud-stop cloud-start \
        billing cloud-users cloud-mobile-users cloud-staging-incident demo-fase1 demo-db \
        objetos \
        cloud-images cloud-deploy cloud-apply cloud-allow-my-ip restore-drill \
        landing-preview landing-e2e landing-audit landing-deploy

API_DIR := api
WEB_DIR := web
EDGE_DIR := edge
ANALYZER_DIR := analyzer
MOBILE_DIR := mobile
LANDING_DIR := landing
SDK_DIR := shared/sdk-ts
TOKENS_DIR := shared/design-tokens
# Los tests de este módulo son plan-only (credenciales falsas, sin red): corren en
# `make test` como cualquier otra suite, no necesitan sesión de AWS.
TF_OBSERVABILITY := infra/terraform/modules/observability
# [T-2.71] Alcance IAM del silenciador de alarmas: la única mitad de las
# ventanas de mantenimiento que terraform puede blindar (las mute rules en sí
# las crea el API y no están en el estado).
TF_DATABASE := infra/terraform/modules/database
# [T-2.72] La retención de los respaldos. Este módulo existía desde julio SIN un
# solo test, y por ahí vivió nueve meses una regla de lifecycle que parecía una
# política de retención y era un cambio de etiqueta: `Expiration` sobre un bucket
# VERSIONADO no borra un byte, pone un delete marker. Para el PITR es peor que un
# coste — el delete marker esconde el objeto al restaurador aunque los bytes
# sigan ahí. La corrección se podía borrar entera sin que nada se pusiera rojo.
TF_STORAGE := infra/terraform/modules/storage
TF_IDENTITY := infra/terraform/modules/identity

install:
	cd $(API_DIR) && python -m pip install -e ".[dev]"
	cd $(WEB_DIR) && npm install
	cd $(EDGE_DIR) && uv sync
	cd $(MOBILE_DIR) && npm install
	cd $(LANDING_DIR) && npm install

db:
	docker compose up -d db

# [T-5.29] Almacén de objetos local. La escena C4 de la demo genera el reporte
# del simulacro —evidencia con sha256— y `put_object` necesita un bucket; el
# servicio `minio-init` lo crea y termina.
objetos:
	docker compose up -d minio minio-init

api:
	cd $(API_DIR) && uvicorn takab_api.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(WEB_DIR) && npm run dev

edge:
	cd $(EDGE_DIR) && uv run takab-edge

# ufw bloquea el 8081 ⇒ el QR de `expo start` no conecta; para device real usa
# REACT_NATIVE_PACKAGER_HOSTNAME=localhost npx expo run:android (túnel adb).
mobile:
	cd $(MOBILE_DIR) && npx expo start

dev: db
	$(MAKE) -j2 api web

# Metering diario (T-1.24): default = ayer UTC; DAY=YYYY-MM-DD para re-computar.
# Scheduling dev = cron con este target; AWS = EventBridge->ECS run-task (prod).
billing:
	cd $(API_DIR) && uv run python -m takab_api.billing $(if $(DAY),--day $(DAY),)

# --- Hito de salida Fase 1: demo en vivo con 3 gabinetes ---------------------
# `demo-db` deja la DB local lista (migrada + flota sembrada). OJO: alembic lee la
# env BARE `DATABASE_URL`, mientras la API y los workers leen `TAKAB_API_DATABASE_URL`.
DEMO_DSN := postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab

# Seeds partidos (T-1.47): prod = flota real + rule_set v1 (lo ÚNICO que ve la
# nube); sim = 20 sitios/4 gateways de la demo, EXCLUSIVO de entornos locales.
# La suite de api EXIGE una base SIN el seed de desarrollo: contra `takab` (la que siembra
# `demo-db`) el tenant de la demo choca con el de los fixtures y salen fallos FALSOS —
# 12 failed + 90 errors que no tienen nada que ver con el código. CI nunca lo sufre porque
# su Postgres es un contenedor recién creado en cada corrida; en local hay que reproducir
# esa condición a mano, y por eso `make test` depende de `test-db`.
TEST_DSN := postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test

test-db: db
	@until docker compose exec -T db pg_isready -U takab -q; do sleep 1; done
	@docker compose exec -T db psql -U takab -d postgres -tAc \
	  "select 1 from pg_database where datname='takab_test'" | grep -q 1 \
	  || docker compose exec -T db createdb -U takab takab_test

demo-db: db objetos
	@until docker compose exec -T db pg_isready -U takab -q; do sleep 1; done
	cd $(API_DIR) && DATABASE_URL="$(DEMO_DSN)" uv run python -m alembic upgrade head
	PGPASSWORD=takab_dev psql -h 127.0.0.1 -p 5433 -U takab -d takab -q -f db/seeds/prod_fleet.sql
	PGPASSWORD=takab_dev psql -h 127.0.0.1 -p 5433 -U takab -d takab -q -f db/seeds/sim_fleet.sql
	PGPASSWORD=takab_dev psql -h 127.0.0.1 -p 5433 -U takab -d takab -q -f db/seeds/reference_earthquakes.sql

# Levanta 3 EdgeSupervisor reales + el consumer real + el motor de quórum real y
# acredita los 3 criterios con evidencia medible. Falla ruidosamente si alguno cae.
demo-fase1: demo-db
	cd $(API_DIR) && uv run python ../demo/run.py

# --- SOC local interactivo (Fase 1.7) ------------------------------------------
# Todo el stack en local para RECORRER la consola antes de desplegar: DB sembrada,
# API con /dev/token (JWKS inline de dev), worker de incidentes/dictamen, web dev
# server y UN gabinete real simulado (gw-dev-0001, panel LAN en :8080) con bridge
# al Postgres local. Estímulos: curl -X POST :9100/quake | /sasmex | /wan/off.
# Login en http://localhost:5173 → "token de desarrollo" (rol soc_operator o
# tenant_admin, tenant tenant-dev). Ctrl+C apaga todo.
soc-local: demo-db
	cd $(API_DIR) && uv run python scripts/dev_auth_env.py
	@test -f web/.env || (cp web/.env.example web/.env && echo "web/.env creado desde el example")
	bash demo/soc_local.sh

# --- Ensayo de restore (T-2.73) -----------------------------------------------
# Un solo comando: construye un origen sintético, lo vuelca, lo restaura en una
# base que el propio ensayo crea, VERIFICA la integridad de lo restaurado y
# publica el RTO desglosado por fases. `RUNBOOK-backup-restore-db.md:3` dice
# "RESTORE JAMÁS PROBADO" y su §2 dice "RTO: NO MEDIDO"; esto no cierra G-09
# (eso es la ventana AWS de T-2.74) pero deja de ser una hipótesis.
#
# La DSN apunta a `postgres` A PROPÓSITO: el ensayo NO toca `takab`. Crea sus dos
# bases con nombre generado y marcador propio, y se niega a escribir en cualquier
# otra cosa. Para ensayar contra datos reales: DRILL_ARGS="--source-db takab"
# (la base origen sólo se LEE). Para reproducir el §3 del runbook tal como está
# escrito hoy —y ver qué pierde—: DRILL_ARGS=--como-el-runbook.
#
# POR QUÉ NO ESTÁ EN CI, y qué haría falta para que lo estuviera:
#   1. Exige `pg_dump`/`pg_restore` del MISMO major que el servidor. El runner no
#      pinea esa versión y un cliente de otro major produce un restore con
#      errores que `pg_restore` reporta como "ignorados" — el verde mentiroso que
#      esta tarea persigue, reintroducido en el vigilante. Medido en local:
#      cliente 18.4 contra servidor 16 → `unrecognized configuration parameter
#      "transaction_timeout"`.
#   2. Crea y borra bases en el servidor: contra el contenedor de servicio
#      compartido de un job, es una clase de flake nueva por un número que no es
#      una regresión, es una medición.
# Lo que SÍ corre en cada PR es el verificador entero, con sus 36 mutaciones
# (`api/tests/ops/test_restore_check.py`, dentro del job `api`): la pieza que se
# pudre es esa, no la ceremonia. Para meter el ensayo en CI bastaría con fijar
# `postgresql-client-16` en el job `api` y añadir el paso; ~30 s.
#
# DESDE UN WORKTREE, este target (como `db`, `test-db` y `test`) choca con el
# contenedor del checkout principal: `container_name: takab-db` es fijo en
# docker-compose.yml —y tiene que serlo, porque runbooks y scripts hacen
# `docker exec takab-db`—, así que `docker compose up -d db` responde
# `Conflict. The container name "/takab-db" is already in use`. Es preexistente y
# no es de este target. Con el contenedor del principal ya vivo, salta el
# prerrequisito y llama al módulo directo:
#   cd api && DATABASE_URL=<RESTORE_DRILL_DSN> uv run python -m takab_api.ops.restore_drill
RESTORE_DRILL_DSN := postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/postgres

restore-drill: db
	@until docker compose exec -T db pg_isready -U takab -q; do sleep 1; done
	cd $(API_DIR) && DATABASE_URL="$(RESTORE_DRILL_DSN)" \
		uv run python -m takab_api.ops.restore_drill $(DRILL_ARGS)

down:
	docker compose down

# Paridad con ci.yml, incluido `mobile`: el job existe en CI desde T-2.00 pero el
# Makefile lo ignoraba, y por ahí se coló un merge en rojo (main, 2026-07-18).
# `ruff format --check` de api también faltaba: CI lo corre, make no.
# T-2.62: el `typecheck` de web es la tercera fuga de la misma familia — CI lo corría
# dentro de su build y make no lo corría en ningún sitio, así que un error de tipos
# en web/src pasaba `make lint && make test` en verde y reventaba el PR. Va en `lint`
# (es un error de tipos, no una suite; ~5 s) exactamente como el de `mobile` de abajo.
# `terraform fmt -check` es la cuarta: un .tf desalineado rompía el PR sin ningún
# aviso local. Cabe en `lint` porque es instantáneo, offline y no añade requisito
# nuevo al entorno (`make test` ya invoca terraform para el módulo observability).
# Sus hermanos `validate` NO caben: exigen un `init` que descarga providers, y
# lintar no puede depender de la red — quedan declarados en test_ci_parity.sh.
lint:
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB_DIR) && npm run lint && npm run format:check && npm run typecheck
	cd $(EDGE_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(ANALYZER_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(MOBILE_DIR) && npm run lint && npm run typecheck
	cd $(LANDING_DIR) && npm run lint && npm run format:check && npm run typecheck
	terraform fmt -check -recursive infra/terraform

# Paridad con ci.yml: perf se excluye (B-1) y demo/tests corre con el venv de
# api (B-2) — sus imports son takab_api + psycopg, sin dependencia del edge.
# `-rs` en el edge: los tests que necesitan hardware se saltan, y sin `-rs` se
# saltaban ANÓNIMOS (un "67 skipped" no dice qué dejó de cubrirse). Mismo flag en
# el job `edge` de ci.yml.
test: test-db
	cd $(API_DIR) && DATABASE_URL="$(TEST_DSN)" uv run pytest -q -m "not perf"
	cd $(API_DIR) && DATABASE_URL="$(TEST_DSN)" uv run pytest -q ../demo/tests
	cd $(WEB_DIR) && npm run test -- --run
	cd $(EDGE_DIR) && GPIOZERO_PIN_FACTORY=mock uv run pytest -q -rs
	cd $(ANALYZER_DIR) && uv run pytest -q -rs
	cd $(MOBILE_DIR) && npm test
	cd $(LANDING_DIR) && npm run test
	cd $(TF_OBSERVABILITY) && terraform init -backend=false -input=false >/dev/null && terraform test
	cd $(TF_DATABASE) && terraform init -backend=false -input=false >/dev/null && terraform test
	cd $(TF_STORAGE) && terraform init -backend=false -input=false >/dev/null && terraform test
	cd $(TF_IDENTITY) && terraform init -backend=false -input=false >/dev/null && terraform test
	bash infra/scripts/tests/test_merge_env.sh
	bash infra/scripts/tests/test_ci_parity.sh
	bash infra/scripts/tests/test_secret_scan.sh
	# [T-5.22] El recolector del acta del reflejo. Un procedimiento que se ejecuta
	# una vez cada varios meses no puede descubrirse roto delante del gabinete: el
	# que sustituye lo estaba en sus tres pasos.
	bash edge/tests/test_acta_reflejo_script.sh
	./ci/check-licenses.sh

# Gates de drift: el contrato y los tipos generados deben coincidir con lo
# commiteado. Los dos primeros solo vivían en CI; el de design-tokens no lo
# invocaba nadie (ni CI ni make) pese a estar escrito como gate.
drift:
	cd $(API_DIR) && uv run python scripts/export_openapi.py
	git diff --exit-code $(SDK_DIR)/openapi.json
	cd $(SDK_DIR) && npm run generate
	git diff --exit-code $(SDK_DIR)/src/gen
	cd $(SDK_DIR) && npm run check
	cd $(TOKENS_DIR) && npm run check
	# [T-5.28] La matriz RBAC que consumen los tests de web. Era una tabla escrita
	# a mano que se declaraba espejo de `auth/matrix.py` y divergió en 13 celdas;
	# ahora se genera, y aquí es donde se caza que alguien mueva la matriz sin
	# regenerarla. `api/tests/auth/test_rbac_fixture_es_la_matriz.py` lo ata además
	# por igualdad, celda a celda.
	cd $(API_DIR) && uv run python scripts/export_rbac_matrix.py
	git diff --exit-code shared/fixtures/rbac-matrix.json

# El bundler, en su propio target: `test` ya levanta Docker, corre terraform y 4
# suites; meterle vite lo convertiría en otra cosa. Aquí vive el `vite build` que
# CI corre desde siempre (job `web`) y que en local no corría nadie.
# `build` empaqueta las DOS superficies. El bundle de móvil es el equivalente del
# `vite build` de web, y no existía: jest, tsc y eslint pueden estar los tres en
# verde con una app QUE NO ARRANCA. `expo-router` arma su tabla de rutas con un
# `require.context` sobre `src/app`, así que cualquier fichero que caiga ahí entra
# en el bundle; el 2026-08-08 entraron tres `*.test.tsx`, arrastraron el `console`
# de Node y el bundle dejó de construirse durante un día sin que nada se pusiera
# rojo. Sale a /tmp porque aquí interesa que COMPILE, no el artefacto.
build:
	cd $(WEB_DIR) && npm run build
	cd $(MOBILE_DIR) && npx expo export --platform android --output-dir /tmp/expo-export
	cd $(LANDING_DIR) && npm run build

# Lo que corre CI, de una sola vez: el desarrollador no debería tener que saberse
# qué target cubre qué job. Precio explícito y aceptado: `tsc` corre dos veces
# (typecheck en `lint` + el build de aquí, ~5 s) a cambio de que no exista un orden
# de targets que deje un gate fuera. `test_ci_parity.sh` vigila que ci.yml no vuelva
# a ganar un paso sin espejo local, y corre en los DOS lados (`test` aquí y el job
# `infra` en CI): un gate que sólo viva en local no protege un PR.
verify: lint test build drift

fmt:
	cd $(API_DIR) && ruff format . && ruff check --fix .
	cd $(WEB_DIR) && npm run format
	cd $(EDGE_DIR) && uv run ruff format . && uv run ruff check --fix .

# --- Infra dev (T-1.15) --------------------------------------------------------
AWS_PROFILE ?= takab-dev
TF_DEV := infra/terraform/envs/dev

db-tunnel:
	@DB_ID=$$(terraform -chdir=$(TF_DEV) output -raw db_instance_id); \
	DB_IP=$$(terraform -chdir=$(TF_DEV) output -raw db_private_ip); \
	AWS_PROFILE=$(AWS_PROFILE) aws ssm start-session --region us-east-2 --target "$$DB_ID" \
		--document-name AWS-StartPortForwardingSessionToRemoteHost \
		--parameters "{\"host\":[\"$$DB_IP\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5434\"]}"

cloud-stop:
	@DB_ID=$$(terraform -chdir=$(TF_DEV) output -raw db_instance_id); \
	AWS_PROFILE=$(AWS_PROFILE) aws ec2 stop-instances --region us-east-2 --instance-ids "$$DB_ID"

cloud-start:
	@DB_ID=$$(terraform -chdir=$(TF_DEV) output -raw db_instance_id); \
	AWS_PROFILE=$(AWS_PROFILE) aws ec2 start-instances --region us-east-2 --instance-ids "$$DB_ID"

# --- Despliegue de la nube co-locada (T-1.37) ---------------------------------
# `cloud-images` construye y sube; `cloud-deploy` copia los artefactos al EC2 por SSM
# y levanta compose. Idempotentes: repetirlos no rompe nada. Runbook completo y
# precondiciones en deploy/cloud/README.md.
#
# OJO: `terraform apply` con instance_type nuevo PARA la instancia (la DB cae unos
# minutos y el gabinete acumula spool). Eso NO lo hace este target: es una decisión
# humana, no un efecto colateral de desplegar.
AWS_REGION ?= us-east-2
CLOUD_TAG  ?= $(shell git rev-parse --short HEAD)

# `--platform linux/arm64` SIEMPRE: el EC2 es Graviton y una imagen x86 muere
# en el pull con "no matching manifest" (descubierto en el primer deploy real;
# antes era una nota manual del README, que es como se olvidan las cosas).
# Cross-build desde x86 requiere binfmt una vez:
#   docker run --privileged --rm tonistiigi/binfmt --install arm64
cloud-images:
	@set -e; \
	if ! ls /proc/sys/fs/binfmt_misc/ 2>/dev/null | grep -qiE 'aarch64|arm64'; then \
		echo "ERROR: no hay interprete binfmt para arm64 en este equipo." >&2; \
		echo "       El build cruzado moriria dentro del contenedor con un" >&2; \
		echo "       'exec /bin/sh: exec format error' que no dice esto." >&2; \
		echo "       Se pierde en CADA reinicio del equipo; hay que reinstalarlo:" >&2; \
		echo "         docker run --privileged --rm tonistiigi/binfmt --install arm64" >&2; \
		exit 1; \
	fi; \
	ACC=$$(AWS_PROFILE=$(AWS_PROFILE) aws sts get-caller-identity --query Account --output text); \
	REG="$$ACC.dkr.ecr.$(AWS_REGION).amazonaws.com"; \
	AWS_PROFILE=$(AWS_PROFILE) aws ecr get-login-password --region $(AWS_REGION) \
		| docker login --username AWS --password-stdin "$$REG"; \
	AUTH=$$(terraform -chdir=$(TF_DEV) output -raw issuer); \
	CID=$$(terraform -chdir=$(TF_DEV) output -raw client_id); \
	DOM=$$(terraform -chdir=$(TF_DEV) output -raw hosted_ui_domain); \
	URL=$$(terraform -chdir=$(TF_DEV) output -raw console_url); \
	docker build --platform linux/arm64 -f api/Dockerfile -t "$$REG/takab/cloud:$(CLOUD_TAG)" .; \
	docker build --platform linux/arm64 -f deploy/cloud/console.Dockerfile -t "$$REG/takab/console:$(CLOUD_TAG)" \
		--build-arg VITE_COGNITO_AUTHORITY="$$AUTH" \
		--build-arg VITE_COGNITO_CLIENT_ID="$$CID" \
		--build-arg VITE_COGNITO_DOMAIN="$$DOM" \
		--build-arg VITE_COGNITO_REDIRECT_URI="$$URL/auth/callback" \
		--build-arg VITE_COGNITO_POST_LOGOUT_URI="$$URL/" .; \
	docker push "$$REG/takab/cloud:$(CLOUD_TAG)"; \
	docker push "$$REG/takab/console:$(CLOUD_TAG)"

cloud-deploy:
	@CLOUD_TAG=$(CLOUD_TAG) AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) \
		TF_DEV=$(TF_DEV) bash deploy/cloud/deploy.sh

# [T-2.171] `terraform apply` con las mismas guardas que un despliegue, porque es
# un despliegue: cambia infraestructura viva. Es el que menos se deja guardar
# —se teclea a mano, sin script de por medio— y por eso existe este target.
#
# Las DOS guardas salen de fallos medidos el 2026-08-27:
#
#   · A-1 (rama): un apply desde una rama de trabajo NO aplico el topic ni la
#     regla IoT que venia a aplicar, y no fallo — «sin cambios» es la respuesta
#     correcta cuando el codigo no trae el cambio.
#
#   · `local.auto.tfvars`: esta en .gitignore, asi que un arbol donde no exista
#     —un worktree recien creado, por ejemplo— hace que TODO lo que va con
#     `count` evalue a cero. Aquel dia el plan proponia DESTRUIR los tres
#     registros DKIM, DMARC, MAIL FROM y la consola. Lo caza un `plan` que
#     alguien mire, y eso no es una guardia: es suerte. Aqui se niega antes.
cloud-apply:
	@test -f $(TF_DEV)/local.auto.tfvars || { \
		echo "ERROR: falta $(TF_DEV)/local.auto.tfvars (esta en .gitignore)."; \
		echo "  Sin el, todo lo que lleva 'count' evalua a CERO y el plan propone DESTRUIR"; \
		echo "  SES, los tres DKIM, DMARC, MAIL FROM y la consola. Aplica desde tu arbol"; \
		echo "  de siempre, o copia ese fichero antes de planificar."; exit 1; }
	@bash -c '. deploy/lib/guardas.sh && guarda_de_rama "terraform"'
	@AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) \
		terraform -chdir=$(TF_DEV) apply

# --- Landing pública (takabailert.com) -----------------------------------------
# El sitio se sirve desde S3+CloudFront (modules/site). El contenido lo posee
# `aws s3 sync` (deploy/landing/deploy.sh), NO terraform: el módulo dejó de subir
# el index.html inline. Runbook completo en deploy/landing/README.md.
# `landing-preview` es el staging (local); `landing-e2e` captura los 4
# breakpoints + axe; `landing-audit` corre Lighthouse con budgets (LCP<2s 4G).
landing-preview:
	cd $(LANDING_DIR) && npm run build && npm run preview

landing-e2e:
	cd $(LANDING_DIR) && npm run e2e

landing-audit:
	cd $(LANDING_DIR) && npm run build && npm run audit

landing-deploy:
	@AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) TF_DEV=$(TF_DEV) \
		bash deploy/landing/deploy.sh

# Usuarios de consola en Cognito (T-1.62): un perfil por rol web, con su grupo
# (sin grupo el login da 401) y su contraseña en Secrets Manager. Idempotente.
# Cada usuario enrola MFA TOTP en su primer login: el pool lo exige a todos.
# La IP doméstica es dinámica: cada rotación deja la consola inalcanzable. Este
# target la reabre y, de paso, limpia las reglas manuales que harían fallar el
# siguiente `terraform apply` por duplicada. MODE=--status|--revoke.
cloud-allow-my-ip:
	@AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) bash infra/scripts/allow_my_ip.sh $(MODE)

cloud-users:
	@AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) bash infra/scripts/seed_console_users.sh $(ROLES)

# Usuarios MÓVILES (occupant/brigadista). Pool DISTINTO por rol y surface=mobile:
# los de `cloud-users` son surface=web y NO entran a la app. Siembra además la
# zona y el código de enrolamiento (el occupant sin asignación ve 404, R2).
cloud-mobile-users:
	@AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) bash infra/scripts/seed_mobile_users.sh $(ROLES)

# Incidente de staging para los E2E móviles (GATE-HW): abre/conduce un incidente
# controlable en el sitio piloto. PHASE=crisis|conclude|reentry|roster|reset|status
# (default crisis). Siembra por SQL vía túnel SSM; no hay POST /incidents.
cloud-staging-incident:
	@AWS_PROFILE=$(AWS_PROFILE) AWS_REGION=$(AWS_REGION) bash infra/scripts/seed_staging_incident.sh $(PHASE)

# --- [T-3.12.b] Imagen del Lambda de conteo de CCTV --------------------------
#
# El modelo se descarga AQUI y se comprueba su sha256 antes de entrar en el contexto de
# build. Bajarlo dentro del Dockerfile dejaria la imagen dependiendo de que una release de
# GitHub no cambie bajo sus pies — y el peso es lo que produce un numero que va a un
# dictamen, asi que su identidad no puede ser «lo que hubiera ese dia».
CCTV_MODELO_URL := https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx
CCTV_MODELO_SHA := c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d

.PHONY: cctv-modelo
cctv-modelo: ## Descarga y VERIFICA el peso YOLOX-nano (Apache-2.0) del Lambda
	@mkdir -p $(ANALYZER_DIR)/modelos
	@test -f $(ANALYZER_DIR)/modelos/yolox_nano.onnx || \
		curl -fsSL -o $(ANALYZER_DIR)/modelos/yolox_nano.onnx "$(CCTV_MODELO_URL)"
	@echo "$(CCTV_MODELO_SHA)  $(ANALYZER_DIR)/modelos/yolox_nano.onnx" | sha256sum -c - \
		|| (echo "✗ el peso NO coincide con el declarado: no se construye"; exit 1)

# Las TRES banderas de abajo no son gusto: sin ellas Lambda RECHAZA la imagen.
#
#   --platform linux/amd64  el Lambda corre en x86-64 salvo que se pida arm64, y buildx
#                           construye para la arquitectura de quien compila.
#   --provenance=false      buildx añade por defecto una attestation `unknown/unknown`, y
#   --sbom=false            eso convierte el manifiesto en un OCI *image index*.
#
# Lambda solo acepta un manifiesto de UNA arquitectura, no un índice. Con el índice falla
# con `InvalidParameterValueException: The image manifest ... is not supported`, que no
# menciona ni buildx ni las attestations — medido el 2026-08-30, con la imagen ya subida.
.PHONY: cctv-lambda-image
cctv-lambda-image: cctv-modelo ## Construye la imagen del Lambda (necesita el peso verificado)
	docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
		--load -t takab/cctv-analyzer:$(shell git rev-parse --short HEAD) $(ANALYZER_DIR)

.PHONY: cctv-lambda-push
cctv-lambda-push: cctv-modelo ## Construye y EMPUJA la imagen a ECR, en un solo manifiesto
	@TAG=$$(git rev-parse --short HEAD); \
	URI=$(CCTV_ECR)/takab/cctv-analyzer:$$TAG; \
	aws ecr get-login-password --profile $(AWS_PROFILE) --region $(AWS_REGION) \
		| docker login --username AWS --password-stdin $(CCTV_ECR); \
	docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
		--push -t $$URI $(ANALYZER_DIR); \
	echo "cctv_analyzer_image_uri = \"$$URI\""

AWS_PROFILE ?= takab-dev
AWS_REGION  ?= us-east-2
CCTV_ECR    ?= 634882473845.dkr.ecr.us-east-2.amazonaws.com
