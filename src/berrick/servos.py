"""Servo outputs with per-servo slew-rate limiting.

A background thread updates every servo at ``update_hz`` and moves it towards
its target at no more than ``max_speed_us_s``: this replaces the blocking
step loops of the 2019 code and gives smooth, non-jerky motion.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from .config import ServoConfig, ServosConfig

log = logging.getLogger(__name__)


class PulseOutput(Protocol):
    def write(self, us: float | None) -> None:
        """Send a pulse width in µs, or ``None`` to stop pulsing (servo goes limp)."""

    def close(self) -> None: ...


class Backend(Protocol):
    def output(self, pin: int) -> PulseOutput: ...
    def close(self) -> None: ...


# --- backends ----------------------------------------------------------------


class _PigpioOutput:
    def __init__(self, pi, pin: int) -> None:
        self._pi, self._pin = pi, pin

    def write(self, us: float | None) -> None:
        self._pi.set_servo_pulsewidth(self._pin, 0 if us is None else int(round(us)))

    def close(self) -> None:
        self.write(None)


class PigpioBackend:
    """DMA-timed pulses via the pigpio daemon. Jitter-free; Pi 1-4 only."""

    def __init__(self) -> None:
        import pigpio

        self._pi = pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError("cannot reach pigpiod: run `sudo systemctl enable --now pigpiod`")

    def output(self, pin: int) -> PulseOutput:
        return _PigpioOutput(self._pi, pin)

    def close(self) -> None:
        self._pi.stop()


class _GpiozeroOutput:
    MIN, MAX = 500.0, 2500.0

    def __init__(self, pin: int) -> None:
        from gpiozero import Servo

        self._servo = Servo(
            pin,
            initial_value=None,
            min_pulse_width=self.MIN / 1e6,
            max_pulse_width=self.MAX / 1e6,
            frame_width=0.02,
        )

    def write(self, us: float | None) -> None:
        if us is None:
            self._servo.value = None
            return
        mid, half = (self.MAX + self.MIN) / 2, (self.MAX - self.MIN) / 2
        self._servo.value = max(-1.0, min(1.0, (us - mid) / half))

    def close(self) -> None:
        self._servo.close()


class GpiozeroBackend:
    """gpiozero (lgpio pin factory). Works on every Pi including the Pi 5."""

    def output(self, pin: int) -> PulseOutput:
        return _GpiozeroOutput(pin)

    def close(self) -> None:
        pass


class _MockOutput:
    def __init__(self, pin: int) -> None:
        self.pin = pin
        self.last: float | None = None

    def write(self, us: float | None) -> None:
        self.last = us

    def close(self) -> None:
        self.last = None


class MockBackend:
    """No hardware: records pulse widths. For desktop development and tests."""

    def __init__(self) -> None:
        self.outputs: dict[int, _MockOutput] = {}

    def output(self, pin: int) -> PulseOutput:
        out = self.outputs[pin] = _MockOutput(pin)
        return out

    def close(self) -> None:
        pass


def create_backend(name: str) -> Backend:
    if name == "pigpio":
        return PigpioBackend()
    if name == "gpiozero":
        return GpiozeroBackend()
    if name == "mock":
        return MockBackend()
    raise ValueError(f"unknown servo backend '{name}'")


# --- servo + bank ------------------------------------------------------------


class Servo:
    def __init__(self, name: str, cfg: ServoConfig, out: PulseOutput) -> None:
        self.name, self.cfg, self._out = name, cfg, out
        self.position = cfg.home_us
        self.target = cfg.home_us
        self._out.write(self.position)

    def set_target(self, us: float) -> None:
        self.target = self.cfg.clamp(us)

    def nudge(self, delta_us: float) -> None:
        self.set_target(self.target + delta_us)

    def home(self) -> None:
        self.set_target(self.cfg.home_us)

    def step(self, dt: float) -> None:
        max_step = self.cfg.max_speed_us_s * dt
        diff = self.target - self.position
        if diff == 0:
            return
        self.position += max(-max_step, min(max_step, diff))
        self._out.write(self.position)

    def release(self) -> None:
        self._out.close()


class ServoBank:
    NAMES = ("pan", "tilt", "mouth", "eye_x", "eye_y")

    def __init__(self, cfg: ServosConfig, backend: Backend | None = None) -> None:
        self._cfg = cfg
        self._backend = backend or create_backend(cfg.backend)
        self.servos: dict[str, Servo] = {}
        for name in self.NAMES:
            scfg: ServoConfig = getattr(cfg, name)
            if scfg.enabled:
                self.servos[name] = Servo(name, scfg, self._backend.output(scfg.pin))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def get(self, name: str) -> Servo | None:
        return self.servos.get(name)

    def __enter__(self) -> ServoBank:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def step(self, dt: float) -> None:
        with self._lock:
            for s in self.servos.values():
                s.step(dt)

    def home(self) -> None:
        with self._lock:
            for s in self.servos.values():
                s.home()

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="servo-bank", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        period = 1.0 / self._cfg.update_hz
        last = time.monotonic()
        while not self._stop.wait(period):
            now = time.monotonic()
            self.step(now - last)
            last = now

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        for s in self.servos.values():
            try:
                s.release()
            except Exception:  # pragma: no cover - best effort on shutdown
                log.exception("failed to release servo %s", s.name)
        self._backend.close()
