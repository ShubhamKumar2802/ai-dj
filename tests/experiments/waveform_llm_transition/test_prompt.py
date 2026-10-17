import base64

from experiments.waveform_llm_transition.config import load_config
from experiments.waveform_llm_transition.prompt import build_request
from experiments.waveform_llm_transition.schema import TrackFacts
from experiments.waveform_llm_transition.tiles import tile_windows


def _facts(label, name, duration, bpm, lufs) -> TrackFacts:
    return TrackFacts(
        label=label,
        name=name,
        path=f"{name}.mp3",
        duration=duration,
        bpm=bpm,
        lufs=lufs,
        downbeats=[0.5 + i * 240 / bpm for i in range(int(duration * bpm / 240))],
        downbeat_confidence=0.6,
    )


def _tiles(tmp_path, label, duration):
    tiles = []
    for w in tile_windows(duration, 60, 8):
        path = tmp_path / f"{label}_{w.index}.png"
        path.write_bytes(f"{label}{w.index}".encode())  # stand-in bytes, identifiable per tile
        tiles.append((w, path))
    return tiles


def _request(tmp_path, max_tokens=32768):
    cfg = load_config()
    cfg.llm.max_tokens = max_tokens
    a = _facts("A", "Rock Tha Party", 207.9, 110.1, -9.6)
    b = _facts("B", "Marjaani", 243.0, 112.5, -11.2)
    request = build_request(
        a, b, _tiles(tmp_path, "A", 207.9), _tiles(tmp_path, "B", 243.0),
        cfg.bands, cfg.tiles, cfg.llm,
    )
    return request


def test_all_tiles_in_order_a_then_b(tmp_path):
    request = _request(tmp_path)
    decoded = [base64.b64decode(img.data).decode() for img in request.images]
    assert decoded == ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "B5"]
    assert "Image 1: A tile 1/4 (0:00–1:00)" in request.prompt
    assert "Image 5: B tile 1/5 (0:00–1:00)" in request.prompt


def test_facts_for_both_tracks(tmp_path):
    prompt = _request(tmp_path).prompt
    for part in ("Rock Tha Party", "3:27", "110.1 BPM", "-9.6 LUFS",
                 "Marjaani", "4:03", "112.5 BPM", "-11.2 LUFS"):
        assert part in prompt


def test_no_key_or_cue_values(tmp_path):
    prompt = _request(tmp_path).prompt.lower()
    for forbidden in ("camelot", "key:", "cue", "hook", "phrase grid", "5a", "11b"):
        assert forbidden not in prompt


def test_megamix_framing(tmp_path):
    prompt = _request(tmp_path).prompt.lower()
    assert "megamix" in prompt
    assert "short excerpt of each song" in prompt


def test_exit_entry_and_notes_rules(tmp_path):
    prompt = _request(tmp_path).prompt
    assert "Leave A at the FIRST point where its opening full-energy section ends" in prompt
    assert "Check the 16 bars after your entry point in B" in prompt
    assert "go through every tile of the track in order and list every visible change" in prompt
    assert "comes back two or three times" in prompt


def test_section_changes_need_two_bars(tmp_path):
    prompt = _request(tmp_path).prompt
    assert "a breakdown, dip, drop or gap that lasts at least 2 bars" in prompt
    assert "Ignore any dip shorter than one bar" in prompt
    assert "after the beat is in that lasts at least 2 bars" in prompt
    assert "breaks down for 2 bars or more" in prompt


def test_request_carries_version_and_settings(tmp_path):
    request = _request(tmp_path)
    assert request.prompt_version == "waveform_transition_v6"
    assert request.temperature == 0.2
    assert request.model is None
    assert request.max_tokens == 32768
    assert request.timeout_s == 300


def test_lane_note_describes_shared_db_scale(tmp_path):
    prompt = _request(tmp_path).prompt
    assert "24 dB scale shared by both tracks" in prompt
    assert "averaged over 1 beat(s)" in prompt
    assert "drawn symmetrically about its centre line" in prompt


def test_null_max_tokens_leaves_it_unset(tmp_path):
    assert _request(tmp_path, max_tokens=None).max_tokens is None
