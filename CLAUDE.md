# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is a bare `uv`-scaffolded Python project (`main.py`, `pyproject.toml`, `.python-version`, empty `README.md`). No source code, dependencies, or tests have been written yet — `src/` is empty and `main.py` only contains a placeholder `Hello from ai-dj!` entry point. Treat the architecture below as the intended design, not yet-implemented code.

The full design rationale lives in `resources/ai-dj-domain-and-architecture.md` — read it before implementing any ingestion/processing/export module; this section is a condensed pointer, not a replacement. `resources/architecture_diagram.drawio` has the same pipeline as a diagram.

## Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management (Python >=3.11, pinned to 3.11 via `.python-version`).

- Run the app: `uv run main.py`
- Add a dependency: `uv add <package>`
- Add a dev dependency: `uv add --dev <package>`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`

Source lives under `src/`; tests live under `tests/`, mirroring `src/`'s package structure (see `tests/README.md`).

## Development workflow: spec-driven

This project is spec-driven. Before implementing any module, write or update its spec under `resources/documentation/` (sub-folders per component/layer, added as needed — see `resources/documentation/README.md`). The spec is the single source of truth: code implements the spec, not the reverse.

- No implementation without a spec to implement.
- If behavior needs to change — whether the change is decided before coding or discovered during/after implementation (code review, bug fix, design rethink) — edit the spec first, then bring the code in line. Never let code and spec drift silently.

Naming, storage, and amendment/versioning rules: see `resources/documentation/README.md`, or invoke the `write-spec` skill.

## Intended architecture

AI DJ Mixer: given a set of tracks, produce a single continuous **hook-cut megamix** (reference: ~15 tracks in ~17 minutes, not a long-blend club set). Three stages, split by iteration cost rather than by concept:

1. **Analysis** (audio in, expensive, cached per track) — feature extractor (beats, downbeats, chroma, LUFS) → cue derivation (phrase grid, cue-in/cue-out points, confidence/`status` quarantine).
2. **Planning** (metadata only, milliseconds, run constantly) — edge builder scores every track pair across cue-point combinations and transition-strategy tiers, storing the argmin junction plan per edge; path search (beam search over partial sequences — this is an **orienteering problem**, not Dijkstra and not a BPM sort) picks the min-cost subset+order, producing a `MixPlan`.
3. **Render** (audio + plan in, deterministic) — dumb executor: applies envelopes, gain (LUFS), and time-stretch. Decides nothing. Needs direct PCM access (the "audio bypass" line), not just the plan.

Diagram: track list → analysis (metadata + cue points) → planning (edge scoring + beam search → `MixPlan`) → render → DJ-mixed playlist track + junction preview clips.

### Design invariants (violate these and the architecture breaks)

- **Metadata-only planning invariant** — anything in the planning stage must be testable with small JSON fixtures, no audio. The moment a planning component needs to peek at a waveform, the design has broken.
- **Transition type selection lives inside edge construction**, not after path search — otherwise the tier penalty can't influence which pairings get chosen.
- **Strategy tier is a cost, not a fallback** — a per-tier penalty on the edge cost, not an if-stuck branch. Fallback ladder (best→worst): bass-swap at section boundary → bass-swap at nearest downbeat → cut-on-the-1 → echo-out → filter-fade. Cut-on-the-1 is the workhorse; full crossfade is deliberately excluded (worst failure mode).
- **Key/BPM/confidence are soft, nullable scores, never hard gates** — MIR estimates (especially on Bollywood/raga-influenced material) are unreliable; a hard gate can dead-end the search.
- **Cache key is `(content_hash, feature_extractor_version)`**, not filename — swapping beat trackers must invalidate stale metadata automatically.
- **Energy arc is a property of the whole path**, not decomposable into pairwise edge costs — factor into the path-search objective (`total = Σ edge_costs + λ·arc_deviation + μ·diversity_penalty`), not per-edge.

### Data contracts (define before any DSP code)

`Track`: id/path/duration, bpm+confidence, beat/downbeat times, phrase grid, key+confidence (nullable), LUFS, energy curve, `cue_ins[]`/`cue_outs[]` (position/kind/confidence), analysis_version, status.

`MixPlan`: tracks[], junctions[] (from/to, cue_out, cue_in, strategy_tier, length_bars, gain per side, automation envelopes).

Full field lists and an example bass-swap junction are in `resources/ai-dj-domain-and-architecture.md` §4.

### Build order

Walking skeleton first: two hard-coded tracks, cue points found by ear in Mixxx and typed into JSON, one hard cut, one rendered WAV — no analysis, no search. Then: feature extractor + cache → cue derivation → edge builder → beam search → renderer upgrades (bass-swap envelopes, LUFS, time-stretch). See §7 of the domain doc for the full rationale.
