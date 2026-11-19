"""Command line interface: `berrick run | calibrate | download-model`."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import Config, ServosConfig, load_config

log = logging.getLogger("berrick")


def _raise_interrupt(signum, frame):  # SIGTERM (systemd stop) -> clean shutdown
    raise KeyboardInterrupt


def cmd_run(args: argparse.Namespace, cfg: Config) -> int:
    from .camera import open_camera
    from .detection import create_detector
    from .experiment import KeyboardExperiment
    from .leds import LedRing
    from .servos import ServoBank
    from .tracker import EventLog, Tracker, draw_overlay

    if args.no_preview:
        cfg.preview = False
    if args.log_dir:
        cfg.log_dir = args.log_dir

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = Path(cfg.log_dir) if cfg.log_dir else None
    if args.experiment and log_dir is None:
        log_dir = Path("logs")

    stop = threading.Event()
    camera = open_camera(cfg.camera)
    events = EventLog(log_dir / f"events-{stamp}.csv") if log_dir else None
    servos = ServoBank(cfg.servos)
    leds = LedRing(cfg.leds)
    experiment = None
    try:
        detector = create_detector(cfg.detector)
        log.info(
            "detector: %s, servos: %s, leds: %s",
            detector.name,
            cfg.servos.backend,
            cfg.leds.backend,
        )
        tracker = Tracker(cfg, detector, servos, leds, events)
        servos.start()
        leds.idle()

        if args.experiment:
            experiment = KeyboardExperiment(
                lambda: tracker.engaged,
                log_dir / f"experiment-{stamp}.csv",
                duration_s=args.duration,
                on_finish=stop.set if args.stop_after_experiment else None,
            )
            experiment.start()

        if cfg.preview:
            import cv2

        fps, last = 0.0, time.monotonic()
        while not stop.is_set():
            frame = camera.read()
            if frame is None:
                log.warning("camera returned no frame")
                time.sleep(0.05)
                continue
            status = tracker.process(frame)
            now = time.monotonic()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-6)
            last = now
            if cfg.preview:
                cv2.imshow("Berrick", draw_overlay(frame, status, fps))
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    except KeyboardInterrupt:
        print()
        log.info("stopping")
    finally:
        stop.set()
        if experiment:
            experiment.stop_event.set()
            experiment.join(timeout=2)
        servos.home()
        time.sleep(0.5)  # let the servos glide home before releasing them
        servos.close()
        leds.close()
        camera.close()
        if events:
            events.close()
        if cfg.preview:
            try:
                import cv2

                cv2.destroyAllWindows()
            except Exception:
                pass
    return 0


CALIBRATE_HELP = """\
Calibrating servo '{name}' on GPIO {pin}  (start {pos:.0f} µs)
  a / d : -10 / +10 µs      A / D : -50 / +50 µs
  h     : go to configured home
  q     : quit (servo is released)
