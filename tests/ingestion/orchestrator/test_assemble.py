from ingestion.orchestrator.assemble import _assemble_track


def test_assemble_track_maps_fields_from_raw_features(
    make_raw_features, make_cue_derivation_result
):
    raw = make_raw_features(
        content_hash="hash-123",
        duration=200.0,
        sample_rate=44100,
        bpm=140.0,
        bpm_confidence=0.7,
        beat_times=[0.0, 1.0],
        downbeat_times=[0.0, 4.0],
        downbeat_confidence=0.6,
        beats_per_bar=3,
        key="4B",
        key_confidence=0.5,
        lufs_integrated=-8.0,
        true_peak=-0.5,
        energy_curve=[0.1, 0.2, 0.3],
    )
    cue_result = make_cue_derivation_result()

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.content_hash == "hash-123"
    assert track.duration == 200.0
    assert track.sample_rate == 44100
    assert track.bpm == 140.0
    assert track.bpm_confidence == 0.7
    assert track.beat_times == [0.0, 1.0]
    assert track.downbeat_times == [0.0, 4.0]
    assert track.downbeat_confidence == 0.6
    assert track.beats_per_bar == 3
    assert track.key == "4B"
    assert track.key_confidence == 0.5
    assert track.lufs_integrated == -8.0
    assert track.true_peak == -0.5
    assert track.energy_curve == [0.1, 0.2, 0.3]


def test_assemble_track_maps_fields_from_cue_derivation_result(
    make_raw_features, make_cue_derivation_result
):
    raw = make_raw_features()
    phrase_grid = [make_cue_derivation_result().phrase_grid[0]]
    cue_ins = [make_cue_derivation_result().cue_ins[0]]
    cue_outs = [make_cue_derivation_result().cue_outs[0]]
    cue_result = make_cue_derivation_result(
        grid_start=1.5,
        grid_confidence=0.4,
        free_intro_end=16.0,
        phrase_length_bars=16.0,
        phrase_grid=phrase_grid,
        structure_template="film",
        cue_ins=cue_ins,
        cue_outs=cue_outs,
        status="cut_only",
    )

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.grid_start == 1.5
    assert track.grid_confidence == 0.4
    assert track.free_intro_end == 16.0
    assert track.phrase_length_bars == 16.0
    assert track.phrase_grid == phrase_grid
    assert track.structure_template == "film"
    assert track.cue_ins == cue_ins
    assert track.cue_outs == cue_outs
    assert track.status == "cut_only"


def test_assemble_track_id_is_content_hash(make_raw_features, make_cue_derivation_result):
    raw = make_raw_features(content_hash="abc-content-hash")
    cue_result = make_cue_derivation_result()

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.id == "abc-content-hash"


def test_assemble_track_path_is_input_parameter_not_source_path(
    make_raw_features, make_cue_derivation_result
):
    raw = make_raw_features(source_path="different-from-input.mp3")
    cue_result = make_cue_derivation_result()

    track = _assemble_track("actual-input-path.mp3", raw, cue_result)

    assert track.path == "actual-input-path.mp3"


def test_assemble_track_vocal_mask_is_renamed_vocal_band_energy(
    make_raw_features, make_cue_derivation_result
):
    raw = make_raw_features(vocal_band_energy=[0.9, 0.8, 0.7])
    cue_result = make_cue_derivation_result()

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.vocal_mask == [0.9, 0.8, 0.7]


def test_assemble_track_analysis_version_is_composed(make_raw_features, make_cue_derivation_result):
    raw = make_raw_features(feature_extractor_version="3")
    cue_result = make_cue_derivation_result(cue_derivation_version="2")

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.analysis_version == "3+2"


def test_assemble_track_familiarity_fields_are_none(make_raw_features, make_cue_derivation_result):
    raw = make_raw_features()
    cue_result = make_cue_derivation_result()

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.familiarity_score is None
    assert track.era is None
    assert track.is_club_edit is None


def test_assemble_track_beats_per_bar_carried_through(
    make_raw_features, make_cue_derivation_result
):
    raw = make_raw_features(beats_per_bar=3)
    cue_result = make_cue_derivation_result()

    track = _assemble_track("some/path.mp3", raw, cue_result)

    assert track.beats_per_bar == 3
