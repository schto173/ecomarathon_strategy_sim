"""Optimizer validation on the real track.

Runs the DP once (coarsened for speed) and asserts the structural guarantees the
strategy must satisfy: feasibility, corner caps, periodicity, sane fuel, and that the
independent forward simulator reproduces the optimizer's own fuel/time.
"""
import os

import numpy as np
import pytest

from ecomarathon.config import Config
from ecomarathon.track import load_track
from ecomarathon.optimize import DPOptimizer
from ecomarathon.strategy import extract_strategy
from ecomarathon.sim import simulate, constant_control_policy

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "silesia_ring.csv")


def fast_cfg():
    cfg = Config()
    cfg.solver.lam_iters = 8          # coarser sweep -> faster tests
    cfg.solver.v_step = 0.4 / 3.6
    cfg.solver.rollout_laps = 5
    return cfg


@pytest.fixture(scope="module")
def solved():
    cfg = fast_cfg()
    track = load_track(DATA, a_lat_max=cfg.limits.a_lat_max, v_max=cfg.limits.v_max)
    opt = DPOptimizer(track, cfg)
    res = opt.optimize()
    return cfg, track, opt, res


def test_meets_time_limit(solved):
    cfg, track, opt, res = solved
    assert res.feasible
    assert res.lap_time <= res.target_lap_time * 1.01


def test_corner_caps_respected(solved):
    cfg, track, opt, res = solved
    assert res.traj.cap_ratio <= 1.02      # never meaningfully above any corner cap
    assert not res.traj.stalled


def test_cycle_is_periodic(solved):
    cfg, track, opt, res = solved
    dv_kmh = abs(res.traj.v[-1] - res.traj.v[0]) * 3.6
    assert dv_kmh < 1.5                    # start speed ~= end speed (repeatable lap)


def test_fuel_is_sane(solved):
    cfg, track, opt, res = solved
    assert 0.3 < res.lap_fuel_ml < 3.0     # GX35 eco prototype ball-park
    assert res.n_pulses >= 1


def test_simulator_reproduces_optimizer(solved):
    # Forward-sim the optimal controls with the independent integrator; fuel and time
    # should match the optimizer's rollout (plus the restart fuel the sim doesn't model).
    cfg, track, opt, res = solved
    sim = simulate(track, constant_control_policy(res.u), cfg, res.v_start, n_laps=1)
    fuel = sim.lap_fuel_g[0] + res.n_pulses * cfg.engine.restart_fuel_g
    assert sim.lap_time[0] == pytest.approx(res.lap_time, rel=0.03)
    assert fuel == pytest.approx(res.lap_fuel_g, rel=0.05)


def test_pareto_trend_and_determinism(solved):
    cfg, track, opt, res = solved
    front = opt.pareto()
    times = [t for (_, t, _, _) in front]
    fuels = [ml for (_, _, ml, _) in front]
    # Going faster (less time) should cost more fuel overall: fastest burns more than slowest.
    assert fuels[times.index(min(times))] > fuels[times.index(max(times))]
    # Determinism: same inputs -> same answer.
    res2 = opt.optimize()
    assert res2.lap_time == pytest.approx(res.lap_time, rel=1e-9)
    assert res2.lap_fuel_g == pytest.approx(res.lap_fuel_g, rel=1e-9)


def test_strategy_phases_cover_lap(solved):
    cfg, track, opt, res = solved
    strat = extract_strategy(track, res.traj)
    total = strat.burn_dist + strat.glide_dist + strat.brake_dist
    assert total == pytest.approx(track.lap_length, rel=0.02)
    assert strat.n_pulses == res.n_pulses
