import pytest
from pydantic import ValidationError

from experiments.waveform_llm_transition.schema import TransitionAnswer

_ANSWER = {
    "exit_bar_a": 65,
    "exit_time_a": "2:21",
    "entry_bar_b": 1,
    "entry_time_b": "0:01",
    "technique": "bass_swap",
    "length_bars": 8,
    "reasoning": "A's last chorus ends at bar 64; B opens on a drum-only intro.",
    "notes_a": "intro bars 1-8, ...",
    "notes_b": "drums only bars 1-8, ...",
}


def test_sample_answer_parses():
    answer = TransitionAnswer.model_validate_json(
        '{"exit_bar_a": 65, "exit_time_a": "2:21", "entry_bar_b": 1, "entry_time_b": "0:01",'
        ' "technique": "bass_swap", "length_bars": 8, "reasoning": "r",'
        ' "notes_a": "a", "notes_b": "b"}'
    )
    assert answer.exit_bar_a == 65
    assert answer.technique == "bass_swap"


def test_unknown_technique_rejected():
    with pytest.raises(ValidationError, match="technique"):
        TransitionAnswer(**{**_ANSWER, "technique": "crossfade"})
