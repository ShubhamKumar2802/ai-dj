from ingestion.feature_extractor.config import FeatureExtractorConfig
from ingestion.feature_extractor.content_hash import hash_file
from ingestion.feature_extractor.key_estimation import estimate_key
from ingestion.feature_extractor.loader import load_canonical
from ingestion.feature_extractor.loudness import compute_loudness
from ingestion.feature_extractor.rhythm import detect_rhythm
from ingestion.feature_extractor.riser_detection import detect_risers
from ingestion.feature_extractor.schema import RawFeatures
from ingestion.feature_extractor.spectral_features import compute_per_bar_features
from ingestion.feature_extractor.vocal_band import compute_vocal_band_energy


def extract_features(path: str, config: FeatureExtractorConfig) -> RawFeatures:
    """Pure extraction (spec §12) — always decodes and runs the full
    pipeline, never checks or writes the cache. `cache.py`'s
    `get_or_extract_features` is the only entry point real callers use.
    """
    pcm = load_canonical(path, sample_rate=config.sample_rate)
    rhythm = detect_rhythm(pcm)
    per_bar = compute_per_bar_features(pcm, rhythm)
    loudness = compute_loudness(pcm, per_bar)
    vocal_band_energy = compute_vocal_band_energy(pcm, per_bar)
    key, key_confidence = estimate_key(pcm)
    risers = detect_risers(pcm)

    duration = pcm.samples.shape[0] / pcm.sample_rate

    return RawFeatures(
        content_hash=hash_file(path),
        feature_extractor_version=config.extractor_version,
        source_path=path,
        duration=duration,
        sample_rate=pcm.sample_rate,
        bpm=rhythm.bpm,
        bpm_confidence=rhythm.bpm_confidence,
        beat_times=rhythm.beat_times,
        downbeat_times=rhythm.downbeat_times,
        downbeat_confidence=rhythm.downbeat_confidence,
        beats_per_bar=rhythm.beats_per_bar,
        per_bar_features=per_bar,
        lufs_integrated=loudness.lufs_integrated,
        true_peak=loudness.true_peak,
        energy_curve=loudness.energy_curve,
        vocal_band_energy=vocal_band_energy,
        key=key,
        key_confidence=key_confidence,
        riser_candidates=risers,
    )
