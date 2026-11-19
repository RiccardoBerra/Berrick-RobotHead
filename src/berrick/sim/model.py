"""Procedural MJCF model of Berrick and a person, built from the config.

The robot is made of primitives sized like the real head. Joint ranges come
from the servo pulse limits, with the servo's ``home_us`` as the neutral pose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..config import Config, ServoConfig

TABLE_Z = 0.72  # robot sits on a table
LEDS_PER_EYE = 7  # 2 x 7 = the 14-pixel strip of the original build
EYE_Y, EYE_Z, HEAD_FRONT = 0.042, 0.055, 0.081


@dataclass(frozen=True)
class JointMap:
    joint: str
    sign: int
    mouth: bool = False


# Signs reproduce the default `invert = true` wiring of the 2019 robot:
# a lower pan pulse turns the head right, a lower tilt pulse looks down,
# a lower mouth pulse opens the jaw.
SERVO_JOINTS: dict[str, tuple[JointMap, ...]] = {
    "pan": (JointMap("pan", +1),),
    "tilt": (JointMap("tilt", -1),),
    "eye_x": (JointMap("eye_x_l", +1), JointMap("eye_x_r", +1)),
    "eye_y": (JointMap("eye_y_l", -1), JointMap("eye_y_r", -1)),
    "mouth": (JointMap("jaw", -1, mouth=True),),
}


def pulse_to_angle(cfg: Config, servo: ServoConfig, jm: JointMap, us: float) -> float:
    """Joint angle (rad) for a pulse width (µs)."""
    k = cfg.sim.mouth_deg_per_us if jm.mouth else cfg.sim.deg_per_us
    return math.radians(jm.sign * (us - servo.home_us) * k)


def _range(cfg: Config, servo: ServoConfig, jm: JointMap) -> tuple[float, float]:
    a, b = (pulse_to_angle(cfg, servo, jm, us) for us in (servo.min_us, servo.max_us))
    lo, hi = sorted((a, b))
    return lo - 0.01, hi + 0.01


def _joint(name: str, axis: str, rng: tuple[float, float]) -> str:
    return f'<joint name="{name}" type="hinge" axis="{axis}" range="{rng[0]:.4f} {rng[1]:.4f}"/>'


def _eye(cfg: Config, side: str, y: float) -> str:
    rx = _range(cfg, cfg.servos.eye_x, SERVO_JOINTS["eye_x"][0])
    ry = _range(cfg, cfg.servos.eye_y, SERVO_JOINTS["eye_y"][0])
    return f"""
          <body name="eye_{side}" pos="{HEAD_FRONT - 0.012} {y} {EYE_Z}">
            {_joint(f"eye_x_{side}", "0 0 1", rx)}
            {_joint(f"eye_y_{side}", "0 1 0", ry)}
            <geom type="sphere" size="0.021" material="eyewhite" mass="0.005"/>
            <geom type="sphere" size="0.0085" pos="0.016 0 0" material="pupil" mass="0.001"/>
          </body>"""


def _leds() -> str:
    out = []
    for e, y0 in enumerate((EYE_Y, -EYE_Y)):
        for i in range(LEDS_PER_EYE):
            a = 2 * math.pi * i / LEDS_PER_EYE + math.pi / 2
            y, z = y0 + 0.031 * math.cos(a), EYE_Z + 0.031 * math.sin(a)
            n = e * LEDS_PER_EYE + i
            out.append(
                f'<geom name="led{n}" type="sphere" size="0.0055" material="led{n}" '
                f'pos="{HEAD_FRONT} {y:.4f} {z:.4f}" mass="0.0001"/>'
            )
    return "\n          ".join(out)


def build_mjcf(cfg: Config, face_texture: str | None = None) -> str:
    """Return the MJCF XML. ``face_texture`` is an image path for the person's face."""
    s, sim = cfg.servos, cfg.sim
    pan_rng = _range(cfg, s.pan, SERVO_JOINTS["pan"][0])
    tilt_rng = _range(cfg, s.tilt, SERVO_JOINTS["tilt"][0])
    jaw_rng = _range(cfg, s.mouth, SERVO_JOINTS["mouth"][0])
    w, h = max(sim.view_width, cfg.camera.width), max(sim.view_height, cfg.camera.height)

    face_asset = ""
    face_geom = (  # simple features, so the person visibly faces the robot
        '<geom type="sphere" size="0.012" pos="0.072 0.032 0.025" material="pupil"/>'
        '<geom type="sphere" size="0.012" pos="0.072 -0.032 0.025" material="pupil"/>'
        '<geom type="ellipsoid" size="0.02 0.012 0.022" pos="0.082 0 -0.005" material="skin"/>'
        '<geom type="box" size="0.006 0.026 0.005" pos="0.07 0 -0.05" material="lips"/>'
    )
    if face_texture:
        face_asset = (
            f'<texture name="face" type="2d" file="{face_texture}"/>'
            '<material name="face" texture="face" texrepeat="1 1" texuniform="false"/>'
        )
        face_geom = (
            '<geom name="person_face" type="box" size="0.004 0.085 0.11" pos="0.086 0 0" '
            'material="face" contype="0" conaffinity="0"/>'
        )

    actuators = []
    for servo, joints in SERVO_JOINTS.items():
        for jm in joints:
            lo, hi = _range(cfg, getattr(s, servo), jm)
            actuators.append(
                f'<position name="{jm.joint}" joint="{jm.joint}" kp="3" dampratio="1" '
                f'ctrlrange="{lo:.4f} {hi:.4f}" forcerange="-0.25 0.25"/>'
            )

    return f"""<mujoco model="berrick">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="0.002"/>
  <visual>
    <global offwidth="{w}" offheight="{h}"/>
    <quality shadowsize="2048"/>
    <headlight ambient=".35 .35 .35" diffuse=".5 .5 .5" specular=".1 .1 .1"/>
  </visual>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1=".62 .72 .84" rgb2=".18 .2 .24"
             width="256" height="256"/>
    <texture name="grid" type="2d" builtin="checker" rgb1=".82 .82 .82" rgb2=".72 .72 .72"
             width="512" height="512"/>
    <material name="floor" texture="grid" texrepeat="10 10" reflectance=".05"/>
    <material name="wood" rgba=".55 .38 .24 1"/>
    <material name="shell" rgba=".94 .94 .91 1" specular=".3"/>
    <material name="dark" rgba=".16 .16 .17 1"/>
    <material name="eyewhite" rgba=".98 .98 .98 1" specular=".6"/>
    <material name="pupil" rgba=".05 .05 .08 1" specular=".8"/>
    <material name="skin" rgba=".86 .68 .56 1"/>
    <material name="lips" rgba=".62 .3 .3 1"/>
    <material name="shirt" rgba=".22 .4 .65 1"/>
    {face_asset}
    {"".join(f'<material name="led{i}" rgba=".2 .2 .2 1"/>' for i in range(2 * LEDS_PER_EYE))}
  </asset>
  <default>
    <joint damping="0.02" armature="0.0005"/>
    <geom contype="0" conaffinity="0"/>
  </default>
  <worldbody>
    <light pos="0.6 -1.2 2.4" dir="-0.2 0.5 -1" diffuse=".6 .6 .6" castshadow="true"/>
    <geom name="floor" type="plane" size="4 4 .1" material="floor"/>
    <geom name="table" type="box" pos="0.25 0 {TABLE_Z - 0.02}" size="0.45 0.55 0.02"
          material="wood"/>
    <geom name="table_leg" type="box" pos="0.25 0 {(TABLE_Z - 0.04) / 2}"
          size="0.04 0.04 {(TABLE_Z - 0.04) / 2}" material="wood"/>
    <body name="robot" pos="0 0 {TABLE_Z}">
      <geom name="base" type="box" pos="0 0 0.04" size="0.075 0.075 0.04" material="shell"
            mass="0.4"/>
      <body name="neck" pos="0 0 0.08">
        {_joint("pan", "0 0 1", pan_rng)}
        <geom type="cylinder" pos="0 0 0.035" size="0.022 0.035" material="dark" mass="0.03"/>
        <body name="head" pos="0 0 0.09">
          {_joint("tilt", "0 1 0", tilt_rng)}
          <geom name="skull" type="box" pos="0 0 0.045" size="0.08 0.095 0.075"
                material="shell" mass="0.12"/>
          <geom type="box" pos="0 0 0.125" size="0.06 0.075 0.008" material="shell"
                mass="0.01"/>
          <camera name="robot_cam" pos="{HEAD_FRONT + 0.001} 0 0.098" xyaxes="0 -1 0 0 0 1"
                  fovy="{sim.camera_fovy_deg}"/>
          <geom type="cylinder" pos="{HEAD_FRONT} 0 0.098" zaxis="1 0 0" size="0.009 0.002"
                material="dark"/>
          {_eye(cfg, "l", EYE_Y)}
          {_eye(cfg, "r", -EYE_Y)}
          {_leds()}
          <body name="jaw" pos="0.035 0 -0.012">
            {_joint("jaw", "0 1 0", jaw_rng)}
            <geom type="box" pos="0.03 0 -0.008" size="0.03 0.055 0.008" material="dark"
                  mass="0.01"/>
          </body>
        </body>
      </body>
    </body>
    <body name="person" mocap="true" pos="{sim.person_distance} 0 {sim.person_height}">
      <geom name="person_head" type="ellipsoid" size="0.085 0.075 0.11" material="skin"/>
      {face_geom}
      <geom type="cylinder" fromto="0 0 -0.09 0 0 -0.16" size="0.04" material="skin"/>
      <geom type="capsule" fromto="0 0.09 -0.3 0 -0.09 -0.3" size="0.1" material="shirt"/>
      <geom type="box" pos="0 0 -0.48" size="0.09 0.17 0.18" material="shirt"/>
    </body>
  </worldbody>
  <actuator>
    {chr(10).join("    " + a for a in actuators).strip()}
  </actuator>
</mujoco>"""
