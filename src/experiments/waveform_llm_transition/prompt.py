"""The one LLM request per pair: both tracks' tiles plus their measured facts.

Only duration, BPM, integrated LUFS and the bar grid (drawn on the images) reach the LLM —
never the key, phrase grid or any cue/hook estimate (spec: "What the LLM is given").
"""

import base64
from pathlib import Path

from common.llm_service import ImageInput, MultimodalRequest
from common.llm_service.prompt_manager import PromptManager
from experiments.waveform_llm_transition.bars import format_mmss
from experiments.waveform_llm_transition.config import BandsConfig, LlmConfig, TilesConfig
from experiments.waveform_llm_transition.schema import TrackFacts
from experiments.waveform_llm_transition.tiles import TileWindow

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
TEMPLATE_NAME = "waveform_transition_v6.txt"

Tile = tuple[TileWindow, Path]


def track_facts_text(facts: TrackFacts) -> str:
    return (
        f"Track {facts.label}: {facts.name} — duration {format_mmss(facts.duration)}, "
        f"{facts.bpm:.1f} BPM, {facts.lufs:.1f} LUFS integrated, "
        f"{len(facts.downbeats)} bars (numbered 1–{len(facts.downbeats)})."
    )


def image_list_text(tiles_a: list[Tile], tiles_b: list[Tile]) -> str:
    lines = []
    for number, (label, (window, _)) in enumerate(
        [("A", t) for t in tiles_a] + [("B", t) for t in tiles_b], start=1
    ):
        lines.append(f"Image {number}: {label} {window.label}")
    return "\n".join(lines)


def build_request(
    a: TrackFacts,
    b: TrackFacts,
    tiles_a: list[Tile],
    tiles_b: list[Tile],
    bands: BandsConfig,
    tiles: TilesConfig,
    llm: LlmConfig,
    prompt_manager: PromptManager | None = None,
) -> MultimodalRequest:
    """A's tiles first, then B's, each in time order — the order `image_list` describes."""
    prompt_manager = prompt_manager or PromptManager(PROMPTS_DIR)
    prompt, version = prompt_manager.render(
        TEMPLATE_NAME,
        tile_s=tiles.tile_s,
        overlap_s=tiles.overlap_s,
        low_hz=bands.low_hz,
        high_hz=bands.high_hz,
        range_db=bands.range_db,
        smooth_beats=bands.smooth_beats,
        track_a_facts=track_facts_text(a),
        track_b_facts=track_facts_text(b),
        image_list=image_list_text(tiles_a, tiles_b),
    )
    images = [
        ImageInput(
            source="base64",
            data=base64.b64encode(path.read_bytes()).decode("ascii"),
            mime_type="image/png",
        )
        for _, path in tiles_a + tiles_b
    ]
    return MultimodalRequest(
        prompt=prompt,
        images=images,
        model=llm.model,
        temperature=llm.temperature,
        max_tokens=llm.max_tokens,
        prompt_version=version,
        timeout_s=llm.timeout_s,
        metadata={"consumer": "waveform_llm_transition"},
    )
