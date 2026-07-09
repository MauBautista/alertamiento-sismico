.PHONY: dev down lint test fmt api web edge db install db-tunnel cloud-stop cloud-start billing \
        demo-fase1 demo-db

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

demo-db: db
	@until docker compose exec -T db pg_isready -U takab -q; do sleep 1; done
	cd $(API_DIR) && DATABASE_URL="$(DEMO_DSN)" uv run python -m alembic upgrade head
	PGPASSWORD=takab_dev psql -h 127.0.0.1 -p 5433 -U takab -d takab -q -f db/seeds/dev_fleet.sql

# Levanta 3 EdgeSupervisor reales + el consumer real + el motor de quórum real y
# acredita los 3 criterios con evidencia medible. Falla ruidosamente si alguno cae.
demo-fase1: demo-db
	cd $(API_DIR) && uv run python ../demo/run.py

down:
	docker compose down

lint:
	cd $(API_DIR) && ruff check .
	cd $(WEB_DIR) && npm run lint && npm run format:check
	cd $(EDGE_DIR) && uv run ruff check . && uv run ruff format --check .

test:
	cd $(API_DIR) && pytest -q
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
