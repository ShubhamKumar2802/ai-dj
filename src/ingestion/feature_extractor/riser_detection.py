import essentia.standard as es
import numpy as np

from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.schema import RiserCandidate

# Implementer-chosen constants (spec §11 names the shape of the detector —
# "monotonic upward drift... terminating in a transient" — not these values).
_FRAME_SIZE = 2048
_HOP_SIZE = 1024
_WINDOW_S = 1.5  # sliding-window length tested for monotonic centroid drift
_MIN_CORRELATION = 0.7  # Pearson r threshold for "monotonic enough"
_MIN_CENTROID_RISE_HZ = 200.0  # avoid flagging near-flat noise as a riser
_TRANSIENT_SEARCH_S = 0.5  # where to look for the terminating transient
# once a drift region ends


def _frame_series(mono: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-frame spectral centroid and onset-strength series, not bar-gated
    (risers occur in the free-time region before a reliable beat grid — F3).
    """
    windowing = es.Windowing(type="hann")
    spectrum_algo = es.Spectrum()
    centroid_algo = es.SpectralCentroidTime(sampleRate=sample_rate)
    onset_algo = es.OnsetDetection(method="hfc", sampleRate=sample_rate)
    empty_phase = np.array([], dtype=np.float32)

    times, centroids, onset_strengths = [], [], []
    for i, frame in enumerate(
        es.FrameGenerator(mono, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE, startFromZero=True)
    ):
        spectrum = spectrum_algo(windowing(frame))
        times.append(i * _HOP_SIZE / sample_rate)
        centroids.append(float(centroid_algo(frame)))
        onset_strengths.append(float(onset_algo(spectrum, empty_phase)))

    return np.array(times), np.array(centroids), np.array(onset_strengths)


def _monotonic_regions(times: np.ndarray, centroids: np.ndarray) -> list[tuple[int, int, float]]:
    """Contiguous frame-index ranges where spectral centroid rises with a
    strong linear (monotonic) trend, merged where adjacent windows both
    qualify. Returns (start_idx, end_idx, mean_correlation) triples.
    """
    if len(times) < 2:
        return []

    frames_per_window = max(2, int(round(_WINDOW_S / max(times[1] - times[0], 1e-9))))
    qualifying = np.zeros(len(times), dtype=bool)
    correlations = np.zeros(len(times))

    for start in range(0, len(times) - frames_per_window + 1):
        end = start + frames_per_window
        window = centroids[start:end]
        rise = window[-1] - window[0]
        if rise < _MIN_CENTROID_RISE_HZ:
            continue
        r = np.corrcoef(np.arange(frames_per_window), window)[0, 1]
        if np.isnan(r) or r < _MIN_CORRELATION:
            continue
        qualifying[start:end] = True
        correlations[start:end] = np.maximum(correlations[start:end], r)

    regions = []
    in_region = False
    region_start = 0
    for i, flag in enumerate(qualifying):
        if flag and not in_region:
            in_region = True
            region_start = i
        elif not flag and in_region:
            in_region = False
            regions.append((region_start, i, float(np.mean(correlations[region_start:i]))))
    if in_region:
        regions.append((region_start, len(qualifying), float(np.mean(correlations[region_start:]))))

    return regions


def _find_terminating_transient(
    times: np.ndarray, onset_strengths: np.ndarray, region_end_idx: int
) -> tuple[float, float]:
    """The onset-strength peak shortly after a drift region ends — the
    transient the riser resolves into (F4). Returns (resolution_time,
    prominence in [0,1] relative to the search window's own range).
    """
    if region_end_idx >= len(times):
        region_end_idx = len(times) - 1

    search_end_time = times[region_end_idx] + _TRANSIENT_SEARCH_S
    search_end_idx = min(int(np.searchsorted(times, search_end_time, side="right")), len(times))
    start_idx = max(0, region_end_idx - 1)
    if start_idx >= search_end_idx:
        return times[region_end_idx], 0.0

    window = onset_strengths[start_idx:search_end_idx]
    peak_offset = int(np.argmax(window))
    peak_idx = start_idx + peak_offset

    window_range = window.max() - window.min()
    prominence = float((window[peak_offset] - window.min()) / window_range) if window_range else 0.0
    return float(times[peak_idx]), prominence


def detect_risers(pcm: StereoPCM) -> list[RiserCandidate]:
    mono = np.ascontiguousarray(pcm.samples.mean(axis=1), dtype=np.float32)
    times, centroids, onset_strengths = _frame_series(mono, pcm.sample_rate)

    candidates = []
    for start_idx, end_idx, correlation in _monotonic_regions(times, centroids):
        resolution_time, prominence = _find_terminating_transient(times, onset_strengths, end_idx)
        confidence = max(0.0, min(1.0, correlation * (0.5 + 0.5 * prominence)))
        candidates.append(
            RiserCandidate(
                start_time=float(times[start_idx]),
                resolution_time=resolution_time,
                confidence=confidence,
            )
        )

    return candidates
