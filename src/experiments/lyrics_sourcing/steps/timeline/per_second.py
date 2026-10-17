"""One timeline row per integer second: per-bar metadata + events + lyric starts (spec §4.6). Pure.

A second belongs to the bar whose [start_time, end_time) contains t + 0.5; seconds outside
the bar grid (before the first downbeat / after the last) get None for every per-bar column.
"""

import math
from bisect import bisect_left, bisect_right

from experiments.lyrics_sourcing.config import TimelineConfig
from experiments.lyrics_sourcing.schema import (
    IngestedTrack,
    SyncedLyrics,
    Timeline,
    TimelineHeader,
    TimelineRow,
    TrackMetadata,
)

# Essentia's NNLSChroma (the Vamp NNLS Chroma algorithm) orders its 12 bins starting at A.
PITCH_CLASSES = ("A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#")


class PerSecondTimelineBuilder:
    def __init__(self, cfg: TimelineConfig) -> None:
        self._cfg = cfg

    def build(self, track: IngestedTrack, lyrics: SyncedLyrics, meta: TrackMetadata) -> Timeline:
        return build_per_second(track, lyrics, meta)


def build_per_second(track: IngestedTrack, lyrics: SyncedLyrics, meta: TrackMetadata) -> Timeline:
    raw, cues = meta.raw, meta.cues
    bars = raw.per_bar_features
    bar_starts = [bar.start_time for bar in bars]

    scaled = {
        "vocal": _minmax(raw.vocal_band_energy),
        "rms": _minmax([b.rms for b in bars]),
        "low": _minmax([b.low_band_energy for b in bars]),
        "high": _minmax([b.high_band_energy for b in bars]),
        "centroid": _minmax([b.spectral_centroid for b in bars]),
        "flux": _minmax([b.spectral_flux for b in bars]),
    }
    all_cues = sorted(cues.cue_ins + cues.cue_outs, key=lambda cue: cue.position)

    rows = []
    for t in range(math.floor(raw.duration) + 1):
        bar = _bar_at(t + 0.5, bar_starts, bars)
        phrase_strengths = [p.strength for p in cues.phrase_grid if _in_second(p.position, t)]
        cue_kinds = list(dict.fromkeys(c.kind for c in all_cues if _in_second(c.position, t)))
        lyric_texts = [s.text for s in lyrics.segments if _in_second(s.start, t)]

        rows.append(
            TimelineRow(
                t=t,
                bar=bar,
                downbeat=int(_count_in(raw.downbeat_times, t) > 0),
                beats=_count_in(raw.beat_times, t),
                energy_lufs=_round(_at(raw.energy_curve, bar), 1),
                vocal=_at(scaled["vocal"], bar),
                rms=_at(scaled["rms"], bar),
                low=_at(scaled["low"], bar),
                high=_at(scaled["high"], bar),
                centroid=_at(scaled["centroid"], bar),
                flux=_at(scaled["flux"], bar),
                chroma=_chroma(bars[bar].chroma_vector) if bar is not None else None,
                phrase=round(max(phrase_strengths), 2) if phrase_strengths else None,
                cue=";".join(cue_kinds) or None,
                riser=int(any(r.start_time <= t < r.resolution_time for r in raw.riser_candidates)),
                lyric=";".join(lyric_texts) or None,
            )
        )

    header = TimelineHeader(
        title=track.title or track.raw_title,
        artist=track.artist,
        video_id=track.video_id,
        duration=round(raw.duration, 2),
        bpm=_round(raw.bpm, 1),
        bpm_confidence=_round(raw.bpm_confidence, 2),
        key=raw.key,
        key_confidence=_round(raw.key_confidence, 2),
        lufs_integrated=_round(raw.lufs_integrated, 1),
        true_peak=_round(raw.true_peak, 1),
        structure_template=cues.structure_template,
        grid_start=_round(cues.grid_start, 2),
        phrase_length_bars=_round(cues.phrase_length_bars, 1),
        cue_status=cues.status,
        lyrics_source=lyrics.source,
        lyrics_verdict=lyrics.verdict,
        lyrics_offset_s=_round(lyrics.offset_applied_s, 2),
    )
    return Timeline(header=header, rows=rows, lyrics=list(lyrics.segments))


def _bar_at(time: float, bar_starts: list[float], bars: list) -> int | None:
    i = bisect_right(bar_starts, time) - 1
    if i >= 0 and time < bars[i].end_time:
        return i
    return None


def _in_second(time: float, t: int) -> bool:
    return t <= time < t + 1


def _count_in(sorted_times: list[float], t: int) -> int:
    return bisect_left(sorted_times, t + 1) - bisect_left(sorted_times, t)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [0.0] * len(values)
    return [round((v - low) / (high - low), 2) for v in values]


def _at(values: list, index: int | None):
    if index is None or index >= len(values):
        return None
    return values[index]


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def _chroma(vector: list[float]) -> str | None:
    if not vector or max(vector) <= 0:
        return None
    return PITCH_CLASSES[max(range(len(vector)), key=vector.__getitem__)]
