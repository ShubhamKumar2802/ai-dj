# Module overview

A snapshot of module coverage against `resources/ai-dj-design-v3.md`'s architecture
(§4) and build order (§10) — **not** auto-generated, so it can drift; re-check
against the design doc before trusting it, especially the `Spec`/`Code` columns.
Update this table as each module's spec or implementation lands.

Last checked: 2026-08-23.

## Build order

| Step | Module | design-v3 ref | Spec | Code |
|---|---|---|---|---|
| — | `acquisition/youtube_downloader` (new layer, upstream of `ingestion/` — not part of design-v3's original build order; produces the local paths `ingestion/orchestrator` consumes as input) | — (not in design-v3) | Done | Done |
| 0 | Walking skeleton milestone — exercises Milestone A of `render/transition_renderer` (#6) + `render/playlist_renderer` (#7) below | §10 | Done | — |
| 1 | `ingestion/feature_extractor` | D6, D25 | Done | Done |
| 2 | Per-bar feature stack (folded into `feature_extractor` §7 — not its own module) | §6.3 step 1 | Done (part of #1) | Done (part of #1) |
| 3 | `ingestion/cue_derivation` | D8/D9/D22/D27 | Done | Done |
| — | `ingestion/orchestrator` (glue implied by §4's `RawFeatures → Track[]` arrow; no design-v3 step number — sits between #3 and #4) | §4 | Done | Done |
| 4 | `processing/edge_builder` | D4/D5/D19 | Done | Done (need to test with real tracks using example script after YT downloader module is implemented) |
| 5 | `processing/path_search` | D3/D21 | — | — |
| 6 | `render/transition_renderer` (Milestone A done; Milestone B — tiers 2/4/5, LUFS, tempo lock — documented, not built) | D17 | Done | — |
| 7 | `render/playlist_renderer` (Milestone A done; Milestone B — MP3, CUE sheet, segment caching — documented, not built) | D17 | Done | — |
| 8 | `ingestion/familiarity_scorer` (calls `llm_service` with `FamiliarityRequest`/`FamiliarityScore`, writes `Track.familiarity_score`/`.era`/`.is_club_edit`) | §6.1 | — | — |

## Infrastructure (`common/`, built ahead of build order — cross-cutting, no step number of its own)

| Module | Spec | Code |
|---|---|---|
| `common/llm_service` | Done | Done |
| `common/logging` | Done | Done |

## Deliberately not counted as gaps

Real design-v3 concepts, but not v1 modules — don't re-flag these as missing without
re-checking the doc first:

- Grid-confidence calibration model (§6.5) — explicitly v2.
- Template-constrained decoding / SSM repetition / section labelling (§6.3 Steps 2-3) — v2.
- Tempo ramping (D18) — "v1 status: not needed."
- Natural-language mix-config parsing (§6.1) — "interface sugar," deferred.
- Junction-preview / eval harness (§9) — a dev tool that falls out of D17's
  testability property for free, not a pipeline module.
