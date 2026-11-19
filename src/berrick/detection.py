"""Face detectors: YuNet (DNN, default) and Haar cascade (2019 behaviour)."""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .config import DetectorConfig

log = logging.getLogger(__name__)

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)

_HAAR_NAME = "haarcascade_frontalface_default.xml"
_HAAR_SYSTEM_DIRS = (
    "/usr/share/opencv4/haarcascades",
    "/usr/local/share/opencv4/haarcascades",
    "/opt/homebrew/share/opencv4/haarcascades",
)


@dataclass(frozen=True)
class Face:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self) -> tuple[float, float]:
        # NB: the 2019 code used (x + w) / 2, which is not the box centre.
        return (self.x + self.w / 2, self.y + self.h / 2)

    @property
    def area(self) -> int:
        return self.w * self.h


class FaceDetector(Protocol):
    name: str

    def detect(self, frame: np.ndarray) -> list[Face]: ...


def _find_haar(explicit: str) -> str:
    import cv2

    candidates = [explicit] if explicit else []
    data = getattr(cv2, "data", None)
    if data is not None:
        candidates.append(str(Path(data.haarcascades) / _HAAR_NAME))
    candidates += [str(Path(d) / _HAAR_NAME) for d in _HAAR_SYSTEM_DIRS]
    for c in candidates:
        if Path(c).is_file():
            return c
    raise FileNotFoundError(f"Haar cascade not found (tried: {', '.join(candidates)})")


class HaarDetector:
    name = "haar"

    def __init__(self, cfg: DetectorConfig) -> None:
        import cv2

        if not hasattr(cv2, "CascadeClassifier"):
            raise RuntimeError(
                f"OpenCV {cv2.__version__} has no Haar cascades (removed in OpenCV 5): "
                "use detector.backend = 'yunet' or install opencv-python<5"
            )
        self._cv2 = cv2
        self._cfg = cfg
        path = _find_haar(cfg.haar_cascade)
        self._clf = cv2.CascadeClassifier(path)
        if self._clf.empty():
            raise RuntimeError(f"failed to load Haar cascade {path}")

    def detect(self, frame: np.ndarray) -> list[Face]:
        cv2 = self._cv2
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        size = self._cfg.min_face_size
        rects, _levels, weights = self._clf.detectMultiScale3(
            gray,
            scaleFactor=self._cfg.haar_scale_factor,
            minNeighbors=self._cfg.haar_min_neighbors,
            minSize=(size, size),
            flags=cv2.CASCADE_SCALE_IMAGE,
            outputRejectLevels=True,
        )
        weights = np.ravel(weights)
        return [
            Face(int(x), int(y), int(w), int(h), float(s))
            for (x, y, w, h), s in zip(rects, weights, strict=False)
        ]


class YuNetDetector:
    name = "yunet"

    def __init__(self, cfg: DetectorConfig) -> None:
        import cv2

        path = Path(cfg.model_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"YuNet model not found at {path}. Run `berrick download-model`."
            )
        self._cfg = cfg
        self._size = (320, 240)
        self._det = cv2.FaceDetectorYN.create(
            str(path), "", self._size, cfg.score_threshold, cfg.nms_threshold, 5000
        )

    def detect(self, frame: np.ndarray) -> list[Face]:
        h, w = frame.shape[:2]
        if (w, h) != self._size:
            self._size = (w, h)
            self._det.setInputSize(self._size)
        _, faces = self._det.detect(frame)
        if faces is None:
            return []
        out = []
        for f in faces:
            x, y, fw, fh = (int(v) for v in f[:4])
            if min(fw, fh) >= self._cfg.min_face_size:
                out.append(Face(x, y, fw, fh, float(f[14])))
        return out


def create_detector(cfg: DetectorConfig) -> FaceDetector:
    if cfg.backend == "haar":
        return HaarDetector(cfg)
    if cfg.backend == "yunet":
        try:
            return YuNetDetector(cfg)
        except Exception as exc:
            if not cfg.fallback_to_haar:
                raise
            log.warning("YuNet unavailable (%s); falling back to Haar cascade", exc)
            try:
                return HaarDetector(cfg)
            except Exception as haar_exc:
                raise RuntimeError(f"no face detector available: {exc}; {haar_exc}") from exc
    raise ValueError(f"unknown detector backend '{cfg.backend}'")


def download_model(dest: str | Path, url: str = YUNET_URL) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as fh:
        while chunk := resp.read(1 << 16):
            fh.write(chunk)
    tmp.replace(dest)
    return dest
