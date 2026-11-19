"""Camera backends returning BGR frames (OpenCV convention)."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from .config import CameraConfig


class Camera(Protocol):
    def read(self) -> np.ndarray | None: ...
    def close(self) -> None: ...


class OpenCVCamera:
    """USB webcam / laptop camera. Handy for developing without a Pi."""

    def __init__(self, cfg: CameraConfig) -> None:
        import cv2

        self._cv2 = cv2
        self._cfg = cfg
        self._cap = cv2.VideoCapture(cfg.device)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open camera device {cfg.device}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        self._cap.set(cv2.CAP_PROP_FPS, cfg.fps)

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        if not ok:
            return None
        h, w = frame.shape[:2]
        if (w, h) != (self._cfg.width, self._cfg.height):
            frame = self._cv2.resize(frame, (self._cfg.width, self._cfg.height))
        if self._cfg.hflip or self._cfg.vflip:
            code = -1 if (self._cfg.hflip and self._cfg.vflip) else (1 if self._cfg.hflip else 0)
            frame = self._cv2.flip(frame, code)
        return frame

    def close(self) -> None:
        self._cap.release()


class Picamera2Camera:
    """Raspberry Pi camera via libcamera (replaces the legacy `picamera`)."""

    def __init__(self, cfg: CameraConfig) -> None:
        from libcamera import Transform
        from picamera2 import Picamera2

        self._cam = Picamera2()
        config = self._cam.create_video_configuration(
            # "RGB888" in picamera2 is BGR byte order, i.e. what OpenCV expects.
            main={"size": (cfg.width, cfg.height), "format": "RGB888"},
            transform=Transform(hflip=cfg.hflip, vflip=cfg.vflip),
            controls={"FrameRate": cfg.fps},
        )
        self._cam.configure(config)
        self._cam.start()

    def read(self) -> np.ndarray | None:
        return self._cam.capture_array("main")

    def close(self) -> None:
        self._cam.stop()
        self._cam.close()


def open_camera(cfg: CameraConfig) -> Camera:
    if cfg.backend == "picamera2":
        return Picamera2Camera(cfg)
    if cfg.backend == "opencv":
        return OpenCVCamera(cfg)
    raise ValueError(f"unknown camera backend '{cfg.backend}'")
