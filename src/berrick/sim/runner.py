"""`berrick sim`: run the real tracker against the MuJoCo robot."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from ..config import Config
from ..leds import LedRing
from ..servos import ServoBank
from ..tracker import EventLog, State, Status, Tracker, draw_overlay
from .backends import SimCamera, SimPixels, SimServoBackend
from .world import GroundTruthDetector, Simulation

log = logging.getLogger(__name__)

HELP = [
    "q quit   space show/hide person",
    "1 sweep  2 static  3 manual",
    "manual: a/d left-right  w/s near-far  r/f up-down",
    "view: j/l orbit  i/k tilt  u/o zoom",
]


@dataclass
class SimHistory:
    t: list[float] = field(default_factory=list)
    error_x: list[float] = field(default_factory=list)
    error_y: list[float] = field(default_factory=list)
    engaged: list[bool] = field(default_factory=list)
    pan: list[float] = field(default_factory=list)

    def add(self, t: float, status: Status, pan: float) -> None:
        self.t.append(t)
        self.error_x.append(status.error[0] if status.face else float("nan"))
        self.error_y.append(status.error[1] if status.face else float("nan"))
        self.engaged.append(status.state is State.ENGAGED)
        self.pan.append(pan)


def _panel(sim: Simulation, status: Status, t: float, width: int, height: int) -> np.ndarray:
    import cv2

    img = np.full((height, width, 3), 28, np.uint8)
    deg = {j: np.degrees(sim.joint_angle(j)) for j in ("pan", "tilt", "eye_x_l", "jaw")}
    lines = [
        f"t={t:6.1f}s  {status.state.value.upper()}  person: {sim.person_motion}",
        f"pan {deg['pan']:+5.1f}  tilt {deg['tilt']:+5.1f}  "
        f"eyes {deg['eye_x_l']:+5.1f}  jaw {deg['jaw']:+4.1f} deg",
        *HELP,
    ]
    for i, line in enumerate(lines):
        color = (120, 230, 120) if i == 0 and status.state is State.ENGAGED else (220, 220, 220)
        cv2.putText(img, line, (10, 20 + 17 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
    return img


def _compose(view: np.ndarray, robot: np.ndarray, panel: np.ndarray) -> np.ndarray:
    import cv2

    h = view.shape[0]
    pw = panel.shape[1]
    robot = cv2.resize(robot, (pw, h - panel.shape[0]))
    return np.hstack([view, np.vstack([robot, panel])])


def _handle_key(sim: Simulation, key: int) -> bool:
    """Return False to quit."""
    if key in (ord("q"), 27):
        return False
    step = {ord("a"): (0, 0.03, 0), ord("d"): (0, -0.03, 0), ord("w"): (-0.03, 0, 0),
            ord("s"): (0.03, 0, 0), ord("r"): (0, 0, 0.02), ord("f"): (0, 0, -0.02)}  # fmt: skip
    cam = sim.free_cam
    if key in step:
        sim.person_motion = "manual"
        sim.manual += step[key]
        sim.manual[0] = max(0.3, sim.manual[0])
    elif key == ord(" "):
        sim.person_visible = not sim.person_visible
    elif key in (ord("1"), ord("2"), ord("3")):
        sim.person_motion = ("sweep", "static", "manual")[key - ord("1")]
    elif key in (ord("j"), ord("l")):
        cam.azimuth += 5 if key == ord("j") else -5
    elif key in (ord("i"), ord("k")):
        cam.elevation = float(np.clip(cam.elevation + (3 if key == ord("i") else -3), -89, 89))
    elif key in (ord("u"), ord("o")):
        cam.distance = float(np.clip(cam.distance * (0.9 if key == ord("u") else 1.1), 0.3, 6))
    return True


def run_sim(
    cfg: Config,
    *,
    duration: float | None = None,
    preview: bool = True,
    realtime: bool = True,
    twin: bool = False,
    record: str | None = None,
    log_dir: str | None = None,
) -> SimHistory:
    sim = Simulation(cfg)
    servos = ServoBank(cfg.servos, SimServoBackend(sim, cfg))
    leds = LedRing(cfg.leds, SimPixels(sim))

    if twin:
        from ..camera import OpenCVCamera
        from ..detection import create_detector

        camera = OpenCVCamera(cfg.camera)
        detector = create_detector(cfg.detector)
        sim.person_visible = False
    else:
        camera = SimCamera(sim)
        if cfg.sim.detector == "real":
            from ..detection import create_detector

            detector = create_detector(cfg.detector)
        else:
            detector = GroundTruthDetector(sim)
    log.info("sim: detector=%s twin=%s", detector.name, twin)

    events = None
    if log_dir:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        events = EventLog(Path(log_dir) / f"sim-events-{stamp}.csv")
    tracker = Tracker(cfg, detector, servos, leds, events)
    leds.idle()

    writer = None
    history = SimHistory()
    dt = 1.0 / cfg.camera.fps
    t = 0.0
    wall0 = last_wall = time.monotonic()
    fps = 0.0
    try:
        if preview or record:
            import cv2
        while duration is None or t < duration:
            t += dt
            servos.step(dt)  # deterministic servo slewing on sim time
            sim.step_to(t)
            frame = camera.read()
            if frame is None:
                continue
            status = tracker.process(frame, now=t)
            history.add(t, status, sim.joint_angle("pan"))

            if preview or record:
                robot = draw_overlay(frame, status, fps or 1 / dt)
                panel_w = int(cfg.sim.view_height * 4 / 3 * 0.75)
                panel = _panel(sim, status, t, panel_w, cfg.sim.view_height // 4)
                img = _compose(sim.render_view(), robot, panel)
                if record:
                    if writer is None:
                        Path(record).parent.mkdir(parents=True, exist_ok=True)
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        writer = cv2.VideoWriter(record, fourcc, 1 / dt, img.shape[1::-1])
                    writer.write(img)
                if preview:
                    cv2.imshow("Berrick sim", img)
                    if not _handle_key(sim, cv2.waitKey(1) & 0xFF):
                        break

            if realtime:
                lag = (wall0 + t) - time.monotonic()
                if lag > 0:
                    time.sleep(lag)
            now = time.monotonic()
            fps = 0.9 * fps + 0.1 / max(now - last_wall, 1e-6)
            last_wall = now
    except KeyboardInterrupt:
        pass
    finally:
        if writer is not None:
            writer.release()
        if events:
            events.close()
        servos.close()
        camera.close()
        sim.close()
        if preview:
            import cv2

            cv2.destroyAllWindows()
    return history
