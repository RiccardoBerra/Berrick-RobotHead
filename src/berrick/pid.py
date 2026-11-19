"""Discrete PID controller with output clamping and anti-windup."""

from __future__ import annotations


def _clamp(value: float, limit: float | None) -> float:
    if limit is None:
        return value
    return max(-limit, min(limit, value))


class PID:
    def __init__(
        self,
        kp: float = 1.0,
        ki: float = 0.0,
        kd: float = 0.0,
        output_limit: float | None = None,
        integral_limit: float | None = None,
    ) -> None:
        self.kp, self.ki, self.kd = kp, ki, kd
        self.output_limit = output_limit
        self.integral_limit = integral_limit
        self.reset()

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error: float | None = None
        self._last_output = 0.0

    def update(self, error: float, dt: float) -> float:
        """Return the control output for ``error`` after ``dt`` seconds.

        Unlike the 2019 version this never sleeps: timing belongs to the caller.
        """
        if dt <= 0:
            return self._last_output

        integral = _clamp(self._integral + error * dt, self.integral_limit)
        derivative = 0.0 if self._prev_error is None else (error - self._prev_error) / dt
        raw = self.kp * error + self.ki * integral + self.kd * derivative
        out = _clamp(raw, self.output_limit)

        # Anti-windup: only accumulate when not saturated in the error direction.
        if out == raw or (raw > 0) != (error > 0):
            self._integral = integral

        self._prev_error = error
        self._last_output = out
        return out
