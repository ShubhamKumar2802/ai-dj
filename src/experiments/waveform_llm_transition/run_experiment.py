"""CLI for the waveform_llm_transition experiment (openspec change: waveform-llm-transition).

    uv run --group experiments python src/experiments/waveform_llm_transition/run_experiment.py \\
        [--config PATH]

For each configured pair: cached features -> 3-band waveform tiles -> one LLM call ->
validate -> hard-cut preview WAV -> score against ground_truth.yaml. Pairs run
independently; a failing pair is reported and the rest still run. Writes
outputs/<pair_id>/{tiles/*.png, request.json, answer.json, preview.wav} and outputs/summary.md.

Features and LLM answers are cached, so re-running after filling in ground_truth.yaml only
redraws, re-renders and re-scores. Uses the repo's llm_service config (config.yaml) unless
this experiment's config sets `llm.model`; the model must accept images.
"""

import argparse
import json
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SRC.parent
# Replace the script's own directory (sys.path[0]) with src/: this folder holds modules
# named config.py / schema.py that must never shadow anything as top-level imports.
sys.path[0] = str(_SRC)

from common.llm_service import get_llm_service  # noqa: E402
from common.llm_service.factory import load_config as load_llm_config  # noqa: E402
from experiments.waveform_llm_transition.bands import (  # noqa: E402
    normalise_pair,
    track_envelopes,
)
from experiments.waveform_llm_transition.bars import (  # noqa: E402
    bar_start,
    check_disagreement,
    range_error,
)
from experiments.waveform_llm_transition.config import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    ExperimentConfig,
    PairConfig,
    TrackConfig,
    load_config,
)
from experiments.waveform_llm_transition.preview import (  # noqa: E402
    render_preview,
    write_preview,
)
from experiments.waveform_llm_transition.prompt import build_request  # noqa: E402
from experiments.waveform_llm_transition.report import write_summary  # noqa: E402
from experiments.waveform_llm_transition.schema import (  # noqa: E402
    PairResult,
    TrackFacts,
    TransitionAnswer,
)
from experiments.waveform_llm_transition.scoring import (  # noqa: E402
    GroundTruthEntry,
    load_ground_truth,
    score_pair,
)
from experiments.waveform_llm_transition.tiles import draw_tile, tile_windows  # noqa: E402
from ingestion.feature_extractor.cache import get_or_extract_features  # noqa: E402
from ingestion.feature_extractor.config import FeatureExtractorConfig  # noqa: E402
from ingestion.feature_extractor.loader import load_canonical  # noqa: E402


def _facts(label: str, track: TrackConfig) -> TrackFacts:
    raw = get_or_extract_features(track.path, FeatureExtractorConfig())
    return TrackFacts(
        label=label,
        name=track.name,
        path=track.path,
        duration=raw.duration,
        bpm=raw.bpm,
        lufs=raw.lufs_integrated,
        downbeats=list(raw.downbeat_times),
        downbeat_confidence=raw.downbeat_confidence,
    )


