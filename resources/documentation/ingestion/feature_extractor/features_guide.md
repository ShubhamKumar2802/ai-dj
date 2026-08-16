# Feature extractor — a plain-language guide to the output

`spec.md` is the authoritative contract for `ingestion/feature_extractor` — field
types, algorithms, design rationale. This is a companion doc for reading the *output*:
what a `RawFeatures` JSON object (the thing `get_or_extract_features` returns, and
`examples/example_extract.py` writes to `examples/outputs/*.json`) actually means,
field by field, in plain terms. No spec-amendment lifecycle applies to this file — it's
explanatory, not a contract.

Every `RawFeatures` object describes one track, using only signal measurements — no
musical *decisions* have been made yet (see §9 below). Section numbers in parentheses
point back to the relevant part of `spec.md`.

---

## 1. Identity

| Field | What it means |
|---|---|
| `content_hash` | SHA-256 of the file's raw bytes. Together with `feature_extractor_version`, this is the cache key (§5) — same file + same extractor version = instant cache hit, no reprocessing. |
| `feature_extractor_version` | Hand-bumped version of this module's extraction logic. Changing an algorithm and forgetting to bump this is a silent-staleness risk (§5) — old cached results keep getting served. |
| `source_path` | Where the file was loaded from. Informational only — never part of the cache key, so renaming a file doesn't force reprocessing. |
| `duration` | Track length in seconds. |
| `sample_rate` | Always 48000 — every track is resampled to this canonical rate at load time (D25), regardless of the source file's native rate. |

---

## 2. Tempo & rhythm

| Field | What it means |
|---|---|
| `bpm` | Estimated tempo, stored as a raw float — **never rounded**. Flooring a BPM like 128.4 to 128 drifts the beat grid by over a second across a four-minute track (§1.1). |
| `bpm_confidence` | 0–1. Essentia's own confidence, discounted if an independent second opinion (librosa) disagrees on the tempo. High = both trackers agree; low = they diverged (§6). |
| `beat_times` | Every detected beat, as timestamps in seconds. |
| `downbeat_times` | Every 4th beat — i.e. where each bar starts. A subset of `beat_times`. |
| `downbeat_confidence` | 0–1, and often genuinely low. Without a dedicated downbeat tracker, this module guesses *which* of the 4 beats in a bar is "beat 1" by looking for a bass/kick accent — a much weaker signal than the tempo estimate itself (§6). A low value here isn't a bug; it's an honest admission that this particular track doesn't have a clean bass accent to lock onto. |
| `beats_per_bar` | Always 4 in v1 (assumes 4/4 time). |

**Why `downbeat_confidence` matters downstream:** once `ingestion/cue_derivation` exists,
a low value here is expected to push a track toward lower-information transition
techniques — specifically, it costs eligibility for the tier-2 "bass swap" transition
(which needs a confidently phase-locked grid), not correctness. Tier 3 ("cut on the 1")
only needs *one* confident downbeat and is already the designed-for technique for film
material, not a fallback (§1.9) — so a low `downbeat_confidence` mostly just means a
track leans on the workhorse tier instead of the fancier one.

---

## 3. Per-bar feature stack (`per_bar_features`)

One entry per **bar** — the span between two consecutive detected downbeats. A track
with 136 downbeats produces 135 bars (the gaps between them; no entry before the first
or after the last downbeat).

Each bar has:

