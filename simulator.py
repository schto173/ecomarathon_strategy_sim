"""
Dynamic-programming global-optimum benchmark.

Method: semi-Lagrangian backward DP. State = (track position, speed, engine on/off);
control = engine power. The cost-to-go is built by backward recursion with *linear
interpolation* of V at the (continuous) next speed -- essential, because nearest-node
snapping would let a glide that loses 0.02 m/s round back to the same grid node and
look lossless ("free energy"). Interpolation conserves energy.

The engine-state dimension lets us charge a restart penalty on every off->on
transition, so the optimum is a finite-pulse pulse-and-glide (not unphysical
50 Hz chattering). We minimise fuel + lambda*time per step and sweep lambda to hit
the lap-time budget. The optimal policy is then forward-simulated with the
*continuous* integrator (no grid error) to report an honest, dynamically-feasible
lap -- the lower bound the drivable pulse-and-glide must approach.
"""
from __future__ import annotations
import math
import numpy as np

from vehicle import resistive_force, traction_force, fuel_rate
from simulator import Telemetry, lap_metrics

BIG = 1.0e12


def _control_set(cfg):
    """Glide (0) plus a dense sweep of the useful 50-100% load range (BSFC sweet
    spot). Low intermediate loads are never optimal, so no grid is wasted there."""
    high = np.linspace(0.5, 1.0, cfg.dp_n_ctrl) * cfg.power_max
    return np.concatenate([[0.0], high])


def _backward_dp(track, cfg, lam, vgrid, controls, laps=3):
    """Return (policy_off, policy_on) each [step, v_node] -> control index, and the
    cost-to-go (V_off, V_on) at step 0."""
    n = track.n
    nv = len(vgrid)
    H = laps * n
    f_max = cfg.mu_long * cfg.mass * cfg.g
    fr = np.array([float(fuel_rate(p, cfg)) for p in controls])
    is_on = np.array([p > 0 for p in controls])
    restart = cfg.restart_fuel_g

    pol_off = np.zeros((H, nv), np.int16)
    pol_on = np.zeros((H, nv), np.int16)
    V_off = np.zeros(nv)
    V_on = np.zeros(nv)

    for step in range(H - 1, -1, -1):
        i = step % n
        ds = track.ds[i]
        sin_t = track.sin_theta[i]
        cos_t = track.cos_theta[i]
        cap = min(track.v_cap[i], cfg.dp_v_max)
        grade = cfg.mass * cfg.g * sin_t * (cfg.grade_uphill_factor if sin_t > 0 else 1.0)
        f_res = (0.5 * cfg.rho_air * cfg.cda * vgrid * vgrid
                 + cfg.crr * cfg.mass * cfg.g * cos_t + grade)

        best_off = np.full(nv, BIG)
        best_on = np.full(nv, BIG)
        bp_off = np.zeros(nv, np.int16)
        bp_on = np.zeros(nv, np.int16)

        for ci, p in enumerate(controls):
            if p > 0:
                f_tr = np.minimum(cfg.drive_eff * p / np.maximum(vgrid, cfg.v_floor), f_max)
            else:
                f_tr = 0.0
            a = (f_tr - f_res) / cfg.m_eff
            v2 = vgrid * vgrid + 2.0 * a * ds
            v_next = np.sqrt(np.maximum(v2, cfg.v_floor ** 2))
            v_arr = np.minimum(v_next, cap)        # friction braking clips arrival to the cap
            v_mid = np.maximum(0.5 * (vgrid + v_arr), cfg.v_floor)
            dt = ds / v_mid
            step_cost = fr[ci] * dt + lam * dt
            v_to_go = np.interp(v_arr, vgrid, V_on if is_on[ci] else V_off)
            base = step_cost + v_to_go

            cand_off = base + (restart if is_on[ci] else 0.0)  # off->on pays restart
            cand_on = base                                     # already on (or shutting off)

            u = cand_off < best_off
            best_off = np.where(u, cand_off, best_off)
            bp_off = np.where(u, ci, bp_off).astype(np.int16)
            u = cand_on < best_on
            best_on = np.where(u, cand_on, best_on)
            bp_on = np.where(u, ci, bp_on).astype(np.int16)

        pol_off[step] = bp_off
        pol_on[step] = bp_on
        V_off = best_off
        V_on = best_on

    return (pol_off, pol_on), (V_off, V_on)


