"""One sub-package per pipeline step: interface.py (Protocol), <impl>.py, factory.py (spec §3.1)."""

from collections.abc import Callable, Mapping
from typing import TypeVar

F = TypeVar("F", bound=Callable)


def resolve_impl(registry: Mapping[str, F], name: str, step: str) -> F:
    """Shared by every factory: look `name` up, or fail listing the valid names."""
    try:
        return registry[name]
    except KeyError:
        valid = ", ".join(sorted(registry))
        raise ValueError(f"unknown {step} impl '{name}'; valid: {valid}") from None
