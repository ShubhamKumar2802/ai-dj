"""Waveform image tiles: fixed-duration, overlapping windows of a track, each drawn as three
stacked band lanes with a header, bar-number and mm:ss label rows, and bar gridlines.

Every tile has the same pixel size and covers `tile_s` seconds, so px/s is identical across
tiles and across both tracks of a pair — the last tile of a track is drawn with empty space
after the track ends rather than stretched.
"""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from experiments.waveform_llm_transition.bands import BandEnvelopes  # noqa: E402
from experiments.waveform_llm_transition.bars import format_mmss  # noqa: E402
from experiments.waveform_llm_transition.schema import TrackFacts  # noqa: E402

_DPI = 100
# Top to bottom, as DJ software stacks them.
_LANES = (("high", "HIGH", "#6b6b6b"), ("mid", "MID", "#e8871e"), ("low", "LOW", "#1f5fbf"))
_BAR_LABEL_EVERY = 2
_PHRASE_EVERY = 4
_TIME_LABEL_EVERY_S = 5


@dataclass
class TileWindow:
    index: int  # 1-based
    count: int
    start: float
    end: float  # clipped to the track's duration

    @property
    def label(self) -> str:
        return f"tile {self.index}/{self.count} ({format_mmss(self.start)}–{format_mmss(self.end)})"


def tile_windows(duration: float, tile_s: float, overlap_s: float) -> list[TileWindow]:
    """Windows starting every `tile_s - overlap_s` seconds until one reaches `duration`."""
    if not 0 <= overlap_s < tile_s:
        raise ValueError(f"overlap_s must be in [0, tile_s); got {overlap_s} for {tile_s}")
    step = tile_s - overlap_s
    starts = [0.0]
    while starts[-1] + tile_s < duration:
        starts.append(starts[-1] + step)
    return [
        TileWindow(index=i + 1, count=len(starts), start=s, end=min(s + tile_s, duration))
        for i, s in enumerate(starts)
    ]


def header_text(facts: TrackFacts, window: TileWindow) -> str:
    return (
        f"{facts.label}: {facts.name}  |  {facts.bpm:.1f} BPM  |  "
        f"duration {format_mmss(facts.duration)}  |  {facts.lufs:.1f} LUFS  |  {window.label}"
    )


def draw_tile(
    envelopes: BandEnvelopes,
    facts: TrackFacts,
    window: TileWindow,
    tile_s: float,
    height_px: int,
    out_path: Path,
) -> Path:
    width_px = round(tile_s * envelopes.px_per_s)
    fig = plt.figure(figsize=(width_px / _DPI, height_px / _DPI), dpi=_DPI)
    # Fixed margins, so the plot area — and therefore px/s — is the same on every tile.
    fig.subplots_adjust(left=0.05, right=0.99, top=0.90, bottom=0.17, hspace=0.06)
    axes = fig.subplots(len(_LANES), 1, sharex=True)
    fig.text(0.05, 0.95, header_text(facts, window), fontsize=13, weight="bold", va="center")

    x_limits = (window.start, window.start + tile_s)
    first_col = int(window.start * envelopes.px_per_s)
    last_col = int(np.ceil(window.end * envelopes.px_per_s))
    bars_in_window = [
        (n, t) for n, t in enumerate(facts.downbeats, start=1) if x_limits[0] <= t <= x_limits[1]
    ]

    for ax, (band, name, colour) in zip(axes, _LANES):
        values = envelopes.get(band)[first_col:last_col]
        x = (first_col + np.arange(len(values))) / envelopes.px_per_s
        ax.fill_between(x, -values, values, color=colour, linewidth=0)
        ax.set_xlim(*x_limits)
        ax.set_ylim(-1.05, 1.05)
        ax.set_yticks([])
        ax.set_ylabel(name, rotation=0, ha="right", va="center", fontsize=11, weight="bold")
        for n, t in bars_in_window:
            if (n - 1) % _PHRASE_EVERY == 0:
                ax.axvline(t, color="black", linewidth=1.1, alpha=0.65)
            else:
                ax.axvline(t, color="black", linewidth=0.5, alpha=0.2)

    bottom = axes[-1]
    labelled = [(n, t) for n, t in bars_in_window if (n - 1) % _BAR_LABEL_EVERY == 0]
    bottom.set_xticks([t for _, t in labelled], [str(n) for n, _ in labelled], fontsize=10)
    bottom.tick_params(axis="x", length=4)

    first_label_s = np.ceil(x_limits[0] / _TIME_LABEL_EVERY_S) * _TIME_LABEL_EVERY_S
    times = np.arange(first_label_s, x_limits[1] + 1e-9, _TIME_LABEL_EVERY_S)
    time_axis = bottom.secondary_xaxis(-0.42)
    time_axis.set_xticks(times, [format_mmss(t) for t in times], fontsize=10)
    time_axis.tick_params(axis="x", length=4)

    fig.text(0.03, 0.125, "bar", ha="right", va="center", fontsize=10, weight="bold")
    fig.text(0.03, 0.045, "time", ha="right", va="center", fontsize=10, weight="bold")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    return out_path
