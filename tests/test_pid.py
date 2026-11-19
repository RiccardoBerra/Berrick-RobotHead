import pytest

from berrick.pid import PID


def test_proportional():
    assert PID(kp=2).update(3, 0.1) == pytest.approx(6)


def test_integral_accumulates():
    pid = PID(kp=0, ki=1)
    pid.update(1, 0.5)
    assert pid.update(1, 0.5) == pytest.approx(1.0)


def test_derivative():
    pid = PID(kp=0, kd=1)
    pid.update(0, 0.1)
    assert pid.update(1, 0.1) == pytest.approx(10)


def test_output_clamped_and_antiwindup():
    pid = PID(kp=1, ki=1, output_limit=1)
    for _ in range(100):
        assert pid.update(10, 0.1) == 1
    # integral did not wind up: reversing the error reacts immediately
    assert pid.update(-1, 0.1) < 0


def test_zero_dt_returns_last():
    pid = PID(kp=1)
    pid.update(5, 0.1)
    assert pid.update(100, 0) == 5


def test_reset():
    pid = PID(kp=0, ki=1)
    pid.update(1, 1)
    pid.reset()
    assert pid.update(0, 1) == 0
