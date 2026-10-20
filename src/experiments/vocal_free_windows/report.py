"""Run result, ground-truth ratings, and the per-run `summary.md`."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from experiments.vocal_free_windows.windows import Window
from experiments.waveform_llm_transition.bars import format_mmss

OUTPUT_KINDS = ("cut", "overlap", "bass_swap")


class Rating(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None


class PairRatings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cut: Rating = Rating()
    overlap: Rating = Rating()
    bass_swap: Rating = Rating()


def load_ratings(path: str | Path, pair_id: str) -> PairRatings:
    """This pair's ratings; blank when the file or the pair's entry is missing."""
    path = Path(path)
    if not path.is_file():
        return PairRatings()
    data = yaml.safe_load(path.read_text()) or {}
    return PairRatings(**((data.get("pairs") or {}).get(pair_id) or {}))


@dataclass
class TrackInfo:
    name: str
    path: str
    bpm: float
    lufs: float


@dataclass
class OutputInfo:
    kind: str  # one of OUTPUT_KINDS
    path: str | None = None
    peak_dbfs: float | None = None
    skipped: str | None = None  # why it wasn't written


@dataclass
class RunResult:
    pair_id: str
    a: TrackInfo
    b: TrackInfo
    failure: str | None = None
    windows: list[Window] = field(default_factory=list)
    cutoff_db: float | None = None
    exit_after_bar: int | None = None
    exit_window: Window | None = None
    entry_s: float | None = None
    gain_db: float | None = None
    overlap_bars: int | None = None
    bass_swap_bars: int | None = None
    drift_overlap_ms: float | None = None
    drift_bass_swap_ms: float | None = None
    image_path: str | None = None
    outputs: list[OutputInfo] = field(default_factory=list)


def _t(seconds: float) -> str:
    return f"{format_mmss(seconds)} ({seconds:.2f} s)"


def _rating_line(kind: str, ratings: PairRatings) -> str:
    r: Rating = getattr(ratings, kind)
    score = "not rated" if r.rating is None else f"{r.rating}/5"
    return f"- **{kind}:** {score}" + (f" — {r.note}" if r.note else "")


def render_summary(result: RunResult, ratings: PairRatings) -> str:
    lines = [
        "# vocal_free_windows — run summary",
        "",
        f"## {result.pair_id}",
        "",
        f"- **A:** {result.a.name} — {result.a.bpm:.1f} BPM, {result.a.lufs:.1f} LUFS",
        f"- **B:** {result.b.name} — {result.b.bpm:.1f} BPM, {result.b.lufs:.1f} LUFS",
        "",
    ]
    if result.cutoff_db is not None:
        lines += [f"**A's vocal-free windows** (threshold {result.cutoff_db:.1f} dBFS):", ""]
        lines += [
            f"- bars {w.first_bar}–{w.last_bar}: {_t(w.start_s)} – {_t(w.end_s)}"
            for w in result.windows
        ] or ["- none"]
        lines.append("")

    if result.failure:
        lines += [f"**Failed:** {result.failure}", ""]
        return "\n".join(lines)

    w = result.exit_window
    lines += [
        f"- **Exit A:** bar {w.first_bar} at {_t(w.start_s)} — first window starting after "
        f"bar {result.exit_after_bar} (window bars {w.first_bar}–{w.last_bar})",
        f"- **Entry B:** bar 1 (intro) at {_t(result.entry_s)}",
        f"- **Gain on B:** {result.gain_db:+.1f} dB",
        f"- **BPM difference:** {result.b.bpm - result.a.bpm:+.1f} (no tempo matching)",
        f"- **Drift:** {result.drift_overlap_ms:.0f} ms over the {result.overlap_bars}-bar "
        f"overlap, {result.drift_bass_swap_ms:.0f} ms over the {result.bass_swap_bars}-bar "
        "bass swap",
        f"- **Image:** `{result.image_path}`",
        "",
        "**Outputs:**",
        "",
    ]
    for out in result.outputs:
        if out.skipped:
            lines.append(f"- **{out.kind}:** skipped — {out.skipped}")
        else:
            lines.append(f"- **{out.kind}:** `{out.path}` (peak {out.peak_dbfs:+.1f} dBFS)")
    lines += ["", "**Ratings** (`ground_truth.yaml`):", ""]
    lines += [_rating_line(kind, ratings) for kind in OUTPUT_KINDS]
    lines.append("")
    return "\n".join(lines)


def write_summary(path: Path, result: RunResult, ratings: PairRatings) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary(result, ratings))
    return path
