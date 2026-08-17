import re

import numpy as np

from ingestion.feature_extractor.key_estimation import estimate_key, key_to_camelot
from ingestion.feature_extractor.loader import StereoPCM

SAMPLE_RATE = 48000

# Hand-verified against the standard Camelot wheel (§1.2), anchored at the
# well-known C major = 8B / A minor = 8A pair, spanning the wheel.
_KNOWN_CAMELOT_MAPPINGS = [
    ("C", "major", "8B"),
    ("A", "minor", "8A"),
    ("G", "major", "9B"),
    ("E", "minor", "9A"),
    ("D", "major", "10B"),
    ("B", "minor", "10A"),
    ("F", "major", "7B"),
    ("D", "minor", "7A"),
    ("Bb", "minor", "3A"),
    ("Db", "major", "3B"),
    ("C#", "major", "3B"),  # enharmonic of Db — same Camelot code
    ("Ab", "minor", "1A"),
]


def test_key_to_camelot_matches_standard_wheel():
    for key, scale, expected in _KNOWN_CAMELOT_MAPPINGS:
        assert key_to_camelot(key, scale) == expected, f"{key} {scale}"


def test_key_to_camelot_relative_major_minor_share_number():
    major = key_to_camelot("C", "major")
    minor = key_to_camelot("A", "minor")
    assert major[:-1] == minor[:-1]  # same number
    assert major[-1] == "B"
    assert minor[-1] == "A"


def test_key_to_camelot_unknown_key_returns_none():
    assert key_to_camelot("H", "major") is None


def test_key_to_camelot_unknown_scale_returns_none():
    assert key_to_camelot("C", "phrygian") is None


def _triad_pcm(freqs: list[float], duration_s: float = 4.0) -> StereoPCM:
    t = np.arange(int(duration_s * SAMPLE_RATE)) / SAMPLE_RATE
    mono = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    mono = (0.3 * mono / np.max(np.abs(mono))).astype(np.float32)
    stereo = np.stack([mono, mono], axis=1)
    return StereoPCM(samples=stereo, sample_rate=SAMPLE_RATE)


def test_estimate_key_detects_c_major_triad():
    pcm = _triad_pcm([261.63, 329.63, 392.00])  # C4, E4, G4
    key, confidence = estimate_key(pcm)

    assert key == "8B"
    assert confidence is not None
    assert 0.0 <= confidence <= 1.0


def test_estimate_key_detects_a_minor_triad():
    pcm = _triad_pcm([220.0, 261.63, 329.63])  # A3, C4, E4
    key, confidence = estimate_key(pcm)

    assert key == "8A"
    assert confidence is not None
    assert 0.0 <= confidence <= 1.0


def test_estimate_key_returns_valid_camelot_format():
    pcm = _triad_pcm([261.63, 329.63, 392.00])
    key, _confidence = estimate_key(pcm)

    assert re.fullmatch(r"(1[0-2]|[1-9])[AB]", key)