def run_pair(
    pair: PairConfig, cfg: ExperimentConfig, ground_truth: dict[str, GroundTruthEntry], log
) -> tuple[PairResult, str | None]:
    """Returns the pair's result and the prompt version used (None if it never got that far)."""
    result = PairResult(pair_id=pair.pair_id)
    out_dir = Path(cfg.outputs_dir) / pair.pair_id

    missing = pair.missing_paths()
    if missing:
        result.failure = "audio file not found: " + "; ".join(missing)
        return result, None

    log("features")
    result.a, result.b = _facts("A", pair.a), _facts("B", pair.b)
    for facts in (result.a, result.b):
        if len(facts.downbeats) < 2:
            result.failure = f"track {facts.label} has fewer than 2 detected downbeats"
            return result, None

    log("waveforms")
    pcm_a, pcm_b = load_canonical(pair.a.path), load_canonical(pair.b.path)
    band_args = (cfg.tiles.px_per_s, cfg.bands.low_hz, cfg.bands.high_hz, cfg.bands.filter_order)
    env_a, env_b = normalise_pair(
        track_envelopes(
            pcm_a.samples, pcm_a.sample_rate, *band_args,
            bpm=result.a.bpm, smooth_beats=cfg.bands.smooth_beats,
        ),
        track_envelopes(
            pcm_b.samples, pcm_b.sample_rate, *band_args,
            bpm=result.b.bpm, smooth_beats=cfg.bands.smooth_beats,
        ),
        cfg.bands.range_db,
    )
    tiles = {}
    for facts, env in ((result.a, env_a), (result.b, env_b)):
        tiles[facts.label] = [
            (
                window,
                draw_tile(
                    env, facts, window, cfg.tiles.tile_s, cfg.tiles.height_px,
                    out_dir / "tiles" / f"{facts.label}_{window.index:02d}.png",
                ),
            )
            for window in tile_windows(facts.duration, cfg.tiles.tile_s, cfg.tiles.overlap_s)
        ]

    log(f"llm ({len(tiles['A']) + len(tiles['B'])} images)")
    request = build_request(
        result.a, result.b, tiles["A"], tiles["B"], cfg.bands, cfg.tiles, cfg.llm
    )
    (out_dir / "request.json").write_text(
        json.dumps(
            {
                "prompt": request.prompt,
                "prompt_version": request.prompt_version,
                "model": request.model,
                "images": [str(path) for _, path in tiles["A"] + tiles["B"]],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    try:
        answer = get_llm_service().generate(request, TransitionAnswer)
    except Exception as exc:  # provider/validation errors of every shape: report, don't crash
        result.failure = f"LLM call failed: {type(exc).__name__}: {exc}"
        return result, request.prompt_version
    result.answer = answer
    (out_dir / "answer.json").write_text(answer.model_dump_json(indent=2))

    errors = [
        e
        for e in (
            range_error("exit", result.a.downbeats, answer.exit_bar_a),
            range_error("entry", result.b.downbeats, answer.entry_bar_b),
        )
        if e
    ]
    if errors:
        result.failure = "; ".join(errors)
        return result, request.prompt_version

    result.exit_time = bar_start(result.a.downbeats, answer.exit_bar_a)
    result.entry_time = bar_start(result.b.downbeats, answer.entry_bar_b)
    result.disagreements = [
        d
        for d in (
            check_disagreement("exit_a", result.a.downbeats, answer.exit_bar_a,
                               answer.exit_time_a),
            check_disagreement("entry_b", result.b.downbeats, answer.entry_bar_b,
                               answer.entry_time_b),
        )
        if d
    ]

    log("preview")
    audio = render_preview(
        pcm_a.samples, pcm_b.samples, pcm_a.sample_rate, result.exit_time, result.entry_time,
        cfg.preview.pre_s, cfg.preview.post_s, pair.a.track_id, pair.b.track_id, result.a.bpm,
    )
    result.preview_path = str(write_preview(audio, out_dir / "preview.wav"))

    result.score = score_pair(
        ground_truth.get(pair.pair_id), result.a.downbeats, result.b.downbeats,
        answer.exit_bar_a, answer.entry_bar_b,
    )
    return result, request.prompt_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="config.yaml path")
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    os.chdir(_REPO_ROOT)  # every relative path in config.yaml is repo-root-relative
    cfg = load_config(config_path)
    ground_truth = load_ground_truth(cfg.ground_truth)

    results, prompt_version = [], "-"
    for pair in cfg.pairs:
        print(f"\n=== {pair.a.name} -> {pair.b.name}  ({pair.pair_id})")
        try:
            result, version = run_pair(
                pair, cfg, ground_truth, lambda step: print(f"  [{step}]", flush=True)
            )
        except Exception as exc:  # one pair failing must not stop the others
            result, version = PairResult(pair_id=pair.pair_id), None
            result.failure = f"{type(exc).__name__}: {exc}"
        prompt_version = version or prompt_version
        results.append(result)
        if result.ok:
            print(f"  exit A bar {result.answer.exit_bar_a}, entry B bar "
                  f"{result.answer.entry_bar_b} -> {result.preview_path}")
        else:
            print(f"  FAILED: {result.failure}")

    model = cfg.llm.model or load_llm_config().model
    summary = write_summary(results, model, prompt_version, Path(cfg.outputs_dir) / "summary.md")
    print(f"\nsummary: {summary}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
