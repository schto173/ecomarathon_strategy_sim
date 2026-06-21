"""Reporting: printed summary, plots and a quick fuel-sensitivity analysis."""
from __future__ import annotations

import copy
import os
from typing import List, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .config import Config
from .track import Track
from .optimize import OptResult
from .strategy import Strategy, cheat_sheet
from .sim import simulate, constant_control_policy
from .vehicle import BURN

_PHASE_COLOR = {0: "#2e8b57", 1: "#d6453d", 2: "#e08a1e"}  # glide / burn / brake


# ---------------------------------------------------------------- summary ----
def summary_text(cfg: Config, track: Track, res: OptResult, strat: Strategy) -> str:
    race = cfg.race
    km_per_l = (track.lap_length / 1000.0) / (res.lap_fuel_ml / 1000.0)
    lap_total = res.lap_time * race.n_laps
    fuel_total_ml = res.lap_fuel_ml * race.n_laps
    avg_speed = track.lap_length / res.lap_time * 3.6
    margin = race.total_time_limit - lap_total
    L = []
    L.append("=" * 70)
    L.append("  OPTIMAL BURN-AND-COAST STRATEGY  —  Silesia Ring")
    L.append("=" * 70)
    status = "FEASIBLE" if res.feasible else "INFEASIBLE (cannot meet the time limit)"
    L.append(f"  Result: {status}")
    L.append("")
    L.append(f"  Lap time          {res.lap_time:7.1f} s     (target ≤ {res.target_lap_time:.1f} s, "
             f"avg {avg_speed:.2f} km/h)")
    L.append(f"  Fuel / lap        {res.lap_fuel_ml:7.3f} mL    ({res.lap_fuel_g:.3f} g)")
    L.append(f"  Economy           {km_per_l:7.0f} km/L")
    L.append(f"  Speed band        {res.traj.v.min()*3.6:4.1f} – {res.traj.v.max()*3.6:.1f} km/h")
    L.append(f"  Pulses / lap      {res.n_pulses:5d}        "
             f"(engine on {strat.engine_on_frac*100:.0f}% of the lap, "
             f"{strat.burn_dist:.0f} m burn / {strat.glide_dist:.0f} m glide)")
    if strat.brake_dist > 1:
        L.append(f"  Braking           {strat.brake_dist:.0f} m of forced braking into corners")
    L.append("")
    L.append(f"  OVER {race.n_laps} LAPS ({track.lap_length*race.n_laps/1000:.2f} km):")
    L.append(f"    Total time      {lap_total:7.1f} s   = {lap_total/60:.2f} min "
             f"(limit {race.total_time_limit/60:.0f} min — margin {margin:+.0f} s)")
    L.append(f"    Total fuel      {fuel_total_ml:7.1f} mL")
    if margin < 0:
        L.append("    ⚠ OVER THE TIME LIMIT — lower the target / reduce margin or the run is disqualified.")
    L.append("")
    L.append("  DRIVER CHEAT-SHEET (one lap, distance from start/finish line):")
    L.append(cheat_sheet(track, strat))
    L.append("=" * 70)
    return "\n".join(L)


# ------------------------------------------------------------ sensitivity ----
def sensitivity(cfg: Config, track: Track, res: OptResult) -> List[Tuple[str, float]]:
    """First-order fuel sensitivity: %% change in lap fuel for +10%% in each parameter,
    holding the optimal control schedule fixed (cheap, shows where accuracy matters)."""
    pol = constant_control_policy(res.u)

    def lap_fuel(c: Config) -> float:
        tr = simulate(track, pol, c, res.v_start, n_laps=1)
        return tr.lap_fuel_g[0] + res.n_pulses * c.engine.restart_fuel_g

    base = lap_fuel(cfg)
    out = []
    for name, mut in [
        ("Cd·A (drag area)", lambda c: setattr(c.vehicle, "Cd", c.vehicle.Cd * 1.10)),
        ("Crr (rolling)", lambda c: setattr(c.vehicle, "Crr", c.vehicle.Crr * 1.10)),
        ("Vehicle mass", lambda c: setattr(c.vehicle, "mass_car", c.vehicle.mass_car + 0.10 * c.vehicle.mass)),
        ("BSFC (engine)", lambda c: setattr(c.engine, "bsfc", c.engine.bsfc * 1.10)),
    ]:
        c2 = copy.deepcopy(cfg)
        mut(c2)
        out.append((name, (lap_fuel(c2) - base) / base * 100.0))
    return out


def sensitivity_text(rows: List[Tuple[str, float]]) -> str:
    L = ["  FUEL SENSITIVITY (per +10% in each parameter, strategy held fixed):"]
    for name, pct in sorted(rows, key=lambda r: -abs(r[1])):
        bar = "█" * int(round(abs(pct) * 2))
        L.append(f"    {name:<20} {pct:+5.1f}%  {bar}")
    L.append("    → measure the top items first; they move the fuel number most.")
    return "\n".join(L)


