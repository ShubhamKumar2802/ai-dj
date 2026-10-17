import json
from pathlib import Path

from experiments.lyrics_sourcing.steps.lyrics.lrclib import (
    clean_title,
    parse_lrclib_record,
    parse_lrclib_search,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _search():
    return json.loads((FIXTURES / "lrclib_search.json").read_text())


def test_search_keeps_only_synced_results_with_duration_recorded():
    candidates = parse_lrclib_search(_search(), max_candidates=3)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status == "synced"
    assert candidate.source_ref == "101"
    assert candidate.reference_duration == 172.0
    assert candidate.lines[0].text == "Abhi toh party shuru hui hai"


def test_search_without_synced_falls_back_to_plain_then_not_found():
    results = _search()[1:]
    assert [c.status for c in parse_lrclib_search(results, 3)] == ["plain_only"]
    assert [c.status for c in parse_lrclib_search([], 3)] == ["not_found"]


def test_max_candidates_caps_synced_results():
    record = _search()[0]
    assert len(parse_lrclib_search([record, record, record, record], 2)) == 2


def test_instrumental_record_is_not_found():
    candidate = parse_lrclib_record(_search()[2])
    assert candidate.status == "not_found"
    assert candidate.error == "instrumental"


def test_clean_title_strips_video_noise():
    raw = "'Abhi Toh Party Shuru Hui Hai' FULL VIDEO Song | Khoobsurat | Badshah, Aastha (HD)"
    assert clean_title(raw) == "Abhi Toh Party Shuru Hui Hai"
    assert clean_title("Kesariya - Official Video [4K]") == "Kesariya"
