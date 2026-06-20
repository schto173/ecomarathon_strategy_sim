#!/usr/bin/env python3
"""LAM Ecoquest Strategy Engine — local web app.

A thin FastAPI wrapper around the *validated* burn-and-coast optimiser. Run it and open
the browser; the heavy lifting (the DP we calibrated against telemetry) stays in Python.

    pip install fastapi uvicorn          # (already present in this environment)
    python webapp/app.py                 # -> http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import sys

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ecomarathon.config import Config              # noqa: E402
from ecomarathon.track import load_track           # noqa: E402
from ecomarathon.optimize import DPOptimizer       # noqa: E402
from ecomarathon.strategy import extract_strategy  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CSV = os.path.join(ROOT, "data", "silesia_ring.csv")

app = FastAPI(title="LAM Ecoquest Strategy Engine")
_track_cache: dict = {}


def base_params() -> dict:
    c = Config()
    return {
        "mass_car": c.vehicle.mass_car, "mass_driver": c.vehicle.mass_driver,
        "Cd": c.vehicle.Cd, "frontal_area": round(c.vehicle.frontal_area, 4),
        "Crr": c.vehicle.Crr, "driveline_eff": c.vehicle.driveline_eff,
        "inertia_factor": c.vehicle.inertia_factor,
        "burn_power_wheel": c.engine.burn_power_wheel, "bsfc": c.engine.bsfc,
        "restart_fuel_g": c.engine.restart_fuel_g, "rho": c.env.rho,
        "n_laps": c.race.n_laps, "total_time_limit": c.race.total_time_limit,
        "time_margin": c.race.time_margin, "a_lat_max": c.limits.a_lat_max,
        "quality": "fast",
    }


def presets() -> dict:
    b = base_params()
    cal = {**b, "Cd": 0.0162, "Crr": 0.0098, "burn_power_wheel": 270.0}
    return {
        "default": dict(b),
        "calibrated_2025": cal,
        "halve_crr": {**cal, "Crr": round(0.0098 / 2, 4)},
    }


def build_config(p: dict) -> Config:
    c = Config()
    c.vehicle.mass_car = float(p["mass_car"]); c.vehicle.mass_driver = float(p["mass_driver"])
    c.vehicle.Cd = float(p["Cd"]); c.vehicle.frontal_area = float(p["frontal_area"])
    c.vehicle.Crr = float(p["Crr"]); c.vehicle.driveline_eff = float(p["driveline_eff"])
    c.vehicle.inertia_factor = float(p["inertia_factor"])
    c.engine.burn_power_wheel = float(p["burn_power_wheel"]); c.engine.bsfc = float(p["bsfc"])
    c.engine.restart_fuel_g = float(p["restart_fuel_g"]); c.env.rho = float(p["rho"])
    c.race.n_laps = int(p["n_laps"]); c.race.total_time_limit = float(p["total_time_limit"])
    c.race.time_margin = float(p["time_margin"]); c.limits.a_lat_max = float(p["a_lat_max"])
    if p.get("quality") == "fast":                    # interactive: coarser speed grid
        c.solver.lam_iters = 10; c.solver.v_step = 0.34 / 3.6; c.solver.rollout_laps = 6
    return c


def get_track(a_lat_max: float, v_max: float):
    key = round(a_lat_max, 3)
    if key not in _track_cache:
        _track_cache[key] = load_track(CSV, a_lat_max=a_lat_max, v_max=v_max)
    return _track_cache[key]


def _do_optimize(p: dict) -> dict:
    c = build_config(p)
    track = get_track(c.limits.a_lat_max, c.limits.v_max)
    opt = DPOptimizer(track, c)
    tgt = p.get("target_override")
    res = opt.optimize(target_lap_time=float(tgt) if tgt else None)
    strat = extract_strategy(track, res.traj)
    n = track.n
    km_l = (track.lap_length / 1000.0) / (res.lap_fuel_ml / 1000.0) if res.lap_fuel_ml > 0 else 0.0
    lap_total = res.lap_time * c.race.n_laps
    margin = c.race.total_time_limit - lap_total
    cap = np.minimum(track.v_cap_point[:n], c.limits.v_max) * 3.6
    return {
        "feasible": bool(res.feasible and margin >= 0),
        "summary": {
            "lap_time": round(res.lap_time, 1), "fuel_ml": round(res.lap_fuel_ml, 3),
            "fuel_g": round(res.lap_fuel_g, 3), "km_l": round(km_l, 0),
            "n_pulses": int(res.n_pulses),
            "avg_speed_kmh": round(track.lap_length / res.lap_time * 3.6, 2),
            "engine_on_frac": round(float(np.mean(res.u == 1)) * 100, 1),
            "vmin_kmh": round(float(res.traj.v[:n].min()) * 3.6, 1),
            "vmax_kmh": round(float(res.traj.v[:n].max()) * 3.6, 1),
            "lap_total_s": round(lap_total, 1), "fuel_total_ml": round(res.lap_fuel_ml * c.race.n_laps, 1),
            "margin_s": round(margin, 1), "n_laps": c.race.n_laps,
            "time_limit_s": c.race.total_time_limit, "target_lap_time": round(res.target_lap_time, 1),
            "burn_dist": round(strat.burn_dist, 0), "glide_dist": round(strat.glide_dist, 0),
        },
        "v_kmh": np.round(res.traj.v[:n] * 3.6, 2).tolist(),
        "u": [int(x) for x in res.u[:n]],
        "cap_kmh": np.round(cap, 1).tolist(),
        "phases": [{"kind": ph.kind, "from_m": round(ph.s0 % track.lap_length, 0),
                    "to_m": round(ph.s1 % track.lap_length, 0), "len_m": round(ph.length, 0),
                    "v_in": round(ph.v0 * 3.6, 1), "v_out": round(ph.v1 * 3.6, 1)} for ph in strat.phases],
        "pareto": [[round(l, 5), round(t, 1), round(ml, 3), int(pu)] for (l, t, ml, pu) in opt.pareto()],
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/init")
def init():
    c = Config()
    track = get_track(c.limits.a_lat_max, c.limits.v_max)
    n = track.n
    return {
        "track": {
            "s": np.round(track.s, 1).tolist(),
            "x": np.round(track.x, 2).tolist(),
            "y": np.round(track.y, 2).tolist(),
            "elev": np.round(track.elev_s, 3).tolist(),
            "cap_kmh": np.round(np.minimum(track.v_cap_point, c.limits.v_max) * 3.6, 1).tolist(),
            "lap_length": round(track.lap_length, 1),
            "corners": [[round(d, 0), round(r, 1), round(v, 1)] for (d, r, v) in track.corners()],
        },
        "defaults": base_params(),
        "presets": presets(),
    }


@app.post("/api/optimize")
async def optimize(req: Request):
    p = await req.json()
    return await run_in_threadpool(_do_optimize, p)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn
    print("LAM Ecoquest Strategy Engine -> http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