# ------------------------------------------------------------------ plots ----
def _phase_segments(s: np.ndarray, u: np.ndarray):
    """Yield (start_idx, end_idx, control) runs for colouring."""
    a = 0
    for i in range(1, len(u) + 1):
        if i == len(u) or u[i] != u[a]:
            yield a, i, int(u[a])
            a = i


def make_plots(cfg: Config, track: Track, res: OptResult,
               pareto: List[Tuple[float, float, float, int]], outdir: str) -> List[str]:
    os.makedirs(outdir, exist_ok=True)
    n = track.n
    u = res.u
    v = res.traj.v[:n]
    s = res.traj.s[:n]
    corners = track.corners()
    paths = []

    # 1) Track plan view coloured by burn / glide / brake -----------------
    fig, ax = plt.subplots(figsize=(7, 7))
    for a, b, c in _phase_segments(s, u):
        ax.plot(track.x[a:b + 1], track.y[a:b + 1], color=_PHASE_COLOR[c], lw=4, solid_capstyle="round")
    for (cs, cr, cv) in corners:
        idx = int(cs / track.lap_length * n) % n
        ax.plot(track.x[idx], track.y[idx], "ko", ms=4)
        ax.annotate(f"{cv:.0f}", (track.x[idx], track.y[idx]), fontsize=8,
                    textcoords="offset points", xytext=(4, 4))
    ax.plot(track.x[0], track.y[0], "b^", ms=10, label="start/finish")
    ax.set_aspect("equal"); ax.set_title("Silesia Ring — red = BURN, green = GLIDE, orange = BRAKE")
    ax.set_xlabel("UTM East (m)"); ax.set_ylabel("UTM North (m)"); ax.legend(loc="best")
    p = os.path.join(outdir, "track_map.png"); fig.tight_layout(); fig.savefig(p, dpi=110); plt.close(fig)
    paths.append(p)

    # 2) Elevation profile with burn shading ------------------------------
    fig, ax = plt.subplots(figsize=(11, 3.2))
    ax.plot(s, track.elev_s[:n], color="#555", lw=1.5)
    for a, b, c in _phase_segments(s, u):
        if c == BURN:
            ax.axvspan(s[a], s[min(b, n - 1)], color=_PHASE_COLOR[1], alpha=0.25)
    for (cs, cr, cv) in corners:
        ax.axvline(cs, color="k", ls=":", lw=0.7)
        ax.annotate(f"{cv:.0f}", (cs, track.elev_s[:n].max()), fontsize=7, ha="center")
    ax.set_title("Elevation & burn zones (red) — corners dotted (km/h cap)")
    ax.set_xlabel("distance from lap line (m)"); ax.set_ylabel("elev (m)")
    p = os.path.join(outdir, "elevation.png"); fig.tight_layout(); fig.savefig(p, dpi=110); plt.close(fig)
    paths.append(p)

    # 3) Speed vs distance with caps and engine shading -------------------
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.plot(s, v * 3.6, color="#1f4e79", lw=1.8, label="speed")
    ax.plot(s, np.minimum(track.v_cap_point[:n], cfg.limits.v_max) * 3.6,
            color="#c00", lw=1.0, ls="--", label="corner cap")
    avg = track.lap_length / res.lap_time * 3.6
    ax.axhline(avg, color="green", lw=0.9, ls=":", label=f"avg {avg:.1f} km/h")
    for a, b, c in _phase_segments(s, u):
        if c == BURN:
            ax.axvspan(s[a], s[min(b, n - 1)], color=_PHASE_COLOR[1], alpha=0.18)
    ax.set_ylim(0, max(track.v_cap_point[:n].max(), v.max()) * 3.6 * 1.05)
    ax.set_title("Speed plan — red bands = engine ON")
    ax.set_xlabel("distance from lap line (m)"); ax.set_ylabel("km/h"); ax.legend(loc="lower right", ncol=2)
    p = os.path.join(outdir, "speed.png"); fig.tight_layout(); fig.savefig(p, dpi=110); plt.close(fig)
    paths.append(p)

    # 4) Pareto front -----------------------------------------------------
    if pareto:
        pts = [(t, ml) for (_, t, ml, _) in pareto if t < 1e4]
        fig, ax = plt.subplots(figsize=(6, 4))
        ts, mls = zip(*sorted(pts))
        ax.plot(ts, mls, "o-", color="#444", ms=3)
        ax.axvline(res.target_lap_time, color="red", ls="--", label=f"DQ limit {res.target_lap_time:.0f} s")
        ax.plot(res.lap_time, res.lap_fuel_ml, "r*", ms=15, label="chosen")
        ax.set_xlabel("lap time (s)"); ax.set_ylabel("fuel (mL/lap)")
        ax.set_title("Fuel vs lap-time trade-off"); ax.legend()
        p = os.path.join(outdir, "pareto.png"); fig.tight_layout(); fig.savefig(p, dpi=110); plt.close(fig)
        paths.append(p)
    return paths
