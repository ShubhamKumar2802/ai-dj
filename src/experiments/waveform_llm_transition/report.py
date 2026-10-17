"""The per-run summary.md: one section per pair, results or failure reason."""

from pathlib import Path

from experiments.waveform_llm_transition.bars import format_mmss
from experiments.waveform_llm_transition.schema import PairResult, Score, TrackFacts


def _track_line(facts: TrackFacts) -> str:
    return (
        f"- **{facts.label}:** {facts.name} — {facts.bpm:.1f} BPM, "
        f"{format_mmss(facts.duration)}, {facts.lufs:.1f} LUFS, {len(facts.downbeats)} bars, "
        f"downbeat_confidence {facts.downbeat_confidence:.2f}"
    )


def _signed(value: float, unit: str) -> str:
    return f"{value:+.0f} {unit}" if unit == "bars" else f"{value:+.1f} {unit}"


def _score_lines(score: Score | None) -> list[str]:
    if score is None or not score.marked and score.rating is None:
        return ["- **Score:** not marked (fill in `ground_truth.yaml` and re-run)"]
    lines = []
    for name, bars, secs in (
        ("Exit error", score.exit_error_bars, score.exit_error_s),
        ("Entry error", score.entry_error_bars, score.entry_error_s),
    ):
        if bars is None:
            lines.append(f"- **{name}:** not marked")
        else:
            lines.append(f"- **{name}:** {_signed(bars, 'bars')} ({_signed(secs, 's')}) vs. yours")
    rating = f"{score.rating}/5" if score.rating is not None else "not rated"
    lines.append(f"- **Rating:** {rating}" + (f" — {score.note}" if score.note else ""))
    return lines


def pair_section(result: PairResult) -> str:
    lines = [f"## {result.pair_id}", ""]
    for facts in (result.a, result.b):
        if facts is not None:
            lines.append(_track_line(facts))
    if not result.ok:
        lines += ["", f"**FAILED:** {result.failure}"]
        return "\n".join(lines)

    answer = result.answer
    lines += [
        "",
        f"- **Exit A:** bar {answer.exit_bar_a} at {format_mmss(result.exit_time)} "
        f"(LLM said {answer.exit_time_a})",
        f"- **Entry B:** bar {answer.entry_bar_b} at {format_mmss(result.entry_time)} "
        f"(LLM said {answer.entry_time_b})",
        f"- **Suggested technique:** {answer.technique}, {answer.length_bars} bars "
        "(recorded only; the preview is a hard cut)",
        f"- **Preview:** `{result.preview_path}`",
    ]
    for d in result.disagreements:
        detail = "not a m:ss time" if d.delta_s is None else f"{d.delta_s:+.1f} s off"
        lines.append(
            f"- **Flag:** {d.which} bar {d.bar} starts at {format_mmss(d.bar_time)}, "
            f"but the LLM said {d.stated_time!r} ({detail})"
        )
    lines += _score_lines(result.score)
    lines += [
        "",
        f"**Reasoning:** {answer.reasoning}",
        "",
        f"**Notes on A:** {answer.notes_a}",
        "",
        f"**Notes on B:** {answer.notes_b}",
    ]
    return "\n".join(lines)


def render_summary(results: list[PairResult], model: str, prompt_version: str) -> str:
    ok = sum(r.ok for r in results)
    header = [
        "# waveform_llm_transition — run summary",
        "",
        f"Model: `{model}` · prompt `{prompt_version}` · {ok}/{len(results)} pairs succeeded",
        "",
        "",
    ]
    return "\n".join(header) + "\n\n".join(pair_section(r) for r in results) + "\n"


def write_summary(
    results: list[PairResult], model: str, prompt_version: str, path: Path
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary(results, model, prompt_version))
    return path
