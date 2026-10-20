"""CLI for the vocal_free_windows experiment (openspec change: vocal-free-transition-windows).

    uv run --group experiments python src/experiments/vocal_free_windows/run_experiment.py \\
        [--config PATH] [--a PATH_A --b PATH_B]

One pair, A -> B (default: the adhoc pair in config.yaml). Cached features -> A's vocal
stem (cached) -> per-bar levels -> vocal-free windows -> exit at the first window starting
after `exit_after_bar` -> B entered at its intro (bar 1) -> three full-length outputs.
Writes outputs/<pair_id>/{A_vocal_lane.png, windows.json, transition_cut.wav,
transition_overlap.wav, transition_bass_swap.wav, summary.md}.

B is never separated. Stems are cached, so re-running after filling in ground_truth.yaml
only redoes the windows, renders and report.
"""

import argparse
import json
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SRC.parent
# Replace the script's own directory (sys.path[0]) with src/: this folder holds modules
# named config.py / windows.py that must never shadow anything as top-level imports.
sys.path[0] = str(_SRC)

from experiments.vocal_free_windows.bass_swap import (  # noqa: E402
    render_bass_swap,
    skip_reason,
)
from experiments.vocal_free_windows.config import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    ExperimentConfig,
    PairConfig,
    TrackConfig,
    load_config,
)
from experiments.vocal_free_windows.levels import bar_levels  # noqa: E402
from experiments.vocal_free_windows.mix import (  # noqa: E402
    SAMPLE_RATE,
    drift_ms,
    loudness_gain,
    peak_dbfs,
    render_cut,
    render_overlap,
    transition_span,
)
from experiments.vocal_free_windows.plot import draw_vocal_lane  # noqa: E402
from experiments.vocal_free_windows.report import (  # noqa: E402
    OutputInfo,
    RunResult,
    TrackInfo,
    load_ratings,
    write_summary,
)
from experiments.vocal_free_windows.stem_cache import get_or_separate  # noqa: E402
from experiments.vocal_free_windows.windows import (  # noqa: E402
    NoExitWindow,
    find_windows,
    pick_exit,
    threshold,
    to_db,
)
from ingestion.feature_extractor.cache import get_or_extract_features  # noqa: E402
from ingestion.feature_extractor.config import FeatureExtractorConfig  # noqa: E402
from ingestion.feature_extractor.loader import load_canonical  # noqa: E402
from render.playlist_renderer.writer import write_wav  # noqa: E402
from render.transition_renderer import StereoPCM  # noqa: E402


def _separate(config: ExperimentConfig):
    def separate(path: str):
        # Imported lazily: torch/demucs load only on a stem cache miss.
        from experiments.vocal_free_windows.separation import separate_file

        print("  [separating A's vocals]", flush=True)
        return separate_file(path, config.separator)

    return separate


