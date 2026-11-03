"""Shared evidence/compare for browser observations (target-agnostic).

Compares a reference and an independent candidate on functional state,
layout geometry, and temporal trajectory. No product-specific selectors
or constants live here; callers pass observed values. Canvas/WebGL/3D
comparison is deliberately absent: no claim is made for it.
"""
from __future__ import annotations

import math


def _interp(samples, t):
    if not samples:
        return None
    if t <= samples[0][0]:
        return samples[0][1]
    for (t0, x0), (t1, x1) in zip(samples, samples[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return x1
            return x0 + (x1 - x0) * (t - t0) / (t1 - t0)
    return samples[-1][1]


def trajectory_rmse(ref, cand, grid_ms=8.0):
    """RMSE of candidate vs reference x(t) on a common time grid.

    ref/cand: list of (tMs, x) samples aligned so t=0 is release.
    """
    if not ref or not cand:
        return None
    t_end = min(ref[-1][0], cand[-1][0])
    n = int(t_end // grid_ms)
    if n < 2:
        return None
    sq = 0.0
    for i in range(n + 1):
        t = i * grid_ms
        d = _interp(cand, t) - _interp(ref, t)
        sq += d * d
    return math.sqrt(sq / (n + 1))


def overshoot(samples):
    if not samples:
        return {"min_x": None, "present": False}
    m = min(x for _, x in samples)
    return {"min_x": m, "present": m < -1.0}


def settling_time(samples, band_px=2.0):
    """First t after which |x| stays within band; None if never."""
    if not samples:
        return None
    last_out = None
    for t, x in samples:
        if abs(x) > band_px:
            last_out = t
    if last_out is None:
        return samples[0][0]
    after = [t for t, _ in samples if t > last_out]
    return after[0] if after else None


def compare(ref_obs, cand_obs, *, rmse_threshold_px=8.0, layout_tol_px=4.0):
    """ref_obs/cand_obs: {functional:{}, layout:{sel:[x,y,w,h]},
    trajectory:[(t,x)], parallax:{scrollY: rectY}}"""
    out = {}
    rf, cf = ref_obs.get("functional", {}), cand_obs.get("functional", {})
    out["functional"] = {"match": rf == cf, "ref": rf, "cand": cf}
    rl, cl = ref_obs.get("layout", {}), cand_obs.get("layout", {})
    diffs = []
    for sel in set(rl) & set(cl):
        diffs += [abs(a - b) for a, b in zip(rl[sel], cl[sel])]
    out["layout"] = {"max_diff_px": max(diffs) if diffs else None,
                      "pass": bool(diffs) and max(diffs) <= layout_tol_px}
    rmse = trajectory_rmse(ref_obs.get("trajectory", []),
                           cand_obs.get("trajectory", []))
    ro, co = overshoot(ref_obs.get("trajectory", [])), overshoot(cand_obs.get("trajectory", []))
    rs, cs = settling_time(ref_obs.get("trajectory", [])), settling_time(cand_obs.get("trajectory", []))
    out["trajectory"] = {"rmse_px": rmse, "pass": rmse is not None and rmse <= rmse_threshold_px}
    out["overshoot"] = {"ref": ro, "cand": co, "match": ro["present"] == co["present"]}
    out["settling"] = {"ref_s": None if rs is None else rs / 1000.0,
                       "cand_s": None if cs is None else cs / 1000.0}
    rp, cp = ref_obs.get("parallax", {}), cand_obs.get("parallax", {})
    pdiff = [abs(rp[k] - cp[k]) for k in set(rp) & set(cp)]
    out["parallax"] = {"max_diff_px": max(pdiff) if pdiff else None}
    out["pass"] = bool(out["functional"]["match"] and out["layout"]["pass"]
                       and out["trajectory"]["pass"] and out["overshoot"]["match"])
    return out
