from experiments.waveform_llm_transition.report import render_summary, write_summary
from experiments.waveform_llm_transition.schema import (
    Disagreement,
    PairResult,
    Score,
    TrackFacts,
    TransitionAnswer,
)


def _facts(label, name):
    return TrackFacts(label, name, f"{name}.mp3", 207.9, 110.1, -9.6,
                      [0.52 + 2.18 * i for i in range(95)], 0.61)


def _results():
    good = PairResult(
        pair_id="gwqenR0crHo__RDIRaFGr19s",
        a=_facts("A", "Rock Tha Party"),
        b=_facts("B", "Marjaani"),
        answer=TransitionAnswer(
            exit_bar_a=65, exit_time_a="1:40", entry_bar_b=1, entry_time_b="0:00",
            technique="bass_swap", length_bars=8, reasoning="r", notes_a="na", notes_b="nb",
        ),
        exit_time=140.04,
        entry_time=0.52,
        disagreements=[Disagreement("exit_a", 65, "1:40", 140.04, -40.04)],
        preview_path="outputs/gwqenR0crHo__RDIRaFGr19s/preview.wav",
        score=Score(marked=True, exit_error_bars=4, exit_error_s=8.7, rating=3, note="ok"),
    )
    failed = PairResult(
        pair_id="5AeX7Ddq4ts__Jn5hsfbhWx4",
        a=_facts("A", "Zingaat"),
        b=_facts("B", "Munni Badnaam Hui"),
        failure="exit bar 200 out of range (1–95)",
    )
    return [good, failed]


def test_summary_with_one_succeeded_one_failed():
    text = render_summary(_results(), model="gemma-4-31b-it", prompt_version="v1")
    assert "1/2 pairs succeeded" in text
    for part in (
        "bar 65 at 2:20 (LLM said 1:40)",
        "bass_swap, 8 bars",
        "downbeat_confidence 0.61",
        "outputs/gwqenR0crHo__RDIRaFGr19s/preview.wav",
        "**Flag:** exit_a bar 65 starts at 2:20, but the LLM said '1:40' (-40.0 s off)",
        "**Exit error:** +4 bars (+8.7 s) vs. yours",
        "**Entry error:** not marked",
        "**Rating:** 3/5 — ok",
        "**FAILED:** exit bar 200 out of range (1–95)",
    ):
        assert part in text, part


def test_unmarked_score_says_so():
    result = _results()[0]
    result.score = Score(marked=False)
    assert "not marked (fill in `ground_truth.yaml`" in render_summary([result], "m", "v")


def test_write_summary(tmp_path):
    path = write_summary(_results(), "m", "v", tmp_path / "out" / "summary.md")
    assert path.read_text().startswith("# waveform_llm_transition")
