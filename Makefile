.PHONY: dev down lint test fmt api web db install

API_DIR := apps/api
WEB_DIR := apps/web

install:
	cd $(API_DIR) && python -m pip install -e ".[dev]"
	cd $(WEB_DIR) && npm install

db:
	docker compose up -d db

api:
	cd $(API_DIR) && uvicorn takab_api.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(WEB_DIR) && npm run dev

dev: db
	$(MAKE) -j2 api web

down:
	docker compose down

lint:
	cd $(API_DIR) && ruff check .
	cd $(WEB_DIR) && npm run lint && npm run format:check

test:
	cd $(API_DIR) && pytest -q
	cd $(WEB_DIR) && npm run test -- --run

fmt:
	cd $(API_DIR) && ruff format . && ruff check --fix .
	cd $(WEB_DIR) && npm run format
