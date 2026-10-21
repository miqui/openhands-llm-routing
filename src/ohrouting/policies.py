"""Routing policies (T3, ADR 0005): pure functions of (turn, phase, previous model).

A policy answers "which model serves this turn?" and whether that is a switch. No I/O, no
globals, no randomness. Turns are 1-based. Models are identified by their config profile key
(``"frontier"`` / ``"cheap"``, see ``Config.models()``); the runner maps keys to profiles.

FLAGGED ASSUMPTIONS (the design doc and ADR 0005 are silent on these):

1. Every policy starts on the frontier model; turn 1 never counts as a switch.
2. Every switch toggles to the other model of the pair (frontier <-> cheap).
3. switch-at-N switches frontier -> cheap exactly once, at turn N, and never again.
4. phase-boundary toggles the model whenever ``phase`` differs from ``previous_phase``.
   "Changes vs the previous turn" needs the previous turn's phase, so the call takes an extra
   ``previous_phase`` argument beyond (turn, phase, previous model); ``None`` on turn 1.
5. Phases are opaque strings here; their names are defined by the tasks (T4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

FRONTIER = "frontier"
CHEAP = "cheap"
MODELS = (FRONTIER, CHEAP)
START_MODEL = FRONTIER
SWITCH_POINTS = (5, 10, 15)  # mirrors Config.switch_points defaults
POLICY_NAMES = ("sticky", "alternate", "phase-boundary", "switch-at-N")


class PolicyError(ValueError):
    """Invalid policy name, parameter or call input."""


@dataclass(frozen=True)
class Decision:
    model: str
    switched: bool


Policy = Callable[[int, str, str | None, str | None], Decision]


def _other(model: str) -> str:
    return CHEAP if model == FRONTIER else FRONTIER


def _check(turn: int, previous_model: str | None) -> None:
    if isinstance(turn, bool) or not isinstance(turn, int) or turn < 1:
        raise PolicyError(f"turn must be an integer >= 1 (1-based), got {turn!r}")
    if previous_model is not None and previous_model not in MODELS:
        raise PolicyError(f"unknown model {previous_model!r}; expected one of {list(MODELS)}")
    if turn == 1 and previous_model is not None:
        raise PolicyError("turn 1 has no previous model")
    if turn > 1 and previous_model is None:
        raise PolicyError(f"turn {turn} requires a previous model")


def _decide(previous_model: str | None, switch: bool) -> Decision:
    if previous_model is None:
        return Decision(START_MODEL, False)
    return Decision(_other(previous_model), True) if switch else Decision(previous_model, False)


def sticky(turn: int, phase: str, previous_model: str | None, previous_phase: str | None = None):
    """Never switch; stay on the frontier model."""
    _check(turn, previous_model)
    return _decide(previous_model, False)


def alternate(turn: int, phase: str, previous_model: str | None, previous_phase: str | None = None):
    """Switch on every request after the first."""
    _check(turn, previous_model)
    return _decide(previous_model, True)


def phase_boundary(
    turn: int, phase: str, previous_model: str | None, previous_phase: str | None = None
):
    """Switch when the declared phase differs from the previous turn's phase."""
    _check(turn, previous_model)
    return _decide(previous_model, previous_phase is not None and phase != previous_phase)


def make_switch_at_n(n: int) -> Policy:
    """Build a policy that switches frontier -> cheap once, at turn ``n``."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise PolicyError(f"switch-at-N requires an integer N >= 1, got {n!r}")

    def switch_at_n(
        turn: int, phase: str, previous_model: str | None, previous_phase: str | None = None
    ) -> Decision:
        _check(turn, previous_model)
        if previous_model is None:
            return Decision(START_MODEL, False)
        if turn == n:
            return Decision(CHEAP, previous_model != CHEAP)
        return Decision(previous_model, False)

    return switch_at_n


def get_policy(name: str, n: int | None = None) -> Policy:
    """Look up a policy by name. ``switch-at-N`` requires ``n``; others reject it."""
    if name == "switch-at-N":
        if n is None:
            raise PolicyError("policy 'switch-at-N' requires parameter N")
        return make_switch_at_n(n)
    simple: dict[str, Policy] = {
        "sticky": sticky,
        "alternate": alternate,
        "phase-boundary": phase_boundary,
    }
    if name not in simple:
        raise PolicyError(f"unknown policy {name!r}; expected one of {list(POLICY_NAMES)}")
    if n is not None:
        raise PolicyError(f"policy {name!r} takes no parameter N")
    return simple[name]