Write the values you find into your config file (min_us, max_us, home_us).
"""


def cmd_calibrate(args: argparse.Namespace, cfg: Config) -> int:
    import termios
    import tty

    from .servos import ServoBank

    scfg = getattr(cfg.servos, args.servo)
    wide = dataclasses.replace(scfg, enabled=True, min_us=500, max_us=2500, max_speed_us_s=1000)
    only = ServosConfig(backend=cfg.servos.backend, update_hz=cfg.servos.update_hz)
    for name in ServoBank.NAMES:
        setattr(only, name, dataclasses.replace(getattr(only, name), enabled=False))
    setattr(only, args.servo, wide)

    steps = {"a": -10, "d": 10, "A": -50, "D": 50}
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    with ServoBank(only) as bank:
        servo = bank.get(args.servo)
        print(CALIBRATE_HELP.format(name=args.servo, pin=wide.pin, pos=servo.target))
        try:
            tty.setcbreak(fd)
            while (key := sys.stdin.read(1)) != "q":
                with bank.lock:
                    if key in steps:
                        servo.nudge(steps[key])
                    elif key == "h":
                        servo.set_target(scfg.home_us)
                    else:
                        continue
                print(f"\r{args.servo}: {servo.target:6.0f} µs   ", end="", flush=True)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            print()
    return 0


def cmd_download_model(args: argparse.Namespace, cfg: Config) -> int:
    from .detection import download_model

    dest = Path(args.dest or cfg.detector.model_path)
    if dest.exists() and not args.force:
        print(f"{dest} already exists (use --force to re-download)")
        return 0
    print(f"downloading YuNet face detector to {dest} ...")
    download_model(dest)
    print(f"done ({dest.stat().st_size / 1024:.0f} KiB)")
    return 0


def cmd_sim(args: argparse.Namespace, cfg: Config) -> int:
    try:
        from .sim import run_sim
    except ImportError as exc:
        print(f"simulation needs MuJoCo: pip install -e '.[sim]' ({exc})", file=sys.stderr)
        return 1

    if args.twin:
        cfg.camera.backend = "opencv"
    if args.face:
        cfg.sim.face_texture = args.face
        cfg.sim.detector = "real"
    if args.real_detector:
        cfg.sim.detector = "real"
    if args.person:
        cfg.sim.person_motion = args.person
    for name in args.enable or []:
        getattr(cfg.servos, name).enabled = True
        if name == "tilt":
            cfg.tilt.enabled = True

    hist = run_sim(
        cfg,
        duration=args.duration,
        preview=not args.headless,
        realtime=not args.fast,
        twin=args.twin,
        record=args.record,
        log_dir=args.log_dir or (cfg.log_dir or None),
    )
    if hist.t:
        import math

        engaged = sum(hist.engaged) / len(hist.t)
        errs = [abs(e) for e, g in zip(hist.error_x, hist.engaged, strict=True)
                if g and not math.isnan(e)]  # fmt: skip
        mean = sum(errs) / len(errs) if errs else float("nan")
        print(f"simulated {hist.t[-1]:.1f}s: engaged {engaged:.0%} of the time, "
              f"mean |pan error| while engaged {mean:.3f}")  # fmt: skip
    if args.record:
        print(f"video saved to {args.record}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="berrick", description="Berrick robotic head controller")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-c", "--config", help="path to a TOML config file")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="track faces")
    run.add_argument("--no-preview", action="store_true", help="do not open a video window")
    run.add_argument("--log-dir", help="write CSV event logs to this directory")
    run.add_argument(
        "--experiment", action="store_true", help="run the keyboard HRI experiment in parallel"
    )
    run.add_argument("--duration", type=float, default=180.0, help="experiment length (s)")
    run.add_argument(
        "--stop-after-experiment", action="store_true", help="exit when the experiment ends"
    )
    run.set_defaults(func=cmd_run)

    cal = sub.add_parser("calibrate", help="move one servo by hand to find its limits")
    cal.add_argument("servo", choices=["pan", "tilt", "mouth", "eye_x", "eye_y"])
    cal.set_defaults(func=cmd_calibrate)

    sim = sub.add_parser("sim", help="simulate the robot in MuJoCo (no hardware needed)")
    sim.add_argument("--person", choices=["sweep", "static", "manual"], help="person motion")
    sim.add_argument("--enable", nargs="+", choices=["tilt", "eye_x", "eye_y"],
                     help="enable extra servos")  # fmt: skip
    sim.add_argument("--face", help="face photo to texture the virtual person (uses YuNet)")
    sim.add_argument("--real-detector", action="store_true",
                     help="run [detector] on rendered frames instead of ground truth")  # fmt: skip
    sim.add_argument("--twin", action="store_true",
                     help="digital twin: your webcam drives the virtual robot")  # fmt: skip
    sim.add_argument("--duration", type=float, help="stop after N simulated seconds")
    sim.add_argument("--headless", action="store_true", help="no window")
    sim.add_argument("--fast", action="store_true", help="run faster than real time")
    sim.add_argument("--record", help="save the view to an .mp4 file")
    sim.add_argument("--log-dir", help="write CSV event logs to this directory")
    sim.set_defaults(func=cmd_sim)

    dl = sub.add_parser("download-model", help="download the YuNet face-detection model")
    dl.add_argument("--dest", help="output path (default: detector.model_path)")
    dl.add_argument("--force", action="store_true")
    dl.set_defaults(func=cmd_download_model)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    signal.signal(signal.SIGTERM, _raise_interrupt)
    cfg = load_config(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
