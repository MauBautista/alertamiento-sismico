"""Separación de las claves ``meta_*`` inyectadas por la IoT Rule (T-1.15).

``meta_principal`` (= thing name del publicador, no falsificable), ``meta_topic``
y ``meta_ts_iot`` (epoch ms) se separan ANTES de validar contra schema. Un
replay manual puede no traerlas → Meta con None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

META_KEYS = frozenset({"meta_principal", "meta_topic", "meta_ts_iot"})


@dataclass(frozen=True)
class Meta:
    principal: str | None
    topic: str | None
    ts_iot: datetime | None


def split_meta(raw: dict) -> tuple[dict, Meta]:
    """Devuelve (payload sin ``meta_*``, Meta). Tolera ``meta_*`` ausentes."""
    payload = {k: v for k, v in raw.items() if k not in META_KEYS}
    ts_raw = raw.get("meta_ts_iot")
    ts_iot = None if ts_raw is None else datetime.fromtimestamp(ts_raw / 1000.0, tz=UTC)
    return payload, Meta(
        principal=raw.get("meta_principal"),
        topic=raw.get("meta_topic"),
        ts_iot=ts_iot,
    )
