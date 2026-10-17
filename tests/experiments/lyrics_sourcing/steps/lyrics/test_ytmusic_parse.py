import json
from pathlib import Path

from experiments.lyrics_sourcing.steps.lyrics.ytmusic import parse_ytmusic_lyrics

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_timed_payload_maps_to_synced_seconds():
    payload = json.loads((FIXTURES / "ytmusic_timed.json").read_text())
    candidate = parse_ytmusic_lyrics(payload, "MPLYt_x")
    assert candidate.status == "synced"
    assert candidate.source_ref == "MPLYt_x"
    assert [(ln.start, ln.end, ln.text) for ln in candidate.lines] == [
        (12.34, 15.8, "Abhi toh party shuru hui hai"),
        (15.8, 19.0, "Abhi toh raat baaki hai"),
    ]


def test_plain_payload_is_plain_only():
    payload = {"lyrics": "line one\nline two", "hasTimestamps": False, "source": "x"}
    candidate = parse_ytmusic_lyrics(payload, "b")
    assert candidate.status == "plain_only"
    assert candidate.plain_text == "line one\nline two"


def test_missing_payload_is_not_found():
    assert parse_ytmusic_lyrics(None, None).status == "not_found"
    assert parse_ytmusic_lyrics({"lyrics": None}, "b").status == "not_found"


def test_objects_with_attributes_work_like_dicts():
    class Line:
        def __init__(self, text, start_time, end_time):
            self.text, self.start_time, self.end_time = text, start_time, end_time

    payload = {"lyrics": [Line("a b c", 1000, 2000)], "hasTimestamps": True}
    assert parse_ytmusic_lyrics(payload, "b").lines[0].start == 1.0
