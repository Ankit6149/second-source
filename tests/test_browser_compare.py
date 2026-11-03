"""Shared browser evidence/compare: temporal, layout, functional.

Negative controls included. No Canvas/WebGL/3D comparison exists or is
claimed by this module.
"""
import math

from second_source.browser_compare import compare, overshoot, trajectory_rmse


def spring(k=180.0, c=14.0, x0=150.0, seconds=1.2, dt_ms=8.0):
    samples, x, v, t = [], x0, 0.0, 0.0
    while t <= seconds * 1000:
        samples.append((t, x))
        a = -k * x - c * v
        v += a * (dt_ms / 1000.0)
        x += v * (dt_ms / 1000.0)
        t += dt_ms
    return samples


def obs(traj, state="At rest", box=(10, 10, 100, 50)):
    return {"functional": {"state": state}, "layout": {"#card": list(box)},
            "trajectory": traj, "parallax": {0: -120, 300: -225}}


def test_identical_trajectories_pass():
    out = compare(obs(spring()), obs(spring()))
    assert out["pass"] is True
    assert out["trajectory"]["rmse_px"] < 1e-9


def test_wrong_spring_detected():
    out = compare(obs(spring()), obs(spring(k=120.0, c=42.0)))
    assert out["trajectory"]["rmse_px"] > 8
    assert out["pass"] is False


def test_no_overshoot_detected():
    out = compare(obs(spring()), obs(spring(k=120.0, c=42.0)))
    assert overshoot(spring(k=120.0, c=42.0))["present"] is False
    assert out["overshoot"]["match"] is False


def test_layout_and_state_mismatch_detected():
    out = compare(obs(spring()), obs(spring(), state="Settling", box=(30, 10, 100, 50)))
    assert out["functional"]["match"] is False
    assert out["layout"]["pass"] is False
    assert out["pass"] is False


def test_rmse_uses_common_grid():
    ref = [(0, 100.0), (100, 0.0)]
    cand = [(0, 100.0), (50, 50.0), (100, 0.0)]
    assert trajectory_rmse(ref, cand) == 0.0
    assert trajectory_rmse([], cand) is None
