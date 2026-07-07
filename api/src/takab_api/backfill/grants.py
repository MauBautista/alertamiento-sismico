"""Grant service del backfill (T-1.25): request verificado → URL pre-firmada.

El edge publica ``backfill_request`` en ``takab/backfill/request/<thing>``; la
IoT Rule lo enruta a ``q-backfill`` con ``meta_principal`` (thing del cert
X.509, no falsificable). Aquí se verifica que el thing del TOPIC sea el
principal (nadie pide grants a nombre de otro), se resuelve el gateway y se
responde por ``takab/backfill/grant/<thing>`` con la **key canónica** —
autoridad de la NUBE (v1.1.0):

- ``backfill/{thing}/{from}_{to}.ndjson.gz``          (bucket transfer)
- ``evidence/{tenant_id}/{event_uuid}/{sha256}.mseed`` (bucket evidence)

Anti-thundering-herd: el TTL del presign es corto y el edge serializa (un
objeto por gateway); aquí no se guarda estado — el request re-emitido tras un
grant perdido simplemente recibe otro.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta

import boto3

from takab_api.commands.publisher import CommandPublisher, PublishError
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import GatewayCtx
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.backfill")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TS_FMT = "%Y%m%dT%H%M%SZ"


def _presign_put(settings: Settings, bucket: str, key: str, content_type: str) -> str:
    client = boto3.client("s3", region_name=settings.aws_region)
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=int(settings.backfill_presign_ttl_s),
    )


def canonical_key(payload: dict, ctx: GatewayCtx, thing: str) -> tuple[str, str, str] | None:
    """(bucket_attr, key, content_type) del request, o ``None`` si es inválido."""
    mode = payload.get("mode")
    if mode == "backfill":
        try:
            ts_from = datetime.fromisoformat(payload["ts_from"])
            ts_to = datetime.fromisoformat(payload["ts_to"])
        except (KeyError, TypeError, ValueError):
            return None
        key = (
            f"backfill/{thing}/"
            f"{ts_from.astimezone(UTC):{_TS_FMT}}_{ts_to.astimezone(UTC):{_TS_FMT}}.ndjson.gz"
        )
        return ("transfer_bucket", key, "application/x-ndjson")
    if mode == "evidence":
        event_id = payload.get("event_id") or ""
        sha256 = payload.get("sha256") or ""
        if not event_id or not _SHA256_RE.fullmatch(sha256):
            return None
        key = f"evidence/{ctx.tenant_id}/{event_id}/{sha256}.mseed"
        return ("evidence_bucket", key, "application/vnd.fdsn.mseed")
    return None


def handle_backfill_request(
    payload: dict,
    meta: Meta,
    ctx: GatewayCtx,
    publisher: CommandPublisher,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Procesa un request verificado por identidad; devuelve (ok, razón).

    El llamador (consumer) YA validó el schema y resolvió ``ctx`` por
    ``meta.principal``; aquí se re-verifica la identidad del TOPIC y se emite
    el grant. Fail-closed: sin bucket configurado no se otorga nada.
    """
    now = now or datetime.now(tz=UTC)
    thing = (meta.topic or "").removeprefix("takab/backfill/request/")
    if not thing or thing != meta.principal:
        return False, "backfill_request: principal/topic mismatch"

    resolved = canonical_key(payload, ctx, thing)
    if resolved is None:
        return False, "backfill_request: payload inválido (mode/ventana/sha256)"
    bucket_attr, key, content_type = resolved
    bucket = getattr(settings, bucket_attr)
    if not bucket:
        return False, f"backfill_request: bucket no configurado ({bucket_attr})"

    grant = {
        "kind": "backfill_grant",
        "request_id": payload.get("request_id", ""),
        "mode": payload["mode"],
        "url": _presign_put(settings, bucket, key, content_type),
        "key": key,
        "expires_at": (now + timedelta(seconds=settings.backfill_presign_ttl_s)).isoformat(),
    }
    try:
        publisher.publish(f"takab/backfill/grant/{thing}", json.dumps(grant).encode())
    except PublishError as exc:
        return False, f"backfill_request: publish del grant falló ({exc})"
    logger.info("grant %s → %s (%s)", payload["mode"], key, thing)
    return True, ""
