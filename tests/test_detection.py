import os
from pathlib import Path

import numpy as np
import pytest

from berrick.config import DetectorConfig
from berrick.detection import create_detector

cv2 = pytest.importorskip("cv2")
has_haar = pytest.mark.skipif(
    not hasattr(cv2, "CascadeClassifier"), reason="Haar cascades removed in OpenCV 5"
)
MODEL = Path(os.environ.get("BERRICK_YUNET", "models/face_detection_yunet_2023mar.onnx"))
BLANK = np.zeros((240, 320, 3), np.uint8)


@has_haar
def test_haar_on_blank_frame_finds_nothing():
    det = create_detector(DetectorConfig(backend="haar"))
    assert det.detect(BLANK) == []


@has_haar
def test_yunet_missing_model_falls_back(tmp_path):
    det = create_detector(DetectorConfig(model_path=str(tmp_path / "missing.onnx")))
    assert det.name == "haar"


def test_yunet_missing_model_no_fallback(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_detector(
            DetectorConfig(model_path=str(tmp_path / "missing.onnx"), fallback_to_haar=False)
        )


@pytest.mark.skipif(not MODEL.is_file(), reason="YuNet model not downloaded")
def test_yunet_blank_frame():
    det = create_detector(DetectorConfig(model_path=str(MODEL), fallback_to_haar=False))
    assert det.name == "yunet"
    assert det.detect(BLANK) == []
    assert det.detect(np.zeros((480, 640, 3), np.uint8)) == []  # input size change
