"""Configuration model for Berrick.

Every value has a sensible default (taken from the original 2019 build), so a
TOML file only needs to contain what differs on *your* robot.
"""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ServoConfig:
    """One hobby servo driven by a 50 Hz pulse (values in microseconds)."""

    pin: int
    min_us: float
    max_us: float
    home_us: float
    enabled: bool = True
    max_speed_us_s: float = 800.0

    def clamp(self, us: float) -> float:
        lo, hi = sorted((self.min_us, self.max_us))
        return max(lo, min(hi, us))


@dataclass
class PIDConfig:
    kp: float = 500.0
    ki: float = 0.0
    kd: float = 20.0
    output_limit: float = 600.0
    integral_limit: float = 1.0


@dataclass
class AxisConfig:
    """Closed-loop axis (pan or tilt) driven by the normalised face offset."""

    enabled: bool = True
    invert: bool = True
    deadband: float = 0.08
    pid: PIDConfig = field(default_factory=PIDConfig)


@dataclass
class CameraConfig:
    backend: str = "picamera2"  # "picamera2" | "opencv"
    device: int = 0  # only for the opencv backend
    width: int = 320
    height: int = 240
    fps: int = 30
    hflip: bool = False
    vflip: bool = False


@dataclass
class DetectorConfig:
    backend: str = "yunet"  # "yunet" | "haar"
    model_path: str = "models/face_detection_yunet_2023mar.onnx"
    score_threshold: float = 0.7
    nms_threshold: float = 0.3
    haar_cascade: str = ""  # empty = bundled OpenCV cascade
    haar_scale_factor: float = 1.05
    haar_min_neighbors: int = 9
    min_face_size: int = 30
    fallback_to_haar: bool = True


@dataclass
class ServosConfig:
    backend: str = "pigpio"  # "pigpio" | "gpiozero" | "mock"
    update_hz: float = 50.0
    pan: ServoConfig = field(
        default_factory=lambda: ServoConfig(pin=27, min_us=1200, max_us=2400, home_us=1850)
    )
    tilt: ServoConfig = field(
        default_factory=lambda: ServoConfig(
            pin=22, min_us=800, max_us=2000, home_us=1350, enabled=False
        )
    )
    mouth: ServoConfig = field(
        default_factory=lambda: ServoConfig(
            pin=17, min_us=1100, max_us=2100, home_us=2100, max_speed_us_s=4000
        )
    )
    eye_x: ServoConfig = field(
        default_factory=lambda: ServoConfig(
            pin=19, min_us=1000, max_us=1700, home_us=1200, enabled=False, max_speed_us_s=3000
        )
    )
    eye_y: ServoConfig = field(
        default_factory=lambda: ServoConfig(
            pin=26, min_us=600, max_us=1800, home_us=1200, enabled=False, max_speed_us_s=3000
        )
    )


@dataclass
class LedConfig:
    backend: str = "neopixel_spi"  # "neopixel_spi" | "rpi_ws281x" | "mock" | "none"
    count: int = 14
    gpio_pin: int = 10  # rpi_ws281x only; neopixel_spi always uses SPI MOSI (GPIO10)
    rgbw: bool = True
    brightness: float = 0.7
    engaged_color: list[int] = field(default_factory=lambda: [255, 0, 0, 0])
    idle_color: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    wipe_ms: float = 2.0


@dataclass
class BehaviorConfig:
    acquire_frames: int = 3
    lost_timeout_s: float = 1.0
    return_home_after_s: float = 5.0
    greet_with_mouth: bool = False
    greet_open_s: float = 0.4
    eyes_invert_x: bool = True
    eyes_invert_y: bool = True


@dataclass
class SimConfig:
    """MuJoCo simulation (`berrick sim`). Angles follow the default `invert` wiring."""

    person_motion: str = "sweep"  # "sweep" | "static" | "manual"
    person_distance: float = 0.8  # m in front of the robot
    person_height: float = 1.12  # m, face centre (robot camera is at ~1.0 m)
    person_offset: float = 0.25  # m, lateral offset for "static"
    sweep_amplitude: float = 0.35  # m
    sweep_period_s: float = 12.0
    leave_every_s: float = 30.0  # 0 = never walk out of view
    leave_for_s: float = 5.0
    face_texture: str = ""  # photo of a face -> lets the real detector run on renders
    detector: str = "ground_truth"  # "ground_truth" | "real" (uses [detector])
    noise_px: float = 2.0  # ground-truth detector jitter
    miss_rate: float = 0.05  # ground-truth detector false-negative probability
    camera_fovy_deg: float = 48.8  # Raspberry Pi Camera v2
    deg_per_us: float = 0.09  # 180° over 2000 µs, standard hobby servo
    mouth_deg_per_us: float = 0.035
    view_width: int = 640
    view_height: int = 480
    seed: int = 0


@dataclass
class Config:
    camera: CameraConfig = field(default_factory=CameraConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    servos: ServosConfig = field(default_factory=ServosConfig)
    pan: AxisConfig = field(default_factory=AxisConfig)
    tilt: AxisConfig = field(default_factory=lambda: AxisConfig(enabled=False))
    leds: LedConfig = field(default_factory=LedConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    sim: SimConfig = field(default_factory=SimConfig)
    preview: bool = True
    log_dir: str = ""


class ConfigError(ValueError):
    pass


def _merge(obj: Any, data: dict[str, Any], path: str = "") -> None:
    known = {f.name: f for f in dataclasses.fields(obj)}
    for key, value in data.items():
        where = f"{path}{key}"
        if key not in known:
            raise ConfigError(f"unknown config key '{where}'")
        current = getattr(obj, key)
        if dataclasses.is_dataclass(current):
            if not isinstance(value, dict):
                raise ConfigError(f"'{where}' must be a table")
            _merge(current, value, where + ".")
            continue
        if isinstance(current, bool) != isinstance(value, bool):
            raise ConfigError(f"'{where}' must be a boolean")
        if isinstance(current, float) and isinstance(value, int):
            value = float(value)
        if not isinstance(value, type(current)):
            raise ConfigError(
                f"'{where}' must be {type(current).__name__}, got {type(value).__name__}"
            )
        setattr(obj, key, value)


def config_from_dict(data: dict[str, Any]) -> Config:
    cfg = Config()
    _merge(cfg, data)
    return cfg


def load_config(path: str | Path | None) -> Config:
    if path is None:
        return Config()
    with open(path, "rb") as fh:
        return config_from_dict(tomllib.load(fh))
