"""Genera `.env.dev-auth` (raíz del repo) para correr el SOC local SIN Cognito.

La consola local usa `POST /dev/token` (routers/dev_token.py), que solo se monta
cuando `auth_jwks_json` no está vacío — señal inequívoca de entorno dev/test.
Este script fabrica un keypair RSA efímero de DESARROLLO y escribe un archivo
shell-sourceable con las 4 variables `TAKAB_API_AUTH_*` que la API necesita.

- Idempotente: si el archivo ya existe NO se regenera (los tokens vivos seguirían
  validando); `--force` lo rota.
- El archivo queda cubierto por el `.gitignore` raíz (`.env.*`): la clave, aunque
  sea de juguete, jamás se versiona (regla de oro 6).

Uso (lo invoca `make soc-local`):
    uv run --directory api python scripts/dev_auth_env.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env.dev-auth"

_ISSUER = "https://dev.local/takab"
_AUDIENCE = "takab-dev-console"
_KID = "takab-dev-local"


def _build_env() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": _KID, "alg": "RS256", "use": "sig"})
    jwks = json.dumps({"keys": [jwk]})
    return (
        "# Auth de DESARROLLO para el SOC local (generado por api/scripts/dev_auth_env.py).\n"
        "# NO es material de producción; .gitignore lo cubre. Rotar: --force.\n"
        f"TAKAB_API_AUTH_ISSUER='{_ISSUER}'\n"
        f"TAKAB_API_AUTH_AUDIENCE='{_AUDIENCE}'\n"
        f"TAKAB_API_AUTH_JWKS_JSON='{jwks}'\n"
        f"TAKAB_API_AUTH_DEV_PRIVATE_KEY='{private_pem}'\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="regenera aunque exista")
    args = parser.parse_args()

    if _ENV_FILE.exists() and not args.force:
        print(f"ya existe {_ENV_FILE} (usa --force para rotar)")
        return 0
    _ENV_FILE.write_text(_build_env())
    print(f"escrito {_ENV_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
