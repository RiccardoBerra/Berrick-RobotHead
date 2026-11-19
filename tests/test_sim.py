import math

import numpy as np
import pytest

pytest.importorskip("mujoco")

from berrick import cli  # noqa: E402
from berrick.config import Config  # noqa: E402
from berrick.sim import Simulation, run_sim  # noqa: E402
from berrick.sim.model import SERVO_JOINTS, pulse_to_angle  # noqa: E402


@pytest.fixture
def cfg():
    c = Config()
    c.sim.leave_every_s = 0
    return c


def test_home_pulse_is_neutral_pose(cfg):
    for servo, joints in SERVO_JOINTS.items():
        s = getattr(cfg.servos, servo)
        for jm in joints:
            assert pulse_to_angle(cfg, s, jm, s.home_us) == 0


def test_model_builds_with_all_servos(cfg):
    for name in ("tilt", "eye_x", "eye_y"):
        getattr(cfg.servos, name).enabled = True
    sim = Simulation(cfg)
    sim.step_to(0.2)
    assert sim.data.time >= 0.2


def test_face_projection_centered_when_straight_ahead(cfg):
    cfg.sim.person_motion = "static"
    cfg.sim.person_offset = 0.0
    sim = Simulation(cfg)
    cam_z = sim.data.cam_xpos[sim._cam][2]
    sim.manual[:] = (0.8, 0.0, cam_z)
    sim.person_motion = "manual"
    sim.step_to(0.01)
    face = sim.project_face()
    cx, cy = face.center
    assert abs(cx - cfg.camera.width / 2) < 3
    assert abs(cy - cfg.camera.height / 2) < 3


def test_person_left_appears_left_in_image(cfg):
    cfg.sim.person_motion = "static"
    cfg.sim.person_offset = 0.25  # +y = robot's left
    sim = Simulation(cfg)
    sim.step_to(0.01)
    assert sim.project_face().center[0] < cfg.camera.width / 2


def test_hidden_person_not_detected(cfg):
    sim = Simulation(cfg)
    sim.person_visible = False
    sim.step_to(0.01)
    assert sim.project_face() is None


def test_closed_loop_centres_static_person(cfg):
    cfg.sim.person_motion = "static"
    cfg.sim.person_offset = 0.25
    hist = run_sim(cfg, duration=8, preview=False, realtime=False)
    assert hist.engaged[-1]
    assert abs(np.nanmean(hist.error_x[-30:])) < cfg.pan.deadband + 0.03
    expected = math.atan2(0.25, cfg.sim.person_distance)
    assert hist.pan[-1] == pytest.approx(expected, abs=math.radians(5))


def test_disengages_when_person_leaves(cfg):
    cfg.sim.leave_every_s = 10
    cfg.sim.leave_for_s = 4
    hist = run_sim(cfg, duration=10, preview=False, realtime=False)
    assert any(hist.engaged)
    assert not hist.engaged[-1]


def test_leds_follow_engagement(cfg):
    cfg.sim.person_motion = "static"
    sim = Simulation(cfg)
    sim.set_led(0, (255, 0, 0, 0))
    assert sim.model.mat_rgba[sim._led_mats[0]][0] > 0.5
    sim.set_led(0, (0, 0, 0, 0))
    assert sim.model.mat_emission[sim._led_mats[0]] == 0


def test_cli_sim_headless(tmp_path):
    rc = cli.main(["sim", "--headless", "--fast", "--duration", "2", "--log-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("sim-events-*.csv"))
