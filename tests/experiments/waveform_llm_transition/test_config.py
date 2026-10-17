import pytest
import yaml
from pydantic import ValidationError

from experiments.waveform_llm_transition.config import (
    DEFAULT_CONFIG_PATH,
    PairConfig,
    load_config,
)


def test_committed_config_loads():
    cfg = load_config()
    assert [(p.a.name, p.b.name) for p in cfg.pairs] == [
        ("Rock Tha Party", "Marjaani"),
        ("Zingaat", "Munni Badnaam Hui"),
    ]
    assert cfg.pairs[0].pair_id == "gwqenR0crHo__RDIRaFGr19s"
    assert cfg.tiles.tile_s == 60
    assert cfg.llm.model is None
    assert cfg.llm.max_tokens == 32768
    assert cfg.llm.timeout_s == 300
    assert cfg.bands.range_db == 24


def test_unknown_key_fails(tmp_path):
    data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    data["tiles"]["tile_secs"] = 30
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ValidationError, match="tile_secs"):
        load_config(path)


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_max_tokens_fails(tmp_path, value):
    data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    data["llm"]["max_tokens"] = value
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ValidationError, match="max_tokens"):
        load_config(path)


@pytest.mark.parametrize(
    ("section", "key"),
    [("llm", "timeout_s"), ("bands", "range_db"), ("bands", "smooth_beats")],
)
@pytest.mark.parametrize("value", [0, -5])
def test_non_positive_settings_fail(tmp_path, section, key, value):
    data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    data[section][key] = value
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ValidationError, match=key):
        load_config(path)


def test_null_max_tokens_loads(tmp_path):
    data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    data["llm"]["max_tokens"] = None
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    assert load_config(path).llm.max_tokens is None


def test_missing_path_is_reported_per_pair(tmp_path):
    present = tmp_path / "a [abcdef1].mp3"
    present.write_bytes(b"")
    pair = PairConfig(
        a={"name": "A", "path": str(present)},
        b={"name": "B", "path": str(tmp_path / "gone.mp3")},
    )
    assert pair.missing_paths() == [str(tmp_path / "gone.mp3")]
    assert pair.pair_id == "abcdef1__gone"