def _forward_policy(track, cfg, policies, controls, vgrid, v0, e0, laps, report_lap):
    pol_off, pol_on = policies
    n = track.n
    H = laps * n
    v0g = vgrid[0]
    dv = cfg.dp_dv
    tel = Telemetry(n)
    v = v0
    e = e0
    fuel_cum = 0.0
    t_cum = 0.0
    prev_on = False

    for step in range(H):
        i = step % n
        k = min(max(int(round((v - v0g) / dv)), 0), len(vgrid) - 1)
        ci = (pol_on if e == 1 else pol_off)[step, k]
        p = float(controls[ci])
        on = p > 0

        f_res = resistive_force(v, track.sin_theta[i], track.cos_theta[i], cfg)
        f_tr = float(traction_force(p, v, cfg)) if p > 0 else 0.0
        a = (f_tr - f_res) / cfg.m_eff
        v2 = v * v + 2.0 * a * track.ds[i]
        v_new = math.sqrt(v2) if v2 > cfg.v_floor ** 2 else cfg.v_floor
        if v_new > track.v_cap[i]:
            v_new = track.v_cap[i]
        v_mid = max(0.5 * (v + v_new), cfg.v_floor)
        dt = track.ds[i] / v_mid
        f = float(fuel_rate(p, cfg)) * dt if p > 0 else 0.0
        restart_cost = cfg.restart_fuel_g if (on and e == 0) else 0.0

        if step // n == report_lap:
            if step % n == 0:
                tel.v_start = v
                prev_on = (e == 1)
            if on and not prev_on:
                tel.n_pulses += 1
            prev_on = on
            fuel_cum += f + restart_cost
            t_cum += dt
            tel.v[i] = v_new
            tel.p[i] = p
            tel.engine_on[i] = on
            tel.fuel_cum[i] = fuel_cum
            tel.t_cum[i] = t_cum
            if i == n - 1:
                tel.v_end = v_new
        e = 1 if on else 0
        v = v_new

    tel.fuel_total = fuel_cum
    tel.time_total = t_cum
    return tel


def dp_optimum(track, cfg, v0=6.5, verbose=True):
    vgrid = np.arange(cfg.v_floor, cfg.dp_v_max + cfg.dp_dv, cfg.dp_dv)
    controls = _control_set(cfg)
    target_time = cfg.target_lap_time()
    laps = 3
    report_lap = 1

    def run(lam):
        policies, (V_off, V_on) = _backward_dp(track, cfg, lam, vgrid, controls, laps=laps)
        node = int(np.argmin(np.minimum(V_off, V_on)))
        e0 = 0 if V_off[node] <= V_on[node] else 1
        v_start = float(vgrid[node])
        return _forward_policy(track, cfg, policies, controls, vgrid, v_start, e0, laps, report_lap)

    lam_lo, lam_hi = 0.0, 0.002
    tries = 0
    while run(lam_hi).time_total > target_time and lam_hi < 50.0 and tries < 22:
        lam_hi *= 2.5
        tries += 1

    best_tel = run(lam_hi)
    best_lam = lam_hi
    for _ in range(18):
        lam = 0.5 * (lam_lo + lam_hi)
        tel = run(lam)
        if tel.time_total > target_time:
            lam_lo = lam
        else:
            lam_hi = lam
            best_tel = tel
            best_lam = lam
    if verbose:
        print(f"  DP lambda={best_lam:.5f}  time={best_tel.time_total:.1f}s "
              f"fuel={best_tel.fuel_total:.3f}g  pulses={best_tel.n_pulses}  "
              f"v_in={best_tel.v_start*3.6:.1f} v_out={best_tel.v_end*3.6:.1f} km/h")
    m = lap_metrics(track, best_tel, cfg)
    return {"lambda": best_lam}, best_tel, m
