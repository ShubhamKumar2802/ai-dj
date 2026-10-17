from experiments.lyrics_sourcing.persistence import load_step, save_step
from experiments.lyrics_sourcing.schema import (
    HookWindow,
    LabeledSection,
    StructureLabels,
    StructureResult,
    TrackMetadata,
)
from ingestion.cue_derivation.schema import Cue, CueDerivationResult, PhraseBoundary
from ingestion.feature_extractor.schema import PerBarFeatures, RawFeatures, RiserCandidate


def _metadata() -> TrackMetadata:
    raw = RawFeatures(
        content_hash="h",
        feature_extractor_version="2",
        source_path="a.mp3",
        duration=10.0,
        sample_rate=48000,
        bpm=120.0,
        bpm_confidence=0.9,
        beat_times=[0.5, 1.0],
        downbeat_times=[0.5, 2.5],
        downbeat_confidence=0.8,
        beats_per_bar=4,
        per_bar_features=[PerBarFeatures(0, 0.5, 2.5, 0.1, 1000.0, 0.2, 0.3, 0.4, [0.0] * 12)],
        lufs_integrated=-9.0,
        true_peak=-1.0,
        energy_curve=[-10.0],
        vocal_band_energy=[0.5],
        key="8A",
        key_confidence=None,
        riser_candidates=[RiserCandidate(1.0, 2.0, 0.7)],
    )
    cues = CueDerivationResult(
        grid_start=0.5,
        grid_confidence=0.9,
        free_intro_end=0.5,
        phrase_length_bars=None,
        phrase_grid=[PhraseBoundary(0.5, 1.2, None)],
        structure_template="film",
        cue_ins=[Cue(0.5, "first_downbeat", 0.9)],
        cue_outs=[],
        status="ok",
        cue_derivation_version="1",
    )
    return TrackMetadata(raw=raw, cues=cues)


def test_track_metadata_round_trips_to_real_instances(tmp_path):
    meta = _metadata()
    save_step(tmp_path, "04_metadata", meta)
    loaded = load_step(tmp_path, "04_metadata", TrackMetadata)
    assert loaded == meta
    assert isinstance(loaded.raw.per_bar_features[0], PerBarFeatures)
    assert isinstance(loaded.cues.cue_ins[0], Cue)


def test_structure_result_round_trips_pydantic_inside_dataclass(tmp_path):
    result = StructureResult(
        labels=StructureLabels(
            sections=[LabeledSection(type="intro", start=0, end=10, confidence=0.5, evidence="x")],
            hook=HookWindow(start=2, end=8, reason="r"),
            notes="",
        ),
        issues=["a"],
        model="m",
        prompt_version="1",
        estimated_tokens=100,
        serializer="toon",
    )
    save_step(tmp_path, "06_llm", result)
    assert load_step(tmp_path, "06_llm", StructureResult) == result
