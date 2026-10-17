"""Post-validation of the model's labels (spec §4.7). Pure.

Clamps into [0, floor(duration)] and sorts by start; everything else is *reported* as an issue,
never fixed — how well-formed a local model's output is, is part of what's being measured.
"""

import math

from experiments.lyrics_sourcing.schema import StructureLabels

_MAX_GAP_S = 2


def validate(labels: StructureLabels, duration: float) -> tuple[StructureLabels, list[str]]:
    max_t = math.floor(duration)
    issues: list[str] = []

    def clamp(value: int, what: str) -> int:
        clamped = min(max(value, 0), max_t)
        if clamped != value:
            issues.append(f"{what} clamped {value} -> {clamped}")
        return clamped

    sections = [
        section.model_copy(
            update={
                "start": clamp(section.start, f"section {i} ({section.type}) start"),
                "end": clamp(section.end, f"section {i} ({section.type}) end"),
            }
        )
        for i, section in enumerate(labels.sections)
    ]
    sections.sort(key=lambda section: section.start)

    if not sections:
        issues.append("no sections returned")
    for section in sections:
        if section.end <= section.start:
            issues.append(f"{section.type} {section.start}-{section.end}: end <= start")
    for before, after in zip(sections, sections[1:]):
        if after.start < before.end:
            issues.append(
                f"overlap: {before.type} {before.start}-{before.end} and "
                f"{after.type} {after.start}-{after.end}"
            )
        elif after.start - before.end > _MAX_GAP_S:
            issues.append(f"gap: {before.end}-{after.start} not covered by any section")
    if sections:
        if sections[0].start > _MAX_GAP_S:
            issues.append(f"gap: 0-{sections[0].start} not covered by any section")
        if max_t - sections[-1].end > _MAX_GAP_S:
            issues.append(f"gap: {sections[-1].end}-{max_t} not covered by any section")

    hook = labels.hook.model_copy(
        update={
            "start": clamp(labels.hook.start, "hook start"),
            "end": clamp(labels.hook.end, "hook end"),
        }
    )
    if hook.end <= hook.start:
        issues.append(f"hook {hook.start}-{hook.end}: end <= start")
    if not any(
        s.type == "chorus_or_hook" and s.start <= hook.start and hook.end <= s.end for s in sections
    ):
        issues.append(f"hook {hook.start}-{hook.end} is not inside any chorus_or_hook section")

    return labels.model_copy(update={"sections": sections, "hook": hook}), issues
