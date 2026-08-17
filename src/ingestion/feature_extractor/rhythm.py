from dataclasses import dataclass

import essentia.standard as es
import librosa
import numpy as np

from ingestion.feature_extractor.loader import StereoPCM

BEATS_PER_BAR = 4  # hardcoded 4/4 in v1 (F8)

# Implementer-chosen band cutoffs — §1.7 references "lows"/"highs" without
# giving Hz numbers. Shared with spectral_features.py's low_band_energy/
# high_band_energy (spec §7) rather than redefined there.
LOW_BAND_HZ = (20.0, 250.0)  # sub-bass + bass/kick — what §6's downbeat
# phase heuristic below reads as "bass energy"
HIGH_BAND_HZ = (4000.0, 20000.0)  # cymbals/hats/air

# RhythmExtractor2013's own docstring: "the algorithm requires the sample
# rate of the input signal to be 44100 Hz in order to work correctly."
# Resampling only for this call is safe — its output (beat times, seconds)
# is sample-rate-independent, so this never leaks into the canonical 48kHz
# contract (D25).
_RHYTHM_EXTRACTOR_SAMPLE_RATE = 44100

# BeatTrackerMultiFeature's documented confidence range is [0, 5.32]
# (essentia.standard.BeatTrackerMultiFeature docstring) — not a guess.
_MAX_BEATS_CONFIDENCE = 5.32

# Relative BPM tolerance for the librosa cross-check, mirroring §1.6's
# ±6% audible-artifact threshold rather than an arbitrary new constant.
_BPM_AGREEMENT_TOLERANCE = 0.06

_DOWNBEAT_WINDOW_S = 0.1  # window around each beat read for low-band energy


@dataclass
class RhythmResult:
    bpm: float
    bpm_confidence: float
    beat_times: list[float]
    downbeat_times: list[float]
    downbeat_confidence: float
    beats_per_bar: int


def band_energy(signal: np.ndarray, sample_rate: int, band_hz: tuple[float, float]) -> float:
    """Mean magnitude spectrum energy of `signal` within `band_hz`."""
    if len(signal) == 0:
        return 0.0
    spectrum = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)
    low, high = band_hz
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return 0.0
    return float(np.mean(spectrum[mask]))


def _resample_mono(mono: np.ndarray, native_rate: int, target_rate: int) -> np.ndarray:
    if native_rate == target_rate:
        return mono
    resampler = es.Resample(inputSampleRate=native_rate, outputSampleRate=target_rate)
    return resampler(np.ascontiguousarray(mono, dtype=np.float32))


def _cross_check_discount(essentia_bpm: float, librosa_bpm: float) -> float:
    """1.0 when the two trackers agree, decaying to 0 as they diverge.

    Treats a 2x/0.5x octave difference as agreement too — beat trackers
    routinely disagree on which metrical level is "the" tempo (half-time/
    double-time), which is not the same kind of disagreement as an actually
    wrong beat grid.
    """
    if essentia_bpm <= 0:
        return 0.0
    candidates = (librosa_bpm, librosa_bpm * 2.0, librosa_bpm / 2.0)
    rel_diff = min(abs(c - essentia_bpm) / essentia_bpm for c in candidates)
    return max(0.0, 1.0 - rel_diff / _BPM_AGREEMENT_TOLERANCE)


def _detect_downbeats(
    mono: np.ndarray, sample_rate: int, beat_times: list[float]
) -> tuple[list[float], float]:
    """v1 downbeat phase heuristic (spec §6) — the real gap left by dropping
    madmom. For each of the 4 candidate phase offsets into `beat_times`,
    compute mean low-band energy at beats landing on that phase; pick the
    phase maximizing contrast against the other three; confidence is the
    normalized margin between the best and second-best phase. Honestly
    weaker than a real DBN tracker — this module's job is to report that
    weakness, not solve it.
    """
    if len(beat_times) < BEATS_PER_BAR * 2:
        return [], 0.0

    half_window = int(_DOWNBEAT_WINDOW_S * sample_rate / 2)

    def energy_at(t: float) -> float:
        center = int(t * sample_rate)
        start = max(0, center - half_window)
        end = min(len(mono), center + half_window)
        return band_energy(mono[start:end], sample_rate, LOW_BAND_HZ)

    phase_scores = []
    for phase in range(BEATS_PER_BAR):
        phase_beats = beat_times[phase::BEATS_PER_BAR]
        energies = [energy_at(t) for t in phase_beats]
        phase_scores.append(float(np.mean(energies)) if energies else 0.0)

    order = sorted(range(BEATS_PER_BAR), key=lambda i: phase_scores[i], reverse=True)
    best_phase, runner_up_phase = order[0], order[1]
    best_score, second_score = phase_scores[best_phase], phase_scores[runner_up_phase]

    downbeat_times = beat_times[best_phase::BEATS_PER_BAR]
    denom = best_score if best_score > 0 else 1.0
    downbeat_confidence = max(0.0, min(1.0, (best_score - second_score) / denom))

    return downbeat_times, downbeat_confidence


def detect_rhythm(pcm: StereoPCM) -> RhythmResult:
    mono = pcm.samples.mean(axis=1).astype(np.float32)

    mono_for_extractor = _resample_mono(mono, pcm.sample_rate, _RHYTHM_EXTRACTOR_SAMPLE_RATE)
    extractor = es.RhythmExtractor2013(method="multifeature")
    essentia_bpm, beat_times_arr, beats_confidence, _estimates, _intervals = extractor(
        mono_for_extractor
    )
    beat_times = [float(t) for t in beat_times_arr]

    librosa_tempo, _ = librosa.beat.beat_track(y=mono, sr=pcm.sample_rate)
    librosa_bpm = float(np.asarray(librosa_tempo).reshape(-1)[0])

    normalized_confidence = min(max(beats_confidence, 0.0) / _MAX_BEATS_CONFIDENCE, 1.0)
    discount = _cross_check_discount(essentia_bpm, librosa_bpm)
    bpm_confidence = normalized_confidence * discount

    downbeat_times, downbeat_confidence = _detect_downbeats(mono, pcm.sample_rate, beat_times)

    return RhythmResult(
        bpm=float(essentia_bpm),
        bpm_confidence=bpm_confidence,
        beat_times=beat_times,
        downbeat_times=downbeat_times,
        downbeat_confidence=downbeat_confidence,
        beats_per_bar=BEATS_PER_BAR,
    )
