"""Experimental sequencer: LLM-labeled chorus boundaries + Camelot-wheel-
adjacency track ordering, bypassing edge_builder/path_search's cost-search
entirely (see camelot_order.py / mix_builder.py module docstrings). Tests
T8/Q7's hypothesis that hook_in/hook_exit's energy+vocal-threshold heuristic
is too crude a proxy for real song structure.

Deliberately standalone — not wired into the main pipeline, no formal spec,
matching this repo's own walking-skeleton / gold-set-build precedent for
this kind of exploratory test. Not part of the test suite: hits the real LLM
API (cached per track after the first run) and real audio.

Run from the repo root:
    uv run python src/experiments/llm_camelot_sequencer/run_experiment.py [music_dir]

With no argument, uses music/gold-set/.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from common.llm_service import get_llm_service  # noqa: E402
from experiments.llm_camelot_sequencer.camelot_order import order_by_camelot  # noqa: E402
from experiments.llm_camelot_sequencer.mix_builder import build_camelot_mix_plan  # noqa: E402
from experiments.llm_camelot_sequencer.structure_llm import (  # noqa: E402
    detect_structure_llm,
    validate_structure_labels,
)
from ingestion.feature_extractor.cache import get_or_extract_features  # noqa: E402
from ingestion.feature_extractor.config import FeatureExtractorConfig  # noqa: E402
from ingestion.feature_extractor.loader import load_canonical  # noqa: E402
from ingestion.orchestrator import IngestionConfig, ingest_tracks  # noqa: E402
from render.playlist_renderer import render_mix, write_wav  # noqa: E402
from render.transition_renderer.schema import StereoPCM  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MUSIC_DIR = _REPO_ROOT / "music" / "gold-set"
_OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
_MIN_PLAY_SECONDS = 8.0
# Gemini/Gemma free-tier quotas are per-minute (request count and/or input
# tokens); this is an unvalidated, deliberately generous guess at a pace that
# stays under them across a batch, not derived from any specific model's
# published limit.
_INTER_CALL_DELAY_S = 15.0


def _load_audio(path: str) -> StereoPCM:
    pcm = load_canonical(path)
    return StereoPCM(samples=pcm.samples.astype(np.float32), sample_rate=pcm.sample_rate)


def main() -> None:
    music_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_MUSIC_DIR
    paths = sorted(str(p) for p in music_dir.glob("*.mp3"))
    if len(paths) < 2:
        print(f"Need at least 2 tracks in {music_dir}. Got {len(paths)}.")
        return

    print(f"Ingesting {len(paths)} tracks from {music_dir}...")
    result = ingest_tracks(paths, IngestionConfig())
    print(f"{len(result.tracks)} ingested, {len(result.failures)} failed.")
    for failure in result.failures:
        print(f"  FAILED {failure.path}: {failure.error_type}: {failure.error}")

    llm_service = get_llm_service()
    fe_config = FeatureExtractorConfig()

    valid_tracks = []
    labels_by_id = {}
    for i, track in enumerate(result.tracks):
        if i > 0:
            # Free-tier quotas are per-minute (request count and/or input
            # tokens, depending on model) — a fixed pause between calls is a
            # blunt but reliable way to stay under them across a whole batch,
            # cheaper than tuning per-model/per-track-length. Retries inside
            # detect_structure_llm already handle a single transient 429/503;
            # this just makes hitting one less likely in the first place.
            time.sleep(_INTER_CALL_DELAY_S)

        name = Path(track.path).name[:55]
        try:
            # Cache hit: ingest_tracks() already ran extraction once per track
            # via the same (content_hash, extractor_version) key.
            raw = get_or_extract_features(track.path, fe_config)
            raw_labels = detect_structure_llm(raw, llm_service)
        except Exception as exc:
            # One track's persistent LLM failure (e.g. a rate limit that
            # outlasts the built-in retry) must not crash the whole batch —
            # same "one bad item never stops the run" convention as
            # ingestion.orchestrator's IngestionFailure handling.
            print(f"  FAILED    {name:55s}  {type(exc).__name__}: {exc}")
            continue

        validated = validate_structure_labels(raw_labels, track, min_play_seconds=_MIN_PLAY_SECONDS)
        if validated is None:
            print(f"  EXCLUDED  {name:55s}  raw LLM labels failed validation: {raw_labels}")
            continue
        valid_tracks.append(track)
        labels_by_id[track.id] = validated
        print(
            f"  OK        {name:55s}  key={track.key}  "
            f"intro_end={validated.intro_end:.1f}s  "
            f"chorus1=[{validated.chorus1_start:.1f}, {validated.chorus1_end:.1f}]s"
        )

    print(f"\n{len(valid_tracks)} / {len(result.tracks)} tracks survive LLM-label validation.")
    if len(valid_tracks) < 2:
        print("Need at least 2 valid tracks to build a chain.")
        return

    order = order_by_camelot(valid_tracks)
    print(f"\nCamelot chain: {len(order)} / {len(valid_tracks)} eligible tracks")
    if len(order) < len(valid_tracks):
        print(
            "  (no full free-move-only ordering exists through every track — longest chain found)"
        )
    if len(order) < 2:
        print("Camelot chain too short to render (need >= 2 tracks) — no two tracks are adjacent.")
        return

    tracks_by_id = {t.id: t for t in valid_tracks}
    for i, track_id in enumerate(order):
        t = tracks_by_id[track_id]
        prefix = "    " if i == 0 else " -> "
        print(f"{prefix}{Path(t.path).name[:60]:60s}  key={t.key}  bpm={t.bpm:.1f}")

    plan = build_camelot_mix_plan(order, tracks_by_id, labels_by_id)
    print(f"\nRendering {len(plan.tracks)}-track plan...")
    mix = render_mix(plan, _load_audio)

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    # Named after the input corpus — a fixed filename would silently overwrite
    # the previous run's WAV when pointed at a different music_dir.
    out_path = _OUTPUTS_DIR / f"llm_camelot_mix_{music_dir.name}.wav"
    write_wav(mix, str(out_path))

    duration_s = mix.samples.shape[0] / mix.sample_rate
    print(f"\nwrote {out_path}  {duration_s / 60:.2f} min")


if __name__ == "__main__":
    main()
