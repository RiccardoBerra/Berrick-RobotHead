import pytest

from berrick.config import ServosConfig
from berrick.servos import MockBackend, ServoBank


def test_only_enabled_servos_created():
    bank = ServoBank(ServosConfig(), MockBackend())
    assert set(bank.servos) == {"pan", "mouth"}


def test_slew_rate_limit():
    backend = MockBackend()
    bank = ServoBank(ServosConfig(), backend)
    pan = bank.get("pan")
    pan.set_target(pan.cfg.max_us)
    bank.step(0.1)
    assert pan.position == pytest.approx(pan.cfg.home_us + pan.cfg.max_speed_us_s * 0.1)
    assert backend.outputs[pan.cfg.pin].last == pan.position
    for _ in range(100):
        bank.step(0.1)
    assert pan.position == pan.cfg.max_us


def test_target_clamped():
    bank = ServoBank(ServosConfig(), MockBackend())
    pan = bank.get("pan")
    pan.set_target(99999)
    assert pan.target == pan.cfg.max_us


def test_close_releases():
    backend = MockBackend()
    bank = ServoBank(ServosConfig(), backend)
    bank.close()
    assert all(o.last is None for o in backend.outputs.values())
