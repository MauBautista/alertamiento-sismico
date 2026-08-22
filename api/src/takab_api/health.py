from fastapi import APIRouter

from takab_api.ops.schema_version import estado_del_esquema
from takab_api.settings import Settings

router = APIRouter()


# `build` = SHA corto del commit con el que se construyó la imagen; lo inyecta
# `deploy/cloud/deploy.sh` desde `CLOUD_TAG` (que ya es `git rev-parse --short HEAD`).
# Sin esto, la única forma de saber qué corría en la nube era abrir una sesión SSM y
# leer `/etc/takab/deploy.env` — y por eso pasó inadvertido que la nube llevaba 82
# commits de retraso. Si la variable no está definida dice `unknown`: jamás una
# versión inventada.
#
# [T-2.153] `esquema` es la otra mitad, y es la que muerde en silencio. El commit
# desplegado no dice contra qué ESQUEMA corre: el 2026-08-21 la nube llevaba ocho
# migraciones de retraso y no lo dijo ni un test, ni una alarma, ni este endpoint.
# Se descubrió por un síntoma lateral, media hora después. Y no basta con DECLARAR
# las dos revisiones: hay que COMPARARLAS aquí, porque declararlas sueltas es darle
# el dato al humano que ya dejó de mirar.
#
# `status` sigue siendo `ok` incondicionalmente y esto NO puede cambiarlo: es una
# sonda de vida del proceso. Un esquema viejo es un problema de datos, no un proceso
# muerto, y tumbar el health por eso reiniciaría en bucle un contenedor sano. Por eso
# la lectura de la base es best-effort y su fallo se declara como `desconocida`, que
# **no es `al_dia`** — un fallback no puede presentarse como `ok` (T-2.152).
@router.get("/health")
async def health() -> dict[str, object]:
    """Salud del servicio, commit desplegado y deriva de esquema."""
    return {
        "status": "ok",
        "build": Settings().build_sha,
        "esquema": await estado_del_esquema(),
    }
