"""Ciclo de vida del incidente — máquina de estados PURA (T-1.19 · G5). Sin DB."""

from __future__ import annotations

import pytest

from takab_api.incident.transitions import (
    STATES,
    VALID_TRANSITIONS,
    InvalidTransition,
    is_terminal,
    validate_transition,
)

VALID = [
    ("open", "acked"),
    ("open", "in_review"),
    ("open", "closed"),
    ("acked", "in_review"),
    ("acked", "closed"),
    ("in_review", "closed"),
]


@pytest.mark.parametrize(("cur", "nxt"), VALID)
def test_valid_transitions_pass(cur: str, nxt: str) -> None:
    validate_transition(cur, nxt)  # no lanza


def test_states_match_schema_check() -> None:
    assert STATES == {"open", "acked", "in_review", "closed"}
    assert set(VALID_TRANSITIONS) == STATES


@pytest.mark.parametrize(
    ("cur", "nxt"),
    [
        ("acked", "open"),  # retroceso
        ("in_review", "open"),  # retroceso
        ("in_review", "acked"),  # retroceso
        ("closed", "open"),  # closed es terminal
        ("closed", "acked"),
        ("closed", "in_review"),
        ("open", "open"),  # auto-transición no permitida
        ("closed", "closed"),
    ],
)
def test_invalid_transitions_raise(cur: str, nxt: str) -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(cur, nxt)


def test_unknown_states_raise() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition("bogus", "closed")
    with pytest.raises(InvalidTransition):
        validate_transition("open", "bogus")


def test_closed_is_terminal() -> None:
    assert is_terminal("closed") is True
    assert VALID_TRANSITIONS["closed"] == frozenset()
    for state in STATES - {"closed"}:
        assert is_terminal(state) is False
