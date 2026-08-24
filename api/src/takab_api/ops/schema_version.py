"""[T-2.153] La revisión de esquema que la imagen TRAE contra la que la base APLICÓ.

**El hecho que originó esto, medido el 2026-08-21:** la nube llevaba
`0038_privacy_erasure_on_behalf` y el repo iba por `0046_privacy_subject_sealing`.
**Ocho migraciones de diferencia, y no lo dijo nada** — ni un test, ni una alarma, ni
el health. Se descubrió por un síntoma lateral (una alarma de retención de PII que no
podía apagarse porque `0043` no había creado su tabla) tras media hora persiguiendo el
script equivocado.

`/health` ya declaraba **el commit** desplegado, así que la mitad del trabajo existía.
Lo que no declaraba es la **cabeza de migración**, que es la que rompe cosas en
silencio: una imagen que no arranca se nota sola; una que arranca contra un esquema
viejo es la que muerde.

**Los tres estados no son dos.** «Al día» y «atrasada» son lo obvio; el tercero —
**`desconocida`** — es el que hay que respetar. Si no se puede leer `alembic_version`
(la base caída, o sin permiso: en la nube la tabla es del rol migrador, no de la app)
**eso NO es «al día»**. Es la doctrina de `T-2.152` —*un fallback no puede presentarse
como `ok`*— y la de la alarma del gabinete mudo: se vigila la AUSENCIA del dato.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

import takab_api

log = logging.getLogger("takab_api.ops")

#: Estados posibles. `desconocida` es un estado de pleno derecho, no un error.
AL_DIA = "al_dia"
ATRASADA = "atrasada"
DESCONOCIDA = "desconocida"
#: La base va por DELANTE de la imagen: pasa en un rollback de imagen sin rollback de
#: esquema, y es peligroso de otra forma — el código viejo no conoce lo que hay debajo.
ADELANTADA = "adelantada"


def _dir_migraciones() -> Path:
    """`api/migrations`, derivado del paquete instalado.

    Vale igual en el repo (`api/src/takab_api` → `api/`) y en la imagen, donde el
    `Dockerfile` copia `api/migrations` junto a `api/src` bajo `/takab/api`.
    """
    return Path(takab_api.__file__).resolve().parents[2] / "migrations"


def _script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(_dir_migraciones()))
    return ScriptDirectory.from_config(cfg)


@lru_cache(maxsize=1)
def revision_esperada() -> str | None:
    """La cabeza que trae ESTA imagen. `None` si no se puede determinar.

    Cacheada: los ficheros de migración no cambian sin reiniciar el proceso.
    """
    try:
        return _script_directory().get_current_head()
    except Exception:  # noqa: BLE001 - declarar que no se sabe, jamás inventar una cabeza
        log.warning("no se pudo derivar la cabeza de migración de la imagen", exc_info=True)
        return None


def _pendientes(aplicada: str, esperada: str) -> int | None:
    """Cuántas migraciones separan a una de otra. `None` si no se puede saber.

    `iterate_revisions(upper, lower)` devuelve `(lower, upper]` —excluye la de abajo—,
    así que su longitud ES el número de migraciones que faltan por aplicar. Verificado
    contra el caso real: `0038 → 0046` da **8**, que es lo que se midió en la nube.
    """
    try:
        return len(list(_script_directory().iterate_revisions(esperada, aplicada)))
    except Exception:  # noqa: BLE001 - una cifra inventada es peor que ninguna
        return None


def comparar(aplicada: str | None, esperada: str | None) -> dict[str, object]:
    """El veredicto. **Declarar sin comparar sería dar el dato al humano que ya no mira.**"""
    if aplicada is None or esperada is None:
        return {
            "aplicada": aplicada,
            "esperada": esperada,
            "estado": DESCONOCIDA,
            "pendientes": None,
        }
    if aplicada == esperada:
        return {"aplicada": aplicada, "esperada": esperada, "estado": AL_DIA, "pendientes": 0}
    faltan = _pendientes(aplicada, esperada)
    if faltan:
        return {
            "aplicada": aplicada,
            "esperada": esperada,
            "estado": ATRASADA,
            "pendientes": faltan,
        }
    # No se pudo recorrer de la aplicada a la esperada. O la base va por DELANTE
    # (rollback de imagen sin rollback de esquema), o la aplicada no está en esta
    # imagen. Las dos son «no al día», y ninguna es `desconocida`: sabemos que
    # DIFIEREN, que es justo el hecho que esto existe para publicar.
    return {"aplicada": aplicada, "esperada": esperada, "estado": ADELANTADA, "pendientes": None}


async def revision_aplicada() -> str | None:
    """Lo que la base dice tener. `None` si no se pudo PREGUNTAR.

    Best-effort a propósito: esto cuelga de `/health`, que es la sonda de vida. Una base
    caída tiene que dar «no lo sé», no tumbar el endpoint que sirve para saber si el
    proceso vive.
    """
    try:
        from takab_api.db.engine import get_engine

        async with get_engine().connect() as conn:
            fila = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
            return None if fila is None else str(fila[0])
    except Exception:  # noqa: BLE001 - «no se pudo preguntar» ≠ «al día»
        log.warning("no se pudo leer alembic_version", exc_info=True)
        return None


async def estado_del_esquema() -> dict[str, object]:
    return comparar(await revision_aplicada(), revision_esperada())
