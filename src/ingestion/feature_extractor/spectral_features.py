import essentia.standard as es
import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.rhythm import HIGH_BAND_HZ, LOW_BAND_HZ, RhythmResult, band_energy
from ingestion.feature_extractor.schema import PerBarFeatures

# Standard STFT framing for spectral_flux/chroma — not spec-pinned, an
# implementer choice (spec §7 names the algorithms, not frame/hop sizes).
_FRAME_SIZE = 2048
_HOP_SIZE = 1024
_CHROMA_BINS = 12


def _bar_segment(
    mono: np.ndarray, sample_rate: int, start_time: float, end_time: float
) -> np.ndarray:
    start = int(start_time * sample_rate)
    end = min(int(end_time * sample_rate), len(mono))
    start = min(start, end)
    return np.ascontiguousarray(mono[start:end], dtype=np.float32)


def _framed_spectra(segment: np.ndarray, windowing, spectrum_algo) -> list:
    """One magnitude spectrum per STFT frame — computed once per bar and
    shared between `_spectral_flux` and `_chroma_vector` (both previously
    re-framed and re-FFT'd the same segment independently).
    """
    if len(segment) < _FRAME_SIZE:
        return []
    return [
        spectrum_algo(windowing(frame))
        for frame in es.FrameGenerator(
            segment, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE, startFromZero=True
        )
    ]


def _spectral_flux(spectra: list, flux_algo) -> float:
    """Mean frame-to-frame spectral flux over the bar (spec §7).

    `Flux` is stateful — each call diffs against whatever spectrum it was
    last called with internally. It must be called on *every* frame
    (including frame 0, to seed that internal state) or the first recorded
    diff ends up comparing frame 1 against Flux's uninitialized/zero state
    instead of against frame 0 — an easy mistake since frame 0 has no
    "previous frame" of its own to report a diff for.
    """
    if not spectra:
        return 0.0
    flux_algo.reset()
    flux_values = [flux_algo(spectrum) for spectrum in spectra]
    return float(np.mean(flux_values[1:])) if len(flux_values) > 1 else 0.0


def _chroma_vector(spectra: list, sample_rate: int) -> list[float]:
    """12-dim chroma via Essentia `NNLSChroma` (spec §7).

    `NNLSChroma` takes a sequence of log-frequency spectrum frames (plus
    per-frame tuning estimates from `LogSpectrum`), not raw spectra directly
    — build that per-frame chain, then reduce NNLSChroma's per-frame
    chromagram output to one vector per bar by averaging.

    `LogSpectrum`/`NNLSChroma` are deliberately constructed fresh per bar
    (unlike `Windowing`/`Spectrum`/`Flux` above) — sharing them across the
    whole track would change their tuning-estimate accumulation behavior,
    a real algorithmic difference already verified under today's per-bar
    semantics (A4/C4 tones peak exactly 3 semitone-bins apart), not a
    pure efficiency cleanup.
    """
    if not spectra:
        return [0.0] * _CHROMA_BINS

    log_spectrum_algo = es.LogSpectrum(sampleRate=sample_rate)

    log_spectrogram: list = []
    local_tunings: list = []
    mean_tuning: list = []  # LogSpectrum's meanTuning is itself a running
    # vector_real (a tuning histogram), not a per-frame scalar — NNLSChroma
    # wants the final accumulated value, not one appended per frame.
    for spectrum in spectra:
        log_freq_spectrum, mean_tuning, local_tuning = log_spectrum_algo(spectrum)
        log_spectrogram.append(log_freq_spectrum)
        local_tunings.append(local_tuning)

    # useNNLS=True (the algorithm's default) silently returns all-zero
    # chroma in the installed Essentia dev build (2.1b6.dev1389) — verified
    # directly: even a clean sustained tone produces an all-zero chromagram
    # with the default. useNNLS=False (linear spectral mapping, same
    # algorithm) produces musically correct output — checked against known
    # pitches (A4/C4 peak exactly 3 semitone-bins apart, as they should).
    nnls = es.NNLSChroma(sampleRate=sample_rate, useNNLS=False)
    _tuned, _semitone, _bass_chromagram, chromagram = nnls(
        log_spectrogram, mean_tuning, local_tunings
    )

    chroma_frames = np.array(chromagram)
    if chroma_frames.size == 0:
        return [0.0] * _CHROMA_BINS
    return [float(v) for v in chroma_frames.mean(axis=0)]


def compute_per_bar_features(pcm: StereoPCM, rhythm: RhythmResult) -> list[PerBarFeatures]:
    """One `PerBarFeatures` entry per detected downbeat interval (spec §2) —
    i.e. `len(downbeat_times) - 1` bars. No entry before the first downbeat
    or after the last: those spans aren't a full detected bar.
    """
    mono = pcm.samples.mean(axis=1).astype(np.float32)
    sample_rate = pcm.sample_rate
    downbeats = rhythm.downbeat_times

    # Windowing/Spectrum are stateless (pure frame-in/frame-out, no memory
    # across calls) — safe to construct once per track and reuse across all
    # bars. Flux is stateful (see _spectral_flux) but its constructor cost
    # is avoided the same way, via .reset() per bar instead of rebuilding.
    windowing = es.Windowing(type="hann")
    spectrum_algo = es.Spectrum()
    flux_algo = es.Flux()

    bars = []
    for bar_index, (start_time, end_time) in enumerate(zip(downbeats[:-1], downbeats[1:])):
        segment = _bar_segment(mono, sample_rate, start_time, end_time)
        spectra = _framed_spectra(segment, windowing, spectrum_algo)

        if len(segment) == 0:
            rms = 0.0
            centroid = 0.0
        else:
            rms = float(np.sqrt(np.mean(segment**2)))
            centroid = float(es.SpectralCentroidTime(sampleRate=sample_rate)(segment))

        bars.append(
            PerBarFeatures(
                bar_index=bar_index,
                start_time=start_time,
                end_time=end_time,
                rms=rms,
                spectral_centroid=centroid,
                spectral_flux=_spectral_flux(spectra, flux_algo),
                low_band_energy=band_energy(segment, sample_rate, LOW_BAND_HZ),
                high_band_energy=band_energy(segment, sample_rate, HIGH_BAND_HZ),
                chroma_vector=_chroma_vector(spectra, sample_rate),
            )
        )

    return bars
