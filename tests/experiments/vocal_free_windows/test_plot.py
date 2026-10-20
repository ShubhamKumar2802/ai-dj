from experiments.vocal_free_windows.plot import draw_vocal_lane
from experiments.vocal_free_windows.windows import Window


def test_draws_png(tmp_path):
    levels = [0.1] * 40 + [0.0001] * 4 + [0.1] * 20
    times = [(i * 2.0, (i + 1) * 2.0) for i in range(len(levels))]
    path = draw_vocal_lane(
        tmp_path / "A_vocal_lane.png", "A: test", levels, times, -38.0,
        [Window(41, 44, 80.0, 88.0)], 32, 41,
    )
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
