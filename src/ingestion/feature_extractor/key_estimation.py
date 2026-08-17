import essentia.standard as es
import numpy as np

from ingestion.feature_extractor.loader import StereoPCM

# Essentia's Key algorithm returns note names using a mix of sharps/flats
# (verified against real output: e.g. "Bb", not "A#") — mapped here by pitch
# class to cover every enharmonic spelling Essentia might emit, rather than
# a string-keyed table that only matches one spelling per pitch.
_NOTE_TO_PITCH_CLASS = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

# Standard Camelot wheel (§1.2) — major-key pitch class -> Camelot number,
# anchored at the well-known C major = 8B / A minor = 8A pair. Each +1 in
# Camelot number is a perfect fifth up (7 semitones), matching §1.2's
# "±1, same letter = perfect fifth" rule — verified by hand against the
# wheel, not copied from an unverified source.
_MAJOR_PITCH_CLASS_TO_CAMELOT_NUMBER = {
    0: 8,  # C
    7: 9,  # G
    2: 10,  # D
    9: 11,  # A
    4: 12,  # E
    11: 1,  # B
    6: 2,  # F#/Gb
    1: 3,  # C#/Db
    8: 4,  # G#/Ab
    3: 5,  # D#/Eb
    10: 6,  # A#/Bb
    5: 7,  # F
}


def key_to_camelot(key: str, scale: str) -> str | None:
    """Standard-notation key + scale -> Camelot code (e.g. "C", "major" ->
    "8B"), or None if `key`/`scale` aren't recognized.
    """
    pitch_class = _NOTE_TO_PITCH_CLASS.get(key)
    if pitch_class is None:
        return None

    if scale == "major":
        number = _MAJOR_PITCH_CLASS_TO_CAMELOT_NUMBER[pitch_class]
        return f"{number}B"
    if scale == "minor":
        # Relative major is a minor third above the minor tonic (§1.2:
        # "same number, flip letter" = relative minor/major).
        relative_major_pc = (pitch_class + 3) % 12
        number = _MAJOR_PITCH_CLASS_TO_CAMELOT_NUMBER[relative_major_pc]
        return f"{number}A"
    return None


def estimate_key(pcm: StereoPCM) -> tuple[str | None, float | None]:
    """Camelot key + confidence (§1.2, D10) — nullable soft score, never a
    hard gate downstream (spec §10).
    """
    mono = np.ascontiguousarray(pcm.samples.mean(axis=1), dtype=np.float32)
    extractor = es.KeyExtractor(sampleRate=pcm.sample_rate)
    key, scale, strength = extractor(mono)

    camelot = key_to_camelot(key, scale)
    if camelot is None:
        return None, None

    return camelot, float(min(max(strength, 0.0), 1.0))
