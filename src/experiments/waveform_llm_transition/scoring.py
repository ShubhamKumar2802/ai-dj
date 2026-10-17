"""The light accuracy check: the LLM's exit/entry bars vs. the user's hand-marked times."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from experiments.waveform_llm_transition.bars import bar_start, nearest_bar, parse_mmss
from experiments.waveform_llm_transition.schema import Score


class GroundTruthEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_a: str | None = None
    entry_b: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None


def load_ground_truth(path: str | Path) -> dict[str, GroundTruthEntry]:
    """Entries by pair id; an empty dict when the file doesn't exist yet."""
    path = Path(path)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {pair_id: GroundTruthEntry(**(entry or {})) for pair_id, entry in
            (data.get("pairs") or {}).items()}


def _error(downbeats: list[float], llm_bar: int, marked: str | None) -> tuple[int, float] | None:
    """(signed bar error, signed seconds error) of the LLM's bar vs. a marked m:ss time."""
    if marked is None:
        return None
    marked_s = parse_mmss(str(marked))
    return llm_bar - nearest_bar(downbeats, marked_s), bar_start(downbeats, llm_bar) - marked_s


def score_pair(
    entry: GroundTruthEntry | None,
    downbeats_a: list[float],
    downbeats_b: list[float],
    exit_bar_a: int,
    entry_bar_b: int,
) -> Score:
    if entry is None or (entry.exit_a is None and entry.entry_b is None and entry.rating is None):
        return Score(marked=False)
    exit_error = _error(downbeats_a, exit_bar_a, entry.exit_a)
    entry_error = _error(downbeats_b, entry_bar_b, entry.entry_b)
    return Score(
        marked=exit_error is not None or entry_error is not None,
        exit_error_bars=exit_error[0] if exit_error else None,
        exit_error_s=exit_error[1] if exit_error else None,
        entry_error_bars=entry_error[0] if entry_error else None,
        entry_error_s=entry_error[1] if entry_error else None,
        rating=entry.rating,
        note=entry.note,
    )
