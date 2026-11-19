"""Drop-in sim implementations of the hardware interfaces."""

from __future__ import annotations

import numpy as np

from ..config import Config
from .model import SERVO_JOINTS
from .world import Simulation


class _SimOutput:
    def __init__(self, sim: Simulation, servo: str) -> None:
        self._sim, self._servo = sim, servo

    def write(self, us: float | None) -> None:
        if us is not None:  # a released servo simply holds its last position
            self._sim.set_pulse(self._servo, us)

    def close(self) -> None:
        pass


class SimServoBackend:
    """Maps GPIO pins back to servo names and drives the simulated joints."""

    def __init__(self, sim: Simulation, cfg: Config) -> None:
        self._sim = sim
        self._by_pin = {getattr(cfg.servos, name).pin: name for name in SERVO_JOINTS}

    def output(self, pin: int) -> _SimOutput:
        return _SimOutput(self._sim, self._by_pin[pin])

    def close(self) -> None:
        pass


class SimPixels:
    def __init__(self, sim: Simulation) -> None:
        self._sim = sim

    def set(self, i: int, color) -> None:
        self._sim.set_led(i, color)

    def show(self) -> None:
        pass

    def close(self) -> None:
        for i in range(self._sim.cfg.leds.count):
            self._sim.set_led(i, (0, 0, 0, 0))


class SimCamera:
    def __init__(self, sim: Simulation) -> None:
        self._sim = sim

    def read(self) -> np.ndarray:
        return self._sim.render_robot_camera()

    def close(self) -> None:
        pass
