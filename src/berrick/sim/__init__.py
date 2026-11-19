"""MuJoCo simulation of Berrick: run the real tracker on a virtual robot.

Requires the optional ``sim`` extra (``pip install -e ".[sim]"``).
"""

from .runner import SimHistory, run_sim
from .world import GroundTruthDetector, Simulation

__all__ = ["GroundTruthDetector", "SimHistory", "Simulation", "run_sim"]
