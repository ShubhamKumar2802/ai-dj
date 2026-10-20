import pytest
import yaml
from pydantic import ValidationError

from experiments.vocal_free_windows.config import (
    DEFAULT_CONFIG_PATH,
    PairConfig,
    SeparatorConfig,
    load_config,
)


def _write(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    return path


def _data():
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())


def test_committed_config_loads():
    cfg = load_config()
    assert (cfg.pair.a.name, cfg.pair.b.name) == ("Subha Hone Na De", "Lat Lag Gayee")
    assert cfg.pair.pair_id == "Y7G-tYRzwYY__KxCjVIFxZNo"
    assert cfg.exit_after_bar == 32
    assert cfg.render.bass_swap_bars == 16
    assert cfg.render.overlap_bars == 2
    assert cfg.windows.min_bars == 2


def test_unknown_key_fails(tmp_path):
    data = _data()
    data["render"]["overlap_beats"] = 4
    with pytest.raises(ValidationError, match="overlap_beats"):
        load_config(_write(tmp_path, data))


def test_odd_bass_swap_fails(tmp_path):
    data = _data()
    data["render"]["bass_swap_bars"] = 15
    with pytest.raises(ValidationError, match="bass_swap_bars"):
        load_config(_write(tmp_path, data))


def test_missing_field_fails(tmp_path):
    data = _data()
    del data["exit_after_bar"]
    with pytest.raises(ValidationError, match="exit_after_bar"):
        load_config(_write(tmp_path, data))


def test_missing_paths_reported():
    pair = PairConfig(
        a={"name": "A", "path": "nope/a [abcdefghijk].mp3"},
        b={"name": "B", "path": __file__},
    )
    assert pair.missing_paths() == ["nope/a [abcdefghijk].mp3"]
    assert pair.a.track_id == "abcdefghijk"


@pytest.mark.parametrize(
    "change", [{"model": "htdemucs_ft"}, {"shifts": 2}, {"overlap": 0.5}]
)
def test_separator_version_changes(change):
    base = {"model": "htdemucs", "shifts": 1, "overlap": 0.25, "device": "auto", "cache_dir": "x"}
    assert (
        SeparatorConfig(**base).separator_version
        != SeparatorConfig(**{**base, **change}).separator_version
    )


def test_separator_version_ignores_device():
    base = {"model": "htdemucs", "shifts": 1, "overlap": 0.25, "device": "auto", "cache_dir": "x"}
    assert (
        SeparatorConfig(**base).separator_version
        == SeparatorConfig(**{**base, "device": "cpu"}).separator_version
    )
