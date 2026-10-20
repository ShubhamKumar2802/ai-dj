import pytest

from experiments.vocal_free_windows.run_experiment import main


def test_missing_a_path_exits_naming_it(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)  # main() chdirs to the repo root; keep the test's cwd clean
    b = tmp_path / "b.mp3"
    b.write_bytes(b"x")
    missing = tmp_path / "nope [abcdefghijk].mp3"
    with pytest.raises(SystemExit) as exc:
        main(["--a", str(missing), "--b", str(b)])
    assert exc.value.code == 2
    assert str(missing) in capsys.readouterr().err


def test_a_without_b_is_an_error():
    with pytest.raises(SystemExit):
        main(["--a", "x.mp3"])
