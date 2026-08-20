import os

import pytest

from ingestion.orchestrator import orchestrate as orchestrate_module
from ingestion.orchestrator.config import IngestionConfig
from ingestion.orchestrator.orchestrate import ingest_tracks
from ingestion.orchestrator.schema import IngestionFailure, Track

# Module-level (not nested/closure) so loky's spawn start method can
# re-import these by reference in a child process — required for the two
# real-backend="loky" tests below.


def _module_level_dummy_worker(path: str, config: IngestionConfig) -> Track:
    return Track(
        id=f"id-{path}",
        path=path,
        content_hash=f"hash-{path}",
        duration=100.0,
        sample_rate=48000,
        bpm=120.0,
        bpm_confidence=0.9,
        beat_times=[],
        downbeat_times=[],
        downbeat_confidence=0.9,
        beats_per_bar=4,
        grid_start=0.0,
        grid_confidence=0.9,
        free_intro_end=8.0,
        phrase_length_bars=8.0,
        phrase_grid=[],
        key=None,
        key_confidence=None,
        lufs_integrated=-10.0,
        true_peak=-1.0,
        energy_curve=[],
        vocal_mask=[],
        structure_template="unknown",
        cue_ins=[],
        cue_outs=[],
        familiarity_score=None,
        era=None,
        is_club_edit=None,
        analysis_version="test+test",
        status="ok",
    )


def _module_level_crashing_worker(path: str, config: IngestionConfig) -> Track:
    if path == "crash.mp3":
        os._exit(1)
    return _module_level_dummy_worker(path, config)


def test_ingest_tracks_returns_tracks_and_failures(make_track):
    ok_track = make_track(path="ok.mp3")
    fail = IngestionFailure(path="bad.mp3", error="boom", error_type="RuntimeError")

    def fake_worker(path, config):
        return ok_track if path == "ok.mp3" else fail

    result = ingest_tracks(
        ["ok.mp3", "bad.mp3"], IngestionConfig(), _worker=fake_worker, _backend="threading"
    )

    assert result.tracks == [ok_track]
    assert result.failures == [fail]


def test_ingest_tracks_dedupes_paths_by_literal_equality(make_track):
    calls = []

    def fake_worker(path, config):
        calls.append(path)
        return make_track(path=path)

    result = ingest_tracks(
        ["a.mp3", "b.mp3", "a.mp3"], IngestionConfig(), _worker=fake_worker, _backend="threading"
    )

    assert sorted(calls) == ["a.mp3", "b.mp3"]
    assert len(result.tracks) == 2


def test_ingest_tracks_dedup_is_order_preserving(make_track):
    queued_order = []

    def on_progress(path, status):
        if status == "queued":
            queued_order.append(path)

    def fake_worker(path, config):
        return make_track(path=path)

    ingest_tracks(
        ["b.mp3", "a.mp3", "b.mp3", "c.mp3"],
        IngestionConfig(),
        on_progress=on_progress,
        _worker=fake_worker,
        _backend="threading",
    )

    assert queued_order == ["b.mp3", "a.mp3", "c.mp3"]


def test_ingest_tracks_fires_queued_for_every_deduped_path_before_any_completion(make_track):
    events = []

    def on_progress(path, status):
        events.append((path, status))

    def fake_worker(path, config):
        return make_track(path=path)

    ingest_tracks(
        ["a.mp3", "b.mp3"],
        IngestionConfig(),
        on_progress=on_progress,
        _worker=fake_worker,
        _backend="threading",
    )

    queued_events = [e for e in events if e[1] == "queued"]
    first_non_queued_index = next(i for i, e in enumerate(events) if e[1] != "queued")

    assert len(queued_events) == 2
    assert all(status == "queued" for _, status in events[:first_non_queued_index])


def test_ingest_tracks_fires_completed_and_failed_correctly(make_track):
    outcomes = {}

    def on_progress(path, status):
        if status != "queued":
            outcomes[path] = status

    ok_track = make_track(path="ok.mp3")
    fail = IngestionFailure(path="bad.mp3", error="boom", error_type="RuntimeError")

    def fake_worker(path, config):
        return ok_track if path == "ok.mp3" else fail

    ingest_tracks(
        ["ok.mp3", "bad.mp3"],
        IngestionConfig(),
        on_progress=on_progress,
        _worker=fake_worker,
        _backend="threading",
    )

    assert outcomes == {"ok.mp3": "completed", "bad.mp3": "failed"}


def test_ingest_tracks_propagates_on_progress_exception(make_track):
    def on_progress(path, status):
        raise ValueError("callback boom")

    def fake_worker(path, config):
        return make_track(path=path)

    with pytest.raises(ValueError, match="callback boom"):
        ingest_tracks(
            ["a.mp3"],
            IngestionConfig(),
            on_progress=on_progress,
            _worker=fake_worker,
            _backend="threading",
        )


class _FakeParallel:
    """Spy standing in for joblib.Parallel — records the n_jobs it was
    constructed with, and actually runs the delayed(fn)(*args, **kwargs)
    tuples the generator yields so the rest of ingest_tracks still works.
    """

    captured_n_jobs: int | None = None

    def __init__(self, n_jobs, backend, return_as):
        _FakeParallel.captured_n_jobs = n_jobs

    def __call__(self, generator):
        return iter([func(*args, **kwargs) for func, args, kwargs in generator])


def test_ingest_tracks_max_workers_none_maps_to_all_cores(monkeypatch, make_track):
    monkeypatch.setattr(orchestrate_module, "Parallel", _FakeParallel)

    def fake_worker(path, config):
        return make_track(path=path)

    ingest_tracks(["a.mp3"], IngestionConfig(max_workers=None), _worker=fake_worker)

    assert _FakeParallel.captured_n_jobs == -1


def test_ingest_tracks_max_workers_respected(monkeypatch, make_track):
    monkeypatch.setattr(orchestrate_module, "Parallel", _FakeParallel)

    def fake_worker(path, config):
        return make_track(path=path)

    ingest_tracks(["a.mp3"], IngestionConfig(max_workers=4), _worker=fake_worker)

    assert _FakeParallel.captured_n_jobs == 4


def test_ingest_tracks_loky_backend_pickles_across_process_boundary():
    """The only test in the always-run suite that pickles IngestionConfig/
    Track/a worker function across a real process boundary (spec §7)."""
    result = ingest_tracks(
        ["a.mp3", "b.mp3"], IngestionConfig(), _worker=_module_level_dummy_worker
    )

    assert {t.path for t in result.tracks} == {"a.mp3", "b.mp3"}
    assert result.failures == []


def test_ingest_tracks_survives_worker_crash_loky():
    """Empirically confirms spec §6/§10 Q4: a loky worker crash (os._exit,
    not a Python exception) surfaces as a TerminatedWorkerError from the
    generator, after which the generator is exhausted — orchestrate.py's
    post-loop reconciliation must account for every path that never
    produced a real result, so ingest_tracks's completeness invariant
    (every input path ends up in tracks[] or failures[]) holds even then.
    """
    paths = ["a.mp3", "crash.mp3", "b.mp3"]

    result = ingest_tracks(paths, IngestionConfig(), _worker=_module_level_crashing_worker)

    all_result_paths = {t.path for t in result.tracks} | {f.path for f in result.failures}
    assert all_result_paths == set(paths)
    assert len(result.tracks) + len(result.failures) == len(paths)
    assert "crash.mp3" not in {t.path for t in result.tracks}
