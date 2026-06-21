"""Dynamic-programming optimal-control solver for the burn-and-coast strategy.

Fuel-optimal driving with an on/off engine is provably *bang-bang*: at every instant
the engine is either delivering its efficient burst or fully off (plus an optional
brake where coasting cannot make a corner). We compute that optimal schedule with
dynamic programming over a (distance x speed x engine-state) grid.

Why engine state?
-----------------
With a fixed-efficiency burst and *no* cost to switching, the minimum-fuel solution is
degenerate: thousands of on/off patterns burn essentially the same fuel, and the raw DP
picks high-frequency chatter (toggling every metre). A real engine cannot do that --
each start costs restart fuel and effort. We therefore track whether the engine is
running and charge ``restart_fuel_g`` per start. That single penalty collapses the
chatter into executable pulse-and-glide; the bigger it is, the fewer and longer the
pulses.

Method
------
* Speed is discretised onto a grid; control u in {COAST, BURN, BRAKE}; engine state
  e in {off, on}.
* Per (segment, control, speed) the exact transition (exit speed, time, fuel) is
  precomputed once.
* The lap-time constraint is handled by Lagrangian relaxation: minimise
  ``fuel + lambda * time``; larger lambda buys speed at the cost of fuel.
* The closed loop is solved by cyclic value iteration (a few renormalised backward
  sweeps); the greedy policy is rolled forward to the steady periodic cycle.
* Bisecting lambda hits the lap-time target; sweeping it traces the fuel-vs-time front.

Corner caps enter as hard state constraints (speed above a corner's cap is illegal).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .config import Config
from .track import Track
from .sim import Trajectory
from . import vehicle as veh
from .vehicle import COAST, BURN, BRAKE

_BIG = 1e15  # finite "infinity" so interpolation never produces NaNs


@dataclass
class OptResult:
    lam: float
    feasible: bool
    lap_time: float          # s, steady lap
    lap_fuel_g: float        # g, steady lap
    lap_fuel_ml: float       # mL, steady lap
    v_start: float           # m/s, steady-cycle entry speed
    u: np.ndarray            # realised control per segment (len N)
    traj: Trajectory         # single steady lap
    target_lap_time: float
    n_pulses: int


class DPOptimizer:
    def __init__(self, track: Track, cfg: Config):
        self.track = track
        self.cfg = cfg
        lim, sol = cfg.limits, cfg.solver
        self.vg = np.arange(lim.v_min, lim.v_max + sol.v_step, sol.v_step)
        self.v0 = float(self.vg[0])
        self.step = float(self.vg[1] - self.vg[0])
        self.nv = len(self.vg)
        self.allow_brake = sol.allow_brake
        self.controls = [COAST, BURN] + ([BRAKE] if sol.allow_brake else [])
        self.restart = cfg.engine.restart_fuel_g
        self.nxt = (np.arange(track.n) + 1) % track.n
        self.legal = self.vg[None, :] <= track.v_cap_point[:, None] + 1e-9   # (N, Nv)
        self._build_transitions()

    # ---- precompute -------------------------------------------------------
    def _build_transitions(self) -> None:
        """Exit speed / time / fuel for every (segment, control code, speed)."""
        tr, cfg = self.track, self.cfg
        n, nv = tr.n, self.nv
        sub = cfg.solver.substeps
        self.VN = np.empty((n, 3, nv))
        self.DT = np.empty((n, 3, nv))
        self.DF = np.empty((n, 3, nv))
        wind_par = veh.tailwind_component(tr.ux, tr.uy, cfg)
        wind_par = np.broadcast_to(np.asarray(wind_par, dtype=float), (n,))
        for i in range(n):
            st, ct, ds = tr.sin_theta[i], tr.cos_theta[i], tr.ds[i]
            kp, wp = tr.kappa[i], float(wind_par[i])
            h = ds / sub
            for u in (COAST, BURN, BRAKE):
                fr = veh.fuel_rate(u, cfg)
                v = self.vg.copy()
                dt = np.zeros(nv)
                for _ in range(sub):
                    def dvds(vv):
                        vc = np.maximum(vv, 0.3)
                        return veh.net_accel(vc, st, ct, u, cfg, kappa=kp, w_par=wp) / vc
                    k1 = dvds(v)
                    k2 = dvds(v + 0.5 * h * k1)
                    k3 = dvds(v + 0.5 * h * k2)
                    k4 = dvds(v + h * k3)
                    v_new = np.maximum(v + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4), 0.3)
                    dt += 0.5 * h * (1.0 / np.maximum(v, 0.3) + 1.0 / v_new)
                    v = v_new
                self.VN[i, u] = v
                self.DT[i, u] = dt
                self.DF[i, u] = fr * dt
        # Interpolation weights for exit speeds (fixed, so precompute once).
        pos = (self.VN - self.v0) / self.step
        idx = np.floor(pos).astype(int)
        self._frac = pos - idx
        self._valid = (idx >= 0) & (idx < nv - 1)
        self._idx = np.clip(idx, 0, nv - 2)

    def _gather(self, Vrow: np.ndarray, i: int, u: int) -> np.ndarray:
        """Value of ``Vrow`` at the exit speeds of (segment i, control u), vectorised."""
        idx = self._idx[i, u]
        frac = self._frac[i, u]
        g = Vrow[idx] * (1.0 - frac) + Vrow[idx + 1] * frac
        return np.where(self._valid[i, u], g, _BIG)

    # ---- dynamic programming ---------------------------------------------
    def solve(self, lam: float, max_sweeps: int = 8) -> np.ndarray:
        """Cyclic value iteration for multiplier ``lam``.

        Returns the cost-to-go value array ``V`` of shape ``(N, 2, Nv)``, indexed by
        (segment, engine_state, speed). The forward rollout takes the greedy control
        with respect to this value function.
        """
        n, nv = self.track.n, self.nv
        cost_burn = self.DF[:, BURN] + lam * self.DT[:, BURN]    # (N, Nv)
        cost_coast = lam * self.DT[:, COAST]
        cost_brake = lam * self.DT[:, BRAKE]
        if not self.allow_brake:
            cost_brake = np.full((n, nv), _BIG)

        V = np.where(self.legal[:, None, :], 0.0, _BIG).repeat(2, axis=1)  # (N,2,Nv)
        policy = np.zeros((n, 2, nv), dtype=np.int8)
        prev_policy = None
        for _ in range(max_sweeps):
            for i in range(n - 1, -1, -1):
                Voff, Von = V[self.nxt[i], 0], V[self.nxt[i], 1]
                c_burn = cost_burn[i] + self._gather(Von, i, BURN)
                c_coast = cost_coast[i] + self._gather(Voff, i, COAST)
                c_brake = cost_brake[i] + self._gather(Voff, i, BRAKE)
                # engine ON now: burning incurs no start cost
                on = np.stack([c_coast, c_burn, c_brake])               # codes 0,1,2
                # engine OFF now: burning incurs a restart
                off = np.stack([c_coast, c_burn + self.restart, c_brake])
                legal_i = self.legal[i]
                policy[i, 1] = np.argmin(on, axis=0)
                policy[i, 0] = np.argmin(off, axis=0)
                V[i, 1] = np.where(legal_i, on.min(axis=0), _BIG)
                V[i, 0] = np.where(legal_i, off.min(axis=0), _BIG)
            m = V[:, :, :][np.broadcast_to(self.legal[:, None, :], V.shape)].min()
            V -= m
            if prev_policy is not None and np.array_equal(policy, prev_policy):
                break
            prev_policy = policy.copy()
        return V

    # ---- forward rollout --------------------------------------------------
    def _interp_T(self, arr: np.ndarray, i: int, u: int, v: float) -> float:
        """Interpolate a transition table arr[i,u,:] at continuous speed v (clamped)."""
        pos = (v - self.v0) / self.step
        idx = int(np.floor(pos))
        if idx < 0:
            idx, frac = 0, 0.0
        elif idx >= self.nv - 1:
            idx, frac = self.nv - 2, 1.0
        else:
            frac = pos - idx
        return arr[i, u, idx] * (1.0 - frac) + arr[i, u, idx + 1] * frac

    def _value_at(self, Vrow: np.ndarray, vp: float) -> float:
        """Cost-to-go interpolated at exit speed vp; BIG if off the grid (illegal)."""
        pos = (vp - self.v0) / self.step
        idx = int(np.floor(pos))
        if idx < 0 or idx >= self.nv - 1:
            return _BIG
        frac = pos - idx
        return Vrow[idx] * (1.0 - frac) + Vrow[idx + 1] * frac

    def _rollout(self, V: np.ndarray, lam: float, v_init: float, e_init: int,
                 n_laps: int) -> Trajectory:
        """Forward-roll the *continuous* greedy policy w.r.t. value ``V``.

        Choosing the control by one-step lookahead at the true (continuous) speed
        avoids the grid-snapping that otherwise induces spurious period-2 limit cycles.
        """
        tr = self.track
        n = tr.n
        npts = n_laps * n + 1
        s = np.empty(npts); s_lap = np.empty(npts)
        vv = np.empty(npts); tt = np.empty(npts); ff = np.empty(npts)
        uu = np.zeros(npts, dtype=int)
        v, e, t, fuel = v_init, e_init, 0.0, 0.0
        s[0] = s_lap[0] = 0.0
        vv[0], tt[0], ff[0] = v, 0.0, 0.0
        lap_time: List[float] = []; lap_fuel: List[float] = []
        t0 = f0 = 0.0
        cap_ratio = 0.0; stalled = False
        k = 0
        for _lap in range(n_laps):
            for i in range(n):
                Voff, Von = V[self.nxt[i], 0], V[self.nxt[i], 1]
                best_u, best_c, best_v, best_dt, best_df = COAST, None, v, 0.0, 0.0
                for u in self.controls:
                    vp = self._interp_T(self.VN, i, u, v)
                    dt = self._interp_T(self.DT, i, u, v)
                    df = self._interp_T(self.DF, i, u, v)
                    if u == BURN and e == 0:
                        df += self.restart           # real restart fuel on each start
                    vtogo = self._value_at(Von if u == BURN else Voff, vp)
                    c = df + lam * dt + vtogo
                    if best_c is None or c < best_c:
                        best_u, best_c, best_v, best_dt, best_df = u, c, vp, dt, df
                u, v = best_u, best_v
                e = 1 if u == BURN else 0
                t += best_dt; fuel += best_df
                k += 1
                s[k] = s[k - 1] + tr.ds[i]
                s_lap[k] = (s_lap[k - 1] + tr.ds[i]) % tr.lap_length
                vv[k], tt[k], ff[k], uu[k - 1] = v, t, fuel, u
                cap_ratio = max(cap_ratio, v / tr.v_cap_seg[i])
                if v <= 0.31:
                    stalled = True
            lap_time.append(t - t0); lap_fuel.append(fuel - f0)
            t0, f0 = t, fuel
        return Trajectory(s=s, s_lap=s_lap, v=vv, t=tt, fuel_g=ff, u=uu,
                          lap_time=lap_time, lap_fuel_g=lap_fuel,
                          cap_ratio=cap_ratio, stalled=stalled)

    def _periodic_lap(self, V: np.ndarray, lam: float, e0: int = 0) -> Trajectory:
        """The best *period-1* cycle: a single lap that returns to its own start speed.

        We find the fixed point of the one-lap map ``v_start -> v_end`` (engine off at
        the lap line) by bisection on the residual ``v_end - v_start``. A repeatable,
        identical-every-lap strategy is what a driver can actually execute over 11 laps;
        without this constraint the fuel optimum can be a multi-lap cycle (e.g. pulsing
        every other lap), which is impractical and inconsistent to display.
        """
        def end(v0: float) -> Trajectory:
            return self._rollout(V, lam, v0, e0, 1)

        vlo, vhi = 14 / 3.6, 40 / 3.6
        tlo, thi = end(vlo), end(vhi)
        rlo, rhi = tlo.v[-1] - vlo, thi.v[-1] - vhi
        tries = 0
        while rlo * rhi > 0 and tries < 6:
            if rlo > 0 and rhi > 0:
                vhi += 6 / 3.6
            elif rlo < 0 and rhi < 0:
                vlo -= 4 / 3.6
            else:
                break
            tlo, thi = end(vlo), end(vhi)
            rlo, rhi = tlo.v[-1] - vlo, thi.v[-1] - vhi
            tries += 1
        if rlo * rhi > 0:                          # no fixed point bracketed -> fall back
            rl = self.cfg.solver.rollout_laps
            warm = self._rollout(V, lam, 28 / 3.6, 0, rl)
            start = self.track.n * (rl - 1)
            return self._rollout(V, lam, float(warm.v[start]),
                                 1 if warm.u[start - 1] == BURN else 0, 1)
        for _ in range(8):                         # bisection on the residual
            vm = 0.5 * (vlo + vhi)
            rm = end(vm).v[-1] - vm
            if rlo * rm <= 0:
                vhi = vm
            else:
                vlo, rlo = vm, rm
        return end(0.5 * (vlo + vhi))

    def steady_lap(self, lam: float) -> Tuple[float, float, np.ndarray, float, Trajectory]:
        """Solve and return the optimal period-1 lap (metrics + trajectory) for ``lam``."""
        V = self.solve(lam)
        n = self.track.n
        lap = self._periodic_lap(V, lam)
        return lap.lap_time[0], lap.lap_fuel_g[0], lap.u[:n].copy(), float(lap.v[0]), lap

    # ---- public API -------------------------------------------------------
    @staticmethod
    def count_pulses(u: np.ndarray) -> int:
        on = (u == BURN).astype(int)
        return int(np.sum((on == 1) & (np.roll(on, 1) == 0)))

    def _eval(self, lam: float) -> dict:
        t, f_g, u, v_start, lap = self.steady_lap(lam)
        return {"lam": lam, "t": t, "fuel_g": f_g, "u": u, "v_start": v_start, "traj": lap}

    def _mk_result(self, p: dict, target: float, meets: bool) -> OptResult:
        traj = p["traj"]
        return OptResult(
            lam=p["lam"],
            feasible=(traj.cap_ratio <= 1.01 and not traj.stalled and meets),
            lap_time=p["t"], lap_fuel_g=p["fuel_g"],
            lap_fuel_ml=self.cfg.fuel.grams_to_ml(p["fuel_g"]),
            v_start=p["v_start"], u=p["u"], traj=traj, target_lap_time=target,
            n_pulses=self.count_pulses(p["u"]))

    def _lam_grid(self) -> List[float]:
        return [0.0] + list(np.logspace(-4.5, -1.0, self.cfg.solver.lam_iters))

    def optimize(self, target_lap_time: Optional[float] = None) -> OptResult:
        """Minimum-fuel period-1 strategy whose steady lap time <= target.

        Uses a lambda sweep (robust to the non-monotonic ``lap_time(lambda)`` that occurs
        near a pulse-count bifurcation) and selects the *slowest feasible* point -- which
        uses the full time budget and therefore burns the least fuel -- then refines
        lambda locally to sit just under the target. The sweep doubles as the Pareto data.
        """
        target = target_lap_time if target_lap_time is not None else self.cfg.race.lap_time_target
        pts = [self._eval(lam) for lam in self._lam_grid()]   # ascending lambda
        self._last_sweep = pts
        feas = [(k, p) for k, p in enumerate(pts) if p["t"] <= target]
        if not feas:
            return self._mk_result(min(pts, key=lambda p: p["t"]), target, meets=False)
        # Objective is least fuel within the time limit; pick that directly (robust to the
        # non-monotonic lap_time(lambda) near a pulse-count bifurcation).
        best_k, best = min(feas, key=lambda kp: kp[1]["fuel_g"])
        # Refine toward the limit (slower lap => less fuel) when the next slower grid point
        # is infeasible: bisect lambda for the slowest lap that still meets the target.
        if best_k > 0 and pts[best_k - 1]["t"] > target:
            lo, hi = pts[best_k - 1]["lam"], best["lam"]
            for _ in range(10):
                mid = 0.5 * (lo + hi)
                e = self._eval(mid)
                if e["t"] <= target:
                    hi = mid
                    if e["fuel_g"] < best["fuel_g"]:
                        best = e
                else:
                    lo = mid
        return self._mk_result(best, target, meets=True)

    def pareto(self, lams: Optional[List[float]] = None) -> List[Tuple[float, float, float, int]]:
        """Fuel-vs-lap-time front: list of (lam, lap_time_s, lap_fuel_ml, n_pulses).

        Reuses the sweep computed by :meth:`optimize` when available.
        """
        if lams is None:
            pts = getattr(self, "_last_sweep", None) or [self._eval(l) for l in self._lam_grid()]
        else:
            pts = [self._eval(l) for l in lams]
        rows = [(p["lam"], p["t"], self.cfg.fuel.grams_to_ml(p["fuel_g"]),
                 self.count_pulses(p["u"])) for p in pts]
        return sorted(rows, key=lambda r: r[1])
