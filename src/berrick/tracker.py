"""Face-tracking behaviour: detect → engage → gaze (head + eyes) → disengage."""

from __future__ import annotations

import csv
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from .config import AxisConfig, Config, ServoConfig
from .detection import Face, FaceDetector
from .leds import LedRing
from .pid import PID
from .servos import ServoBank

log = logging.getLogger(__name__)


class State(Enum):
    IDLE = "idle"
    ENGAGED = "engaged"


@dataclass
class Status:
    state: State
    face: Face | None
    error: tuple[float, float]  # normalised offset of the face from frame centre, [-1, 1]


class EventLog:
    """CSV log of detections and engagement episodes (replaces report.txt)."""

    FIELDS = ("time_s", "event", "score", "duration_s", "x", "y", "w", "h")

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "w", newline="")  # noqa: SIM115 - closed in close()
        self._w = csv.writer(self._fh)
        self._w.writerow(self.FIELDS)
        self._t0 = time.monotonic()

    def write(self, event: str, face: Face | None = None, duration: float | None = None) -> None:
        box = (face.x, face.y, face.w, face.h) if face else ("", "", "", "")
        self._w.writerow(
            (
                f"{time.monotonic() - self._t0:.3f}",
                event,
                f"{face.score:.4f}" if face else "",
                f"{duration:.3f}" if duration is not None else "",
                *box,
            )
        )

    def close(self) -> None:
        self._fh.close()


def _map_offset(cfg: ServoConfig, e: float) -> float:
    """Map e∈[-1, 1] to a pulse: 0 → home, +1 → max_us, -1 → min_us."""
    e = max(-1.0, min(1.0, e))
    if e >= 0:
        return cfg.home_us + e * (cfg.max_us - cfg.home_us)
    return cfg.home_us + e * (cfg.home_us - cfg.min_us)


class _Axis:
    def __init__(self, cfg: AxisConfig) -> None:
        self.cfg = cfg
        p = cfg.pid
        self.pid = PID(p.kp, p.ki, p.kd, p.output_limit, p.integral_limit)

    def command(self, error: float, dt: float) -> float:
        """Return the pulse-width change (µs) to apply this frame."""
        if abs(error) < self.cfg.deadband:
            error = 0.0
        velocity = self.pid.update(error, dt)
        return (-velocity if self.cfg.invert else velocity) * dt


class Tracker:
    def __init__(
        self,
        cfg: Config,
        detector: FaceDetector,
        servos: ServoBank,
        leds: LedRing,
        events: EventLog | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cfg = cfg
        self.detector = detector
        self.servos = servos
        self.leds = leds
        self.events = events
        self.clock = clock
        self.state = State.IDLE
        self._pan = _Axis(cfg.pan)
        self._tilt = _Axis(cfg.tilt)
        self._seen = 0
        self._last_t: float | None = None
        self._last_seen = 0.0
        self._engaged_at = 0.0
        self._mouth_close_at: float | None = None
        self._engaged_flag = threading.Event()  # read by the experiment thread

    @property
    def engaged(self) -> bool:
        return self._engaged_flag.is_set()

    # -- state transitions ---------------------------------------------------

    def _engage(self, now: float, face: Face) -> None:
        self.state = State.ENGAGED
        self._engaged_flag.set()
        self._engaged_at = now
        log.info("engaged (score %.2f)", face.score)
        if self.events:
            self.events.write("engaged", face)
        self.leds.engaged()
        mouth = self.servos.get("mouth")
        if mouth and self.cfg.behavior.greet_with_mouth:
            with self.servos.lock:
                mouth.set_target(mouth.cfg.min_us)
            self._mouth_close_at = now + self.cfg.behavior.greet_open_s

    def _disengage(self, now: float) -> None:
        self.state = State.IDLE
        self._engaged_flag.clear()
        duration = self._last_seen - self._engaged_at
        log.info("disengaged after %.2fs", duration)
        if self.events:
            self.events.write("disengaged", duration=duration)
        self._pan.pid.reset()
        self._tilt.pid.reset()
        self.leds.idle()

    # -- main step -----------------------------------------------------------

    def process(self, frame: np.ndarray, now: float | None = None) -> Status:
        now = self.clock() if now is None else now
        dt = 0.0 if self._last_t is None else now - self._last_t
        self._last_t = now
        b = self.cfg.behavior

        faces = self.detector.detect(frame)
        face = max(faces, key=lambda f: f.area) if faces else None

        if face:
            self._seen += 1
            self._last_seen = now
            if self.events:
                self.events.write("detection", face)
        else:
            self._seen = 0

        if self.state is State.IDLE and self._seen >= b.acquire_frames:
            self._engage(now, face)
        elif self.state is State.ENGAGED and now - self._last_seen > b.lost_timeout_s:
            self._disengage(now)

        ex = ey = 0.0
        h, w = frame.shape[:2]
        if face:
            cx, cy = face.center
            ex, ey = (cx - w / 2) / (w / 2), (cy - h / 2) / (h / 2)

        with self.servos.lock:
            if self.state is State.ENGAGED and face:
                self._drive(ex, ey, dt)
            elif self.state is State.IDLE and now - self._last_seen > b.return_home_after_s:
                for name in ("pan", "tilt", "eye_x", "eye_y"):
                    if s := self.servos.get(name):
                        s.home()

            if self._mouth_close_at is not None and now >= self._mouth_close_at:
                if mouth := self.servos.get("mouth"):
                    mouth.home()
                self._mouth_close_at = None

        return Status(self.state, face, (ex, ey))

    def _drive(self, ex: float, ey: float, dt: float) -> None:
        if self.cfg.pan.enabled and (pan := self.servos.get("pan")):
            pan.nudge(self._pan.command(ex, dt))
        if self.cfg.tilt.enabled and (tilt := self.servos.get("tilt")):
            tilt.nudge(self._tilt.command(ey, dt))
        b = self.cfg.behavior
        if eye := self.servos.get("eye_x"):
            eye.set_target(_map_offset(eye.cfg, -ex if b.eyes_invert_x else ex))
        if eye := self.servos.get("eye_y"):
            eye.set_target(_map_offset(eye.cfg, -ey if b.eyes_invert_y else ey))


def draw_overlay(frame: np.ndarray, status: Status, fps: float) -> np.ndarray:
    import cv2

    color = (0, 255, 0) if status.state is State.ENGAGED else (0, 200, 255)
    if f := status.face:
        cv2.rectangle(frame, (f.x, f.y), (f.x + f.w, f.y + f.h), color, 2)
        cv2.putText(
            frame,
            f"{f.score:.2f}",
            (f.x, max(12, f.y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )
    h, w = frame.shape[:2]
    cv2.drawMarker(frame, (w // 2, h // 2), (255, 255, 255), cv2.MARKER_CROSS, 12, 1)
    cv2.putText(
        frame,
        f"{status.state.value}  {fps:4.1f} fps",
        (6, h - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
    )
    return frame
