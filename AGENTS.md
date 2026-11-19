# AGENTS.md

Guidance for AI coding agents (and humans) working on this repository.

## Project

Berrick is a Raspberry Pi robotic head that tracks faces and signals engagement with
an LED ring (IEEE SMC 2019, doi:10.1109/SMC.2019.8913932). The Python package lives
in `src/berrick/`; `legacy/` holds the original 2019 code and experiment data.

## Rules

- **Never modify `legacy/`.** It is kept verbatim for reproducibility of the paper.
- Hardware code must stay behind the backend interfaces (`Camera`, `FaceDetector`,
  `Backend`/`PulseOutput`, `Pixels`). Import hardware libraries (`picamera2`,
  `pigpio`, `gpiozero`, `board`, `neopixel_spi`, `rpi_ws281x`) **lazily inside the
  backend class**, so the package imports and tests run on any machine.
- Every hardware backend needs a mock counterpart; tests must never require a Pi,
  a camera or network access.
- New settings go in `config.py` as dataclass fields **with defaults**, are added to
  `config/berrick.example.toml` with a comment, and are validated by `_merge`
  (unknown keys are errors by design).
- Servo values are pulse widths in µs. Always set targets through `Servo.set_target`/
  `nudge` (they clamp to the configured limits) and hold `ServoBank.lock` while doing
  it from outside the servo thread.
- No `time.sleep` in the control path except where already present (LED wipe,
  shutdown). The PID receives `dt`; it must not sleep.
- OpenCV must work with both 4.x and 5.x (Haar cascades only exist in 4.x;
  YuNet is the default detector).
- Supported Python: 3.11+ (Raspberry Pi OS Bookworm ships 3.11).

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
berrick download-model                 # needed for YuNet tests (otherwise skipped)
pytest -q                              # tests
ruff check . && ruff format --check .  # lint + format (CI enforces both)
berrick -c config/desktop.toml run     # manual test with webcam + mock hardware
```

## Layout

| File | Role |
|---|---|
| `cli.py` | entry point; wires camera → detector → tracker → servos/LEDs |
| `config.py` | dataclass config, TOML loading/validation |
| `tracker.py` | engagement state machine, PID gaze control, `EventLog` CSV |
| `servos.py` | servo backends, slew-limited `ServoBank` (50 Hz thread) |
| `detection.py` | YuNet/Haar detectors, model download |
| `camera.py`, `leds.py`, `pid.py`, `experiment.py` | as named |

## Conventions

- Sign convention: image error `e ∈ [-1, 1]`, positive = face right/below centre;
  `invert` flags map it to servo direction.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).
- Keep the README usage guide in sync with CLI flags and config keys.
