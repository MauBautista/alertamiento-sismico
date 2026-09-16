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
# [T-7.22] El glosario de procedencia se abre con `read_text()` y SIN respaldo
# (`takab_api/procedencia.py`), y lo alcanza cualquier incidente con correlación
# de catálogo — el caso de la demostración. Sin esta línea era FileNotFoundError
# en la nube y verde en local. Lo vigila `test_TODO_activo_compartido_que_la_api_lee_VIAJA_en_la_imagen`.
COPY shared/glossary shared/glossary

RUN pip install --no-cache-dir -e ./api

ENTRYPOINT ["python", "-m", "takab_api.ingest"]
