"""
Build the self-contained interactive map.

Loads the track + default config, runs the optimiser once for a sensible opening
strategy, and injects everything as JSON into web/template.html, writing the
single-file deliverable  LAM_Ecoquest_Strategy_Map.html  (open it in any browser).
"""
from __future__ import annotations
import json
import os
import numpy as np

from config import Config
from track import load_track
from optimizer import optimize

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "data", "silesia_ring.csv")
TEMPLATE = os.path.join(HERE, "web", "template.html")
OUT = os.path.join(HERE, "LAM_Ecoquest_Strategy_Map.html")


def r(arr, n):
    return [round(float(v), n) for v in arr]


def main():
    cfg = Config()
    track = load_track(CSV, cfg)

    # lon/lat are columns 4,5 of the CSV (LongX, LatY)
    raw = np.genfromtxt(CSV, delimiter=",", skip_header=1)
    lon, lat = raw[:, 4], raw[:, 5]

    print("Optimising opening strategy for the map...")
    params, _, m = optimize(track, cfg, verbose=False)
    print(f"  opening: {params['v_low_kmh']:.1f}-{params['v_high_kmh']:.1f} km/h, "
          f"{params['pulse_frac']*100:.0f}% load -> {m['fuel_g']:.3f} g/lap")

    cfg_fields = [
        "mass", "rot_inertia_factor", "frontal_area", "cd", "crr", "power_max",
        "bsfc_min", "bsfc_load_opt", "bsfc_beta_low", "bsfc_gamma_high", "drive_eff",
        "mu_long", "restart_fuel_g", "grade_uphill_factor", "fuel_density", "rho_air",
        "g", "mu_lat", "corner_safety", "v_corner_cap", "n_laps", "time_limit_s",
        "time_safety_margin", "v_floor",
    ]
    data = {
        "n": track.n,
        "lapLength": round(track.length, 2),
        "elevMin": round(float(track.elev.min()), 2),
        "elevMax": round(float(track.elev.max()), 2),
        "s": r(track.s, 2),
        "elev": r(track.elev_smooth, 2),
        "sin": r(track.sin_theta, 6),
        "cos": r(track.cos_theta, 6),
        "radius": r(np.minimum(track.radius, 1.0e5), 1),
        "lat": r(lat, 7),
        "lon": r(lon, 7),
        "cfg": {k: getattr(cfg, k) for k in cfg_fields},
        "opt": {
            "v_low": round(params["v_low_ms"], 4),
            "v_high": round(params["v_high_ms"], 4),
            "pulse_frac": round(params["pulse_frac"], 4),
        },
    }

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(data, separators=(",", ":"))
    html = html.replace("__TRACK_DATA_JSON__", payload)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) / 1024
    print(f"Wrote {OUT}  ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
