"""By-ear timing check: the track with a click at every lyric line start (spec §4.4.5)."""

from pathlib import Path

import numpy as np
import soundfile as sf

from ingestion.feature_extractor.loader import load_canonical

_CLICK_HZ = 1000.0
_CLICK_S = 0.020
_CLICK_DBFS = -12.0


def write_click_track(audio_path: str, times: list[float], out_path: Path) -> None:
    pcm = load_canonical(audio_path)
    audio = pcm.samples.copy()
    sr = pcm.sample_rate

    n = int(_CLICK_S * sr)
    t = np.arange(n) / sr
    click = (10 ** (_CLICK_DBFS / 20)) * np.sin(2 * np.pi * _CLICK_HZ * t) * np.hanning(n)

    for time in times:
        i = int(round(time * sr))
        if 0 <= i < len(audio):
            chunk = audio[i : i + n]
            chunk += click[: len(chunk), None].astype(np.float32)

    np.clip(audio, -1.0, 1.0, out=audio)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), audio, sr, subtype="PCM_16")
