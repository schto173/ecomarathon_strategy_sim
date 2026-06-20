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


def aero_drag(v, cfg: Config):
    """Aerodynamic drag force (N)."""
    return 0.5 * cfg.env.rho * cfg.vehicle.CdA * v * v


def rolling_resistance(cos_theta, cfg: Config):
    """Rolling resistance force (N) — independent of speed."""
    veh, env = cfg.vehicle, cfg.env
    return veh.Crr * veh.mass * env.g * cos_theta


def grade_force(sin_theta, cfg: Config):
    """Gravity component along the slope (N), positive uphill."""
    veh, env = cfg.vehicle, cfg.env
    return veh.mass * env.g * sin_theta


def resistance_force(v, sin_theta, cos_theta, cfg: Config):
    """Total force opposing forward motion (N) = drag + rolling + grade."""
    return (aero_drag(v, cfg)
            + rolling_resistance(cos_theta, cfg)
            + grade_force(sin_theta, cfg))


def drive_force(v, cfg: Config):
    """Drive force (N) while burning at the efficient setpoint, traction-capped."""
    eng = cfg.engine
    v_safe = np.maximum(v, 1e-3)
    return np.minimum(eng.burn_power_wheel / v_safe, eng.max_traction_force)


def net_accel(v, sin_theta, cos_theta, u: int, cfg: Config):
    """Longitudinal acceleration (m/s^2) for control ``u`` (COAST/BURN/BRAKE)."""
    m = cfg.vehicle.m_eff
    f_res = resistance_force(v, sin_theta, cos_theta, cfg)
    if u == BURN:
        return (drive_force(v, cfg) - f_res) / m
    if u == BRAKE:
        return (-f_res - m * cfg.limits.a_brake) / m
    return (-f_res) / m  # COAST


def fuel_rate(u: int, cfg: Config) -> float:
    """Fuel mass flow (g/s) for control ``u`` — constant power model."""
    if u == BURN:
        return cfg.engine.fuel_rate_burn(cfg.vehicle.driveline_eff)
    return cfg.engine.off_fuel_rate
