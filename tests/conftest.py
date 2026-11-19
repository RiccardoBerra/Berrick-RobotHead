import numpy as np
import pytest

from berrick.config import Config
from berrick.detection import Face
from berrick.leds import LedRing, MockPixels
from berrick.servos import MockBackend, ServoBank


class FakeDetector:
    name = "fake"

    def __init__(self):
        self.faces: list[Face] = []

    def detect(self, frame):
        return list(self.faces)


@pytest.fixture
def cfg():
    c = Config()
    c.servos.backend = "mock"
    c.leds.backend = "mock"
    c.leds.wipe_ms = 0
    return c


@pytest.fixture
def rig(cfg):
    from berrick.tracker import Tracker

    det = FakeDetector()
    bank = ServoBank(cfg.servos, MockBackend())
    leds = LedRing(cfg.leds, MockPixels(cfg.leds))
    return Tracker(cfg, det, bank, leds), det, bank


@pytest.fixture
def frame():
    return np.zeros((240, 320, 3), np.uint8)
