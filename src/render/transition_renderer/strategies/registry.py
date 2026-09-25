from typing import Callable

from render.transition_renderer.errors import UnregisteredStrategyError
from render.transition_renderer.schema import Junction, StereoPCM

# One rendered segment out of one Junction plus the two tracks' PCM in (spec §4).
StrategyFn = Callable[[Junction, StereoPCM, StereoPCM], StereoPCM]

_registry: dict[int, StrategyFn] = {}


def register_strategy(tier: int, fn: StrategyFn, *, overwrite: bool = False) -> None:
    """Register a render strategy under ``tier``. Raises if ``tier`` is already
    registered, unless ``overwrite=True`` — guards against a stray
    re-registration silently clobbering a real strategy (mirrors
    ``common/llm_service``'s provider registry).
    """
    if tier in _registry and not overwrite:
        raise ValueError(
            f"Strategy for tier {tier} is already registered. Pass overwrite=True to replace it."
        )
    _registry[tier] = fn


def get_strategy(tier: int) -> StrategyFn:
    """Resolve the strategy for ``tier``. Raises ``UnregisteredStrategyError``
    listing the registered tiers — this is how tiers 2/4/5 fail loudly in
    Milestone A rather than silently producing wrong audio (spec §4)."""
    try:
        return _registry[tier]
    except KeyError:
        registered = ", ".join(str(t) for t in sorted(_registry)) or "(none)"
        raise UnregisteredStrategyError(
            f"No render strategy registered for tier {tier}. Registered tiers: {registered}"
        ) from None
