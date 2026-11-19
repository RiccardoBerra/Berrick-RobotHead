"""MuJoCo world: physics stepping, person motion, rendering, ground truth."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..config import Config
from ..detection import Face
from .model import LEDS_PER_EYE, SERVO_JOINTS, build_mjcf, pulse_to_angle


def _check_texture(path: str) -> str:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"face texture not found: {p}")
    return str(p)


class Simulation:
    def __init__(self, cfg: Config) -> None:
        import mujoco

        self._mj = mujoco
        self.cfg = cfg
        tex = _check_texture(cfg.sim.face_texture) if cfg.sim.face_texture else None
        self.model = mujoco.MjModel.from_xml_string(build_mjcf(cfg, tex))
        self.data = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(cfg.sim.seed)

        self._act = {
            jm.joint: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, jm.joint)
            for joints in SERVO_JOINTS.values()
            for jm in joints
        }
        self._led_mats = [
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_MATERIAL, f"led{i}")
            for i in range(2 * LEDS_PER_EYE)
        ]
        self._cam = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, "robot_cam")
        self._person_mocap = self.model.body_mocapid[
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "person")
        ]
        self.person_motion = cfg.sim.person_motion
        self.person_visible = True
        self.manual = np.array([cfg.sim.person_distance, 0.0, cfg.sim.person_height])

        self.free_cam = mujoco.MjvCamera()
        self.free_cam.lookat[:] = (0.38, 0.0, 0.95)
        self.free_cam.distance, self.free_cam.azimuth, self.free_cam.elevation = 1.6, 115, -14

        self._renderers: dict[tuple[int, int], object] = {}
        for servo in SERVO_JOINTS:
            self.set_pulse(servo, getattr(cfg.servos, servo).home_us)
        self.set_person(0.0)
        mujoco.mj_forward(self.model, self.data)

    # -- inputs ----------------------------------------------------------------

    def set_pulse(self, servo: str, us: float) -> None:
        scfg = getattr(self.cfg.servos, servo)
        for jm in SERVO_JOINTS[servo]:
            self.data.ctrl[self._act[jm.joint]] = pulse_to_angle(self.cfg, scfg, jm, us)

    def set_led(self, i: int, color) -> None:
        if not 0 <= i < len(self._led_mats):
            return
        c = [*color, 0, 0, 0, 0][:4]
        w = c[3] / 255
        b = self.cfg.leds.brightness
        rgb = [min(1.0, (v / 255 + w) * b) for v in c[:3]]
        lit = any(v > 0.02 for v in rgb)
        rgba = [*rgb, 1.0] if lit else [0.2, 0.2, 0.2, 1.0]
        self.model.mat_rgba[self._led_mats[i]] = rgba
        self.model.mat_emission[self._led_mats[i]] = 1.0 if lit else 0.0

    # -- person ----------------------------------------------------------------

    def person_position(self, t: float) -> np.ndarray | None:
        s = self.cfg.sim
        if not self.person_visible:
            return None
        if self.person_motion == "manual":
            return self.manual.copy()
        if self.person_motion == "static":
            return np.array([s.person_distance, s.person_offset, s.person_height])
        if s.leave_every_s > 0 and (t % s.leave_every_s) > s.leave_every_s - s.leave_for_s:
            return None  # walked away
        y = s.sweep_amplitude * math.sin(2 * math.pi * t / s.sweep_period_s)
        z = s.person_height + 0.04 * math.sin(2 * math.pi * t / (s.sweep_period_s * 0.7))
        return np.array([s.person_distance, y, z])

    def set_person(self, t: float) -> None:
        pos = self.person_position(t)
        if pos is None:
            pos = np.array([self.cfg.sim.person_distance, 2.5, self.cfg.sim.person_height])
        self.data.mocap_pos[self._person_mocap] = pos
        yaw = math.atan2(-pos[1], -pos[0])  # body +x faces the robot
        self.data.mocap_quat[self._person_mocap] = (math.cos(yaw / 2), 0, 0, math.sin(yaw / 2))

    # -- stepping ----------------------------------------------------------------

    def step_to(self, t: float) -> None:
        self.set_person(t)
        while self.data.time < t:
            self._mj.mj_step(self.model, self.data)

    def joint_angle(self, joint: str) -> float:
        jid = self._mj.mj_name2id(self.model, self._mj.mjtObj.mjOBJ_JOINT, joint)
        return float(self.data.qpos[self.model.jnt_qposadr[jid]])

    # -- rendering ----------------------------------------------------------------

    def _renderer(self, w: int, h: int):
        key = (w, h)
        if key not in self._renderers:
            self._renderers[key] = self._mj.Renderer(self.model, h, w)
        return self._renderers[key]

    def render_robot_camera(self) -> np.ndarray:
        """BGR frame from the head camera, the same format as the real camera."""
        w, h = self.cfg.camera.width, self.cfg.camera.height
        r = self._renderer(w, h)
        r.update_scene(self.data, camera=self._cam)
        return np.ascontiguousarray(r.render()[:, :, ::-1])

    def render_view(self) -> np.ndarray:
        r = self._renderer(self.cfg.sim.view_width, self.cfg.sim.view_height)
        r.update_scene(self.data, camera=self.free_cam)
        return np.ascontiguousarray(r.render()[:, :, ::-1])

    def close(self) -> None:
        for r in self._renderers.values():
            r.close()
        self._renderers.clear()

    # -- ground truth ----------------------------------------------------------------

    def project_face(self) -> Face | None:
        """Where the person's face is in the robot camera image (no noise)."""
        if self.data.mocap_pos[self._person_mocap][1] > 2.0:
            return None
        head = self.data.mocap_pos[self._person_mocap]
        cam_pos = self.data.cam_xpos[self._cam]
        R = self.data.cam_xmat[self._cam].reshape(3, 3)  # columns: cam x, y, z in world
        p = R.T @ (head - cam_pos)
        depth = -p[2]  # MuJoCo cameras look along -z
        if depth <= 0.05:
            return None
        w, h = self.cfg.camera.width, self.cfg.camera.height
        f = (h / 2) / math.tan(math.radians(self.model.cam_fovy[self._cam]) / 2)
        u, v = w / 2 + f * p[0] / depth, h / 2 - f * p[1] / depth
        size = f * 0.17 / depth
        if not (0 <= u < w and 0 <= v < h):
            return None
        return Face(int(u - size / 2), int(v - size / 2), int(size), int(size), 1.0)


class GroundTruthDetector:
    """Detector that reads the face position from the simulator, with noise and misses."""

    name = "ground_truth"

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim

    def detect(self, frame: np.ndarray) -> list[Face]:
        face = self.sim.project_face()
        s = self.sim.cfg.sim
        if face is None or self.sim.rng.random() < s.miss_rate:
            return []
        dx, dy = self.sim.rng.normal(0, s.noise_px, 2)
        score = float(np.clip(self.sim.rng.normal(0.9, 0.04), 0, 1))
        return [Face(int(face.x + dx), int(face.y + dy), face.w, face.h, score)]
