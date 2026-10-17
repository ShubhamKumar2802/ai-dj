"""Line anchoring + offset vote + verdict (spec §4.4.2-4.4.3). Pure: no audio, no network.

Each lyric line keeps its top-k fuzzy matches in the transcript (not only the best one —
chorus lines repeat, and a single best match pairs a line with the wrong occurrence). Every
match proposes an offset; correct matches agree on one offset while wrong ones scatter, so
a weighted vote finds it.
"""

import statistics
from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz

from experiments.lyrics_sourcing.config import TimeMatchConfig
from experiments.lyrics_sourcing.schema import Alignment, LyricLine, Transcript
from experiments.lyrics_sourcing.steps.time_match.normalize import (
    count_perso_arabic_words,
    normalize_text,
)


@dataclass
class Anchor:
    line_index: int
    delta: float  # transcript time - lyric time, seconds
    score: float  # rapidfuzz ratio, 0-100


@dataclass
class _Word:
    text: str  # normalized
    start: float


def align(
    source: str,
    lines: list[LyricLine],
    transcript: Transcript,
    duration: float,
    cfg: TimeMatchConfig,
) -> tuple[Alignment, dict[int, Anchor]]:
    """Returns the Alignment and the inlier anchor per line index (for confidences)."""
    words = _flat_words(transcript)
    density_wpm = len(words) / (duration / 60) if duration > 0 else 0.0
    urdu_words = sum(count_perso_arabic_words(w.text) for w in words)

    anchorable, candidates = _anchor_lines(lines, words, cfg)
    offset = _vote(candidates, cfg.offset_bin_s)

    inliers: dict[int, Anchor] = {}
    if offset is not None:
        for line_index, anchors in candidates.items():
            close = [a for a in anchors if abs(a.delta - offset) <= cfg.inlier_tolerance_s]
            if close:
                inliers[line_index] = min(close, key=lambda a: abs(a.delta - offset))

    coverage = len(inliers) / anchorable if anchorable else None
    residual = (
        statistics.median(abs(a.delta - offset) for a in inliers.values())
        if inliers and offset is not None
        else None
    )
    drift = _drift_slope(lines, inliers)

    verdict = _verdict(density_wpm, anchorable, coverage, residual, offset, cfg)
    alignment = Alignment(
        source=source,
        verdict=verdict,
        offset_s=round(offset, 3) if offset is not None else None,
        anchorable_lines=anchorable,
        inlier_lines=len(inliers),
        line_coverage=round(coverage, 3) if coverage is not None else None,
        median_abs_residual_s=round(residual, 3) if residual is not None else None,
        drift_slope=round(drift, 4) if drift is not None else None,
        transcript_density_wpm=round(density_wpm, 1),
        urdu_script_words=urdu_words,
    )
    return alignment, inliers


def _flat_words(transcript: Transcript) -> list[_Word]:
    words = []
    for segment in transcript.segments:
        for word in segment.words:
            text = normalize_text(word.text)
            if text:
                words.append(_Word(text=text, start=word.start))
    return words


def _anchor_lines(
    lines: list[LyricLine], words: list[_Word], cfg: TimeMatchConfig
) -> tuple[int, dict[int, list[Anchor]]]:
    anchorable = 0
    candidates: dict[int, list[Anchor]] = {}
    for index, line in enumerate(lines):
        text = normalize_text(line.text)
        if len(text) < cfg.min_line_chars:
            continue
        anchorable += 1
        anchors = _top_matches(index, line, text, words, cfg)
        if anchors:
            candidates[index] = anchors
    return anchorable, candidates


def _top_matches(
    index: int, line: LyricLine, text: str, words: list[_Word], cfg: TimeMatchConfig
) -> list[Anchor]:
    n = len(text.split())
    lengths = range(max(1, round(0.7 * n)), max(1, round(1.3 * n)) + 1)

    scored: list[tuple[float, int, int]] = []  # (score, first word, length)
    for length in lengths:
        for first in range(0, len(words) - length + 1):
            window = " ".join(w.text for w in words[first : first + length])
            score = fuzz.ratio(text, window)
            if score >= cfg.anchor_min_score:
                scored.append((score, first, length))

    scored.sort(key=lambda s: (-s[0], s[1]))
    chosen: list[tuple[float, int, int]] = []
    for score, first, length in scored:
        if len(chosen) == cfg.k_candidates:
            break
        if all(first + length <= f or f + ln <= first for _, f, ln in chosen):
            chosen.append((score, first, length))

    return [
        Anchor(line_index=index, delta=words[first].start - line.start, score=score)
        for score, first, _ in chosen
    ]


def _vote(candidates: dict[int, list[Anchor]], window_s: float) -> float | None:
    """Weighted vote over every anchor's delta: the `window_s`-wide window holding the most
    weight wins, and the offset is the weighted mean inside it. (A sliding window rather
    than fixed histogram bins, so a true offset sitting on a bin edge isn't split in two.)
    """
    anchors = [a for group in candidates.values() for a in group]
    if not anchors:
        return None

    best_weight, best_members = -1.0, []
    half = window_s / 2
    for centre in anchors:
        members = [a for a in anchors if abs(a.delta - centre.delta) <= half]
        weight = sum(a.score for a in members)
        if weight > best_weight:
            best_weight, best_members = weight, members

    total = sum(a.score for a in best_members)
    return sum(a.delta * a.score for a in best_members) / total


def _drift_slope(lines: list[LyricLine], inliers: dict[int, Anchor]) -> float | None:
    if len(inliers) < 2:
        return None
    lyric_t = np.array([lines[i].start for i in inliers])
    audio_t = lyric_t + np.array([a.delta for a in inliers.values()])
    if np.ptp(lyric_t) == 0:
        return None
    return float(np.polyfit(lyric_t, audio_t, 1)[0])


def _verdict(
    density_wpm: float,
    anchorable: int,
    coverage: float | None,
    residual: float | None,
    offset: float | None,
    cfg: TimeMatchConfig,
) -> str:
    if density_wpm < cfg.min_transcript_wpm:
        return "unverifiable"
    if (
        anchorable < cfg.min_anchorable_lines
        or coverage is None
        or coverage < cfg.min_coverage
        or residual is None
        or residual > cfg.max_residual_s
        or offset is None
    ):
        return "rejected"
    if abs(offset) <= cfg.zero_offset_tolerance_s:
        return "matched"
    return "offset_corrected"
