"""Local Whisper via mlx-whisper on Apple Silicon (spec §4.3).

Decode parameters are fixed to whisper_bakeoff §3.3 so the two experiments' transcripts are
comparable. Weights live in the repo-root `models/` dir, never the Hugging Face cache.
"""

import hashlib
import importlib.metadata
import json
from pathlib import Path

from experiments.lyrics_sourcing.config import TranscribeConfig
from experiments.lyrics_sourcing.persistence import from_dict, to_jsonable
from experiments.lyrics_sourcing.schema import IngestedTrack, Segment, Transcript, Word

WHISPER_SAMPLE_RATE = 16000

DECODE: dict = {
    "word_timestamps": True,
    # Limits hallucination cascading through instrumental sections (04 Q1).
    "condition_on_previous_text": False,
    "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    "task": "transcribe",
    # compression_ratio_threshold, logprob_threshold, no_speech_threshold: Whisper defaults
}


def whisper_config_id(model: str, language: str | None, mlx_whisper_version: str) -> str:
    payload = json.dumps(
        {"model": model, "language": language, "decode": DECODE, "mlx": mlx_whisper_version},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def ensure_weights(repo_id: str, models_dir: str | Path) -> Path:
    """Download `repo_id` into `models_dir/<repo-name>` once; return the local path."""
    local = Path(models_dir) / repo_id.split("/")[-1]
    if not (local / "config.json").exists():
        from huggingface_hub import snapshot_download

        local.mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=repo_id, local_dir=str(local))
    return local


class MlxWhisperTranscriber:
    def __init__(self, cfg: TranscribeConfig) -> None:
        self._cfg = cfg

    def transcribe(self, track: IngestedTrack) -> Transcript:
        config_id = whisper_config_id(
            self._cfg.model, self._cfg.language, importlib.metadata.version("mlx-whisper")
        )
        cache_dir = Path(self._cfg.cache_dir)
        cache_path = cache_dir / f"{track.content_hash}_{config_id}.json"
        if cache_path.exists():
            return from_dict(Transcript, json.loads(cache_path.read_text()))

        import mlx_whisper  # lazy: heavy, Apple-only

        local_model = ensure_weights(self._cfg.model, self._cfg.models_dir)
        result = mlx_whisper.transcribe(
            _load_mono_16k(track.path),
            path_or_hf_repo=str(local_model),
            language=self._cfg.language,
            verbose=None,
            **DECODE,
        )
        transcript = Transcript(
            language=result.get("language"),
            segments=[_segment(s) for s in result.get("segments", [])],
            whisper_config_id=config_id,
            model=self._cfg.model,
        )

        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(to_jsonable(transcript), ensure_ascii=False))
        return transcript


def _load_mono_16k(path: str):
    import librosa
    import numpy as np

    from ingestion.feature_extractor.loader import load_canonical

    pcm = load_canonical(path)
    mono = pcm.samples.mean(axis=1)
    audio = librosa.resample(mono, orig_sr=pcm.sample_rate, target_sr=WHISPER_SAMPLE_RATE)
    return audio.astype(np.float32)


def _segment(raw: dict) -> Segment:
    return Segment(
        text=raw.get("text", "").strip(),
        start=float(raw["start"]),
        end=float(raw["end"]),
        words=[
            Word(
                text=w.get("word", "").strip(),
                start=float(w["start"]),
                end=float(w["end"]),
                probability=w.get("probability"),
            )
            for w in raw.get("words", [])
            if w.get("word", "").strip()
        ],
    )
