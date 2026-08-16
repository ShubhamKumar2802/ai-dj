from ingestion.feature_extractor.loader import StereoPCM
from ingestion.feature_extractor.riser_detection import detect_risers


def test_detect_risers_finds_one_candidate_on_synthetic_riser(riser_audio):
    audio, sample_rate = riser_audio
    candidates = detect_risers(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert len(candidates) == 1


def test_detect_risers_candidate_starts_near_beginning_of_sweep(riser_audio):
    audio, sample_rate = riser_audio
    candidates = detect_risers(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert candidates[0].start_time < 0.5


def test_detect_risers_resolution_time_lands_near_the_transient(riser_audio):
    # The synthetic riser fixture (conftest.py) is a 4s sweep with a
    # transient click layered onto its final ~50ms.
    audio, sample_rate = riser_audio
    duration_s = audio.shape[0] / sample_rate
    candidates = detect_risers(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert abs(candidates[0].resolution_time - duration_s) < 0.5


def test_detect_risers_confidence_is_high_on_a_clean_riser(riser_audio):
    audio, sample_rate = riser_audio
    candidates = detect_risers(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert candidates[0].confidence > 0.8


def test_detect_risers_no_false_positives_on_non_riser_audio(click_track_audio):
    # A click track has no monotonic spectral-centroid drift anywhere —
    # every beat is the same click, so nothing should fire.
    audio, sample_rate = click_track_audio
    candidates = detect_risers(StereoPCM(samples=audio, sample_rate=sample_rate))

    assert candidates == []
