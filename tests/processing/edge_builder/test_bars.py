from processing.edge_builder.bars import position_to_bar


def test_before_first_downbeat(make_track):
    track = make_track(downbeat_times=[2.0, 4.0, 6.0], energy_curve=[0.1, 0.2])
    assert position_to_bar(0.0, track) == 0


def test_exactly_on_a_downbeat(make_track):
    track = make_track(downbeat_times=[0.0, 2.0, 4.0, 6.0], energy_curve=[0.1, 0.2, 0.3])
    assert position_to_bar(2.0, track) == 1
    assert position_to_bar(4.0, track) == 2


def test_past_the_last_downbeat(make_track):
    track = make_track(downbeat_times=[0.0, 2.0, 4.0], energy_curve=[0.1, 0.2])
    assert position_to_bar(100.0, track) == 1


def test_fewer_than_two_downbeats_clamps_without_raising(make_track):
    track = make_track(downbeat_times=[0.0], energy_curve=[])
    assert position_to_bar(0.0, track) == 0
