from experiments.lyrics_sourcing.schema import HookWindow, LabeledSection, StructureLabels
from experiments.lyrics_sourcing.steps.llm.validate import validate


def _section(type_, start, end) -> LabeledSection:
    return LabeledSection(type=type_, start=start, end=end, confidence=0.8, evidence="e")


def _labels(sections, hook=(40, 60)) -> StructureLabels:
    return StructureLabels(
        sections=sections, hook=HookWindow(start=hook[0], end=hook[1], reason="r"), notes=""
    )


def test_well_formed_labels_have_no_issues():
    labels = _labels(
        [_section("intro", 0, 20), _section("verse", 20, 40), _section("chorus_or_hook", 40, 100)]
    )
    validated, issues = validate(labels, 100.4)
    assert issues == []
    assert validated == labels


def test_sorts_and_clamps_but_reports():
    labels = _labels(
        [_section("chorus_or_hook", 40, 130), _section("intro", 0, 40)], hook=(50, 120)
    )
    validated, issues = validate(labels, 100.0)
    assert [s.type for s in validated.sections] == ["intro", "chorus_or_hook"]
    assert validated.sections[1].end == 100
    assert validated.hook.end == 100
    assert any("section 0 (chorus_or_hook) end clamped 130 -> 100" in i for i in issues)
    assert any("hook end clamped" in i for i in issues)


def test_overlap_gap_and_inverted_are_reported_not_fixed():
    labels = _labels(
        [
            _section("intro", 5, 20),  # gap at the start
            _section("verse", 15, 30),  # overlaps intro
            _section("chorus_or_hook", 40, 35),  # inverted
        ],
        hook=(40, 60),
    )
    validated, issues = validate(labels, 100.0)
    assert validated.sections[1].start == 15  # untouched
    text = "\n".join(issues)
    assert "gap: 0-5" in text
    assert "overlap: intro 5-20 and verse 15-30" in text
    assert "chorus_or_hook 40-35: end <= start" in text
    assert "gap: 30-40" in text
    assert "hook 40-60 is not inside any chorus_or_hook section" in text


def test_empty_sections_reported():
    _, issues = validate(_labels([]), 100.0)
    assert "no sections returned" in issues
