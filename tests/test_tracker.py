from berrick.detection import Face
from berrick.tracker import State, _map_offset


def face_at(cx, cy, size=60):
    return Face(int(cx - size / 2), int(cy - size / 2), size, size, 0.9)


def run(tracker, frame, n, t0=0.0, dt=0.05):
    t = t0
    status = None
    for _ in range(n):
        status = tracker.process(frame, now=t)
        t += dt
    return status, t


def test_face_center_is_box_center():
    assert Face(10, 20, 100, 50, 1).center == (60, 45)


def test_engages_after_acquire_frames(rig, frame):
    tracker, det, _ = rig
    det.faces = [face_at(160, 120)]
    status, _ = run(tracker, frame, tracker.cfg.behavior.acquire_frames - 1)
    assert status.state is State.IDLE
    status, _ = run(tracker, frame, 1, t0=1)
    assert status.state is State.ENGAGED
    assert tracker.engaged


def test_disengages_after_timeout(rig, frame):
    tracker, det, _ = rig
    det.faces = [face_at(160, 120)]
    _, t = run(tracker, frame, 5)
    det.faces = []
    status, _ = run(tracker, frame, 1, t0=t + 0.5)
    assert status.state is State.ENGAGED
    status, _ = run(tracker, frame, 1, t0=t + 2.0)
    assert status.state is State.IDLE
    assert not tracker.engaged


def test_pan_moves_toward_face(rig, frame):
    tracker, det, bank = rig
    pan = bank.get("pan")
    home = pan.target
    det.faces = [face_at(300, 120)]  # far right in the image
    status, _ = run(tracker, frame, 10)
    assert status.error[0] > 0.8
    # invert=True by default (2019 wiring): face on the right -> pulse decreases
    assert pan.target < home


def test_deadband_holds_still(rig, frame):
    tracker, det, bank = rig
    pan = bank.get("pan")
    home = pan.target
    det.faces = [face_at(165, 120)]  # ~3% off centre
    run(tracker, frame, 10)
    assert pan.target == home


def test_picks_largest_face(rig, frame):
    tracker, det, _ = rig
    big = face_at(100, 120, size=100)
    det.faces = [face_at(250, 120, size=40), big]
    status, _ = run(tracker, frame, 1)
    assert status.face == big


def test_returns_home_when_idle(rig, frame):
    tracker, det, bank = rig
    pan = bank.get("pan")
    det.faces = [face_at(300, 120)]
    _, t = run(tracker, frame, 10)
    assert pan.target != pan.cfg.home_us
    det.faces = []
    run(tracker, frame, 1, t0=t + 1.5)
    run(tracker, frame, 1, t0=t + 10)
    assert pan.target == pan.cfg.home_us


def test_map_offset():
    from berrick.config import ServoConfig

    s = ServoConfig(pin=1, min_us=1000, max_us=2000, home_us=1200)
    assert _map_offset(s, 0) == 1200
    assert _map_offset(s, 1) == 2000
    assert _map_offset(s, -1) == 1000
    assert _map_offset(s, 5) == 2000
