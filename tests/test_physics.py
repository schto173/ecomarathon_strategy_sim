"""Physics validation: glide distance, energy conservation, fuel units, force signs.

These pin the longitudinal model to analytic ground truth so the optimiser is built
on a trusted simulator.
"""
import numpy as np
import pytest

from ecomarathon.config import Config
from ecomarathon.track import Track
from ecomarathon import vehicle as veh
from ecomarathon.sim import step_segment, simulate, constant_control_policy
from ecomarathon.vehicle import COAST, BURN, BRAKE


def straight_track(length=3000.0, n=3000, grade=0.0):
    """A synthetic flat (or constant-grade) straight with no corners."""
    s = np.linspace(0.0, length, n, endpoint=False)
    ds = np.full(n, length / n)
    sin_t = np.full(n, grade)
    cos_t = np.sqrt(np.maximum(1.0 - sin_t ** 2, 1e-6))
    vmax = 200 / 3.6
    return Track(s=s, x=s.copy(), y=np.zeros(n), lon=np.zeros(n), lat=np.zeros(n),
                 elev=s * grade, elev_s=s * grade, ds=ds, sin_theta=sin_t,
                 cos_theta=cos_t, kappa=np.zeros(n), v_cap_point=np.full(n, vmax),
                 v_cap_seg=np.full(n, vmax), lap_length=length)


def coast_until(track, cfg, v0, v_target):
    """Coast from v0 and return the distance taken to slow to v_target."""
    v, dist, i = v0, 0.0, 0
    while v > v_target and i < track.n:
        v, _, _ = step_segment(v, i, COAST, track, cfg)
        dist += track.ds[i]
        i += 1
    return dist


def test_glide_distance_matches_analytic_no_drag():
    # With drag removed, the only resistance is constant rolling friction, so the
    # glide distance has a closed form: d = m_eff (v0^2 - v1^2) / (2 F_roll).
    cfg = Config()
    cfg.vehicle.Cd = 0.0
    track = straight_track()
    v0, v1 = 40 / 3.6, 25 / 3.6
    F = veh.rolling_resistance(1.0, cfg)
    d_analytic = cfg.vehicle.m_eff * (v0 ** 2 - v1 ** 2) / (2.0 * F)
    d_sim = coast_until(track, cfg, v0, v1)
    assert d_sim == pytest.approx(d_analytic, rel=2e-3)


def test_energy_conservation_coasting_with_drag():
    # Coasting (engine off): the kinetic energy lost must equal the work done
    # against the resisting force integrated over the path.
    cfg = Config()
    track = straight_track()
    v0 = 45 / 3.6
    v, dist, work = v0, 0.0, 0.0
    for i in range(track.n):
        F = veh.resistance_force(v, 0.0, 1.0, cfg)
        v_new, _, _ = step_segment(v, i, COAST, track, cfg)
        work += F * track.ds[i]          # work done against resistance over this segment
        v = v_new
        dist += track.ds[i]
        if v < 5 / 3.6:
            break
    ke_lost = 0.5 * cfg.vehicle.m_eff * (v0 ** 2 - v ** 2)
    assert work == pytest.approx(ke_lost, rel=2e-3)


def test_fuel_rate_units():
    # 600 W at the wheels / 0.9 driveline = 667 W crank; at 400 g/kWh that is
    # 400 * 0.667 / 3600 = 0.0741 g/s.
    cfg = Config()
    assert veh.fuel_rate(BURN, cfg) == pytest.approx(0.0741, rel=1e-2)
    assert veh.fuel_rate(COAST, cfg) == 0.0


def test_fuel_only_burned_while_burning():
    cfg = Config()
    track = straight_track(length=500.0, n=500)
    burn = simulate(track, constant_control_policy(np.full(track.n, BURN)), cfg, 30 / 3.6)
    coast = simulate(track, constant_control_policy(np.full(track.n, COAST)), cfg, 30 / 3.6)
    assert burn.fuel_g[-1] > 0.0
    assert coast.fuel_g[-1] == pytest.approx(0.0, abs=1e-12)


def test_grade_sign_downhill_accelerates_uphill_decelerates():
    cfg = Config()
    v = 28 / 3.6
    a_flat = veh.net_accel(v, 0.0, 1.0, COAST, cfg)
    a_down = veh.net_accel(v, -0.015, 0.9999, COAST, cfg)   # 1.5% downhill
    a_up = veh.net_accel(v, +0.015, 0.9999, COAST, cfg)     # 1.5% uphill
    assert a_down > a_flat > a_up
    assert a_down > 0.0 > a_up   # this car accelerates on a 1.5% drop, decelerates on a climb


def test_burn_accelerates_brake_decelerates_hardest():
    cfg = Config()
    v = 28 / 3.6
    a_burn = veh.net_accel(v, 0.0, 1.0, BURN, cfg)
    a_coast = veh.net_accel(v, 0.0, 1.0, COAST, cfg)
    a_brake = veh.net_accel(v, 0.0, 1.0, BRAKE, cfg)
    assert a_burn > 0.0 > a_coast > a_brake


def test_rk4_step_is_accurate_vs_fine_euler():
    # The RK4 segment integrator should agree with a very fine Euler reference.
    cfg = Config()
    track = straight_track()
    v_rk, _, _ = step_segment(30 / 3.6, 0, COAST, track, cfg)
    # fine Euler reference over the same 1 m segment
    st, ct, ds = 0.0, 1.0, track.ds[0]
    v = 30 / 3.6
    steps = 2000
    h = ds / steps
    for _ in range(steps):
        v = v + h * veh.net_accel(v, st, ct, COAST, cfg) / v
    assert v_rk == pytest.approx(v, rel=1e-6)
