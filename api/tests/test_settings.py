"""Settings (T-1.17): el mapa tier→severity es coherente con el DDL real.

El CHECK de ``incidents.severity`` y el enum de tiers se PARSEAN de sus fuentes
de verdad (``db/schema.sql`` y ``shared/schemas/local_event.schema.json``) para
no petrificar copias.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from takab_api.settings import RANK, SEVERITY_RANK, TIER_SEVERITY, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _severities_from_ddl() -> list[str]:
    ddl = (REPO_ROOT / "db" / "schema.sql").read_text()
    match = re.search(r"severity\s+text NOT NULL CHECK \(severity IN \(([^)]+)\)\)", ddl)
    assert match, "CHECK de incidents.severity no encontrado en db/schema.sql"
    return re.findall(r"'([^']+)'", match.group(1))


def _tiers_from_schema() -> list[str]:
    schema = json.loads((REPO_ROOT / "shared" / "schemas" / "local_event.schema.json").read_text())
    return schema["$defs"]["Tier"]["enum"]


def test_tier_severity_values_match_ddl_check() -> None:
    severities = _severities_from_ddl()
    assert set(TIER_SEVERITY.values()) <= set(severities)
    assert set(SEVERITY_RANK) == set(severities)
    # el rango respeta el orden del CHECK (de menor a mayor)
    assert sorted(severities, key=SEVERITY_RANK.__getitem__) == severities


def test_tier_severity_covers_all_tiers() -> None:
    tiers = _tiers_from_schema()
    assert set(TIER_SEVERITY) == set(tiers)
    assert set(RANK) == set(tiers)
    # el rango respeta el orden del enum (normal < watch < ...)
    assert sorted(tiers, key=RANK.__getitem__) == tiers


def test_tier_severity_is_monotone_with_rank() -> None:
    """Un tier mayor nunca mapea a una severidad menor (UPSERT nunca degrada)."""
    ordered = sorted(RANK, key=RANK.__getitem__)
    ranks = [SEVERITY_RANK[TIER_SEVERITY[tier]] for tier in ordered]
    assert ranks == sorted(ranks)


def test_settings_defaults() -> None:
    s = Settings()
    assert s.database_url == "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    assert s.aws_region == "us-east-2"
    assert s.registry_ttl_s == 30.0
    assert s.queue_url_events == ""
    assert s.dlq_url_telemetry == ""
    assert s.evidence_bucket == ""
    assert s.transfer_bucket == ""


def test_settings_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("TAKAB_API_AWS_REGION", "us-west-2")
    monkeypatch.setenv("TAKAB_API_REGISTRY_TTL_S", "5.5")
    monkeypatch.setenv("TAKAB_API_QUEUE_URL_EVENTS", "https://sqs.example/q-events")
    s = Settings()
    assert s.aws_region == "us-west-2"
    assert s.registry_ttl_s == 5.5
    assert s.queue_url_events == "https://sqs.example/q-events"
