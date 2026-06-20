"""
Shell Eco-Marathon fuel-strategy optimiser -- entry point.

Usage:
    python main.py [path/to/track.csv]

Runs the whole pipeline: load track -> constant-speed baseline -> optimise the
drivable pulse-and-glide strategy -> DP global-optimum benchmark -> report + plots.
"""
from __future__ import annotations
import os
import sys

from config import Config
from track import load_track
from strategy import ConstantSpeedController, extract_zones
from simulator import simulate_continuous, lap_metrics
from optimizer import optimize
from dp_optimizer import dp_optimum
import report


def constant_speed_baseline(track, cfg):
    """Find the slowest constant speed that still meets the time budget, as a
    reference point for how much pulse-and-glide saves."""
    target = cfg.target_lap_time()
    best = None
    v = cfg.min_avg_speed(track.length) * 0.9
    while v < cfg.dp_v_max:
        ctrl = ConstantSpeedController(track, cfg, v)
        tel, _, _, _, _ = simulate_continuous(track, ctrl, cfg, v0=v)
        m = lap_metrics(track, tel, cfg)
        if m["time_s"] <= target:
            best = (tel, m, v)
            break
        v += 0.25
    if best is None:
        ctrl = ConstantSpeedController(track, cfg, cfg.dp_v_max * 0.5)
        tel, _, _, _, _ = simulate_continuous(track, ctrl, cfg, v0=cfg.dp_v_max * 0.5)
        best = (tel, lap_metrics(track, tel, cfg), cfg.dp_v_max * 0.5)
    return best


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "data", "silesia_ring.csv")
    outdir = os.path.join(here, "plots")
    os.makedirs(outdir, exist_ok=True)

    cfg = Config()
    track = load_track(csv_path, cfg)

    report.print_track_summary(track)
    report.print_constraint(track, cfg)

    # ---- baseline ----------------------------------------------------------
    print("\nRunning constant-speed baseline...")
    tel_c, m_c, v_c = constant_speed_baseline(track, cfg)
    report.print_result(f"BASELINE: constant {v_c*3.6:.1f} km/h", None, m_c)

    # ---- drivable pulse-and-glide -----------------------------------------
    print("\nOptimising pulse-and-glide strategy...")
    params, tel_pg, m_pg = optimize(track, cfg)
    report.print_result("OPTIMISED PULSE-AND-GLIDE", params, m_pg)

    # ---- DP global optimum -------------------------------------------------
    print("\nComputing DP global-optimum benchmark...")
    _, tel_dp, m_dp = dp_optimum(track, cfg, v0=params["v_low_ms"])
    report.print_result("DP GLOBAL OPTIMUM (benchmark)", None, m_dp)

    # ---- comparison --------------------------------------------------------
    save_pct = 100.0 * (1 - m_pg["fuel_g"] / m_c["fuel_g"]) if m_c["fuel_g"] > 0 else 0.0
    gap_pct = 100.0 * (m_pg["fuel_g"] / m_dp["fuel_g"] - 1) if m_dp["fuel_g"] > 1e-6 else float("nan")
    print("\n=== COMPARISON (fuel per lap) ===")
    print(f"  naive constant-throttle  : {m_c['fuel_g']:6.3f} g  ({m_c['km_per_l']:>4.0f} km/L)")
    print(f"  optimised pulse-and-glide: {m_pg['fuel_g']:6.3f} g  ({m_pg['km_per_l']:>4.0f} km/L)"
          f"   <-- {save_pct:.0f}% less fuel than naive")
    print(f"  DP global-optimum bench. : {m_dp['fuel_g']:6.3f} g  ({m_dp['km_per_l']:>4.0f} km/L)"
          f"   {'(feasible)' if m_dp['feasible'] else '(INFEASIBLE)'}")
    if gap_pct < 8:
        print(f"  -> drivable P&G is within ~{gap_pct:.0f}% of the optimum — essentially optimal.")
    else:
        print(f"  -> the DP optimum coasts perfectly into every corner ({m_dp['brake_g']:.2f} g braking)")
        print(f"     and uses fewer, longer pulses ({m_dp['n_pulses']} vs {m_pg['n_pulses']}). The drivable single-band")
        print(f"     strategy sits ~{gap_pct:.0f}% above it — chiefly ~{m_pg['brake_g']:.2f} g/lap wasted braking")
        print(f"     for corners + extra restarts. Headroom is in corner-by-corner speed tuning.")
    print(f"  11-lap total (P&G)       : {m_pg['fuel_ml_total']:.1f} mL, "
          f"{m_pg['time_s']*cfg.n_laps/60:.1f} min (DQ limit {cfg.time_limit_s/60:.0f} min)")

    # ---- strategy table + plots -------------------------------------------
    zones = extract_zones(track, tel_pg)
    report.print_strategy_table(zones)
    report.save_strategy_csv(zones, os.path.join(outdir, "strategy_table.csv"))

    p1 = report.plot_strategy(track, tel_pg, params, outdir)
    p2 = report.plot_fuel(track, {"Pulse-and-Glide": tel_pg, "DP optimum": tel_dp,
                                  "Constant speed": tel_c}, outdir)
    p3 = report.plot_dp_vs_pg(track, tel_pg, tel_dp, outdir)
    print(f"\nPlots written to: {outdir}")
    for p in (p1, p2, p3):
        if p:
            print(f"  - {p}")
    print(f"Strategy table: {os.path.join(outdir, 'strategy_table.csv')}")


if __name__ == "__main__":
    main()