| Field | What it means |
|---|---|
| `bar_index` | 0-based position in the sequence. |
| `start_time` | Where this bar begins, in seconds. |
| `rms` | Loudness of this bar, on a linear scale (root-mean-square amplitude). Rising RMS across consecutive bars usually means a build-up; falling RMS means the track is thinning out or reaching a breakdown. |
| `spectral_centroid` | "Brightness," in Hz — where the energy of the sound is concentrated across the frequency spectrum. Higher = more high-frequency content (hi-hats, cymbals, bright synths); lower = bass-heavy or muffled. |
| `spectral_flux` | How much the frequency content is changing from moment to moment within the bar. High flux = busy/percussive/transient-rich; low flux = sustained, steady-state sound (a held chord, a drone). |
| `low_band_energy` | Energy in the sub-bass/bass/kick range (~20–250Hz). |
| `high_band_energy` | Energy in the cymbals/hats/air range (~4kHz and up). |
| `chroma_vector` | 12 numbers, one per pitch class (C, C#, D, ... B — order is internal, not guaranteed to start at C). Shows how much of each note is present harmonically in this bar. Used for harmonic-mixing decisions later. |

A rough read: an intro building into a first chorus typically shows `rms` and
`low_band_energy` both climbing over several consecutive bars, `spectral_centroid`
often rising too as more instruments/frequencies enter. This is a *general* pattern,
not a rule — every track is different.

---

## 4. Loudness

| Field | What it means |
|---|---|
| `lufs_integrated` | The track's overall perceived loudness, in LUFS (the broadcast/streaming loudness standard). More negative = quieter. Modern "loudness war" masters often sit around −8 to −12 LUFS; older or more dynamic masters can be −16 LUFS or quieter (§1.8). |
| `true_peak` | The loudest true (reconstructed, oversampled) peak in the signal, in dBTP. **Can legitimately be positive** (above 0 dBTP) on heavily limited/loud masters — oversampling reveals inter-sample peaks that exceed what the raw digital samples show. This is a real, well-known mastering phenomenon, not a measurement bug. |
| `energy_curve` | One short-term-loudness value (LUFS) per bar, aligned with `per_bar_features`. This is *not* a raw Essentia output taken as-is — it's built by averaging finer-grained loudness readings within each bar's time window, specifically so it lines up with bar boundaries (§8). Use it the same way as `rms` above: a rising curve usually tracks a build-up. |

---

## 5. Vocals

| Field | What it means |
|---|---|
| `vocal_band_energy` | One value per bar: raw energy in the 300Hz–3kHz band, aligned with `per_bar_features`. This band is a cheap proxy for vocal presence (it also catches strings, brass, and lead synths — over-detection is the accepted tradeoff, §9). **This is raw signal only** — no thresholding or "is this vocal or not" decision has been made. Turning this into an actual cost/penalty is `cue_derivation`'s job, not this module's. |

---

## 6. Harmony

| Field | What it means |
|---|---|
| `key` | The track's estimated musical key, in **Camelot notation** — a number 1–12 (position on a wheel of fifths) plus a letter, `A` for minor or `B` for major (e.g. `8A` = A minor, `8B` = C major). Two keys a fifth apart differ by ±1 in number; the relative major/minor of a key shares the same number with the opposite letter. Nullable — can be `None` if estimation fails entirely (§1.2). |
| `key_confidence` | 0–1, or `None` if `key` is `None`. |

**Why key detection sometimes looks "wrong":** it's common for an estimator to report
the *relative* major when the track is actually minor (or vice versa) — same position
on the wheel, different letter. That's a normal mode ambiguity in key detection, not an
error, which is exactly why key is treated as a soft, nullable score and never a hard
gate anywhere downstream (D10).

---

## 7. Risers

| Field | What it means |
|---|---|
| `riser_candidates` | A list of `{start_time, resolution_time, confidence}` triples. A "riser" is a rising sweep/build effect — spectral brightness climbs steadily and then resolves into a sharp transient (a cymbal crash, a drop, a hit). `start_time` is where the rise begins, `resolution_time` is where it lands. |

This is a **candidate list, not a decision** — several candidates across a track is
normal and expected. Nothing in `feature_extractor` picks which one (if any) actually
becomes a usable mix cue point; that filtering is `cue_derivation`'s job.

---

## 8. What's deliberately not here yet

`RawFeatures` is pure signal measurement — no cue points, no phrase grid, no song
structure labels, no `status` (quarantine) field. All of that belongs to
`ingestion/cue_derivation`, which is specced but not yet implemented. `cue_derivation`
is what will read a `RawFeatures` object like this one and turn it into a `Track` —
the thing that actually knows where to cut in and out of a song.
