import soundfile as sf

from render.transition_renderer.schema import StereoPCM

SAMPLE_RATE = 48000  # D25


def write_wav(audio: StereoPCM, output_path: str) -> None:
    """Write ``audio`` to a WAV file (spec §4).

    48 kHz float32 stereo straight through — the canonical format (D25) is never
    converted or downmixed on the way out. ``StereoPCM.samples`` is already
    ``(n_samples, 2)``, which is ``soundfile``'s native frame-major layout, so no
    transpose. No mastering/loudness step in Milestone A.
    """
    assert audio.sample_rate == SAMPLE_RATE, (
        f"write_wav expects {SAMPLE_RATE} Hz PCM (D25); got {audio.sample_rate}"
    )
    sf.write(output_path, audio.samples, audio.sample_rate, subtype="FLOAT")
