import pytest
import yaml
from pydantic import ValidationError

from experiments.lyrics_sourcing.config import DEFAULT_CONFIG_PATH, load_config


def test_committed_config_loads():
    cfg = load_config()
    assert cfg.lyrics.impl == ["ytmusic", "lrclib"]
    assert cfg.transcribe.model == "mlx-community/whisper-small-mlx"
    assert cfg.transcribe.models_dir == "models/whisper"
    assert cfg.llm.provider == "ollama"


def test_unknown_key_fails(tmp_path):
    data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    data["time_match"]["min_coverag"] = 0.5
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValidationError, match="min_coverag"):
        load_config(path)


def test_thresholds_are_numeric_only():
    thresholds = load_config().time_match.thresholds()
    assert thresholds["min_coverage"] == 0.40
    assert "impl" not in thresholds
    assert "write_click_track" not in thresholds