def run_pair(pair: PairConfig, cfg: ExperimentConfig, step=print) -> tuple[RunResult, dict]:
    """Everything for one pair. Returns the result and the `windows.json` payload."""
    out_dir = Path(cfg.outputs_dir) / pair.pair_id

    step("features")
    raw_a = get_or_extract_features(pair.a.path, FeatureExtractorConfig())
    raw_b = get_or_extract_features(pair.b.path, FeatureExtractorConfig())
    result = RunResult(
        pair_id=pair.pair_id,
        a=TrackInfo(pair.a.name, pair.a.path, raw_a.bpm, raw_a.lufs_integrated),
        b=TrackInfo(pair.b.name, pair.b.path, raw_b.bpm, raw_b.lufs_integrated),
        exit_after_bar=cfg.exit_after_bar,
        overlap_bars=cfg.render.overlap_bars,
        bass_swap_bars=cfg.render.bass_swap_bars,
    )

    step("vocal stem (A)")
    sep = cfg.separator
    stem = get_or_separate(pair.a.path, sep.separator_version, sep.cache_dir, _separate(cfg))

    step("windows")
    w = cfg.windows
    levels = bar_levels(stem, SAMPLE_RATE, raw_a.per_bar_features)
    bar_times = [(bar.start_time, bar.end_time) for bar in raw_a.per_bar_features]
    result.cutoff_db = threshold(levels, w.threshold_db, w.floor_dbfs).cutoff_db
    result.windows = find_windows(levels, bar_times, w.threshold_db, w.floor_dbfs, w.min_bars)
    try:
        result.exit_window = pick_exit(result.windows, cfg.exit_after_bar, cfg.render.overlap_bars)
    except NoExitWindow as exc:
        result.failure = str(exc)

    exit_bar = result.exit_window.first_bar if result.exit_window else None
    result.image_path = str(draw_vocal_lane(
        out_dir / "A_vocal_lane.png", f"A: {pair.a.name} — vocal stem per bar", levels,
        bar_times, result.cutoff_db, result.windows, cfg.exit_after_bar, exit_bar,
    ))
    payload = {
        "pair_id": pair.pair_id,
        "a_levels_db": [round(float(v), 2) for v in to_db(levels)],
        "cutoff_db": result.cutoff_db,
        "windows": [win.to_dict() for win in result.windows],
        "exit_bar": exit_bar,
    }
    if result.failure:
        return result, payload

    step("render")
    exit_s = raw_a.downbeat_times[exit_bar - 1]
    result.entry_s = raw_b.downbeat_times[0]
    match = cfg.render.match_loudness
    gain = loudness_gain(raw_a.lufs_integrated, raw_b.lufs_integrated, match)
    result.gain_db = raw_a.lufs_integrated - raw_b.lufs_integrated if match else 0.0
    # The loader's StereoPCM -> the render layer's own StereoPCM type.
    pcm_a, pcm_b = load_canonical(pair.a.path), load_canonical(pair.b.path)
    a = StereoPCM(pcm_a.samples, pcm_a.sample_rate)
    b = StereoPCM((pcm_b.samples * gain).astype("float32"), pcm_b.sample_rate)

    overlap_s = transition_span(raw_a.downbeat_times, exit_bar, cfg.render.overlap_bars, raw_a.bpm)
    bass_bars = cfg.render.bass_swap_bars
    bass_s = transition_span(raw_a.downbeat_times, exit_bar, bass_bars, raw_a.bpm)
    swap_s = transition_span(raw_a.downbeat_times, exit_bar, bass_bars // 2, raw_a.bpm)
    result.drift_overlap_ms = drift_ms(overlap_s, raw_a.bpm, raw_b.bpm)
    result.drift_bass_swap_ms = drift_ms(bass_s, raw_a.bpm, raw_b.bpm)

    renders = {
        "cut": lambda: render_cut(a, b, exit_s, result.entry_s, raw_a.bpm),
        "overlap": lambda: render_overlap(a, b, exit_s, result.entry_s, overlap_s),
        "bass_swap": lambda: render_bass_swap(
            a, b, exit_s, result.entry_s, bass_s, swap_s, cfg.render.crossover_hz
        ),
    }
    skipped = {"bass_swap": skip_reason(raw_a.downbeat_times, exit_bar, bass_bars)}
    for kind, render in renders.items():
        if skipped.get(kind):
            result.outputs.append(OutputInfo(kind, skipped=skipped[kind]))
            continue
        audio = render()
        path = out_dir / f"transition_{kind}.wav"
        write_wav(audio, str(path))
        result.outputs.append(OutputInfo(kind, str(path), peak_dbfs(audio)))

    payload.update(
        exit_s=exit_s,
        entry_s=result.entry_s,
        gain_db=result.gain_db,
        overlap_s=overlap_s,
        bass_swap_s=bass_s,
        bass_swap_at_s=exit_s + swap_s,
    )
    return result, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="config.yaml path")
    parser.add_argument("--a", help="track A audio path (replaces the config's pair, with --b)")
    parser.add_argument("--b", help="track B audio path (replaces the config's pair, with --a)")
    args = parser.parse_args(argv)
    if (args.a is None) != (args.b is None):
        parser.error("--a and --b must be given together")

    config_path = Path(args.config).resolve()
    cli_paths = [str(Path(p).resolve()) for p in (args.a, args.b)] if args.a else None
    os.chdir(_REPO_ROOT)  # every relative path in config.yaml is repo-root-relative
    cfg = load_config(config_path)
    pair = cfg.pair
    if cli_paths:
        pair = PairConfig(
            a=TrackConfig(name=Path(cli_paths[0]).stem, path=cli_paths[0]),
            b=TrackConfig(name=Path(cli_paths[1]).stem, path=cli_paths[1]),
        )

    missing = pair.missing_paths()
    if missing:
        parser.error(f"audio file not found: {missing[0]}")

    print(f"=== {pair.a.name} -> {pair.b.name}  ({pair.pair_id})")
    result, payload = run_pair(pair, cfg, lambda s: print(f"  [{s}]", flush=True))

    out_dir = Path(cfg.outputs_dir) / pair.pair_id
    (out_dir / "windows.json").write_text(json.dumps(payload, indent=2))
    summary = write_summary(
        out_dir / "summary.md", result, load_ratings(cfg.ground_truth, pair.pair_id)
    )
    if result.failure:
        print(f"  FAILED: {result.failure}")
    else:
        print(f"  exit A bar {result.exit_window.first_bar}, entry B bar 1")
        for out in result.outputs:
            print(f"  {out.kind}: {out.path or 'skipped — ' + out.skipped}")
    print(f"summary: {summary}")
    return 1 if result.failure else 0


if __name__ == "__main__":
    sys.exit(main())
