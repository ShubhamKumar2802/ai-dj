# Spec Delta

## Purpose

A sandbox experiment that tests whether a vision-capable LLM, shown DJ-style 3-band waveform images of two tracks, can choose a good transition point between them. Its results are informative only and never feed the production pipeline.

## ADDED Requirements

### Requirement: Pairs are configured, not discovered
The experiment SHALL run on track pairs listed in its config file, each naming track A and track B by audio file path. A run SHALL process every configured pair independently, so that one failing pair does not stop the others.

#### Scenario: Two configured pairs
- **WHEN** the config lists Rock Tha Party → Marjaani and Zingaat → Munni Badnaam Hui
- **THEN** the run produces one set of outputs per pair, in its own folder named after the pair

#### Scenario: Missing audio file
- **WHEN** a configured track path does not exist
- **THEN** that pair is reported as failed with the missing path, and the remaining pairs still run

### Requirement: Measured facts come from the cached feature extractor
The experiment SHALL take each track's duration, BPM, integrated LUFS and downbeat times from the existing feature extractor (cached by content hash), and SHALL NOT compute its own beat or tempo estimates.

#### Scenario: Track already analysed
- **WHEN** a track's features are already cached
- **THEN** the experiment uses the cached duration, BPM, LUFS and downbeats without re-running analysis

### Requirement: Bars are numbered from the downbeats
Bar N (counting from 1) SHALL start at the Nth detected downbeat. The same numbering SHALL be used on the images, in the LLM's answers, for rendering, and for scoring.

#### Scenario: Bar to time
- **WHEN** a track's downbeats are at 0.52 s, 2.70 s, 4.88 s
- **THEN** bar 1 starts at 0.52 s and bar 3 starts at 4.88 s

### Requirement: 3-band waveform tiles
For each track the experiment SHALL render PNG images showing low, mid and high frequency band envelopes as three separate stacked lanes on a shared time axis. Each track SHALL be split into tiles of a fixed duration, and neighbouring tiles SHALL overlap by a fixed amount.

#### Scenario: Tiling a track
- **WHEN** a 208 s track is rendered with 60 s tiles and 8 s overlap
- **THEN** the tiles together cover 0 s to 208 s, and each tile after the first starts 8 s before the previous tile ends

### Requirement: Consistent scale within a pair
Both tracks of a pair SHALL be drawn at the same pixels-per-second and the same per-band height scale, so that widths and band heights are directly comparable across the two tracks.

#### Scenario: Louder low band
- **WHEN** track A's low band is twice as energetic as track B's
- **THEN** A's low lane is drawn visibly taller than B's on the same scale, not normalised to the same height

### Requirement: Tile annotations
Every tile SHALL show:
- a header with track label (A or B), track name, BPM, duration, integrated LUFS, and tile index with its time range
- two rows of x-axis labels, bar numbers and mm:ss
- gridlines through all three lanes: a light one at every bar and a stronger one every 4 bars

#### Scenario: Reading a tile
- **WHEN** a tile covering 1:00–2:00 of track A is produced
- **THEN** it shows the "A" label, track name, BPM, duration, LUFS, the tile's index and range, bar numbers and mm:ss under the axis, and bar/4-bar gridlines

### Requirement: What the LLM is given
The experiment SHALL send one multimodal request per pair, containing both tracks' tiles and, for each track, its duration, BPM and integrated LUFS. It SHALL NOT send the musical key, phrase grid, or any existing cue-point or hook estimates. The prompt SHALL frame the transition as one junction in a megamix that plays a short, high-energy excerpt of each track, so that leaving A at its end or entering B at its start is not the default.

#### Scenario: Prompt contents
- **WHEN** the request for a pair is built
- **THEN** it includes all tiles of A and B and the three measured facts per track, and contains no key or cue-point values

#### Scenario: Megamix framing
- **WHEN** the request for a pair is built
- **THEN** the prompt states that only a short excerpt of each track is played, and still contains no key or cue-point values

### Requirement: What the LLM must return
The LLM response SHALL contain:
- the exit bar in A and the entry bar in B, each with an mm:ss cross-check
- a suggested technique (one of cut, bass swap, echo out, filter fade, other)
- a suggested length in bars
- its reasoning
- free-text notes on what it sees in each track

The experiment SHALL save the raw response.

#### Scenario: Valid response
- **WHEN** the LLM returns exit bar 65 / 2:21 for A and entry bar 1 / 0:01 for B with technique "bass swap" over 8 bars
- **THEN** the response is saved and used to render the preview

### Requirement: Out-of-range or inconsistent answers are flagged, not fixed
If a returned bar does not exist in its track, the pair SHALL be reported as failed with the reason, and no preview SHALL be rendered. If a bar's mm:ss cross-check differs from that bar's start time by more than one bar's duration, the experiment SHALL record the disagreement and still use the bar.

#### Scenario: Bar beyond track end
- **WHEN** the LLM returns exit bar 200 for a track with 95 bars
- **THEN** the pair is reported as failed with "exit bar 200 out of range (1–95)" and no preview is written

#### Scenario: Bar and time disagree
- **WHEN** the LLM returns bar 65 with mm:ss 1:40, but bar 65 starts at 2:21
- **THEN** the report records a 41 s disagreement and the preview cuts at bar 65

### Requirement: Hard-cut audio preview
For each pair with a valid response, the experiment SHALL render a WAV preview using the existing tier-3 hard-cut renderer: track A cut at the start of its exit bar, joined to track B from the start of its entry bar. The preview SHALL include a configurable amount of audio before and after the cut. The suggested technique SHALL be recorded but not rendered.

#### Scenario: Preview window
- **WHEN** A exits at 141.0 s, B enters at 0.5 s, and the preview window is 20 s before and 20 s after
- **THEN** the WAV contains A from 121.0 s to 141.0 s followed by B from 0.5 s to 20.5 s

### Requirement: Scoring against hand-marked points
The experiment SHALL read an optional `ground_truth.yaml` giving, per pair, the user's exit time in A and entry time in B (mm:ss), a 1–5 rating and a note. For each hand-marked time it SHALL take the nearest bar and report how many bars the LLM's choice is from it.

#### Scenario: Scored pair
- **WHEN** the user marked A's exit at 2:20 (nearest bar 65) and the LLM chose bar 69
- **THEN** the report shows an exit error of +4 bars next to the user's rating and note

#### Scenario: No ground truth yet
- **WHEN** `ground_truth.yaml` is missing or has no entry for a pair
- **THEN** the report shows the LLM's choices and marks the score as "not marked"

### Requirement: Run summary
Each run SHALL write a human-readable summary listing, per pair, the LLM's choices (bars and times), the suggested technique and length, any flagged disagreements, the preview file path, and the score and rating when available.

#### Scenario: Summary after a run
- **WHEN** a run finishes with one pair succeeded and one failed
- **THEN** the summary shows the full result for the first pair and the failure reason for the second
