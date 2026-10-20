# vocal-free-transition-experiment Specification

## Purpose

A sandbox experiment that, for one pair of tracks A → B, finds vocal-free windows in A from its separated vocal stem, leaves A at the first such window after bar 32, enters B at its intro, and renders full-length mixed tracks with a hard-cut, a short-overlap, and a bass-swap transition. Its results are informative only and never feed the production pipeline.

## Requirements

### Requirement: One pair per run
A run SHALL process exactly one pair: track A then track B, each given as an audio file path. The pair SHALL come from the command line when given there, otherwise from the config file. The config's default pair SHALL be Subha Hone Na De → Lat Lag Gayee, the adhoc pair from the waveform experiment.

#### Scenario: Default pair
- **WHEN** the experiment runs with no pair on the command line
- **THEN** it processes Subha Hone Na De as A and Lat Lag Gayee as B, writing outputs to a folder named `Y7G-tYRzwYY__KxCjVIFxZNo`

#### Scenario: Pair on the command line
- **WHEN** two audio paths are passed on the command line
- **THEN** the first is A, the second is B, and the config's pair is ignored

#### Scenario: Missing audio file
- **WHEN** either path does not exist
- **THEN** the run stops before any separation with an error naming the missing path

### Requirement: Bar grid comes from the cached feature extractor
The experiment SHALL take each track's downbeat times, per-bar boundaries, BPM, duration and integrated LUFS from the existing feature extractor (cached by content hash), and SHALL NOT compute its own beat or tempo estimates. Bar N (counting from 1) SHALL start at the Nth detected downbeat. The same numbering SHALL be used in the windows, the exit, the report and the image.

#### Scenario: Bar to time
- **WHEN** a track's downbeats are at 0.52 s, 2.70 s, 4.88 s
- **THEN** bar 1 starts at 0.52 s and bar 3 starts at 4.88 s

### Requirement: A's vocal stem is separated once and cached
The experiment SHALL produce a vocal stem for track A with a pretrained source-separation model, and SHALL NOT separate track B. Stems SHALL be cached by the track's content hash together with a separator version that changes whenever the model or its settings change. A cached stem SHALL be reused without re-running separation.

#### Scenario: Re-run on the same audio
- **WHEN** the experiment runs twice on an unchanged A with unchanged separator settings
- **THEN** the second run reuses the cached stem and does not run separation

#### Scenario: Separator changed
- **WHEN** the separator model or its settings change between runs
- **THEN** the stale stem is not used and A is separated again

#### Scenario: Renamed file
- **WHEN** A's file is renamed but its audio content is unchanged
- **THEN** the cached stem is still reused

### Requirement: Per-bar vocal level
The experiment SHALL compute one vocal level per bar of A from its vocal stem, aligned 1:1 with the feature extractor's per-bar features. The value SHALL be non-negative, and higher SHALL mean more vocal.

#### Scenario: Silent stem
- **WHEN** A's vocal stem is silent throughout
- **THEN** every bar's vocal level is zero and the series has one entry per bar

#### Scenario: Series length
- **WHEN** A has 149 bars of per-bar features
- **THEN** its vocal level series has exactly 149 entries in the same bar order

### Requirement: Vocal-free windows
A bar SHALL count as vocal-free when its vocal level is below a configured threshold, set relative to A's own vocal level. A vocal-free window SHALL be a run of at least a configured minimum number of consecutive vocal-free bars, reported by first and last bar with their start and end times. A shorter run SHALL NOT be a window.

#### Scenario: Breath between lines
- **WHEN** a single bar dips below the threshold between two sung bars and the minimum is 2 bars
- **THEN** no window is reported for that bar

#### Scenario: Instrumental break
- **WHEN** bars 57–60 are all below the threshold and the minimum is 2 bars
- **THEN** one window covering bars 57–60 is reported, from the start of bar 57 to the end of bar 60

#### Scenario: Relative threshold
- **WHEN** two tracks have the same vocal pattern but one is mastered 10 dB quieter
- **THEN** both get the same windows

### Requirement: Exit point in A
The exit SHALL be the first bar of the earliest window in A whose first bar is after a configured bar, set to 32 in the shipped config, and that is at least as long as the configured overlap. The scenarios below use 32. The exit time SHALL be that bar's downbeat. If no window qualifies, the run SHALL fail with a reason, write no output audio, and SHALL NOT fall back to a point outside a window.

#### Scenario: First window after bar 32
- **WHEN** A has windows at bars 1–8, 41–42 and 73–80 and the overlap is 2 bars
- **THEN** the exit is bar 41, at bar 41's downbeat

#### Scenario: Window that started before bar 33
- **WHEN** A has a window covering bars 30–36 and another starting at bar 73
- **THEN** the exit is bar 73

#### Scenario: Window too short for the overlap
- **WHEN** A's first window after bar 32 is 2 bars long and the overlap is 4 bars
- **THEN** that window is skipped and the next qualifying window is used

#### Scenario: No usable window
- **WHEN** A has no window whose first bar is after bar 32
- **THEN** the run fails with a reason saying so, and no output audio is written

### Requirement: Entry point in B is its intro
The entry SHALL be B's first downbeat (bar 1). B SHALL play from there to its end in both outputs.

#### Scenario: Entry time
- **WHEN** B's first downbeat is at 0.31 s
- **THEN** both outputs continue with B's audio from 0.31 s

