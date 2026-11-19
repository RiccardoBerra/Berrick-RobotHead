import csv
from pathlib import Path

import numpy as np
import pytest

from berrick import camera, cli

cv2 = pytest.importorskip("cv2")
MODEL = Path("models/face_detection_yunet_2023mar.onnx").resolve()


class FakeCamera:
    def __init__(self, n):
        self.n = n
        self.closed = False

    def read(self):
        if self.n == 0:
            raise KeyboardInterrupt  # what Ctrl+C does in the real loop
        self.n -= 1
        return np.zeros((240, 320, 3), np.uint8)

    def close(self):
        self.closed = True


def _detector_section():
    if MODEL.is_file():
        return f'[detector]\nmodel_path = "{MODEL}"\n'
    if hasattr(cv2, "CascadeClassifier"):
        return '[detector]\nbackend = "haar"\n'
    pytest.skip("needs the YuNet model or OpenCV 4")


def test_run_loop_with_mock_hardware(tmp_path, monkeypatch):
    cam = FakeCamera(20)
    monkeypatch.setattr(camera, "open_camera", lambda cfg: cam)
    cfg_file = tmp_path / "c.toml"
    cfg_file.write_text(
        '[servos]\nbackend = "mock"\n[leds]\nbackend = "mock"\nwipe_ms = 0\n' + _detector_section()
    )
    logs = tmp_path / "logs"
    assert cli.main(["-c", str(cfg_file), "run", "--no-preview", "--log-dir", str(logs)]) == 0
    assert cam.closed
    (log,) = logs.glob("events-*.csv")
    with open(log) as fh:
        assert next(csv.reader(fh))[0] == "time_s"


def test_parser():
    assert cli.build_parser().parse_args(["calibrate", "pan"]).servo == "pan"


def test_missing_config_is_friendly(tmp_path, capsys):
    assert cli.main(["-c", str(tmp_path / "nope.toml"), "download-model"]) == 2
    assert "not found" in capsys.readouterr().err


def test_invalid_config_is_friendly(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("[servos]\nbogus = 1\n")
    assert cli.main(["-c", str(bad), "download-model"]) == 2
    assert "unknown config key 'servos.bogus'" in capsys.readouterr().err
