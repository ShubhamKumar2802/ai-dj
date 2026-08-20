import pickle

from ingestion.orchestrator import worker as worker_module
from ingestion.orchestrator.config import IngestionConfig
from ingestion.orchestrator.schema import IngestionFailure, Track


def test_ingest_one_returns_track_on_success(
    monkeypatch, make_raw_features, make_cue_derivation_result
):
    raw = make_raw_features(content_hash="content-hash-xyz")
    cue_result = make_cue_derivation_result()
    monkeypatch.setattr(worker_module, "get_or_extract_features", lambda path, config: raw)
    monkeypatch.setattr(worker_module, "derive_cues", lambda raw, config: cue_result)

    result = worker_module._ingest_one("some/path.mp3", IngestionConfig())

    assert isinstance(result, Track)
    assert result.id == "content-hash-xyz"
    assert result.path == "some/path.mp3"


def test_ingest_one_returns_ingestion_failure_on_get_or_extract_features_exception(monkeypatch):
    def _raise(path, config):
        raise OSError("disk read failed")

    monkeypatch.setattr(worker_module, "get_or_extract_features", _raise)

    result = worker_module._ingest_one("some/path.mp3", IngestionConfig())

    assert isinstance(result, IngestionFailure)
    assert result.path == "some/path.mp3"
    assert result.error == "disk read failed"
    assert result.error_type == "OSError"


def test_ingest_one_returns_ingestion_failure_on_derive_cues_exception(
    monkeypatch, make_raw_features
):
    raw = make_raw_features()
    monkeypatch.setattr(worker_module, "get_or_extract_features", lambda path, config: raw)

    def _raise(raw, config):
        raise ValueError("bad phrase grid")

    monkeypatch.setattr(worker_module, "derive_cues", _raise)

    result = worker_module._ingest_one("some/path.mp3", IngestionConfig())

    assert isinstance(result, IngestionFailure)
    assert result.path == "some/path.mp3"
    assert result.error == "bad phrase grid"
    assert result.error_type == "ValueError"


def test_ingest_one_error_is_str_not_exception_object(monkeypatch):
    def _raise(path, config):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "get_or_extract_features", _raise)

    result = worker_module._ingest_one("some/path.mp3", IngestionConfig())

    assert isinstance(result.error, str)
    # picklable-safe — must round-trip cleanly across a process boundary
    # (loky's own requirement, spec §2's "never a live exception object").
    roundtripped = pickle.loads(pickle.dumps(result))
    assert roundtripped == result
