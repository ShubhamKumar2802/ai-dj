from experiments.llm_camelot_sequencer.structure_llm import validate_structure_labels


def test_valid_labels_pass_through_unchanged(make_track, make_labels):
    track = make_track(duration=180.0, grid_start=4.0)
    labels = make_labels(intro_end=8.0, chorus1_start=30.0, chorus1_end=60.0)

    result = validate_structure_labels(labels, track)

    assert result == labels


def test_values_are_clamped_to_track_duration(make_track, make_labels):
    track = make_track(duration=100.0, grid_start=4.0)
    labels = make_labels(intro_end=-5.0, chorus1_start=30.0, chorus1_end=150.0)

    result = validate_structure_labels(labels, track)

    assert result is not None
    assert result.intro_end == 0.0
    assert result.chorus1_end == 100.0


def test_missing_intro_end_falls_back_to_free_intro_end(make_track, make_labels):
    track = make_track(duration=180.0, grid_start=4.0, free_intro_end=12.0)
    labels = make_labels(intro_end=None, chorus1_start=30.0, chorus1_end=60.0)

    result = validate_structure_labels(labels, track)

    assert result is not None
    assert result.intro_end == 12.0


def test_missing_chorus_boundary_rejects_the_track(make_track, make_labels):
    track = make_track()
    labels = make_labels(chorus1_start=None)

    assert validate_structure_labels(labels, track) is None


def test_chorus_out_of_order_rejects_the_track(make_track, make_labels):
    track = make_track()
    labels = make_labels(chorus1_start=60.0, chorus1_end=30.0)  # end before start

    assert validate_structure_labels(labels, track) is None


def test_chorus1_start_before_intro_end_rejects_the_track(make_track, make_labels):
    track = make_track()
    labels = make_labels(intro_end=40.0, chorus1_start=10.0, chorus1_end=60.0)

    assert validate_structure_labels(labels, track) is None


def test_chorus_shorter_than_minimum_span_rejects_the_track(make_track, make_labels):
    track = make_track()
    labels = make_labels(chorus1_start=30.0, chorus1_end=31.0)  # 1.0s, below 3.0s minimum

    assert validate_structure_labels(labels, track) is None


def test_span_shorter_than_min_play_seconds_rejects_the_track(make_track, make_labels):
    track = make_track(grid_start=50.0)
    labels = make_labels(chorus1_start=30.0, chorus1_end=55.0)  # 55 - 50 = 5.0s span

    assert validate_structure_labels(labels, track, min_play_seconds=8.0) is None


def test_span_exactly_at_min_play_seconds_is_accepted(make_track, make_labels):
    track = make_track(grid_start=50.0)
    labels = make_labels(chorus1_start=30.0, chorus1_end=58.0)  # 58 - 50 = 8.0s span

    assert validate_structure_labels(labels, track, min_play_seconds=8.0) is not None


def test_outro_before_chorus1_end_is_dropped_not_rejected(make_track, make_labels):
    track = make_track()
    labels = make_labels(chorus1_start=30.0, chorus1_end=60.0, outro_start=45.0)  # before end

    result = validate_structure_labels(labels, track)

    assert result is not None
    assert result.outro_start is None


def test_valid_outro_after_chorus1_end_is_kept(make_track, make_labels):
    track = make_track(duration=180.0)
    labels = make_labels(chorus1_start=30.0, chorus1_end=60.0, outro_start=150.0)

    result = validate_structure_labels(labels, track)

    assert result is not None
    assert result.outro_start == 150.0
