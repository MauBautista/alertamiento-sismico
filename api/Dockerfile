# Imagen única del backend cloud: un build, muchos commands
# (python -m takab_api.ingest --queue …, .incident, .notify, …).
# Contexto de build = RAÍZ del repo:  docker build -f api/Dockerfile .
FROM python:3.12-slim

WORKDIR /takab

COPY api/pyproject.toml api/alembic.ini api/
COPY api/src api/src
COPY api/migrations api/migrations
# El loader de contratos resuelve shared/schemas relativo al árbol del repo:
# la imagen replica el layout y el install es editable para conservarlo.
COPY shared/schemas shared/schemas

RUN pip install --no-cache-dir -e ./api

ENTRYPOINT ["python", "-m", "takab_api.ingest"]
