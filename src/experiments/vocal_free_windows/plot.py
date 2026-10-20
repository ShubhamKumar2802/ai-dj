"""Vocal lane PNG of track A: per-bar stem level, threshold, windows, bar 32 and the exit."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from experiments.vocal_free_windows.windows import Window, to_db  # noqa: E402
from experiments.waveform_llm_transition.bars import format_mmss  # noqa: E402

LABEL_EVERY_BARS = 8


def draw_vocal_lane(
    path: Path,
    title: str,
    levels: list[float],
    bar_times: list[tuple[float, float]],
    cutoff_db: float,
    windows: list[Window],
    exit_after_bar: int,
    exit_bar: int | None,
) -> Path:
    """One bar per step on the x axis; labels show the bar number over its mm:ss."""
    level_db = to_db(levels)
    bars = list(range(1, len(levels) + 1))
    floor = min(cutoff_db - 12, float(level_db.max()) - 48)

    fig, ax = plt.subplots(figsize=(18, 4.5), dpi=100)
    ax.fill_between(bars, floor, level_db, step="post", color="#4c72b0", alpha=0.8,
                    label="vocal stem level (dB)")
    ax.axhline(cutoff_db, color="#c44e52", linestyle="--", linewidth=1.2,
               label=f"threshold {cutoff_db:.1f} dB")
    for i, w in enumerate(windows):
        ax.axvspan(w.first_bar, w.last_bar + 1, color="#55a868", alpha=0.25,
                   label="vocal-free window" if i == 0 else None)
    ax.axvline(exit_after_bar + 1, color="#8172b2", linewidth=1.2,
               label=f"after bar {exit_after_bar}")
    if exit_bar is not None:
        ax.axvline(exit_bar, color="#dd8452", linewidth=2.5, label=f"exit: bar {exit_bar}")

    ticks = [b for b in bars if (b - 1) % LABEL_EVERY_BARS == 0]
    ax.set_xticks(ticks, [f"{b}\n{format_mmss(bar_times[b - 1][0])}" for b in ticks])
    ax.set_xticks(bars, minor=True)
    ax.set_xlim(1, len(bars) + 1)
    ax.set_ylim(floor, float(level_db.max()) + 3)
    ax.set_xlabel("bar / mm:ss")
    ax.set_ylabel("dBFS")
    ax.set_title(title)
    ax.grid(axis="x", which="major", alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path
