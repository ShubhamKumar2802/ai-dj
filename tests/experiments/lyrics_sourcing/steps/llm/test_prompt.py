import re

from experiments.lyrics_sourcing.schema import Timeline, TimelineHeader
from experiments.lyrics_sourcing.steps.llm.llm_service_labeler import render_prompt


def _timeline() -> Timeline:
    header = TimelineHeader(
        title="T", artist=None, video_id="v", duration=187.6, bpm=None, bpm_confidence=None,
        key=None, key_confidence=None, lufs_integrated=None, true_peak=None,
        structure_template=None, grid_start=None, phrase_length_bars=None, cue_status=None,
        lyrics_source=None, lyrics_verdict=None, lyrics_offset_s=None,
    )  # fmt: skip
    return Timeline(header=header, rows=[], lyrics=[])


def test_prompt_renders_with_version_and_no_unfilled_placeholders():
    serialized = "timeline[1]{t,bar}:\n  0,\n"  # braces in the payload must survive untouched
    prompt, version = render_prompt(_timeline(), serialized, "toon")
    assert version == "1"
    assert not prompt.startswith("# prompt_version")
    assert "from second 0 to second 187" in prompt
    assert "Song duration: 187.6 seconds." in prompt
    assert "in TOON format" in prompt
    assert serialized.strip() in prompt
    without_payload = prompt.replace(serialized.strip(), "")
    assert not re.search(r"\{[a-z_]+\}", without_payload)
