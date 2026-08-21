# Edge Builder — Spec

**Layer:** `processing/` — first module in this layer, upstream of `path_search`.
**Depends on:** `resources/documentation/ingestion/orchestrator/spec.md`'s `Track`
contract; the shared `Junction`/`Envelope` contract (§2, moved to
`common/contracts/` by this spec).

---

## 0. Invariant

> **This module never touches audio, and never decides an ordering.** It is a pure
> function of `Track[]` — `build_edges(tracks: list[Track], config: EdgeBuilderConfig)
> -> ScoredEdges` — that scores every *ordered pair* independently. It has no notion of
> mix position, path, or set length. If any code path here needs a waveform, or needs
> to know what came before A, the design has broken (design-v3 D2's metadata-only
> invariant; D3's split between edge-level and path-level terms).

This is design-v3 §4's `Track[] → ScoredEdges` arrow. Per **D4**, this module embeds
the junction search *inside* edge construction rather than leaving it to a later
stage: whether A→B is a good pairing depends on whether a good transition *point*
exists between them, so ordering and transition-point-finding are not sequential
stages. Per D4's corollary, **transition type is chosen here, not after path search**
— otherwise the tier penalty cannot influence which pairings get picked at all.

---

## 1. Scope & consumers

**Boundary:** `build_edges(tracks, config) -> ScoredEdges` takes the `Track[]` node
set produced by `ingestion/orchestrator` and produces, for every ordered pair with a
viable junction, the **argmin** over
`(out_i ∈ A.cue_outs) × (in_j ∈ B.cue_ins) × (tier ∈ enabled_tiers)` — storing the
winning `Junction` plan alongside its scalar cost, so that when `path_search` later
selects A→B the junction plan comes along free (**D4**: *"store the argmin, not just
the min"*).

**Consumer:** `processing/path_search` (not yet specced). It needs O(1) lookup of the
cost for any ordered pair, and a `cost` that is a **single scalar**, since its own
objective sums them (`D3`: `total = Σ edge_costs + λ·arc_deviation + μ·diversity_penalty
+ ν·familiarity_score`).

**Explicitly out of scope:**

- **Every path-level term.** `arc_deviation`, `diversity_penalty` and
  `familiarity_score` are properties of a whole path and are *not decomposable into
  pairwise edge costs* (design-v3 §1.10, D3). They belong to `path_search`'s
  objective. This module never reads `Track.familiarity_score`/`era`/`is_club_edit`
  — which are `None` in v1 anyway (orchestrator spec §3).
- **D24's first/last-track relaxation.** A free cue-in on track 0 and a free cue-out
  on track N−1 depend on mix *position*, which this module structurally cannot know
  (§0) — it scores every pair as if both sat mid-set. `path_search` applies D24 to
  whichever tracks it places at the ends. Same boundary `cue_derivation` §1 already
  draws for itself, one layer further out.
- **`gain_db_a`/`gain_db_b`.** Emitted on the `Junction` but always `0.0` here —
  gain targets depend on the whole set, not the pair (design-v3 §4.2), and are
  `playlist_renderer`'s concern.
- **Rendering any tier.** Selecting tier 2 does not require tier 2 to be renderable;
  `transition_renderer` raises `UnregisteredStrategyError` for unimplemented tiers by
  deliberate design (that spec §4). See §5's note on `enabled_tiers`.
- **Choosing cue candidates.** `cue_derivation` emits the full candidate set in
  preference order (`cues.py`: *"the edge builder searches over cue-point
  combinations… so this module hands over candidates rather than deciding for it"*).
  This module searches that set; it never derives a new cue.

---

## 2. Data contracts (`schema.py`)

```
ScoredEdge:
  from_track    : str          # Track.id
  to_track        : str          # Track.id
  cost              : float        # the argmin's scalar — D3 sums these
  plan                : Junction     # D4: the winning junction, stored not recomputed
  terms                 : CostTerms    # per-term breakdown of `cost` (§4)

CostTerms:                    # every field already normalised to [0,1] (D26), so
                               # these read as relative importance, not raw scale
  tempo        : float
  key            : float
  energy           : float
  vocal              : float
  cue_kind             : float
  phrase                 : float
  tier_penalty             : float   # added unweighted (§4) — per D5 it *is* the penalty

ScoredEdges:
  edges : dict[tuple[str, str], ScoredEdge]   # keyed (from_track_id, to_track_id).
                                                # A missing key means "no viable
                                                # junction exists" — path_search must
                                                # treat it as no edge, never as cost 0
```

`CostTerms` is **not decoration.** Two things depend on retaining it: D5's health
metric (§9) and D26's tuning problem — weights *"determine output quality entirely and
cannot be tuned until the eval harness exists"*, so being able to attribute a cost to
its terms is what makes that tuning tractable at all. It is also the feature vector
any future weight-fitting would need (§12).

**`Junction` and `Envelope` move to `common/contracts/schema.py`.** They were
previously owned by `render/transition_renderer/schema.py` (that spec §2), with
`playlist_renderer` importing them — *"one contract, one owner"*. That ownership
predates this module, and `Junction` is now produced by `processing/` and consumed by
`render/`; leaving it in `render/` would make planning depend on the render layer, and
moving it into `processing/` would only invert the same problem. A neutral shared
location leaves neither layer depending on the other. `StereoPCM` stays in
`render/transition_renderer/schema.py` — it is audio-only and never crosses into
planning.

The moved contract is unchanged, field for field:

```
Junction:
  from_track      : str
  to_track          : str
  cue_out             : float          # seconds into A (D20 — all positions seconds)
  cue_in                : float          # seconds into B
  strategy_tier           : int            # 2 | 3 | 4 | 5 — an int, never a name (§6)
  ramp_bars                 : int            # 0 in v1 (D18/D19)
  length_bars                 : int            # §6
  rate_a                        : float          # 1.0 always in v1 (§6)
  rate_b                          : float          # tier 2 only (D19)
  gain_db_a                         : float          # 0.0 here — playlist_renderer owns
  gain_db_b                           : float          # 0.0 here
  envelopes                             : list[Envelope]   # §6

Envelope:
  target       : "low" | "mid" | "high" | "crossfader"
  side           : "a" | "b"
  breakpoints      : list[tuple[float, float]]   # (bar_offset, value)
```

`MixPlan`/`TrackRef` stay in `playlist_renderer`'s spec for now — they are produced by
`path_search`, which doesn't exist yet, so moving them would restructure a spec for a
module nobody has written (§12 Q6).

---

## 3. Bar mapping and Camelot arithmetic (`bars.py`, `camelot.py`)

Three cost terms index `Track.energy_curve[]`/`vocal_mask[]`, which are **per-bar and
carry no timestamps**. `Track` does not carry `per_bar_features` (orchestrator spec
§1 — it is deliberately not forwarded from `RawFeatures`), so the mapping must be
reconstructed here.

```
position_to_bar(position: float, track: Track) -> int
  bar = bisect_right(track.downbeat_times, position) - 1
  clamp to [0, len(track.energy_curve) - 1]
```

This is **exact, not an approximation**: `feature_extractor`'s
`compute_per_bar_features` enumerates bars as consecutive downbeat pairs
(`spectral_features.py`: `zip(downbeats[:-1], downbeats[1:])`), yielding
`len(downbeat_times) - 1` bars, and `energy_curve[]`/`vocal_mask[]` are index-aligned
to that same list. A track with fewer than two downbeats has no bars at all — such a
track has no usable curve and is skipped as a pair member (§5).

**Camelot distance** (`camelot.py`) implements design-v3 §1.2's table. `Track.key` is
a Camelot string (`"8A"`); parse to `(number ∈ 1..12, letter ∈ {A, B})`.

```
wheel_distance(n_a, n_b) = min(|n_a - n_b|, 12 - |n_a - n_b|)   # the wheel wraps

key_distance:
  same number, same letter                   -> 0.00   # same key
  wheel_distance == 1 and same letter          -> 0.25   # perfect fifth
  wheel_distance == 0 and letters differ         -> 0.25   # relative major/minor
  wheel_distance == 1 and letters differ           -> 1.00   # the diagonal — §1.2:
                                                              # "avoid the diagonal"
  otherwise                                          -> min(1.0, wheel_distance / 6.0)
```

An **unparseable or null `key` on either side scores `0.5`, never `0.0`** — a missing
key is *unknown*, not *a perfect match*, and scoring it 0 would make untagged tracks
the cheapest pairings in the pool. `key` is nullable by contract precisely because
estimators produce *"confident but meaningless labels"* on raga-influenced material
(§1.2), which is also why it stays a penalty and never a gate (D10).

---

## 4. Cost terms (`cost.py`)

```
junction_cost = w_tempo    · tempo
              + w_key        · key
              + w_energy       · energy
              + w_vocal          · vocal
              + w_cue_kind         · cue_kind
              + w_phrase             · phrase
              + tier_penalty[tier, template_a, template_b]
```

Every term is normalised to `[0,1]` **at construction** (**D26**) — that is what makes
the weights interpretable as relative importance rather than arbitrary scale factors,
and D26 is explicit that this "shortens the blind period" before the eval harness
exists. `tier_penalty` is added **unweighted**: per **D5** it is not one signal among
several, it *is* the penalty that makes the ladder mean *"this pairing is worse, pick
someone else."*

D3 names five edge-cost terms (*tempo distance, key distance, energy delta,
vocal/structure compatibility, strategy tier*). This spec adds **`cue_kind`** and
**`phrase`**, both grounded in existing decisions rather than invented: without
`cue_kind` nothing in the argmin would prefer a `hook_exit` over a `time_boxed`
fallback, leaving D27's stated preference order unused; and D10 explicitly names
*"phrase strength"* among the soft constraints that must be scored rather than gated.

| Term | Definition | Grounding |
|---|---|---|
| `tempo` | `min(1, ratio / tempo_full_cost_ratio)` where `ratio = |bpm_a − bpm_b| / bpm_a`, default full-cost ratio `0.06` (§1.6's ±6% audible-artifact threshold) | D3, §1.6 |
| `key` | §3's `key_distance` | §1.2, D10 |
| `energy` | `|energy_curve_a[out_bar] − energy_curve_b[in_bar]|` over `energy_full_cost_delta`, clamped to 1. **Absolute, not signed** — deliberate shaping of rise and fall is the path-level arc (§1.10), so an edge must not prefer "louder next" on its own | D3, D23 |
| `vocal` | **D22 verbatim**: `vocal_mask_a[out_bar] + vocal_mask_b[in_bar]`, each side first normalised against that track's own 95th-percentile `vocal_mask` (the raw signal is unbounded band energy), then halved to land in `[0,1]` | **D22** |
| `cue_kind` | mean of the two sides' preference costs (below) | D27, D12 |
| `phrase` | `1 − strength` of the nearest `PhraseBoundary` within `phrase_tolerance_s` of the cue, per side, averaged; `1.0` when no boundary is near | D8, D10 |
| `tier_penalty` | §5's template-conditioned table | **D5**, §1.9 |

**Cue-kind preference costs** map **D27**'s preference *order* onto the real `CueKind`
enum. D27's prose names do not all exist as kinds — there is no `intro` or
`grid_start`; they surface as `intro_end` and `first_downbeat` — so the mapping is
written against `cue_derivation/schema.py`, not against D27's wording:

```
cue_out:  hook_exit                        -> 0.00   # D27: preferred — musical
          outro_start                        -> 0.33   # never fires in v1 (cues.py)
          chorus_end | interlude_start         -> 0.50
          time_boxed                            -> 1.00   # guaranteed fallback

cue_in:   intro_end | riser_start           -> 0.00   # real DJ padding (edm)
          hook_in                             -> 0.33   # when it does not (film)
          chorus_start                          -> 0.50
          first_downbeat                          -> 1.00   # fallback
```

**Confidence handling — this spec decides; the design doc is silent.** Every
confidence-bearing input blends its term toward a neutral `0.5`, never toward `0.0`:

```
term = c · raw_term + (1 - c) · 0.5
```

Shrinking an unreliable measurement toward zero would make *unmeasurable* tempo or key
look like a *perfect* match, which is the opposite of what low confidence means — and
it would systematically favour exactly the tracks whose analysis failed. Applied with
`min(bpm_confidence_a, bpm_confidence_b)` for `tempo`, `min(key_confidence_a,
key_confidence_b)` for `key`, and each `Cue.confidence` for its side of `cue_kind`.
This keeps every confidence soft (**D10**) rather than letting it gate; the one place
confidence becomes a hard exclusion is `status`, which `cue_derivation` already
decided (D7).

**Half- and double-time** (`allow_half_double_time`, default on): the `tempo` ratio is
computed against `bpm_b`, `2·bpm_b` and `bpm_b / 2`, and the smallest is taken. A
90 BPM track against a 180 BPM one is a musically standard pairing that the plain
ratio would price at maximum cost. The design doc does not mention this (§12 Q4).

---

## 5. Tier eligibility and penalties (`tiers.py`)

**D10 permits exactly three hard constraints** (no track repeats; no cue before
`grid_start`; `status: excluded` omitted). This module adds no new *edge*-level gate —
everything musical stays a penalty — but two rules make individual **tiers** ineligible
for a given pair:

```
pool:      drop every track with status == "excluded"          # D7, D10
           drop every track with fewer than 2 downbeat_times   # §3 — no bars, no curve
edges:     no self-edges (A -> A)

tier 2 is ineligible for a pair when:
  |bpm_a - bpm_b| / bpm_a > tier2_max_bpm_ratio    # D19, default 0.03
  or  A.status == "cut_only"  or  B.status == "cut_only"       # below
```

**D19's ±3% is a gate on a tier, not on an edge** — the pairing survives at tiers 3/4/5
(*"the planner falls to tier 3 (cut, no lock needed) or tier 5"*). Tier 3 has no tempo
constraint at all, which is exactly why a wide-BPM pair can still be a cheap edge
(§1.6: *"at a hard cut, tempo can jump — the cut masks it"*).

**`cut_only` restricts a track to tiers 3–5.** The design doc never names an
enforcement site for `cut_only`; `cue_derivation` §8 says it is *"a signal consumed by
the edge builder to restrict which strategy tiers are eligible for this track's
junctions"*, and this is that site. Tier 2's bass swap is the one v1 tier requiring a
trustworthy phrase grid and downbeats — precisely what a `cut_only` quarantine says is
missing (D7).

**Tier penalties**, conditioned on `structure_template` per **D5** and §1.9's *"two
vocabularies, not one ladder"*. The ladder encodes *how much analysis a technique
needs*, which is not the same as *how good it sounds*: for film masters, tiers 3–4 are
the correct professional idiom, not a degradation, so a flat penalty would push the
planner away from the right answer.

```
tier_penalties_edm  = { 2: 0.00, 3: 0.30, 4: 0.50, 5: 0.70 }   # standard ladder
tier_penalties_film = { 2: 0.10, 3: 0.00, 4: 0.10, 5: 0.50 }   # film/unknown idiom

tier_penalty[tier, a, b] = mean(table(a.structure_template)[tier],
                                table(b.structure_template)[tier])
```

The doc's table conditions on *a* template without saying whose, and leaves a
`film → edm` edge undefined. **Averaging the two sides** is this spec's resolution: it
defines every mixed pair, stays symmetric in the templates, and degenerates to the
doc's table exactly when both sides agree (§12 Q1).

**`enabled_tiers`** (default `{2, 3, 4, 5}`) restricts the search. It exists because
`transition_renderer` currently implements **only tier 3** — passing
`enabled_tiers={3}` yields plans that render end-to-end today, while the default keeps
D5's tier-penalty machinery live and D5's health metric measurable. Nothing in this
module changes when the renderer catches up. Emitting a plan the renderer cannot yet
execute is safe by design: it raises `UnregisteredStrategyError` loudly rather than
silently substituting a different-sounding transition (`transition_renderer` §4).

---

## 6. Junction plan construction (`junction_plan.py`)

Turns the winning `(cue_out, cue_in, tier)` combination into the stored `Junction`.

```
from_track / to_track   = A.id / B.id
cue_out / cue_in          = the winning cues' positions        # seconds (D20)
strategy_tier               = the winning tier                   # int, never a name
ramp_bars                     = 0                                  # always in v1 (D18/D19)
gain_db_a / gain_db_b           = 0.0                                # §1 — not ours to set
rate_a                            = 1.0                                # always (below)
rate_b                              = bpm_a / bpm_b  for tier 2, else 1.0
length_bars                           = 0 (t3) | 16 (t2) | 4 (t4) | 8 (t5)
```

`rate_a` is **always** `1.0`: **D19** stretches *the incoming track* for its entire
appearance, so only side B carries a rate. `rate_b` is a single constant ratio — v1
has no ramping (D18 is explicitly v2, and `ramp_bars` stays 0 through the renderer's
Milestone B too).

`length_bars` is `0` for tier 3 — that is what degenerates the renderer's segment math
to a splice rather than a blend (`transition_renderer` §3), and tier 3 is a cut, not a
short crossfade. Tier 5's `8` is §1.9's *"high-pass A up and out over 8 bars"*. Tier
2's `16` follows §1.9's bass-swap procedure (swap at bar 8 of a 16-bar phrase) but is
configurable: **F8** warns that 16 does not divide 12, so on a 12-bar-phrased library a
swap starting on a boundary ends 4 bars into the next phrase (§12 Q7). Tier 4's `4` is
this spec's choice — the doc never gives echo-out a length.

**Tier 2 envelopes** transcribe design-v3 §5.2's worked bass-swap example directly,
as `(bar_offset, value)` breakpoints over the `length_bars` window:

```
Envelope(target="low",        side="b", breakpoints=[(0, 0.0), (8, 0.0), (12, 1.0)])
Envelope(target="low",        side="a", breakpoints=[(0, 1.0), (8, 1.0), (12, 0.0)])
Envelope(target="crossfader", side="a", breakpoints=[(0, 0.0), (12, 1.0)])
```

Read as: B's lows killed until bar 8 then ramped to unity over 4 bars; A's lows held at
unity until bar 8 then ramped to kill; crossfader travelling A→B across bars 0–12.
Tiers 3 and 4 emit `envelopes=[]`; tier 5 emits a single `high`/`a` ramp over its 8
bars. Tier 4's echo-out **cannot** be expressed in the current `Envelope` contract at
all — `target` has no delay member — so its delay stays the renderer's internal
business (§12 Q2).

---

## 7. Vectorised argmin (`build.py`)

**D4** sizes the full search at N=200 as *"≈128M scalar ops. Seconds in numpy, metadata
only."* The structure is a hybrid, vectorised where the size actually is:

1. **Track-level terms are dense `N×N`.** `tempo`, `key` and `tier_penalty` depend only
   on the pair, not on which cues are chosen — compute each as a full matrix once, up
   front. `tier_penalty` is `N×N×|tiers|`.
2. **Cue-level terms are a per-pair cube.** `energy`, `vocal`, `cue_kind` and `phrase`
   depend on the chosen cues, and cue lists are **ragged** (tracks have different cue
   counts) — which is exactly why this stays per-pair rather than one padded global
   tensor. Per pair, broadcast the `(n_out,)` and `(n_in,)` vectors into an
   `(n_out, n_in, n_tiers)` cube, add the pair's track-level scalars, mask out
   ineligible tiers (§5), then `argmin` over the flattened view.
3. **Recover the winning indices** with `unravel_index`, build the `Junction` (§6) and
   the `CostTerms` breakdown for that one combination only.

A pair contributes **no entry** to `ScoredEdges.edges` when either side has no cues on
the relevant side, or when every tier is ineligible — never a sentinel cost.

---

## 8. Orchestration & config (`build.py`, `config.py`)

```
EdgeBuilderConfig:
  enabled_tiers          : frozenset[int]      # default {2,3,4,5}; {3} = renderable today (§5)
  w_tempo                  : float               # default 1.0
  w_key                      : float               # default 0.8
  w_energy                     : float               # default 0.6
  w_vocal                        : float               # default 1.2 — D22 "heavy penalty"
  w_cue_kind                       : float               # default 0.5
  w_phrase                           : float               # default 0.5
  tier_penalties_edm                   : dict[int, float]    # §5
  tier_penalties_film                    : dict[int, float]    # §5
  tempo_full_cost_ratio                    : float               # default 0.06 (§1.6)
  tier2_max_bpm_ratio                        : float               # default 0.03 (D19)
  energy_full_cost_delta                       : float               # default 6.0 LU
  phrase_tolerance_s                             : float               # default 0.5
  length_bars_tier2 / _tier4 / _tier5              : int                 # 16 / 4 / 8 (§6)
  allow_half_double_time                             : bool                # default True (§4)

build_edges(tracks: list[Track], config: EdgeBuilderConfig) -> ScoredEdges
  1. filter the pool — excluded, bar-less                        # §5
  2. precompute per-track cue/bar/normalisation arrays            # §3
  3. build the N×N track-level term matrices                       # §7 step 1
  4. per ordered pair: eligible tiers -> cue cube -> argmin          # §5, §7
  5. build Junction + CostTerms for each winner                       # §6, §2
  6. assemble ScoredEdges                                              # §2
```

Plain non-frozen `@dataclass` with defaults, matching every sibling config
(`FeatureExtractorConfig`, `CueDerivationConfig`, `IngestionConfig`).

**No version constant**, unlike `feature_extractor`'s `extractor_version` or
`cue_derivation`'s `cue_derivation_version` — the same divergence `orchestrator`'s
spec §2 made, and for the same reason: those versions exist to invalidate a *cached
artifact*, and this module caches nothing. The config object itself is the
reproducibility record, and is already what design-v3 §5.2's `MixPlan.config` carries
(`tier_penalties`, `weights`).

> **Every numeric default above is provisional.** **D26** is explicit that weights
> *"determine output quality entirely and cannot be tuned until the eval harness
> exists."* They are starting points chosen to be interpretable against `[0,1]`
> terms — not tuned values, and not to be read as settled (§12 Q3).

---

## 9. Testing strategy

- **Every test is a millisecond, no-audio, JSON-fixture test** (D2). `conftest.py`
  builds synthetic `Track` objects with hand-set cues, curves and downbeats — reusing
  `ingestion.orchestrator.schema.Track` and `ingestion.cue_derivation.schema.Cue`
  directly, never redefining them (the convention `cue_derivation`'s own conftest
  established for `RawFeatures`).
- `test_bars.py`: `position_to_bar` against known downbeat lists — before the first
  downbeat, exactly on one, past the last, and the fewer-than-two-downbeats case.
- `test_camelot.py`: each row of §3's distance table; wheel wrap-around (12→1);
  null/unparseable key scoring `0.5` and never `0.0`.
- `test_cost.py`: each term isolated at its endpoints; D22's formula reproduced
  exactly; every term inside `[0,1]` (D26) including on adversarial inputs; the
  confidence blend moving toward `0.5` and never toward `0.0`; half/double-time
  folding.
- `test_tiers.py`: D19's ±3% making tier 2 ineligible *while tiers 3/4/5 survive*;
  `cut_only` on either side removing tier 2; `excluded` tracks absent from the pool;
  penalty averaging across mismatched templates.
- `test_junction_plan.py`: `rate_a == 1.0` always and `rate_b` only for tier 2;
  `ramp_bars == 0`; per-tier `length_bars`; the tier-2 envelope breakpoints matching
  §6 exactly; `gain_db_*` left at `0.0`.
- `test_build.py`: the argmin actually being the minimum over a small hand-enumerable
  grid; the stored `plan` corresponding to the winning combination (D4's "store the
  argmin"); `cost` equalling the sum of its `terms`; pairs with no viable junction
  **absent from** `edges` rather than present with a sentinel; no self-edges.
- `schema.py`/`config.py` have no dedicated test files — plain data classes, no
  behaviour.

---

## 10. File layout

```
src/common/contracts/
  __init__.py             # public exports: Junction, Envelope
  schema.py                # Junction, Envelope (§2 — moved from transition_renderer)

src/processing/edge_builder/
  __init__.py             # public exports: ScoredEdge, ScoredEdges, CostTerms,
                           # EdgeBuilderConfig, build_edges
  schema.py                # ScoredEdge, CostTerms, ScoredEdges (§2)
  config.py                 # EdgeBuilderConfig (§8)
  bars.py                     # position_to_bar() (§3)
  camelot.py                    # parse + key_distance() (§3)
  cost.py                         # the seven terms (§4)
  tiers.py                          # eligibility + penalties (§5)
  junction_plan.py                    # build the winning Junction (§6)
  build.py                              # build_edges() — vectorised argmin (§7, §8)
  examples/
    example_build_edges.py                # manual smoke script over a real ingested
                                           # pool — gitignored, not part of the suite

tests/processing/edge_builder/
  conftest.py               # synthetic Track builders — reuse orchestrator's and
                             # cue_derivation's schemas directly, never redefine
  test_bars.py                # §9
  test_camelot.py               # §9
  test_cost.py                    # §9
  test_tiers.py                     # §9
  test_junction_plan.py               # §9
  test_build.py                         # §9
```

`src/processing/edge_builder/examples/` needs a `.gitignore` entry at implementation
time, alongside the three sibling `examples/` lines already there.

---

## 11. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| Choosing the transition type *after* path search | Tier selection inside the argmin (§5, §7) | **D4**'s corollary: otherwise the tier penalty cannot influence which pairings get picked, which is the entire mechanism D5 relies on |
| Hard gates on key, vocal density, or tempo | Weighted penalties (§4), with tier-level gates only where D19 demands one (§5) | **D10**: with a modest pool and unreliable detection a strict gate can leave the search with no legal successor, and the failure is *invisible* — a shorter mix, not an error. Bollywood material is 70–80% vocal, so a hard vocal gate can empty a track's cue set and silently drop it |
| Scoring a null `key` as `0.0` | `0.5`, neutral (§3) | A missing key is unknown, not perfect. Scoring it 0 would make untagged tracks systematically the cheapest pairings in the pool |
| Plain nested-loop scoring | Dense `N×N` matrices for track-level terms + per-pair cue cubes (§7) | D4's own framing (*"seconds in numpy"*); the hybrid keeps the ragged cue lists workable without padding the whole search into one tensor |
| Storing runner-up junctions per edge | The argmin only (§2) | **D4** says store the argmin. Alternatives can be *regenerated* on demand — planning is metadata-only and millisecond-fast (D2) — so persisting them buys nothing |
| A `edge_builder_version` constant | The config object as the reproducibility record (§8) | Sibling versions exist to invalidate cached artifacts; this module caches nothing. Same divergence `orchestrator`'s spec §2 made |
| Keeping `Junction` in `render/transition_renderer/schema.py` | `common/contracts/` (§2) | `Junction` is now produced by `processing/` and consumed by `render/`; leaving it in `render/` makes planning depend on the render layer, and moving it into `processing/` merely inverts that. Neutral ownership leaves neither depending on the other |
| Training the junction cost from an external DJ-mix corpus | Hand-tuned weighted sum (§4); learn the constants later from first-party feedback if ever (§12) | §6's ML table says **"Never (D14)"** for edge cost. The available data is also the wrong shape three ways: it is overwhelmingly Western 4/4 club material, whose idiom §1.9 says is actively wrong for film masters; it is positives-only (what a DJ did, never what they rejected), so a ranker learns "real vs. random" rather than "good vs. slightly worse"; and it supervises placement within a continuous set, not pairwise junction quality. This rejects the **external-corpus** route specifically, not feedback-driven weight fitting |
| Full RL (policy gradient over set construction, delayed whole-mix reward) | Per-junction preference learning, if anything (§12) | A whole-mix reward makes credit assignment across ~14 junctions brutal and needs orders of magnitude more feedback than a human will produce, for a model that is no longer interpretable (D14). A sequential formulation, if it ever earns its place, targets D3's path-level λ/μ/ν terms — `path_search`'s objective, not this module's |

---

## 12. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | Whose `structure_template` should condition the tier penalty? §5 averages A's and B's; design-v3 §1.9's table conditions on *a* template without saying whose, and never defines a `film → edm` edge | Tier-penalty correctness on mixed-template pairs — low blast radius (the average degenerates to the doc's table whenever both sides agree) |
| Q2 | Tier 4's echo-out has no expressible `Envelope.target` — the enum is `low`/`mid`/`high`/`crossfader`, with no delay member (§6) | Whether tier 4's delay stays renderer-internal or `Envelope` gains a target, which would be a `common/contracts` change once `transition_renderer` Milestone B starts |
| Q3 | Every weight and tier penalty in §8 is an untuned starting point — **D26** says they cannot be tuned until the eval harness (§9 of design-v3) exists | Output quality, entirely. Nothing structural — the shape is right, the numbers are guesses |
| Q4 | Half/double-time folding (§4) is this spec's invention; design-v3 never mentions whether 90↔180 BPM pairs should be treated as close | Whether `allow_half_double_time` should default on; trivially reversible via config |
| Q5 | `Envelope.side` is meaningless for `crossfader`, which is a single control, not a per-side one (§6 sets it to `"a"` by convention) | Cosmetic today; worth settling before Milestone B interprets it |
| Q6 | Should `MixPlan`/`TrackRef` join `Junction` in `common/contracts/` when `path_search` is specced (§2)? | Where `path_search`'s output contract lives — deferred deliberately until that module exists |
| Q7 | `length_bars_tier2 = 16` against **F8**'s warning that 16 does not divide 12-bar phrasing, so a swap starting on a boundary ends 4 bars into the next phrase | Tier-2 musicality on a 12-bar-phrased library; design-v3 Q9 already tracks the same question for the library as a whole |
| Q8 | Once the eval harness exists, is it worth fitting the seven `w_*` weights and the tier-penalty tables from collected **pairwise** preferences — a regularised ranking fit that keeps the formula and learns only its constants, with §8's hand-tuned defaults as the prior — rather than continuing to hand-tune? | Nothing today: both hand-tuning and fitting are gated on the same harness. Recorded because it is the most likely direction this module evolves, and because it stays D14-compatible (`junction_cost = Σ wᵢ·termᵢ` is unchanged; determinism, millisecond re-runs, JSON-fixture tests and per-term explainability all survive). §2's `CostTerms` is the feature vector it would need, and D26's `[0,1]` normalisation is what would make regularising toward the prior meaningful |
