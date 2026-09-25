import numpy as np
import pytest

from render.transition_renderer import UnregisteredStrategyError, render_junction
from render.transition_renderer.strategies import registry
from render.transition_renderer.strategies.cut_on_the_one import cut_on_the_one


def test_tier_3_dispatches_to_cut_on_the_one(make_pcm, make_junction):
    audio_a = make_pcm(1.0, freq=200.0)
    audio_b = make_pcm(1.0, freq=330.0)
    junction = make_junction(cue_out=0.6, cue_in=0.1, strategy_tier=3)

    out = render_junction(junction, audio_a, audio_b)
    direct = cut_on_the_one(junction, audio_a, audio_b)

    assert np.array_equal(out.samples, direct.samples)
    assert out.sample_rate == direct.sample_rate


@pytest.mark.parametrize("tier", [2, 4, 5])
def test_unregistered_tiers_fail_loudly(tier, make_pcm, make_junction):
    junction = make_junction(strategy_tier=tier)
    with pytest.raises(UnregisteredStrategyError) as excinfo:
        render_junction(junction, make_pcm(0.5), make_pcm(0.5))
    # The message names the tiers that ARE registered (tier 3 in Milestone A).
    assert "3" in str(excinfo.value)


def test_register_strategy_guards_against_silent_clobber():
    sentinel = object()
    try:
        registry.register_strategy(99, sentinel)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            registry.register_strategy(99, sentinel)  # type: ignore[arg-type]
        registry.register_strategy(99, sentinel, overwrite=True)  # type: ignore[arg-type]
        assert registry.get_strategy(99) is sentinel
    finally:
        registry._registry.pop(99, None)
