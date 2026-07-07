"""Contratos IoT: carga de JSON Schema compartidos + strip de meta_* (T-1.17)."""

from takab_api.contracts.loader import (
    KINDS,
    ContractError,
    kind_for_topic,
    validate,
)
from takab_api.contracts.meta import Meta, split_meta

__all__ = ["KINDS", "ContractError", "Meta", "kind_for_topic", "split_meta", "validate"]
