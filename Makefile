.PHONY: dev down lint test fmt api web edge db install db-tunnel cloud-stop cloud-start billing cloud-users \
        cloud-mobile-users cloud-staging-incident demo-fase1 demo-db cloud-images cloud-deploy

API_DIR := api
WEB_DIR := web
EDGE_DIR := edge

install:
	cd $(API_DIR) && python -m pip install -e ".[dev]"
	cd $(WEB_DIR) && npm install
	cd $(EDGE_DIR) && uv sync

db:
	docker compose up -d db

api:
	cd $(API_DIR) && uvicorn takab_api.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(WEB_DIR) && npm run dev

edge:
	cd $(EDGE_DIR) && uv run takab-edge

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
demo-db: db
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

down:
	docker compose down

lint:
	cd $(API_DIR) && ruff check .
	cd $(WEB_DIR) && npm run lint && npm run format:check
	cd $(EDGE_DIR) && uv run ruff check . && uv run ruff format --check .

# Paridad con ci.yml: perf se excluye (B-1) y demo/tests corre con el venv de
# api (B-2) — sus imports son takab_api + psycopg, sin dependencia del edge.
test:
	cd $(API_DIR) && pytest -q -m "not perf"
	cd $(API_DIR) && uv run pytest -q ../demo/tests
	cd $(WEB_DIR) && npm run test -- --run
	cd $(EDGE_DIR) && GPIOZERO_PIN_FACTORY=mock uv run pytest -q

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

# Usuarios de consola en Cognito (T-1.62): un perfil por rol web, con su grupo
# (sin grupo el login da 401) y su contraseña en Secrets Manager. Idempotente.
# Cada usuario enrola MFA TOTP en su primer login: el pool lo exige a todos.
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
