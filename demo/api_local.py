"""[T-6.18] La API del SOC local, con la BAJADA enchufada al gabinete simulado.

`make soc-local` levantaba la API tal cual (`takab_api.main:app`), y su
`get_publisher()` devuelve el publicador de **AWS IoT Core**. Sin credenciales
—que es el caso en una laptop— cada comando firmado moría al publicar, así que
un simulacro salía con «5 SIN COMANDO EMITIDO» y **el aborto por sismo real no
se podía ensayar en local**: el arnés dejaba fuera justo la mitad del sistema
que va de la nube al gabinete (lo cazó la auditoría UI/UX, U-37).

Aquí se sustituye ESA dependencia y nada más:

    IotDataPublisher  →  SpoolCommandPublisher(<workdir>/bajada)

que es el mismo publicador que usa el guion del hito (`demo/run.py`, T-5.29) y
deja el envelope **ya firmado** en el buzón del thing; el transporte del
gabinete lo entrega a su suscripción y ahí lo recibe el `CommandDispatcher`
REAL, que verifica HMAC, nonce y ventana antes de tocar un relé. La firma no se
salta: si la clave del gabinete no coincide con la de la API, el comando se
rechaza igual que en producción — que es lo que se quiere poder ensayar.

Todo lo demás es la aplicación de producción, importada sin tocar: routers,
auth, base de datos. La sustitución es una `dependency_overrides`, el mismo
mecanismo con el que los tests inyectan sus dobles.

Se sirve con `uvicorn demo.api_local:app` (lo hace `demo/soc_local.sh`). En la
nube nadie importa este módulo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from demo.spool import SpoolCommandPublisher  # noqa: E402

from takab_api.main import app  # noqa: E402
from takab_api.routers.commands import get_publisher  # noqa: E402

#: El MISMO directorio que `demo/soc_local.py` le pasa al gabinete en
#: `--downlink`. Viaja por entorno para que las dos mitades no puedan
#: desincronizarse en silencio: si no coincidieran, el comando se publicaría en
#: un buzón que nadie lee y el simulacro volvería a quedarse sin acuse.
BAJADA = Path(os.environ.get("TAKAB_DEMO_DOWNLINK", _ROOT / ".local-soc" / "bajada"))

#: Uno solo para todo el proceso: `published` es el contador de la bajada y con
#: un publicador por request no contaría nada.
_publisher = SpoolCommandPublisher(BAJADA)

app.dependency_overrides[get_publisher] = lambda: _publisher
