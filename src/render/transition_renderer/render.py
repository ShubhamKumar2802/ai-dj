from render.transition_renderer.schema import Junction, StereoPCM

# Importing anything under the strategies package runs strategies/__init__.py,
# which imports every built-in strategy module and registers it as a side
# effect — so by the time render_junction resolves a tier, tier 3 is registered.
from render.transition_renderer.strategies.registry import get_strategy


def render_junction(junction: Junction, audio_a: StereoPCM, audio_b: StereoPCM) -> StereoPCM:
    """Render one ``Junction`` in isolation (spec §0, §4).

    Resolves ``get_strategy(junction.strategy_tier)`` and calls it. No
    dependency on a full ``MixPlan``, a mix position, or any other junction.
    Milestone A registers tier 3 only; any other tier raises
    ``UnregisteredStrategyError``.
    """
    return get_strategy(junction.strategy_tier)(junction, audio_a, audio_b)