### Requirement: Hard-cut output track
The experiment SHALL write a full-length mixed track, A from its start to the exit time followed by B from its entry to its end, joined as a hard cut on the downbeat (strategy tier 3) through the existing transition renderer.

#### Scenario: Cut output length
- **WHEN** the exit is at 75.0 s and B is 247.0 s long with its first downbeat at 0.31 s
- **THEN** the hard-cut output is 75.0 + 246.69 = 321.69 s long (to the nearest sample)

### Requirement: Overlap output track
The experiment SHALL also write a full-length mixed track that starts B at its entry while A keeps playing from the exit time. For the configured overlap, measured in A's bars from the exit downbeat, it SHALL equal-power crossfade A out and B in, then continue with B to its end. Both tracks SHALL play at their original tempo.

#### Scenario: Overlap output length
- **WHEN** the exit is at 75.0 s, the overlap is 2 bars of A lasting 3.64 s, and B is 247.0 s long with its first downbeat at 0.31 s
- **THEN** the overlap output is 75.0 + 246.69 = 321.69 s long, and A's audio is present only up to 78.64 s

#### Scenario: A stays vocal-free in the overlap
- **WHEN** an overlap output is rendered
- **THEN** every bar of A that sounds during the overlap is a vocal-free bar

### Requirement: Bass-swap output track
The experiment SHALL also write a full-length mixed track with a bass swap that starts at the exit downbeat and lasts a configured, even number of A's bars (16 in the shipped config). B SHALL then continue to its end. The bass swap SHALL NOT be shortened or moved to fit inside A's vocal-free window.

#### Scenario: Bass-swap output length
- **WHEN** the exit is at 75.0 s, the bass swap is 16 bars of A lasting 29.09 s, and B is 247.0 s long with its first downbeat at 0.31 s
- **THEN** the bass-swap output is 75.0 + 246.69 = 321.69 s long, and A's audio is present only up to 104.09 s

#### Scenario: Odd length
- **WHEN** the config sets a 15-bar bass swap
- **THEN** loading the config fails with an error naming that setting

#### Scenario: Not enough of A left
- **WHEN** A has fewer bars after the exit than the bass-swap length
- **THEN** the bass-swap output is not written, the report gives that reason, and the cut and overlap outputs are still written

### Requirement: Bass-swap stages
During the bass swap each track SHALL be split at a configured crossover frequency into a low band and the rest:
- first half: A plays full; B's mids and highs fade in from silence, with B's low band muted
- on the downbeat at the halfway bar: A's low band is muted and B's low band comes in
- second half: B plays full; A's mids and highs fade out to silence by the end

#### Scenario: Swap on the halfway downbeat
- **WHEN** a 16-bar bass swap starts at A's bar 41
- **THEN** only A's low band sounds before A's bar 49 downbeat, and only B's low band sounds from that downbeat on

### Requirement: No tempo matching
The experiment SHALL play both tracks at their original tempo in every output, and SHALL NOT reject a pair because of its BPM difference. The input pair is assumed to be at about the same BPM.

#### Scenario: Different BPMs
- **WHEN** A is 132.0 BPM and B is 130.7 BPM
- **THEN** all three outputs are written with both tracks at their original tempo, and the drift is reported

### Requirement: Loudness matching
When loudness matching is enabled in the config, the experiment SHALL apply a constant gain to all of B's audio in every output, equal to A's integrated LUFS minus B's. A's audio SHALL be unchanged.

#### Scenario: Quieter B
- **WHEN** A is −8.1 LUFS, B is −12.5 LUFS, and matching is enabled
- **THEN** B's audio in every output is 4.4 dB louder than in its source file

### Requirement: Vocal lane image of A
The experiment SHALL write a PNG of A showing the per-bar vocal level, the threshold, the vocal-free windows shaded, bar 32 marked, and the exit bar marked, with bar numbers and mm:ss labels.

#### Scenario: Reading the image
- **WHEN** a run succeeds
- **THEN** the image shows A's windows, the threshold, the bar-32 line and the exit bar

### Requirement: Run report
The experiment SHALL write a report listing:
- both tracks' BPM and LUFS
- A's windows (bars and times)
- the exit bar and time, and B's entry time
- the gain applied to B and each output's peak level
- the output and image paths, or why the bass swap was skipped
- each output's rating and note from the ground-truth file

If the run fails, the report SHALL give the reason instead.

#### Scenario: Failed run
- **WHEN** A has no usable window
- **THEN** the report gives that reason and lists no output paths

#### Scenario: Not rated yet
- **WHEN** the ground-truth file has no rating for an output
- **THEN** the report shows it as not rated, and the run does not fail

### Requirement: Drift is reported
The report SHALL show the BPM difference and how far B's beat drifts against A's beat by the end of the overlap and by the end of the bass swap, in milliseconds.

#### Scenario: Drift reported
- **WHEN** A is 132.0 BPM, B is 130.7 BPM, the overlap is 2 bars and the bass swap is 16 bars
- **THEN** the report shows about 36 ms for the overlap and about 287 ms for the bass swap

### Requirement: Sandbox isolation
The experiment SHALL NOT change the feature extractor's cache, cue derivation, edge builder, path search or render module behaviour, and no production module SHALL import it. Its separation dependency SHALL live only in the experiments dependency group.

#### Scenario: Production install
- **WHEN** the project is installed without the experiments group
- **THEN** every production module imports and its tests pass without the separation library present
