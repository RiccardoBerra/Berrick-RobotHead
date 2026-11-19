"""Keyboard HRI experiment (port of the 2019 `test.testKeyboard`).

While the robot runs, the participant presses a key whenever they feel the
robot is looking at them. Each key press is logged together with the robot's
actual engagement state, so perceived vs. real gaze can be compared.
"""

from __future__ import annotations

import csv
import select
import sys
import termios
import threading
import time
import tty
from collections.abc import Callable
from pathlib import Path


class KeyboardExperiment(threading.Thread):
    def __init__(
        self,
        engaged: Callable[[], bool],
        output: str | Path,
        duration_s: float = 180.0,
        countdown_s: int = 5,
        cooldown_s: float = 0.5,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(name="keyboard-experiment", daemon=True)
        self._engaged = engaged
        self._output = Path(output)
        self._duration = duration_s
        self._countdown = countdown_s
        self._cooldown = cooldown_s
        self._on_finish = on_finish
        self.stop_event = threading.Event()

    def run(self) -> None:
        if not sys.stdin.isatty():
            print("[experiment] stdin is not a terminal; keyboard experiment disabled")
            return
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        self._output.parent.mkdir(parents=True, exist_ok=True)
        try:
            tty.setcbreak(fd)
            for n in range(self._countdown, 0, -1):
                print(f"[experiment] starting in {n}...", flush=True)
                if self.stop_event.wait(1):
                    return
            termios.tcflush(fd, termios.TCIFLUSH)
            print("[experiment] GO - press a key when you feel watched", flush=True)
            with open(self._output, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(("time_s", "robot_engaged", "key"))
                t0 = time.monotonic()
                while not self.stop_event.is_set():
                    remaining = self._duration - (time.monotonic() - t0)
                    if remaining <= 0:
                        break
                    ready, _, _ = select.select([fd], [], [], min(0.2, remaining))
                    if not ready:
                        continue
                    key = sys.stdin.read(1)
                    robot = int(self._engaged())
                    w.writerow((f"{time.monotonic() - t0:.3f}", robot, key))
                    fh.flush()
                    print(f"Robot: {robot}  Human: {key!r}", flush=True)
                    time.sleep(self._cooldown)
                    termios.tcflush(fd, termios.TCIFLUSH)
            print(f"[experiment] done, saved {self._output}", flush=True)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            if self._on_finish:
                self._on_finish()
