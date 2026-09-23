"""Spec-first testing: write the test before the code exists.

Several CoachLink rules are specified precisely in ``ARCHITECTURE.md`` long before
``back`` implements them (volume formula §4, ``is_client_active`` §7, the blocking
consent gate §5.2). QA writes those tests immediately — that is the point of testing
*au fil de l'eau* rather than at the end.

The problem is keeping CI green in the meantime. The usual answer is a
``@pytest.mark.xfail`` decorator, but it has a nasty failure mode: once ``back`` ships
the code, a **stale** marker silently swallows a genuine assertion failure, and nobody
notices that the rule is actually broken. The marker has to be removed by hand, and it
never is.

So we use the imperative form instead, right where the missing symbol is imported::

    def test_bodyweight_exercise_contributes_zero():
        compute_volume = require("app.domain.volume", "compute_volume")
        assert compute_volume(...) == Decimal("0")

While ``app.domain.volume`` does not exist the test reports ``xfail`` (CI stays green).
The moment it exists the import succeeds, the rest of the test body runs for real, and a
wrong result is a **hard failure**. Nothing to remember, nothing to clean up.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from types import ModuleType
from typing import Any

import pytest

__all__ = ["is_available", "require", "require_any", "require_module"]


def require_module(dotted: str) -> ModuleType:
    """Import a module, or mark the calling test ``xfail`` if it does not exist yet."""
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as exc:
        # Guard against a *real* missing third-party dependency inside an existing
        # module being mistaken for "not written yet".
        if exc.name is not None and not (exc.name == dotted or dotted.startswith(f"{exc.name}.")):
            raise
        pytest.xfail(f"not implemented yet: module '{dotted}' does not exist")


def require(dotted: str, name: str) -> Any:
    """Import ``name`` from ``dotted``, or mark the calling test ``xfail``."""
    module = require_module(dotted)
    try:
        return getattr(module, name)
    except AttributeError:
        pytest.xfail(f"not implemented yet: '{dotted}.{name}'")


def require_any(candidates: Sequence[tuple[str, str]]) -> Any:
    """Return the first ``(module, name)`` that resolves, else ``xfail``.

    Used when QA writes the test before ``back`` has picked the final module path — the
    rule is specified, its home is not. Avoids a test failing merely because the function
    landed in ``app.domain.billing`` rather than ``app.domain.activity``.
    """
    for dotted, name in candidates:
        if is_available(dotted, name):
            return getattr(importlib.import_module(dotted), name)
    listed = ", ".join(f"{m}.{n}" for m, n in candidates)
    pytest.xfail(f"not implemented yet: none of [{listed}] exists")


def is_available(dotted: str, name: str | None = None) -> bool:
    """Non-failing probe, for fixtures that must decide without aborting the test."""
    try:
        module = importlib.import_module(dotted)
    except ModuleNotFoundError:
        return False
    return name is None or hasattr(module, name)
