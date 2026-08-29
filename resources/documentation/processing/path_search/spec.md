# Path Search — Spec

**Layer:** `processing/` — second module in this layer, downstream of `edge_builder`
and the last module in the planning stage.
**Depends on:** `resources/documentation/processing/edge_builder/spec.md` (**v2**)'s
`ScoredEdges` contract and the shared `Junction`/`Envelope` contract;
`resources/documentation/ingestion/orchestrator/spec.md`'s `Track` contract.

---

## 0. Invariant

> **This module never touches audio, and it is the last module that decides
> anything.** It is a pure function of `(Track[], ScoredEdges)` —
> `search_path(tracks, edges, config) -> PathSearchResult` — that chooses *which* K
> tracks, in *what* order. It never re-derives a cue, never re-scores a junction, and
> never re-picks a transition tier: `edge_builder` already stored the argmin (**D4**),
> and this module only chooses which stored junctions to string together. If any code
> path here needs a waveform, the design has broken (**D2**).

This is design-v3 §4's `ScoredEdges → MixPlan` arrow, and **D3**'s formulation: a
minimum-cost path through K of N, which is the **orienteering problem** — *"pick the
best subset, don't visit all"* — not Dijkstra (no target node, and no-repeats makes
the state exponential) and emphatically not a sort.

Everything downstream of here executes; nothing downstream decides. That is the D1
seam, and it is why `MixPlan` must be self-sufficient (§2).

---

## 1. Scope & consumers

**Boundary:** `search_path(tracks, edges, config, edge_config=None) ->
PathSearchResult` takes the `Track[]` node set from `ingestion/orchestrator` and the
scored edge set from `processing/edge_builder`, and produces a `MixPlan` — the
ordered track list plus the winning `Junction` between each consecutive pair.

**Consumer:** `render/playlist_renderer` (design-v3 §4.2: *"Playlist serialisation —
Output of path search — collecting winning edges"*). It receives **only** the
`MixPlan` (`render_mix(mix_plan, load_audio)`, that spec §3) — `Track[]` does not
flow past this module, which is why §2 carries `lufs_integrated` into `TrackRef`.

**Explicitly out of scope:**

- **Re-scoring any edge.** `ScoredEdge.cost` is a single scalar precisely so this
  module can sum it (`edge_builder` §1). Recomputing a term here would double-count.
- **Choosing a transition tier.** **D4**'s corollary puts tier selection *inside*
  edge construction — *"otherwise the tier penalty cannot influence which pairings get
  picked"*. This module takes `ScoredEdge.plan` verbatim.
- **Camelot harmonic compatibility.** §1.2's three legal moves are already priced by
  `edge_builder`'s `camelot.key_distance` — stay put `0.00`, ±1 same letter (perfect
  fifth) `0.25`, same number flip letter (relative major/minor) `0.25`, the diagonal
  `1.00`, otherwise `min(1, wheel_distance/6)`. That is a **pairwise** property, which
  is exactly what **D3** assigns to the edge cost. The only key-aware term here is
  §6's set-wide `key_variety_deficit`, which asks a different question (§6).
- **Deriving cues.** `cue_derivation` emits candidates, `edge_builder` picks the
  winning pair per edge. This module picks neither.
- **`gain_db_a`/`gain_db_b`.** Left at `0.0` as `edge_builder` set them; computing
  set-wide gain is `playlist_renderer`'s Milestone B (§2, §16).
- **Familiarity *scoring*.** `ingestion/familiarity_scorer` is build-order step 8 —
  *after* this module. This spec only *consumes* `Track.familiarity_score` (§7).
- **Rendering anything.** Selecting a tier-2 junction does not require tier 2 to be
  renderable; `transition_renderer` raises `UnregisteredStrategyError` for
  unimplemented tiers by deliberate design (§16).

**Load-bearing inherited rule:** `edge_builder` §2 — a missing key in
`ScoredEdges.edges` means **"no viable junction exists"**, never cost `0`. This module
treats it as no edge. Nothing here may invent a cost for an absent pair.

---

## 2. Data contracts (`schema.py`, `common/contracts/schema.py`)

