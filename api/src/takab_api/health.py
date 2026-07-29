from fastapi import APIRouter

from takab_api.settings import Settings

router = APIRouter()


# `build` = SHA corto del commit con el que se construyó la imagen; lo inyecta
# `deploy/cloud/deploy.sh` desde `CLOUD_TAG` (que ya es `git rev-parse --short HEAD`).
# Sin esto, la única forma de saber qué corría en la nube era abrir una sesión SSM y
# leer `/etc/takab/deploy.env` — y por eso pasó inadvertido que la nube llevaba 82
# commits de retraso. Si la variable no está definida dice `unknown`: jamás una
# versión inventada.
@router.get("/health")
def health() -> dict[str, str]:
    """Salud del servicio y commit desplegado."""
    return {"status": "ok", "build": Settings().build_sha}
