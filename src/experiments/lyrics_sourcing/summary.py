"""Human-readable summary.md for one run (spec §4.7). Pure."""

from collections import defaultdict

from experiments.lyrics_sourcing.schema import StructureResult, SyncedLyrics, TrackMetadata
from experiments.lyrics_sourcing.steps.time_match.normalize import normalize_text


def repeated_lines(lyrics: SyncedLyrics) -> list[tuple[str, list[float]]]:
    """Lyric lines (normalized text) occurring more than once, with their start times."""
    starts: dict[str, list[float]] = defaultdict(list)
    first_text: dict[str, str] = {}
    for segment in lyrics.segments:
        key = normalize_text(segment.text)
        if not key:
            continue
        starts[key].append(segment.start)
        first_text.setdefault(key, segment.text)
    repeated = [(first_text[k], times) for k, times in starts.items() if len(times) > 1]
    return sorted(repeated, key=lambda item: (-len(item[1]), item[1][0]))


def build_summary(
    title: str,
    result: StructureResult,
    lyrics: SyncedLyrics,
    meta: TrackMetadata,
) -> str:
    labels = result.labels
    lines = [
        f"# {title}",
        "",
        f"- Model: `{result.model}` (prompt v{result.prompt_version}, "
        f"{result.serializer}, ~{result.estimated_tokens} tokens)",
        f"- Lyrics: source `{lyrics.source}`, verdict `{lyrics.verdict}`, "
        f"offset {lyrics.offset_applied_s:+.2f}s, {len(lyrics.segments)} lines",
        "",
        "## Sections",
        "",
        "| start | end | type | conf | evidence |",
        "|---|---|---|---|---|",
    ]
    for s in labels.sections:
        evidence = s.evidence.replace("|", "/").replace("\n", " ")
        lines.append(f"| {s.start} | {s.end} | {s.type} | {s.confidence:.2f} | {evidence} |")

    heuristic = {
        kind: [c.position for c in meta.cues.cue_ins + meta.cues.cue_outs if c.kind == kind]
        for kind in ("hook_in", "hook_exit")
    }
    lines += [
        "",
        "## Hook",
        "",
        f"- LLM: **{labels.hook.start}-{labels.hook.end}s** — {labels.hook.reason}",
        f"- cue_derivation heuristic: hook_in {_times(heuristic['hook_in'])}, "
        f"hook_exit {_times(heuristic['hook_exit'])}",
        "",
        "## Repeated lyric lines",
        "",
    ]
    repeats = repeated_lines(lyrics)
    lines += [f"- ({len(times)}x) {text} — at {_times(times)}" for text, times in repeats] or [
        "- none"
    ]

    lines += ["", "## Validation issues", ""]
    lines += [f"- {issue}" for issue in result.issues] or ["- none"]
    if labels.notes:
        lines += ["", "## Model notes", "", labels.notes]
    return "\n".join(lines) + "\n"


def _times(times: list[float]) -> str:
    return ", ".join(f"{t:.1f}s" for t in times) if times else "—"
