from dataclasses import dataclass


@dataclass
class PerBarFeatures:
    bar_index: int
    start_time: float
    end_time: float
    rms: float
    spectral_centroid: float
    spectral_flux: float
    low_band_energy: float
    high_band_energy: float
    chroma_vector: list[float]


@dataclass
class RiserCandidate:
    start_time: float
    resolution_time: float
    confidence: float


@dataclass
class RawFeatures:
    content_hash: str
    feature_extractor_version: str
    source_path: str
    duration: float
    sample_rate: int

    bpm: float
    bpm_confidence: float
    beat_times: list[float]

    downbeat_times: list[float]
    downbeat_confidence: float
    beats_per_bar: int

    per_bar_features: list[PerBarFeatures]

    lufs_integrated: float
    true_peak: float
    energy_curve: list[float]

    vocal_band_energy: list[float]

    key: str | None
    key_confidence: float | None

    riser_candidates: list[RiserCandidate]
