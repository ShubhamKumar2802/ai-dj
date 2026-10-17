"""Pick the per-track source of truth (spec §4.4.4). Pure.

1. Accepted lyrics (matched / offset_corrected) win — highest coverage, ties within 0.05 go
   to priority order (the candidates' list order).
2. Else unverifiable lyrics still beat the transcript: the fetch succeeded and there is no
   evidence it's wrong.
3. Else the Whisper transcript is the source of truth — including when every fetched
   candidate was `rejected` (timing that contradicts our audio can't locate the hook).
"""

import statistics

from experiments.lyrics_sourcing.config import TimeMatchConfig
from experiments.lyrics_sourcing.schema import (
    Alignment,
    LyricLine,
    LyricsCandidate,
    LyricSegment,
    SyncedLyrics,
    Transcript,
)
from experiments.lyrics_sourcing.steps.time_match.align import Anchor

_COVERAGE_TIE = 0.05

Aligned = tuple[LyricsCandidate, Alignment, dict[int, Anchor]]


def resolve(
    aligned: list[Aligned],
    transcript: Transcript,
    duration: float,
    cfg: TimeMatchConfig,
) -> SyncedLyrics:
    alignments = [alignment for _, alignment, _ in aligned]

    accepted = [
        (i, entry)
        for i, entry in enumerate(aligned)
        if entry[1].verdict in ("matched", "offset_corrected")
    ]
    if accepted:
        best_coverage = max(entry[1].line_coverage or 0.0 for _, entry in accepted)
        _, (candidate, alignment, inliers) = min(
            (
                item
                for item in accepted
                if (item[1][1].line_coverage or 0.0) >= best_coverage - _COVERAGE_TIE
            ),
            key=lambda item: item[0],
        )
        shift = alignment.offset_s if alignment.verdict == "offset_corrected" else 0.0
        confidences = {i: anchor.score / 100 for i, anchor in inliers.items()}
        segments, dropped = lyric_segments(
            candidate.lines, shift, duration, cfg.max_line_s, confidences
        )
        return SyncedLyrics(
            source=candidate.source,
            verdict=alignment.verdict,
            offset_applied_s=shift or 0.0,
            segments=segments,
            lines_dropped=dropped,
            alignments=alignments,
            thresholds=cfg.thresholds(),
        )

    unverifiable = [entry for entry in aligned if entry[1].verdict == "unverifiable"]
    if unverifiable:
        candidate, _, _ = unverifiable[0]
        return unshifted_lyrics(candidate, duration, cfg, alignments)

    return transcript_lyrics(transcript, cfg, alignments)


def unshifted_lyrics(
    candidate: LyricsCandidate,
    duration: float,
    cfg: TimeMatchConfig,
    alignments: list[Alignment],
) -> SyncedLyrics:
    segments, dropped = lyric_segments(candidate.lines, 0.0, duration, cfg.max_line_s, {})
    return SyncedLyrics(
        source=candidate.source,
        verdict="unverifiable",
        offset_applied_s=0.0,
        segments=segments,
        lines_dropped=dropped,
        alignments=alignments,
        thresholds=cfg.thresholds(),
    )


def transcript_lyrics(
    transcript: Transcript, cfg: TimeMatchConfig, alignments: list[Alignment]
) -> SyncedLyrics:
    segments = []
    for segment in transcript.segments:
        if not segment.text:
            continue
        probabilities = [w.probability for w in segment.words if w.probability is not None]
        segments.append(
            LyricSegment(
                start=round(segment.start, 3),
                end=round(segment.end, 3),
                text=segment.text,
                confidence=round(statistics.mean(probabilities), 3) if probabilities else None,
            )
        )
    return SyncedLyrics(
        source="whisper",
        verdict="fallback",
        offset_applied_s=0.0,
        segments=segments,
        lines_dropped=0,
        alignments=alignments,
        thresholds=cfg.thresholds(),
    )


def lyric_segments(
    lines: list[LyricLine],
    shift: float,
    duration: float,
    max_line_s: float,
    confidences: dict[int, float],
) -> tuple[list[LyricSegment], int]:
    """Shift, give every line an end, clamp to [0, duration]; drop lines wholly outside.

    A line ends at its own `end` if the source gave one (else the next line's start),
    capped at `start + max_line_s`; the last line ends at min(start + max_line_s, duration).
    """
    segments: list[LyricSegment] = []
    dropped = 0
    for i, line in enumerate(lines):
        start = line.start + shift
        if line.end is not None:
            end = line.end + shift
        elif i + 1 < len(lines):
            end = lines[i + 1].start + shift
        else:
            end = start + max_line_s
        end = min(end, start + max_line_s, duration)
        start = max(start, 0.0)
        if end <= start or start >= duration:
            dropped += 1
            continue
        segments.append(
            LyricSegment(
                start=round(start, 3),
                end=round(end, 3),
                text=line.text,
                confidence=round(confidences[i], 3) if i in confidences else None,
            )
        )
    return segments, dropped
