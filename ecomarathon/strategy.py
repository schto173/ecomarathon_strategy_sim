"""Turn an optimal trajectory into an executable driver cheat-sheet.

Groups the per-segment controls of a steady lap into *phases* (burn pulses, glides and
the occasional brake), expressed in distance-from-lap-line so the driver can act on
them, and annotates each with the relevant corner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .track import Track
from .sim import Trajectory
from .vehicle import COAST, BURN, BRAKE

_KIND = {COAST: "GLIDE", BURN: "BURN", BRAKE: "BRAKE"}


@dataclass
class Phase:
    kind: str        # 'BURN' | 'GLIDE' | 'BRAKE'
    s0: float        # start distance from lap line (m)
    s1: float        # end distance (m); may exceed lap length if it wraps the line
    v0: float        # entry speed (m/s)
    v1: float        # exit speed (m/s)
    wraps: bool = False

    @property
    def length(self) -> float:
        return self.s1 - self.s0


@dataclass
class Strategy:
    phases: List[Phase]
    n_pulses: int
    burn_dist: float
    glide_dist: float
    brake_dist: float
    engine_on_frac: float


def extract_strategy(track: Track, traj: Trajectory) -> Strategy:
    """Build the phase list for a single steady lap (traj must be exactly one lap)."""
    n = track.n
    u = traj.u[:n]
    v = traj.v
    s = traj.s
    kinds = [_KIND[int(c)] for c in u]

    # Group consecutive equal-kind segments into runs.
    runs = []  # (kind, a, b)  segments [a, b)
    a = 0
    for i in range(1, n + 1):
        if i == n or kinds[i] != kinds[a]:
            runs.append((kinds[a], a, i))
            a = i

    # Merge a pulse/brake that wraps the start/finish line (first and last runs same kind).
    wrap = False
    if len(runs) > 1 and runs[0][0] == runs[-1][0] and runs[0][0] != "GLIDE":
        wrap = True

    phases: List[Phase] = []
    for kind, a, b in runs:
        phases.append(Phase(kind=kind, s0=float(s[a]), s1=float(s[b]),
                            v0=float(v[a]), v1=float(v[b])))
    if wrap:
        first, last = phases[0], phases[-1]
        merged = Phase(kind=first.kind, s0=last.s0, s1=first.s1 + track.lap_length,
                       v0=last.v0, v1=first.v1, wraps=True)
        phases = phases[1:-1] + [merged]
        phases.sort(key=lambda p: p.s0)

    burn = sum(p.length for p in phases if p.kind == "BURN")
    glide = sum(p.length for p in phases if p.kind == "GLIDE")
    brake = sum(p.length for p in phases if p.kind == "BRAKE")
    n_pulses = sum(1 for p in phases if p.kind == "BURN")
    return Strategy(phases=phases, n_pulses=n_pulses, burn_dist=burn,
                    glide_dist=glide, brake_dist=brake,
                    engine_on_frac=burn / max(track.lap_length, 1e-9))


def _next_corner(s_mid: float, corners, lap_length: float):
    """The corner whose apex is soonest after s_mid (wrapping the lap)."""
    if not corners:
        return None
    best, best_d = None, 1e18
    for (cs, cr, cv) in corners:
        d = (cs - s_mid) % lap_length
        if d < best_d:
            best, best_d = (cs, cr, cv), d
    return best


def cheat_sheet(track: Track, strat: Strategy) -> str:
    """Human-readable driver instruction table for one lap."""
    corners = track.corners()
    lines = []
    lines.append("  #  ACTION   from(m)  to(m)   len   v_in   v_out   note")
    lines.append("  -  ------   -------  -----   ---   ----   -----   ----")
    for k, p in enumerate(strat.phases, 1):
        s0 = p.s0 % track.lap_length
        note = ""
        if p.kind == "BURN":
            verb = "BURN ⛽"
            note = f"fire engine, accelerate to {p.v1 * 3.6:.0f} km/h"
            if p.wraps:
                note += " (across the line)"
        elif p.kind == "BRAKE":
            verb = "BRAKE 🛑"
            c = _next_corner(0.5 * (p.s0 + p.s1), corners, track.lap_length)
            note = f"scrub for corner @{c[0]:.0f} m ({c[2]:.0f} km/h)" if c else "scrub speed"
        else:
            verb = "GLIDE …"
            note = f"engine OFF, coast to {p.v1 * 3.6:.0f} km/h"
        lines.append(f"  {k:<2d} {verb:<8} {s0:7.0f} {p.s1 % track.lap_length:6.0f} "
                     f"{p.length:5.0f} {p.v0 * 3.6:5.1f}  {p.v1 * 3.6:5.1f}   {note}")
    return "\n".join(lines)
