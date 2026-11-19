# Legacy code (2019)

`berrick_2019/` is the original code used for the experiments of the IEEE SMC 2019
paper, kept unchanged for reproducibility. It targets Python 3.5, Raspberry Pi OS
Stretch, the legacy `picamera` stack, `pigpio` and `rpi_ws281x`, and **does not run on
current Raspberry Pi OS**. Use the `berrick` package in `src/` instead.

`berrick_2019/report.txt` is the raw detection log from the experiments
(Haar confidence per detected frame and duration of each detection episode).

Known issues fixed in v2:

| 2019 code | Problem | v2 |
|---|---|---|
| `faceX = (x + w) / 2` | not the box centre (should be `x + w/2`); compensated by the magic `- 163` offset in `go()` | `Face.center` |
| `weightF = w` in `obj_center` | typo, and a local variable anyway: shared `widthF` stayed 0, so the dead-zone never worked | configurable `deadband` |
| `report.txt` opened every frame | file handle leaked whenever a face was found | `EventLog` CSV |
| `while eyeX.value > 1 ...` | outer loop spins at 100% CPU when no face; negative PID output never moves the head | state machine in `Tracker` |
| `PID.update` sleeps 0.2 s | caps control at 5 Hz, unrelated to frame rate | `PID` takes `dt` |
| blocking `setServoAngle*` loops | servo motion stalls the control loop | slew-limited `ServoBank` thread |
| globals shared by `fork` | breaks with Python 3.14's default `forkserver` start method | single process + threads |
| `getch` in a child process | multiprocessing redirects child stdin | `KeyboardExperiment` thread |