**`MixPlan`, `TrackRef` and `MixPlanConfig` live in
`src/common/contracts/schema.py`**, alongside `Junction`/`Envelope`. This resolves
`edge_builder` v1 §12 Q6, which deferred the question *"until that module exists"*.
The answer is the same one that moved `Junction` there: `MixPlan` is **produced by
`processing/` and consumed by `render/`**, so leaving it in `render/` would make the
planning layer depend on the render layer, and moving it into `processing/` would
merely invert that. A neutral shared location leaves neither layer depending on the
other. They were previously defined in `render/playlist_renderer/spec.md` §2 (see that
spec's `## Amendments`).

```
MixPlan:
  config    : MixPlanConfig    # design-v3 §5.2's config block (below)
  tracks    : list[TrackRef]   # in play order; tracks[0] opens, tracks[-1] closes
  junctions : list[Junction]   # len == len(tracks) - 1. junctions[i] joins
                                # tracks[i] -> tracks[i+1], copied verbatim from
                                # ScoredEdge.plan (D4 — stored, never recomputed)

TrackRef:
  id              : str
  path            : str
  cue_in          : float | None  # this track's own opening point. Consulted ONLY
                                   # when it has no preceding junction — i.e. the
                                   # opener (D24's free cue-in). None = from 0.0
  cue_out         : float | None  # this track's own closing point. Consulted ONLY
                                   # when it has no following junction — i.e. the
                                   # closer (D24). None = to the natural end
  fade_out_bars   : int | None    # D24's fallback: `closer_fade_bars` on the last
                                   # track when it has no `outro_start` cue, so the
                                   # renderer fades to silence instead of stopping
                                   # dead. None = no fade. Always None elsewhere (§8)
  lufs_integrated : float         # carried through from Track (§1.8). Not used by
                                   # this module — see below

MixPlanConfig:                  # design-v3 §5.2: { track_count, energy_arc,
                                 # seed_track, tier_penalties, weights }
  track_count  : int             # K as requested. The ACHIEVED count is
                                  # len(tracks), which may be smaller (D21, §9)
  energy_arc   : str             # the arc shape requested (§5)
  seed_track   : str | None      # Track.id pinned at position 0, if any (§11)
  path_search  : dict[str, Any]  # dataclasses.asdict(PathSearchConfig) — §5.2's
                                  # "weights"
  edge_builder : dict[str, Any] | None   # dataclasses.asdict(EdgeBuilderConfig) when
                                          # the caller passes `edge_config`; §5.2's
                                          # "tier_penalties". None otherwise (Q10)
```

**Why `TrackRef.lufs_integrated` exists, given this module never reads it.**
Set-wide gain is currently assigned to a module that cannot reach the data.
`edge_builder` §1 leaves `gain_db_a/b` at `0.0` because *"gain targets depend on the
whole set, not the pair… and are `playlist_renderer`'s concern."*
`transition_renderer` §3 agrees it cannot do the job — *"that needs LUFS data this
module never receives."* But `playlist_renderer` §3's entry point is
`render_mix(mix_plan, load_audio)`: it never receives `Track[]` either, and
`lufs_integrated` exists only on `Track`. The job has an owner with no access to its
input. Carrying one float into `TrackRef` closes that loop and preserves the property
the whole D1 seam rests on — **`MixPlan` is self-sufficient**; the renderer never
needs a second input to execute it. This module sets the field and still leaves
`gain_db_a/b` at `0.0`; computing gains stays `playlist_renderer`'s Milestone B.

Module-local contracts stay in `src/processing/path_search/schema.py` — they are this
module's *report*, not a cross-layer contract:

```
PathSearchResult:
  plan         : MixPlan
  diagnostics  : SearchDiagnostics
  alternatives : list[MixPlan]   # the next-best complete paths, in cost order.
                                  # D1: "generate 50 candidate sets, score them,
                                  # render one". Empty unless n_alternatives > 0.
                                  # Caveat in Q12: these are beam neighbours

SearchDiagnostics:               # D21's "still log total duration"; design-v3 §9's
                                  # objective evaluation metrics
  total_cost           : float           # the winner's objective (§4)
  objective            : ObjectiveTerms  # its five terms, broken out
  achieved_track_count : int             # == len(plan.tracks); < track_count means
                                          # the pool dead-ended (D21), not an error
  estimated_duration_s : float           # D21 — LOGGED, never constrained (§10)
  tier_histogram       : dict[int, int]  # strategy_tier -> count. D5's "% at tier 2
                                          # is the best single health metric" (§9)
  pool_size            : int             # nodes surviving §3's filter
  excluded_count       : int             # D7 quarantine, design-v3 §9
  cut_only_count       : int
  runner_up_costs      : list[float]     # totals of the paths behind the winner
  terminated_on        : "k_reached" | "pool_exhausted"

ObjectiveTerms:                  # every field in [0,1] EXCEPT edges_total, which is
                                  # a sum over K-1 edges and is not normalised (§4)
  edges_total        : float
  arc_deviation      : float
  diversity_penalty  : float
  familiarity_deficit: float
  boundary           : float
```

`NoViablePathError` is raised when no two-track chain exists at all (§11) — loudly,
rather than returning a degenerate one-track plan the renderer would then assert on.

---

## 3. Legal moves — pool and feasibility (`pool.py`, `feasibility.py`)

### Pool

```
drop  status == "excluded"              # D7 quarantine; D10's hard constraint
drop  len(downbeat_times) < 2           # no bars, therefore no energy curve
drop  bpm <= 0                          # same guard edge_builder v2 §5 applies
drop  tracks absent from every edge     # unreachable and unleavable
```

`cut_only` tracks **stay in the pool**. D7 restricts which *tiers* they may use, and
`edge_builder` §5 already priced that restriction into every edge they appear on.
Dropping them here would punish the same quarantine twice, and — per **D10** — would
shrink the pool for a reason that is already represented as a cost.

### Segment feasibility

**A structural gap this module must close, because nothing upstream can.**
`edge_builder`'s §0 invariant is that it scores every pair *"as if both sat mid-set"*
and has **no notion of path**. So the cue-*in* it picks for B on edge `A→B` is chosen
in complete ignorance of the cue-*out* it picks for B on edge `B→C`. Nothing
guarantees they are in order. A path `A → B → C` can hand track B a cue-in at 180 s
and a cue-out at 60 s — a **negative play duration**, emitted silently, with no
upstream check able to catch it because no upstream module knows the ordering.

```
for every interior track j (one junction on each side):
    span_j = junctions[j].cue_out - junctions[j-1].cue_in
    the extension is INFEASIBLE unless span_j >= min_play_seconds
```

Checkable **incrementally**: extending `[…, A, B]` by `C` is precisely the moment
both of B's sides become known, so this costs O(1) per extension and never needs a
reconciliation pass over the finished path.

**This is a fourth hard constraint, and D10 permits it.** D10 forbids hard gates on
*musical* judgements — key, tempo, vocal density — because *"a strict gate can leave
the search with no legal successor"* and *"the failure is invisible."* A
negative-length segment is not a musical judgement. It is definitionally not a
playable segment, the same category as D10's own *"no track repeats."*
`min_play_seconds` defaults to `8.0` (≈ 4 bars at 120 BPM); below that a track is a
glitch in the mix rather than a member of the set. Whether the floor *above* zero
should instead be a graduated penalty is **Q11**.

---

## 4. The objective (`objective.py`)

```
total = Σ edge_costs
      + λ · arc_deviation(path)
      + μ · diversity_penalty(path)
      + ν · familiarity_deficit(path)
      + β · boundary_cost(path)          # this spec's addition (below)
```

The first four terms are **D3** verbatim. Every path-level term is normalised to
`[0,1]` at construction (**D26**), so the weights read as relative importance rather
than arbitrary scale factors.

### The scale trap

`Σ edge_costs` is a **sum** over `K−1 ≈ 14` edges, each costing roughly 1–2, so it
lands around **15–25**. Each path-level term is capped at **1.0** by D26. Naïve
weights of `λ = μ = ν = β = 1.0` would therefore make the entire energy arc worth
about 4% of the objective: **three of the five terms would be silently inert**, and
the module would still produce plausible-looking setlists — a failure that looks like
success.

This spec keeps D3's `Σ` form verbatim and instead defines the weights **in units of
edge-cost**. `λ = 8.0` reads as *"a completely wrong energy arc costs as much as eight
typical junctions."* That restores D26's interpretability against a summed first term
without contradicting D3. Defaults on that scale live in §11 and are provisional
(**Q5**).

### β — the boundary term

**Grounded, not invented.** **D24** states a *preference* (*"free-time or riser intros
are good openers"*), and **D10** says every soft musical preference is a scored cost
rather than a gate. Applying D24 as a bare relaxation would drop the constraint on
whichever track happened to land at position 0 without ever *preferring* a track that
opens well. Same justification `edge_builder` §4 used to add `cue_kind` and `phrase`
beyond D3's five named edge terms.

### The familiarity sign

**D3** writes `+ ν · familiarity_score(path)` inside a **minimised** total, which
inverts §6.1's intent (familiar and party-appropriate is *good*). This spec resolves
it as a **deficit** — `1 − mean(familiarity)` — so that higher familiarity lowers the
objective and D3's `+ν·` remains literally correct (§7).

---

## 5. Energy arc (`energy_arc.py`)

**D3**'s `arc_deviation`, which the design doc names in three places (D3, D23, §1.10)
and never defines. §1.10 is the whole requirement: *"A set builds, peaks, comes down.
Energy dropping mid-set feels like a mistake even when every transition is clean.
**This is a property of the whole path — not decomposable into pairwise edge
costs.**"*

### Per-track energy

```
track_energy(t)  = median(t.energy_curve)             # short-term LUFS per bar (D23)
energy_norm(t)   = clamp((track_energy(t) - p05) / (p95 - p05), 0, 1)
                   # p05/p95 = 5th/95th percentile of track_energy over the POOL
```

**Median, not mean**, and **percentiles, not min–max**, for the same reason: an
`energy_curve` includes near-silent intro and outro bars where short-term LUFS can hit
−70, and one quiet track would otherwise compress every other track's normalised
energy into a narrow band, flattening the arc signal into noise. Percentile
normalisation is already precedented in this codebase — `edge_builder`'s
`normalized_vocal_mask` does exactly this against a 95th percentile under **D22** —
so this reuses a convention rather than inventing a second one. Degenerate pool
(`p95 == p05`): every track scores `0.5`, neutral.

**A whole-track statistic, deliberately, not the played segment.** `edge_builder`'s
`energy` term already prices energy *continuity across a junction* (`|energy_a[out] −
energy_b[in]|`, absolute). This term prices energy *trajectory across the set*. They
are different signals, and using the played segment here would partially re-charge the
first one. Recorded as **Q1**.

### K_eff

```
K_eff = min(target_track_count, pool_size)
```

**Not the raw target.** With a 12-track pool and `target_track_count = 15`, positions
would only ever reach `p = 11/14 = 0.79` and the arc's comedown would be structurally
unreachable — every candidate set would be scored against a shape it cannot make.
`K_eff` is computed once, after §3's pool filter, and **every `K` in §5–§9 means
`K_eff`**. `K_eff < 2` raises `NoViablePathError`, which also guards the `K_eff − 1`
division below.

### Target arcs and deviation

Over normalised position `p = i / (K_eff − 1)`:

```
"arc"  (default)   piecewise-linear through three points — §1.10's "builds, peaks,
                   comes down":
                     p = 0                  -> arc_start_level
                     p = arc_peak_position  -> 1.0
                     p = 1                  -> arc_end_level
"rise"             target(p) = p                    # monotonic build
"flat"             target(p) = arc_start_level      # control shape

arc_deviation(path) = mean_i | energy_norm(path[i]) - target(i / (K_eff - 1)) |
```

Both operands are in `[0,1]`, so the mean is too — **D26 satisfied by construction**,
with no clamp needed.

**Partial paths use the final-`K_eff` position mapping** (`i / (K_eff − 1)`, never
`i / (n − 1)`), so the arc steers the beam from the very first extension rather than
only once a path is complete. This is safe because **beam search only ever compares
paths of equal length** (§9), so the length-dependent denominator is uniform across
every comparison it is used in.

---

## 6. Diversity (`diversity.py`)

**D3** names this term and defines nothing at all — the word "diversity" appears
exactly twice in the entire design corpus, both times inside D3's formula. This spec
defines it as the counterweight to a specific, predictable failure mode of
`Σ edge_costs`: the cheapest edges are always nearest neighbours, so a pure edge-sum
converges on fifteen tracks at one tempo in one key. That is precisely the *"monotonic
tempo ramp is boring"* outcome design-v3 §13 rejects BPM-sorting for.

```
diversity_penalty(path) = mean(bpm_spread_deficit, key_variety_deficit)

bpm_spread_deficit  = 1 - clamp(stdev(bpm over path) / diversity_bpm_target_std, 0, 1)
key_variety_deficit = 1 - clamp((distinct_keys - 1) / (K_eff - 1), 0, 1)
```

`distinct_keys` counts distinct non-null Camelot keys, **plus one** if any track's key
is null — every unknown collapses into a single bucket, because a missing key is
*unknown*, not a distinct key. This mirrors `edge_builder` §3's refusal to let a null
key score as a perfect match. A path shorter than two tracks scores
`bpm_spread_deficit = 1.0` (stdev undefined). `K_eff − 1` is the denominator on
partial paths too, for §5's equal-length reason.

### Does this fight `edge_builder`'s Camelot term?

It looks like a contradiction and is not, so the spec settles it explicitly. Worked
against the defaults over 15 tracks:

| Set | Edge key cost | `key_variety_deficit` | Net at μ = 4.0 |
|---|---|---|---|
| All 15 in `8A` | `0.00` × 14 = **0** | `1 − 0/14` = **1.0** | pays **4.0** in diversity |
| Wheel walk `8A→9A→10A→…` | `0.25` × 14 = **3.5** | `1 − 14/14` = **0.0** | pays **3.5** in edges |
| Random keys | up to `1.00` × 14 = **14** | ≈ 0.0 | pays **≈14** in edges |

Sitting still and jumping randomly are both punished; **walking the wheel one step at
a time is the cheap answer** — which is what a DJ actually does. The two terms are not
opposed, they are two halves of one instruction, and they only read as opposed if you
forget that the edge term is adjacent-pair while this one is set-wide.

The near-tie between the first two rows is the honest reading of a µ that has never
been tuned (**D26**): the objective currently holds no strong opinion between a
single-key set and a wheel walk. That is a weight-calibration question (**Q5**), not a
structural one. §12 pins the ordering with a test so a future µ change cannot invert
it silently.

---

## 7. Familiarity (`familiarity.py`)

**D3**'s `ν` term, sourced from §6.1's LLM scoring — *"Not computable from audio — it
is world knowledge… Enters the objective as the path-level `ν` term (D3)."*

```
familiarity_deficit(path) = 1 - mean(familiarity_of(t) for t in path)

familiarity_of(t) = t.familiarity_score          if not None
                    else pool mean of known scores    if any are known
                    else 0.5                          # neutral, never 0.0
```

Written as a **deficit** so D3's `+ν·` sign stays correct in a minimised objective
(§4).

**Inert in v1, and honestly so.** `ingestion/orchestrator` §3 sets
`familiarity_score` to `None` on every `Track`, and `ingestion/familiarity_scorer` is
build-order step **8** — *after* this module. With no scores anywhere, the term is a
constant `0.5` across every candidate path and cannot change any ranking. It is
specced now so that step 8 becomes a **data** change rather than a code change.

The neutral-`0.5` fallback follows `edge_builder` §4's confidence-blend reasoning
exactly: an unknown value must never look like the *best possible* value, or the
search would systematically favour precisely the tracks whose metadata is missing.

---

## 8. Boundaries — D24 (`boundaries.py`)

**D24**: *"First and last tracks each have one unconstrained side."* `edge_builder` §1
explicitly defers this here — it *"scores every pair as if both sat mid-set"* and
*"`path_search` applies D24 to whichever tracks it places at the ends."*

### Relaxation — what lands in the contract

| Position | Field | Value |
|---|---|---|
| `0` | `cue_in` | `None` — no cue-in constraint; the opener plays from `0.0`, so free-time and riser intros survive intact |
| `N−1`, has an `outro_start` cue | `cue_out` | `None` — plays to its natural end, no time-boxing |
| `N−1`, no `outro_start` cue | `cue_out` | its preferred (first) `cue_outs` entry, and `fade_out_bars = closer_fade_bars` |
| everything else | both | `None` — the flanking `Junction` is authoritative, as `playlist_renderer` §2 already specifies |

The third row is **D24's stated fallback** — *"time-box as normal, then apply a 4-bar
equal-power fade to silence"* — and D24 is explicit that it *will* fire: *"(which will
happen — that's why the time-boxed cut exists)"*.

Note that the junctions themselves need no adjustment: junction `(0,1)` supplies the
opener's `cue_out` and junction `(N−2, N−1)` supplies the closer's `cue_in`, both
already correct. D24 touches only the two genuinely unconstrained outer sides.

### Scoring — the β term

```
boundary_cost(path) = mean(opener_cost(path[0]), closer_cost(path[-1]))

opener_cost(t)  = 0.0   if t.cue_ins contains `riser_start` or `intro_end`
                  0.5   elif t.free_intro_end > t.grid_start   # some real intro
                  1.0   otherwise
closer_cost(t)  = 0.0   if t.cue_outs contains `outro_start`
                  1.0   otherwise                              # the fade fallback
```

**v1 reality, stated rather than discovered later:** `cue_derivation` never emits
`outro_start` in v1 (`edge_builder` §4: *"never fires in v1 (cues.py)"*), so
`closer_cost` is a constant `1.0` and only the opener half of β is live. A constant
term across all candidate paths cannot distort ranking, so this is inert rather than
wrong. **Q13** records the related approximation: the closer half is evaluated on the
frontier track at every step, which is only the *real* closer once a path is complete.

---

## 9. Beam search (`beam.py`)

**D3**: *"beam search (top ~50 partial sequences, extend, rescore, prune) is preferred
over greedy + 2-opt. Greedy handles path-level objectives badly."*

```
1. seed the beam: one length-1 path per pool track
                  (or exactly one, when config.seed_track pins position 0)

2. DO NOT PRUNE before the first edge exists. A length-1 path has no edge cost, so
   pruning at step 1 would rank openers on path-level terms alone and discard the
   best one on noise. At N <= 200 the unpruned first extension is ~40k candidates,
   which is trivial (§14).

3. repeat until every surviving path has length K_eff, or the beam is empty:
     for each beam path:
         extend by every unused j where edges[(last, j)] exists
                                    AND §3's feasibility check passes
         if it produced ZERO feasible extensions:
             RETIRE it into `completed`   # neither carried forward nor discarded
     rescore every survivor in full        # D3's "extend, rescore, prune"
     keep the top `beam_width`

4. from `completed` plus any length-K_eff survivors:
     prefer the LONGEST achieved length;
     among those, the minimum total.
   Never pad a short set to K.
```

### Retiring dead-ended paths is load-bearing

The naïve loop — *"stop when no path extends"* — is wrong in two directions at once.

**Carrying a dead-ended path forward** would put paths of different lengths into the
same beam, which breaks the equal-length comparison that §5 and §6 both depend on to
keep their `K_eff − 1` denominators harmless.

**Discarding it** throws away a legitimate answer: if 49 of 50 paths dead-end at
length 10 and one reaches length 15, the run must still be able to fall back to the
best length-10 set should that lone survivor score worse.

Retiring into a separate `completed` pool does both — the beam stays uniform-length,
and nothing viable is lost.

### Termination and its honest limits

**D21**: *"Beam search terminates on K tracks or pool exhausted, not cumulative
runtime."* `terminated_on` reports `k_reached` when any path reached `K_eff`, else
`pool_exhausted`. The spec states the limitation plainly: beam search cannot know
whether a path pruned at step *n* would have extended further, so `pool_exhausted`
means *this beam* exhausted — not that the pool provably did.

A result shorter than `target_track_count` is a **degradation to report, not an error
and not a choice** — D7's *"better a 12-track set that sounds good than a 15-track set
with one train wreck."* It surfaces through `achieved_track_count`.

### Determinism

**D14** requires the planner to be *"interpretable, instantly re-runnable,
unit-testable."* Ties are broken on `(total_cost, tuple(track_ids))`, so the result
never depends on dict iteration order. This is what makes the module reproducible and
JSON-fixture testable at all.

### Cost

`Σ edge_costs` accumulates incrementally (one addition per extension); the four
path-level terms recompute over the `≤ K_eff` path each time. At N=200, K=15,
beam=50 that is roughly 2M scalar operations for a whole run — well inside **D2**'s
millisecond budget, with no vectorisation required. Stated so a future optimisation
has a target to beat rather than a vague sense that this might be slow.

---

## 10. Duration estimate (`duration.py`)

**D21** is explicit that duration is **logged, never constrained**: *"Still log total
duration. 15 tracks landing at 40 minutes against a ~17-minute reference means the
time-boxed cut is mis-sized — a signal, not a constraint."*

```
per-track span:  track 0     -> junctions[0].cue_out - (tracks[0].cue_in or 0.0)
                 interior i  -> junctions[i].cue_out - junctions[i-1].cue_in
                 track N-1   -> (cue_out or Track.duration) - junctions[-1].cue_in

overlap per junction: length_bars * bar_seconds       # Junction.bar_seconds, v2 §6

estimated_duration_s = Σ spans - Σ overlaps
```

An **estimate**, and the spec says so: the renderer's sample math (D25, 48 kHz) is
authoritative, and tier 2's time-stretch (`rate_b`) shifts B's real duration in a way
this arithmetic does not model. It exists to make D21's signal visible, not to be
exact. `Junction.bar_seconds` is what makes the overlap term computable here at all
(`edge_builder` v2 §6).

---

## 11. Orchestration & config (`search.py`, `config.py`)

```
search_path(tracks: list[Track],
            edges: ScoredEdges,
            config: PathSearchConfig,
            edge_config: EdgeBuilderConfig | None = None) -> PathSearchResult

  1. filter the pool; compute K_eff                        # §3, §5
  2. precompute per-track energy_norm, bpm, key arrays     # §5, §6
  3. seed the beam (or pin seed_track)                     # §9
  4. extend / check feasibility / rescore / prune          # §3, §4, §9
  5. pick the winner: longest, then cheapest               # §9
  6. apply D24 to the two ends; build the MixPlan          # §8, §2
  7. assemble diagnostics + alternatives                   # §2, §10
```

`edge_config` is **provenance only** — it never influences the search. It exists so
`MixPlanConfig.edge_builder` can carry design-v3 §5.2's `tier_penalties` when the
caller has that object to hand (**Q10**).

```
PathSearchConfig:
  target_track_count       : int    # default 15  — §0's "~15 tracks in ~17 minutes"
  beam_width               : int    # default 50  — D3's "top ~50" (Q7)
  seed_track               : str | None   # default None; pins position 0 (D1, Q8)
  min_play_seconds         : float  # default 8.0 — §3's feasibility floor
  energy_arc               : str    # default "arc" — "arc" | "rise" | "flat" (§5)
  arc_peak_position        : float  # default 0.70
  arc_start_level          : float  # default 0.35
  arc_end_level            : float  # default 0.60
  w_arc                    : float  # λ, default 8.0 — in EDGE-COST units (§4)
  w_diversity              : float  # μ, default 4.0
  w_familiarity            : float  # ν, default 8.0 (inert in v1, §7)
  w_boundary               : float  # β, default 4.0
  diversity_bpm_target_std : float  # default 8.0 BPM (§6)
  closer_fade_bars         : int    # default 4 — D24's fade fallback (§8)
  n_alternatives           : int    # default 0; clamped to beam_width (§2)
```

**Input hygiene.** Index `tracks` by `id` once. Ignore any `edges` key naming a track
absent from the pool. `beam_width < 1` and `target_track_count < 2` are **errors, not
clamps** — a caller asking for a one-track mix has a bug, and silently correcting it
would hide that.

Plain non-frozen `@dataclass` with defaults, matching every sibling config
(`FeatureExtractorConfig`, `CueDerivationConfig`, `IngestionConfig`,
`EdgeBuilderConfig`).

**No version constant**, the same divergence `edge_builder` §8 and `orchestrator` §2
made and for the same reason: sibling versions exist to invalidate a *cached artifact*,
and this module caches nothing. The config object itself is the reproducibility
record — which is exactly what `MixPlanConfig` now carries into the plan.

> **Every numeric default above is provisional.** **D26**: weights *"determine output
> quality entirely and cannot be tuned until the eval harness exists."* They are
> starting points chosen to be interpretable against §4's scale — not tuned values,
> and not to be read as settled (**Q5**).

---

## 12. Testing strategy

**Every test is a millisecond, no-audio, JSON-fixture test** (**D2**). `conftest.py`
builds synthetic `Track` objects *and* `ScoredEdges`, reusing
`ingestion.orchestrator.schema.Track`, `ingestion.cue_derivation.schema.Cue` and
`processing.edge_builder.schema.ScoredEdge`/`ScoredEdges` directly, never redefining
them — the convention every sibling conftest follows.

- `test_pool.py`: `excluded` dropped, `cut_only` **kept**, bar-less and non-positive
  BPM dropped, tracks absent from every edge dropped.
- `test_feasibility.py`: a fixture engineered so edge `A→B` picks a **late** cue-in
  for B while edge `B→C` picks an **early** cue-out for B — the `A→B→C` extension must
  be rejected. Without this case the defect ships as a negative-duration segment.
  Also: a span below `min_play_seconds` rejected, one just above it accepted.
- `test_energy_arc.py`: each arc shape at `p = 0`, `arc_peak_position`, `1`;
  `K_eff` clamping to pool size; one near-silent track in the pool **not** flattening
  every other track's normalised energy (the median/percentile choice); degenerate
  `p95 == p05` scoring `0.5`.
- `test_diversity.py`: §6's worked table as a real assertion — a wheel walk must beat
  both a single-key set and a random-key set on `Σ edge_costs + μ·diversity`. This is
  what pins the Camelot interaction so a future µ change cannot invert it silently.
  Also: nulls collapsing to one bucket; a length-1 path scoring `1.0`.
- `test_familiarity.py`: constant when every score is `None` (v1's real case); the
  pool-mean fallback for a partially-scored pool; deficit direction — a more familiar
  path scores **lower**.
- `test_boundaries.py`: D24 setting exactly the two outer sides and leaving every
  interior `cue_in`/`cue_out` at `None`; `fade_out_bars` set only on the closer, and
  only when it has no `outro_start`; `opener_cost` ordering across the three cases.
- `test_objective.py`: with **default** weights, a path with a perfect arc must
  actually outrank an otherwise-identical path with an inverted arc. This is the test
  that catches §4's scale trap — it fails if λ is left at 1.0.
- `test_beam.py`: every path in the beam has identical length at every step (the
  invariant §5/§6's denominators rely on); a pool where most paths dead-end early
  still returns the one long path; a hand-enumerable 4-track pool where the optimum is
  computable by exhaustive search and the beam must find it; identical-cost ties
  producing byte-identical output across runs (**D14**); a missing edge key treated as
  *no edge* rather than cost 0; no track repeated.
- `test_duration.py`: spans and overlaps against a hand-computed two- and three-track
  plan.
- `test_search.py`: end-to-end over a small fixture — `MixPlan` shape invariants
  (`len(junctions) == len(tracks) - 1`, each junction's `from_track`/`to_track`
  matching its neighbours), junctions copied **verbatim** from `ScoredEdge.plan`,
  `NoViablePathError` on an empty/one-track pool, `terminated_on` correctness,
  `alternatives` empty by default.
- `schema.py`/`config.py` have no dedicated test files — plain data classes, no
  behaviour.

---

## 13. File layout

```
src/common/contracts/
  __init__.py             # public exports: + MixPlan, TrackRef, MixPlanConfig
  schema.py                # + MixPlan, TrackRef, MixPlanConfig (§2 — moved here
                            # from render/playlist_renderer)

src/processing/path_search/
  __init__.py             # public exports: PathSearchConfig, PathSearchResult,
                           # SearchDiagnostics, ObjectiveTerms, NoViablePathError,
                           # search_path
  schema.py                # PathSearchResult, SearchDiagnostics, ObjectiveTerms (§2)
  config.py                 # PathSearchConfig (§11)
  pool.py                     # node-pool filtering (§3)
  feasibility.py                # segment-span check per extension (§3)
  energy_arc.py                   # target arcs + arc_deviation (§5)
  diversity.py                      # diversity_penalty (§6)
  familiarity.py                      # familiarity_deficit (§7)
  boundaries.py                         # D24 relaxation + boundary_cost (§8)
  objective.py                            # the five-term total (§4)
  beam.py                                   # the beam itself (§9)
  duration.py                                 # D21's estimate (§10)
  plan_builder.py                               # path -> MixPlan (§2, §8)
  search.py                                       # search_path() entry point (§11)
  examples/
    example_search_path.py                          # hand-built synthetic pool ->
                                                     # search_path; gitignored, not
                                                     # part of the suite
    example_search_path_from_music.py               # end-to-end: real ingest_tracks()
                                                     # over music/*.mp3 -> build_edges()
                                                     # -> search_path(); also
                                                     # gitignored (§16)

tests/processing/path_search/
  conftest.py               # synthetic Track + ScoredEdges builders — reuse
                             # orchestrator's, cue_derivation's and edge_builder's
                             # schemas directly, never redefine
  test_pool.py                # §12
  test_feasibility.py           # §12
  test_energy_arc.py              # §12
  test_diversity.py                 # §12
  test_familiarity.py                 # §12
  test_boundaries.py                    # §12
  test_objective.py                       # §12
  test_beam.py                              # §12
  test_duration.py                            # §12
  test_search.py                                # §12
```

`src/processing/path_search/examples/` needs a `.gitignore` entry at implementation
time, alongside the sibling `examples/` lines already there. None of the test
basenames above collide with an existing `test_*.py` elsewhere under `tests/`, so no
`__init__.py` is required (`tests/README.md`'s collision rule) — re-verify when the
files are written.

Entry point named `search.py`/`search_path()` to match the sibling verb convention
(`build.py`, `derive.py`, `extract.py`, `orchestrate.py`, `download.py`).

---

## 14. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Sort by BPM, then apply Camelot wheel rules | Beam search over the five-term objective (§4, §9) | design-v3 §13's first row: *"One ordering with no lever to fix key mismatches, and a monotonic tempo ramp is boring."* Three concrete failures: a sort **orders** but does not **select** (we need 15 of ~200); compatibility is already the edge cost, so a sort is what you get when compatibility is the *only* objective; and §1.6 notes a hard cut lets tempo jump — a BPM sort throws that degree of freedom away for a constraint tier 3 does not impose |
| Greedy + 2-opt | Beam search (§9) | **D3**: *"Greedy handles path-level objectives badly."* Three of five terms here are path-level |
| Dijkstra or exact DP | Beam search (§9) | **D3**: no target node, and no-repeats makes the state *"which track am I on **and** which have I used"* — exponential. This is the orienteering problem |
| A fixed total-duration target | K tracks (§9), duration logged (§10) | **D21**: bars-to-seconds varies with tempo so count and runtime don't determine each other; a budget makes the search knapsack-flavoured for an arbitrary constraint |
| Hard gates on key, tempo or vocal density | They stay priced in `edge_builder`'s cost (§1) | **D10**: a strict gate can leave the search with no legal successor, and the failure is *invisible* — a shorter mix, not an error |
| Re-picking the transition tier after the ordering is known | Tier chosen inside edge construction (§1) | **D4**'s corollary: the tier penalty cannot influence which pairings get picked if the ordering is already fixed — which is the entire mechanism D5 relies on |
| Re-scoring key compatibility here | `edge_builder`'s `camelot.key_distance` (§1) | It is a pairwise property, which D3 assigns to the edge cost. Scoring it again would double-count one signal and silently double its weight |
| Padding a short result up to K | Return the longest achievable path (§9) | **D7**: *"Better a 12-track set that sounds good than a 15-track set with one train wreck."* Padding would require admitting an edge the search already rejected |
| Pruning the beam at step 1 | Prune only once an edge cost exists (§9) | A length-1 path has no edge cost, so step-1 pruning ranks openers on noise. The unpruned first extension is ~40k candidates at N=200 — trivially affordable |
| Segment-span violations as a soft penalty | A hard feasibility check (§3) | Every *musical* constraint stays soft per D10, but a negative-length segment is not a musical judgement — it is not a playable segment at all, the same category as "no track repeats". The floor *above* zero is Q11 |
| Whole-track mean energy, min–max normalised | Median, 5th/95th percentile (§5) | Near-silent intro/outro bars drag the mean; one quiet track compresses every other track's normalised energy into a narrow band. Percentile normalisation is already precedented by `edge_builder`'s `normalized_vocal_mask` under D22 |
| Weights of 1.0 across the board | Weights in edge-cost units (§4) | `Σ edge_costs` lands at 15–25 while path terms cap at 1.0 — unit weights make three of five terms inert while the module still looks like it works |
| Learning the path-level objective | The hand-tuned weighted sum (§4) | design-v3 §6's ML table: **"Never (D14)"** for path search. D14: a model there *"destroys everything that makes D2 valuable and buys nothing"* |
| A `path_search_version` constant | The config object as the reproducibility record (§11) | Sibling versions exist to invalidate cached artifacts; this module caches nothing. Same divergence `edge_builder` §8 and `orchestrator` §2 made |

---

## 15. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | §5 scores the arc on **whole-track** median energy, not the played segment. The segment is knowable for every track except the beam's frontier, so a segment-accurate variant is implementable — but it would partially re-charge the junction-continuity energy `edge_builder` already prices | Arc fidelity. Nothing structural — the term's shape is unchanged either way |
| Q2 | §6's two axes (BPM spread, key variety) are **this spec's invention**. D3 names `diversity_penalty` and defines nothing; the corpus contains no statement of what dimension diversity should be measured over | Whether the term measures the right thing at all. Its weight µ is separately untuned (Q5) |
| Q3 | **D3 writes `+ ν · familiarity_score` in a minimised objective**, which inverts §6.1's intent. §4/§7 resolve it as a deficit so the sign stays correct — but this is this spec reading intent over letter | Nothing today (ν is inert in v1, §7). Worth confirming before step 8 makes it live |
| Q4 | `"arc"`'s three-point shape and `arc_peak_position = 0.70` are invented. §1.10 says only *"builds, peaks, comes down"* — no peak position, no start/end levels, no vocabulary of shapes | Arc quality. Trivially reversible via config |
| Q5 | **λ, μ, ν, β are all untuned**, and D26 is explicit that weights *"determine output quality entirely and cannot be tuned until the eval harness exists"*. §4's edge-cost scaling fixes the *scale* but not the *values* | Output quality, entirely. design-v3 §8 already lists this as a standing project risk |
| Q6 | `TrackRef.fade_out_bars` has **no renderer support** — `transition_renderer`/`playlist_renderer` are Milestone-A specced and unbuilt (§16) | The closer's fade actually happening. The field is set correctly meanwhile |
| Q7 | `beam_width = 50` is D3's *"top ~50"*, which appears with a tilde in both design docs and was never validated against optimal on a real pool | Search quality vs. runtime. Runtime is not currently a constraint (§9) |
| Q8 | `seed_track` is defined here as **"pins position 0."** design-v3 names the field (§5.2) and D1's prose (*"set length or seed track"*) and never says whether it pins or merely biases | Seeding semantics. Low blast radius — it defaults to `None` |
| Q9 | There is **no must-include / pinned-set concept anywhere in the corpus**. Should a caller be able to require that specific tracks appear, beyond pinning position 0? | A likely product request that would change the beam's seeding and pruning. Deliberately not invented here |
| Q10 | Should `ScoredEdges` carry its own `EdgeBuilderConfig` snapshot, so `MixPlanConfig.edge_builder` fills itself instead of relying on a caller-passed `edge_config`? | Provenance completeness of §5.2's `tier_penalties`. An `edge_builder` contract change, deliberately not bundled into its v2 |
| Q11 | §3's `min_play_seconds` is a **gate above zero**. `span <= 0` is definitionally infeasible, but `0 < span < 8.0` is a musical judgement, and D10 prefers penalties to gates for those | Whether a very short but legal appearance should be priced rather than forbidden. Trivially reversible via config |
| Q12 | `PathSearchResult.alternatives` come from a single beam, so they share long prefixes with the winner — **near-neighbours, not the genuinely distinct candidate sets** D1's *"generate 50 candidate sets, score them, render one"* implies | Whether `n_alternatives` delivers what D1 describes. Defaults to `0`, so it costs nothing today |
| Q13 | §8's `closer_cost` is evaluated on the **frontier** track at every step, which is only the real closer once a path is complete | Moot in v1 (`closer_cost` is a constant `1.0`, §8), but not once `outro_start` cues exist |
| Q14 | §6 counts **distinct keys**, which rates `8A→9A→10A` and `8A→2A→7A` as equally diverse even though only the first is a wheel walk. Raw distinct-count works today only because `edge_builder`'s Camelot term independently punishes the jumps. Should the term reward **wheel coverage or consistent direction** instead, stating the intent directly rather than relying on that interaction? | Diversity's precision, and its robustness to a future µ change |

---

## 16. What is still missing to render a whole mix

Stated as its own section because *"is the plan enough to render?"* is the natural
question after this module, and the answer is: **the data contract is; the renderer is
not yet.** `Track[]` does not flow past this module — `render_mix(mix_plan,
load_audio)` takes only the plan — so everything the renderer needs must live inside
`MixPlan`.

**Contract gaps — both now closed:**

| Gap | Status |
|---|---|
| `lufs_integrated` unreachable by its assigned owner (`playlist_renderer` receives no `Track[]`) | **Closed by this spec** — carried into `TrackRef` (§2) |
| `Junction` carried no tempo, so `length_bars` and `Envelope`'s `(bar_offset, value)` could not be converted to samples | **Closed by `edge_builder` v2** — `Junction.bar_seconds` (that spec §2/§6) |

The tempo gap is worth recording because it looked like it wasn't one:
`transition_renderer` §3 computes `blend_end = blend_start + length_bars` and §4's
`StrategyFn = Callable[[Junction, StereoPCM, StereoPCM], StereoPCM]` receives no
tempo from anywhere. It was invisible only because **the one implemented tier is the
one where it cannot fire** — tier 3 has `length_bars = 0` and degenerates to a splice.
The first tier-2 render would have hit it immediately.

**Capability gaps — build-order steps 6–7, working as designed:**

- `playlist_renderer` §3 asserts exactly one junction / two tracks (its Milestone A
  scope limit). A 15-track `MixPlan` is un-renderable until Milestone B, which still
  carries an unresolved design question about who slices interior tracks' bodies
  (that spec §9 Q1 — itself explicitly blocked on *this* module existing, so this spec
  unblocks it).
- `transition_renderer` implements **tier 3 only**; tiers 2/4/5 raise
  `UnregisteredStrategyError` by deliberate design (that spec §4). A plan is free to
  select them (`edge_builder` §5); they simply won't render until Milestone B.
- Time-stretch (`rate_b`), set-wide LUFS gain, and `fade_out_bars` are all
  Milestone B.

**Consequence for this module, stated plainly:** its first validation is
`SearchDiagnostics` and `examples/example_search_path_from_music.py`, **not
listening**. Passing `enabled_tiers={3}` to `EdgeBuilderConfig` (`edge_builder` §5) is
the way to get a plan whose every junction is renderable with today's strategy
registry, once multi-junction assembly lands.
