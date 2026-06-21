"""Longitudinal force and fuel model for the prototype.

All functions accept scalars or numpy arrays so they can be reused by both the
single-state forward integrator and the vectorised DP precompute.

Sign convention: forces are along the direction of travel; a *resisting* force is
positive when it opposes forward motion. The grade term is signed (positive uphill).
"""
from __future__ import annotations

import numpy as np

from .config import Config

# Control codes used throughout the toolkit.
COAST, BURN, BRAKE = 0, 1, 2


def aero_drag(v, cfg: Config, w_par=0.0):
    """Aerodynamic drag force (N) along the direction of travel.

    ``w_par`` is the tail-wind component of the wind along the car's heading (m/s,
    positive when the wind blows in the direction of travel). Drag depends on the
    *relative* airspeed ``v - w_par``: a head-wind (``w_par < 0``) increases drag, a
    tail-wind decreases it. The signed form ``v_rel * |v_rel|`` keeps the force in
    the correct direction even if a strong tail-wind exceeds the car's speed.
    """
    v_rel = v - w_par
    return 0.5 * cfg.env.rho * cfg.vehicle.CdA * v_rel * np.abs(v_rel)


def rolling_resistance(cos_theta, cfg: Config):
    """Rolling resistance force (N) — independent of speed."""
    veh, env = cfg.vehicle, cfg.env
    return veh.Crr * veh.mass * env.g * cos_theta


def grade_force(sin_theta, cfg: Config):
    """Gravity component along the slope (N), positive uphill."""
    veh, env = cfg.vehicle, cfg.env
    return veh.mass * env.g * sin_theta


def corner_loss_force(v, kappa, cfg: Config):
    """Cornering (slip-induced) drag force (N).

    A cornering tyre runs at a slip angle ``alpha`` to generate the lateral force
    ``F_lat = m * a_lat`` (with ``a_lat = kappa * v^2``). That slip tilts the tyre
    force backwards, costing a longitudinal "induced" drag ``F_lat * tan(alpha)``.
    For small slip ``alpha ~= F_lat / C_alpha`` (cornering stiffness), so the loss is
    *quadratic* in lateral acceleration::

        F_corner = F_lat^2 / C_alpha = corner_loss * m * a_lat^2 / g

    where ``corner_loss`` folds the cornering stiffness into a single tunable,
    dimensionless coefficient (``C_alpha = m*g / corner_loss``). It is zero on a
    straight (``kappa = 0``) and grows fast in tight, fast corners — matching the
    real energy penalty of hard cornering.
    """
    a_lat = kappa * v * v
    return cfg.vehicle.corner_loss * cfg.vehicle.mass * a_lat * a_lat / cfg.env.g


def resistance_force(v, sin_theta, cos_theta, cfg: Config, w_par=0.0):
    """Total force opposing forward motion (N) = drag + rolling + grade."""
    return (aero_drag(v, cfg, w_par)
            + rolling_resistance(cos_theta, cfg)
            + grade_force(sin_theta, cfg))


def drive_force(v, cfg: Config):
    """Drive force (N) while burning at the efficient setpoint, traction-capped."""
    eng = cfg.engine
    v_safe = np.maximum(v, 1e-3)
    return np.minimum(eng.burn_power_wheel / v_safe, eng.max_traction_force)


def net_accel(v, sin_theta, cos_theta, u: int, cfg: Config, kappa=0.0, w_par=0.0):
    """Longitudinal acceleration (m/s^2) for control ``u`` (COAST/BURN/BRAKE).

    ``kappa`` (curvature, 1/m) adds the cornering loss and ``w_par`` (tail-wind
    component, m/s) adjusts the aerodynamic drag. Both default to 0 so the bare
    longitudinal physics is recovered when they are not supplied.
    """
    m = cfg.vehicle.m_eff
    f_res = resistance_force(v, sin_theta, cos_theta, cfg, w_par)
    f_corner = corner_loss_force(v, kappa, cfg)
    if u == BURN:
        return (drive_force(v, cfg) - f_res - f_corner) / m
    if u == BRAKE:
        return (-f_res - f_corner - m * cfg.limits.a_brake) / m
    return (-f_res - f_corner) / m  # COAST


def fuel_rate(u: int, cfg: Config) -> float:
    """Fuel mass flow (g/s) for control ``u`` — constant power model."""
    if u == BURN:
        return cfg.engine.fuel_rate_burn(cfg.vehicle.driveline_eff)
    return cfg.engine.off_fuel_rate


def tailwind_component(ux, uy, cfg: Config):
    """Tail-wind component (m/s) of the configured wind along a heading ``(ux, uy)``.

    ``(ux, uy)`` is a unit heading vector in the UTM plane (east, north). Wind
    direction is the compass bearing the wind blows *from* (0=N, 90=E). Positive
    result = tail-wind (helps), negative = head-wind (hurts).
    """
    w = cfg.env.wind_speed_kmh / 3.6
    if w == 0.0:
        return 0.0 * ux
    to = np.radians(cfg.env.wind_dir_deg + 180.0)   # bearing the wind blows toward
    wx, wy = w * np.sin(to), w * np.cos(to)         # wind velocity vector (east, north)
    return wx * ux + wy * uy
