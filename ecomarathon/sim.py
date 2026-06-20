"""Forward longitudinal simulator (distance domain).

Integrates the car around the closed loop under a given control policy and returns
the realised speed / time / fuel trajectory. Used three ways:

* validating the physics (energy conservation, glide distance) in the tests,
* rolling out the DP policy to the steady periodic cycle and reading off the
  authoritative lap-time and fuel numbers,
* evaluating simple rule-based strategies for comparison.

The state is integrated in the distance domain because the track, gradients and
corner caps are all distance-indexed. For speed ``v`` along arc length ``s``::

    dv/ds = a(v) / v ,   dt/ds = 1 / v ,   d(fuel)/ds = fuel_rate / v

``v`` is advanced with RK4 sub-steps; time follows from the same integration and
fuel is ``fuel_rate * dt`` (constant-power burn => constant fuel rate).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

import numpy as np

from .config import Config
from .track import Track
from . import vehicle as veh

# A policy maps (segment_index, entry_speed) -> control code.
Policy = Callable[[int, float], int]

_V_FLOOR = 0.3  # m/s, keeps 1/v finite if a policy nearly stalls the car


@dataclass
class Trajectory:
    s: np.ndarray            # cumulative distance over all simulated laps (m)
    s_lap: np.ndarray        # distance within the lap at each point (m)
    v: np.ndarray            # speed at each point (m/s)
    t: np.ndarray            # cumulative time (s)
    fuel_g: np.ndarray       # cumulative fuel mass (g)
    u: np.ndarray            # control taken on the segment leaving each point
    lap_time: List[float]    # per-lap time (s)
    lap_fuel_g: List[float]  # per-lap fuel (g)
    cap_ratio: float         # max(v / corner_cap) over the run (<=1 means all caps met)
    stalled: bool            # True if the car hit the speed floor anywhere


def step_segment(v0: float, i: int, u: int, track: Track, cfg: Config):
    st, ct, ds = track.sin_theta[i], track.cos_theta[i], track.ds[i]
    sub = cfg.solver.substeps
    h = ds / sub
    fr = veh.fuel_rate(u, cfg)
    kappa = track.kappa[i]  # ADD THIS

    def dvds(vv: float) -> float:
        vv = vv if vv > _V_FLOOR else _V_FLOOR
        a_lat = kappa * vv ** 2                                          # ADD THIS
        f_lat = cfg.vehicle.Crr_lateral * cfg.vehicle.mass * a_lat      # ADD THIS
        base_accel = veh.net_accel(vv, st, ct, u, cfg)
        lateral_decel = f_lat / (cfg.vehicle.mass * (1.0 + cfg.vehicle.inertia_factor))  # ADD THIS
        return (base_accel - lateral_decel) / vv                        # CHANGE THIS

    v = v0
    dt = 0.0
    for _ in range(sub):
        k1 = dvds(v)
        k2 = dvds(v + 0.5 * h * k1)
        k3 = dvds(v + 0.5 * h * k2)
        k4 = dvds(v + h * k3)
        v_new = v + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        if v_new < _V_FLOOR:
            v_new = _V_FLOOR
        va = v if v > _V_FLOOR else _V_FLOOR
        vb = v_new if v_new > _V_FLOOR else _V_FLOOR
        dt += 0.5 * h * (1.0 / va + 1.0 / vb)   # trapezoid on 1/v
        v = v_new
    return v, dt, fr * dt


def simulate(track: Track, policy: Policy, cfg: Config, v_start: float,
             n_laps: int = 1) -> Trajectory:
    """Roll the car around the loop ``n_laps`` times under ``policy``."""
    n = track.n
    npts = n_laps * n + 1
    s = np.empty(npts)
    s_lap = np.empty(npts)
    vv = np.empty(npts)
    tt = np.empty(npts)
    ff = np.empty(npts)
    uu = np.zeros(npts, dtype=int)

    v, t, fuel = v_start, 0.0, 0.0
    s[0], s_lap[0], vv[0], tt[0], ff[0] = 0.0, 0.0, v, 0.0, 0.0
    lap_time: List[float] = []
    lap_fuel: List[float] = []
    t_lap0 = f_lap0 = 0.0
    cap_ratio = 0.0
    stalled = False

    k = 0
    for lap in range(n_laps):
        for i in range(n):
            u = int(policy(i, v))
            v1, dt, df = step_segment(v, i, u, track, cfg)
            v, t, fuel = v1, t + dt, fuel + df
            k += 1
            s[k] = s[k - 1] + track.ds[i]
            s_lap[k] = (s_lap[k - 1] + track.ds[i]) % track.lap_length
            vv[k], tt[k], ff[k], uu[k - 1] = v, t, fuel, u
            cap_ratio = max(cap_ratio, v / track.v_cap_seg[i])
            if v <= _V_FLOOR:
                stalled = True
        lap_time.append(t - t_lap0)
        lap_fuel.append(fuel - f_lap0)
        t_lap0, f_lap0 = t, fuel

    return Trajectory(s=s, s_lap=s_lap, v=vv, t=tt, fuel_g=ff, u=uu,
                      lap_time=lap_time, lap_fuel_g=lap_fuel,
                      cap_ratio=cap_ratio, stalled=stalled)


def constant_control_policy(controls: np.ndarray) -> Policy:
    """Wrap a per-segment control array as a (state-independent) policy."""
    def policy(i: int, v: float) -> int:
        return int(controls[i])
    return policy
