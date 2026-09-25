# Planning Stage

Part of [resources/documentation/pipeline/](00_pipeline_map.md). Covers the cheap,
metadata-only half of the pipeline (design-v3 **D6**) — everything that runs in
milliseconds, is safe to re-run constantly while tuning, and never touches audio or a
model.

Precise field lists, formulas, and defaults live in each module's own `spec.md`, linked
below. This file gives the mental model, not the contract.

---

## 0. Stage boundary

Two invariants bound this entire stage:

- **D2 — metadata-only.** Every Planning component must be testable from small JSON
  fixtures, no audio. If a Planning component ever needs to peek at a waveform, the
  design has broken.
- **D14 — no model in the planner.** Planning is a scoring function over metadata with
  tunable weights — interpretable, unit-testable, deterministic. Nothing here ever calls
  an LLM or any other model, and nothing here ever will, no matter what new Analysis-stage
  signals get added upstream. This is `common/llm_service`'s own stated boundary, one
  layer earlier: "nothing downstream — cue derivation, edge builder, path search, either
  renderer — ever calls an LLM or knows one exists." It's why [04](04_transcription.md)
  and [05](05_song_structure.md)'s model calls both happen in Analysis, once per track,
  producing plain JSON fields by the time Planning ever sees them.

---

## 1. Stage map

```
Track[]
    │
    ▼  processing/edge_builder
ScoredEdges   (argmin junction plan per viable pair — every strategy tier scored
               together, cheapest wins; D4)
    │
    ▼  processing/path_search
MixPlan       (beam search over K-of-N subset+order)
```

---

## 2. The soft-cost philosophy

**D10** is the load-bearing rule for this whole stage: every soft musical constraint —
tempo match, key (Camelot) compatibility, vocal density, phrase alignment — is a weighted
*cost term*, never a hard gate. The reasoning is specific to this project's material, not
generic caution: with a modest candidate pool and MIR estimates that are unreliable on
Bollywood/raga-influenced material, a strict gate can leave the search with no legal
successor at all — and the failure is invisible (a shorter mix, not an error).

This was tested directly, not just argued for. A confidence-shrinkage mechanism backs
every soft term further: when the underlying measurement is uncertain (low `bpm_confidence`
or `key_confidence`), the term is pulled toward a neutral `0.5` rather than trusted at face
value — treating "unmeasurable" as "unknown," never as "perfect."

There is exactly **one** tier-level hard rule in the entire Planning stage: tier 2
(beat-locked bass-swap) is ineligible for a pair whenever `|bpm_a − bpm_b| / bpm_a` exceeds
3% (design-v3 **D19**) — because tier 2 is the one strategy that actually overlaps two
tracks bar-for-bar, so a real tempo mismatch there is audible, not masked. Tiers 3, 4, and
5 carry no eligibility gate at all; tier 3 (cut-on-the-1) in particular has **no tempo
constraint whatsoever**, by design — a hard cut has no overlap window for a mismatch to be
heard in.

---

## 3. `processing/edge_builder`

For every ordered track pair with a viable junction, computes the argmin over
`(cue_out candidate) × (cue_in candidate) × (strategy tier)` and stores the winning
`Junction` plus its scalar cost. The cost is a weighted sum — tempo distance, key
(Camelot) distance, energy delta, vocal-zone penalty, cue-kind preference, phrase-boundary
proximity, plus a template-conditioned tier penalty — with every term normalized to
`[0,1]` so the weights are interpretable as relative importance (**D26**). Transition-type
selection happens *inside* this step, not after path search, precisely so the tier
penalty can influence which pairings get chosen in the first place.

The five strategy tiers, best to worst (CLAUDE.md's fallback ladder): bass-swap at a
detected section boundary → bass-swap at the nearest confident downbeat → cut-on-the-1 →
echo-out → filter-fade. Tier 1 needs structure/vocal-activity detection this repo doesn't
have yet (not implemented in v1). Cut-on-the-1 (tier 3) is the workhorse; a full crossfade
was deliberately excluded from the ladder entirely as the worst failure mode for this
format.

Full detail: [spec](../processing/edge_builder/spec.md).

---

## 4. `processing/path_search`

Picks the actual sequence: a minimum-cost path through K of N tracks. This is explicitly
**the orienteering problem** — "pick the best subset, don't visit all" — not Dijkstra (no
target node, and no-repeats makes the state exponential) and not a BPM sort. Solved with
beam search: the top ~50 partial sequences are extended, rescored, and pruned at each
step, because a greedy approach handles the path-level objective terms badly.

The objective adds path-level terms on top of `edge_builder`'s pairwise costs:

```
total = Σ edge_costs + λ·arc_deviation + μ·diversity_penalty + ν·familiarity_deficit + β·boundary_cost
```

**Energy arc is scored across the whole path, not decomposed into pairwise edge costs** —
this is the one term that structurally cannot live in `edge_builder`, because judging
"does this track's energy fit where it sits in the overall build/peak/wind-down shape"
requires seeing the whole sequence, not just one pair. `diversity_penalty` and
`familiarity_deficit` are similar path-level judgments. `familiarity_deficit` is currently
**inert** — every `Track.familiarity_score` is `None` until the not-yet-built
`ingestion/familiarity_scorer` (build-order step 8, blocked on nothing technical, just not
built yet) populates it via `common/llm_service`.

Full detail: [spec](../processing/path_search/spec.md).

---

## 5. Known gaps today

Tier 2 is effectively unreachable on the real corpus: eligible on only 0.3% of ordered
pairs, and it won **zero** of 3,477 real edges scored in a measured run. Two causes stack:
`feature_extractor`'s T1 defect quarantines 75% of the library into `cut_only` (which
removes tier 2 from consideration on either side), and even where tier 2 is legal, the
current film tier-penalty table (correctly, by design) still prices tier 3 cheaper for
film-idiom material. See `overview.md`'s **T1**/**T5**/**Q10** entries for the live status.

---

## 6. Where new signals plug in

- **`familiarity_scorer`** (build-order step 8) will populate the currently-inert `ν` term
  above — a data change, not a code change, per `path_search`'s own design.
- **[05_song_structure.md](05_song_structure.md)'s `sections[]`/`transition_points[]`**
  would eventually give `edge_builder`/`path_search` richer signal than today's two-cue-kind
  proxy (e.g. scoring a junction against a real `chorus_or_hook` section instead of the
  `hook_exit` heuristic). This is **future work** — this pipeline folder documents the new
  Analysis-stage modules that would produce that signal, not a redesign of how Planning
  consumes it.

---

## 7. Considered and rejected: hard-gating Camelot/BPM

A recurring question during this pipeline's design was whether Camelot key and BPM
compatibility should be a hard pre-filter on which track pairs are even considered,
rather than a soft cost — the classic club-DJ harmonic-mixing rule. The conclusion,
reached against this project's own D10 rationale and its own measured data (§5 above,
Q10): **no.** A hard gate reintroduces exactly the failure mode D10 was written to avoid,
and this project already has a concrete example of a gate emptying the option pool (tier
2's narrow BPM eligibility rule, which — being an actual hard rule, unlike the fully soft
key/tempo cost terms — is the reason tier 2 is nearly unreachable today). Nothing about
`edge_builder`'s existing design needs to change.

This question was tested directly, not just argued — [06_experiments_sandbox.md](06_experiments_sandbox.md)
documents a sandboxed experiment that deliberately hard-gates Camelot key to see what
happens, exactly to check this conclusion against real behavior rather than intuition
alone.
