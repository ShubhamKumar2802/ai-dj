"""CLI for the lyrics_sourcing experiment (spec §6).

    uv run --group experiments python src/experiments/lyrics_sourcing/run_experiment.py \\
        <youtube-url> [<youtube-url> ...] [--config PATH] [--from-step STEP] [--refetch]

Needs a running Ollama server for the last step, started with the repo's model dir and a
large enough context window (see the spec §2):

    OLLAMA_MODELS="$PWD/models/ollama" OLLAMA_CONTEXT_LENGTH=16384 ollama serve
"""

import argparse
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SRC.parent
# Replace the script's own directory (sys.path[0]) with src/: this folder holds modules
# named config.py / schema.py that must never shadow anything as top-level imports.
sys.path[0] = str(_SRC)

from experiments.lyrics_sourcing.config import DEFAULT_CONFIG_PATH, load_config  # noqa: E402
from experiments.lyrics_sourcing.pipeline import STEPS, run  # noqa: E402
from experiments.lyrics_sourcing.schema import StepError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("urls", nargs="+", help="YouTube video URL(s)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="config.yaml path")
    parser.add_argument("--from-step", choices=STEPS, help="reload earlier steps from outputs/")
    parser.add_argument("--refetch", action="store_true", help="bypass the lyrics fetch cache")
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    os.chdir(_REPO_ROOT)  # every relative path in config.yaml is repo-root-relative
    cfg = load_config(config_path)

    failed = 0
    for url in args.urls:
        print(f"\n=== {url}")
        try:
            summary = run(
                url,
                cfg,
                from_step=args.from_step,
                refetch=args.refetch,
                on_step=lambda step, status: print(f"  [{step}] {status}", flush=True),
            )
        except StepError as exc:
            failed += 1
            print(f"  FAILED at step '{exc.step}': {exc.message}")
            continue
        print(f"  outputs: {Path(cfg.outputs_dir) / summary.video_id}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
