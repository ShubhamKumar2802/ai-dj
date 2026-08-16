from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SAMPLE_RATE = 48000

# Deliberately non-round — avoids masking a rounding/flooring bug behind a
# BPM that happens to coincide with a library's internal default (spec §1.1:
# bpm must never be floored).
CLICK_TRACK_BPM = 123.5
BEATS_PER_BAR = 4
N_BARS = 8


def _decaying_click(duration_s: float, sample_rate: int) -> np.ndarray:
    """A single short percussive click (decaying noise burst)."""
    n = int(duration_s * sample_rate)
    t = np.arange(n) / sample_rate
    envelope = np.exp(-t * 60.0)
    noise = np.random.default_rng(0).standard_normal(n)
    return envelope * noise


@pytest.fixture(scope="session")
def click_track_bpm() -> float:
    return CLICK_TRACK_BPM


@pytest.fixture(scope="session")
def click_track_audio(click_track_bpm) -> tuple[np.ndarray, int]:
    """Synthetic click track + underlying tone at a known BPM.

    Deterministic, numpy-generated, no external file dependency (spec §13).
    A click at every beat is mixed under a quiet steady tone so RMS/
    spectral-centroid/chroma tests have continuous content to measure,
    rather than near-silence between clicks.
    """
    beat_interval_s = 60.0 / click_track_bpm
    n_beats = BEATS_PER_BAR * N_BARS
    duration_s = n_beats * beat_interval_s + 1.0  # tail room past the last beat
    n_samples = int(duration_s * SAMPLE_RATE)

    t = np.arange(n_samples) / SAMPLE_RATE
    tone = 0.05 * np.sin(2 * np.pi * 220.0 * t)  # quiet A3 bed tone

    audio = tone.copy()
    click = _decaying_click(0.05, SAMPLE_RATE)
    for beat_index in range(n_beats):
        start = int(round(beat_index * beat_interval_s * SAMPLE_RATE))
        end = min(start + len(click), n_samples)
        audio[start:end] += click[: end - start]

    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    stereo = np.stack([audio, audio], axis=1)
    return stereo, SAMPLE_RATE


@pytest.fixture
def click_track_wav(tmp_path, click_track_audio) -> Path:
    """The click track written to a real 48kHz stereo float WAV file — a
    fixture that returns a path is more representative of what
    `load_canonical` actually receives from callers than an in-memory array.
    """
    audio, sample_rate = click_track_audio
    path = tmp_path / "click_track.wav"
    sf.write(str(path), audio, sample_rate, subtype="FLOAT")
    return path


@pytest.fixture(scope="session")
def riser_audio() -> tuple[np.ndarray, int]:
    """Synthetic riser: monotonic upward spectral-centroid drift ending in a
    transient (F4) — a linear frequency sweep with a click at its end.
    """
    duration_s = 4.0
    n_samples = int(duration_s * SAMPLE_RATE)
    t = np.arange(n_samples) / SAMPLE_RATE
    start_freq, end_freq = 200.0, 4000.0
    freq = start_freq + (end_freq - start_freq) * (t / duration_s)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sweep = 0.2 * np.sin(phase)

    transient = _decaying_click(0.05, SAMPLE_RATE)
    audio = sweep.copy()
    tail = audio[-len(transient) :]
    tail += transient[: len(tail)]

    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    stereo = np.stack([audio, audio], axis=1)
    return stereo, SAMPLE_RATE


@pytest.fixture
def riser_wav(tmp_path, riser_audio) -> Path:
    audio, sample_rate = riser_audio
    path = tmp_path / "riser.wav"
    sf.write(str(path), audio, sample_rate, subtype="FLOAT")
    return path


# tests/ingestion/feature_extractor/conftest.py -> repo root is 3 parents up.
_MUSIC_DIR = Path(__file__).resolve().parents[3] / "music"


def _find_real_track() -> Path | None:
    if not _MUSIC_DIR.is_dir():
        return None
    tracks = sorted(_MUSIC_DIR.glob("*.mp3"))
    return tracks[0] if tracks else None


@pytest.fixture(scope="session")
def real_track_path() -> Path:
    """Path to a real local track under (gitignored) `music/`.

    Skips the test on a fresh clone with no `music/` directory (spec §13) —
    only `test_real_audio_smoke.py` should depend on this fixture.
    """
    track = _find_real_track()
    if track is None:
        pytest.skip("music/ fixture not present — real-audio smoke test skipped")
    return track
