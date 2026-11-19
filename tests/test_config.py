from pathlib import Path

import pytest

from berrick.config import ConfigError, config_from_dict, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_defaults_match_2019_robot():
    cfg = load_config(None)
    assert cfg.servos.pan.pin == 27
    assert cfg.servos.pan.home_us == 1850
    assert cfg.leds.count == 14


def test_partial_override():
    cfg = config_from_dict({"servos": {"pan": {"home_us": 1500}}, "pan": {"pid": {"kp": 3}}})
    assert cfg.servos.pan.home_us == 1500.0
    assert cfg.servos.pan.pin == 27
    assert cfg.pan.pid.kp == 3.0


@pytest.mark.parametrize(
    "data",
    [{"nope": 1}, {"servos": {"pan": {"pin": "x"}}}, {"preview": 1}, {"camera": 3}],
)
def test_invalid(data):
    with pytest.raises(ConfigError):
        config_from_dict(data)


@pytest.mark.parametrize("name", ["berrick.example.toml", "desktop.toml"])
def test_shipped_configs_load(name):
    load_config(ROOT / "config" / name)


def test_clamp_handles_reversed_range():
    cfg = load_config(None).servos.pan
    assert cfg.clamp(5000) == cfg.max_us
    assert cfg.clamp(0) == cfg.min_us
