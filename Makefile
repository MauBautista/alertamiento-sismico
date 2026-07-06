.PHONY: dev down lint test fmt api web edge db install

API_DIR := api
WEB_DIR := web
EDGE_DIR := edge

install:
	cd $(API_DIR) && python -m pip install -e ".[dev]"
	cd $(WEB_DIR) && npm install
	cd $(EDGE_DIR) && uv sync --extra dev

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
