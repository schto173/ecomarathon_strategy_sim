#!/usr/bin/env python3
"""LAM Ecoquest Eco-Marathon strategy tool — command-line entry point.

Computes the fuel-optimal burn-and-coast strategy for the Silesia Ring and writes a
driver cheat-sheet, plots and machine-readable trajectory/strategy files.

Examples
--------
    python main.py                                  # defaults (Honda GX35, 11 laps / 35 min)
    python main.py --margin 0.05                     # keep 5% time in hand
    python main.py --target 188                       # target a specific lap time (s)
    python main.py --config my_calibration.yaml       # use measured parameters
    python main.py --save-config template.yaml        # dump a calibration template
"""
from __future__ import annotations

import argparse
import csv
import json
import os

import numpy as np

from ecomarathon.config import Config, load_config, save_config
from ecomarathon.track import load_track
from ecomarathon.optimize import DPOptimizer
from ecomarathon.strategy import extract_strategy
from ecomarathon import report


def _write_trajectory_csv(path, track, res):
    n = track.n
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["distance_m", "speed_kmh", "engine", "elevation_m", "corner_cap_kmh"])
        for i in range(n):
            w.writerow([f"{track.s[i]:.1f}", f"{res.traj.v[i] * 3.6:.2f}", int(res.u[i]),
                        f"{track.elev_s[i]:.2f}", f"{min(track.v_cap_point[i], 1e3) * 3.6:.1f}"])


def _write_strategy_json(path, track, res, strat, cfg):
    data = {
        "lap_length_m": track.lap_length,
        "lap_time_s": res.lap_time,
        "lap_fuel_ml": res.lap_fuel_ml,
        "lap_fuel_g": res.lap_fuel_g,
        "km_per_l": (track.lap_length / 1000.0) / (res.lap_fuel_ml / 1000.0),
        "n_pulses": res.n_pulses,
        "feasible": res.feasible,
        "target_lap_time_s": res.target_lap_time,
        "n_laps": cfg.race.n_laps,
        "phases": [
            {"kind": p.kind, "from_m": round(p.s0 % track.lap_length, 1),
             "to_m": round(p.s1 % track.lap_length, 1), "len_m": round(p.length, 1),
             "v_in_kmh": round(p.v0 * 3.6, 1), "v_out_kmh": round(p.v1 * 3.6, 1)}
            for p in strat.phases
        ],
    }
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser(description="Eco-Marathon burn-and-coast optimiser")
    ap.add_argument("--csv", default="data/silesia_ring.csv", help="track CSV")
    ap.add_argument("--config", default=None, help="YAML parameter overrides")
    ap.add_argument("--target", type=float, default=None, help="target lap time (s); overrides race budget")
    ap.add_argument("--margin", type=float, default=None, help="time safety margin fraction (e.g. 0.03)")
    ap.add_argument("--laps", type=int, default=None, help="number of laps")
    ap.add_argument("--restart", type=float, default=None, help="engine restart penalty (g) — tunes pulse count")
    ap.add_argument("--output", default="outputs", help="output directory")
    ap.add_argument("--no-plots", action="store_true", help="skip plot generation")
    ap.add_argument("--save-config", default=None, help="write the resolved config to YAML and exit")
    args = ap.parse_args()

    cfg = load_config(args.config) if args.config else Config()
    if args.margin is not None:
        cfg.race.time_margin = args.margin
    if args.laps is not None:
        cfg.race.n_laps = args.laps
    if args.restart is not None:
        cfg.engine.restart_fuel_g = args.restart

    if args.save_config:
        save_config(cfg, args.save_config)
        print(f"Wrote config template to {args.save_config}")
        return

    print(f"Loading track {args.csv} …")
    track = load_track(args.csv, a_lat_max=cfg.limits.a_lat_max, v_max=cfg.limits.v_max)
    print(f"  {track.n} points, lap {track.lap_length:.1f} m, {len(track.corners())} corners")
    print("Optimising (DP λ-sweep + period-1 cycle) … this takes a few seconds.")

    opt = DPOptimizer(track, cfg)
    res = opt.optimize(target_lap_time=args.target)
    strat = extract_strategy(track, res.traj)

    print()
    print(report.summary_text(cfg, track, res, strat))
    print()
    print(report.sensitivity_text(report.sensitivity(cfg, track, res)))

    os.makedirs(args.output, exist_ok=True)
    _write_trajectory_csv(os.path.join(args.output, "trajectory.csv"), track, res)
    _write_strategy_json(os.path.join(args.output, "strategy.json"), track, res, strat, cfg)
    written = ["trajectory.csv", "strategy.json"]
    if not args.no_plots:
        paths = report.make_plots(cfg, track, res, opt.pareto(), args.output)
        written += [os.path.basename(p) for p in paths]
    print(f"\nWrote to {args.output}/: " + ", ".join(written))


if __name__ == "__main__":
    main()
