# Shell Eco-Marathon Fuel-Strategy Simulator — Design Spec

**Team:** LAM Ecoquest · **Track:** Silesia Ring · **Date:** 2026-06-20 · **Goal:** minimise total fuel over the
official attempt while never breaching the minimum-average-speed (max-time) rule.

---

## 1. Problem definition

### 1.1 Competition constraint (Article 226)

- 11 consecutive laps, total distance 14.6 km, in **≤ 35 min (2100 s)**.
- Lap length from the supplied GPS data: **L ≈ 1319.63 m** (closed loop — elevation and
  position return to the start).
- Per-lap time budget: `2100 / 11 ≈ 190.9 s/lap`.
- Minimum average speed: `L / 190.9 ≈ 6.91 m/s ≈ 24.9 km/h` (≈ 25 km/h, consistent with
  the rules' rounded 14.6 km).
- We optimise against the **time budget with a safety margin** (default 4 %): target
  lap time ≤ `190.9 × (1 − margin)` so GPS/driver variance cannot cause a DQ.

### 1.2 Track character (read from the CSV)

- Very flat: elevation 203.17–206.43 m, **total relief ≈ 3.3 m**, gradients mostly < 1 %.
  ⇒ Fuel use is dominated by **aerodynamic drag + rolling resistance**, not climbing.
  Elevation is a second-order effect used to fine-tune *where* to cut the engine.
- A ring with corners ⇒ speed is locally limited by lateral grip; corner caps come from
  GPS curvature.

### 1.3 Objective

Minimise total fuel mass over the steady (periodic) lap, subject to:
`lap_time ≤ budget` and `v ≤ v_corner(s)` everywhere.

---

## 2. Physics model

Longitudinal dynamics, integrated per 1 m segment:

```
m_eff · dv/dt = F_traction − ½·ρ·Cd·A·v²  −  Crr·m·g·cosθ  −  m·g·sinθ
                 (engine)      (aero drag)     (rolling)        (grade)
```

- **Pulse (engine ON):** runs at its best-BSFC operating point.
  `F_traction = η_drive · P_pulse / v`, `fuel_rate [g/s] = BSFC · P_pulse`.
- **Glide (engine OFF + freewheel):** `F_traction = 0`, **no engine braking**, `fuel = 0`.
  The car decelerates under drag + rolling + grade only.
- **Corner cap:** `v ≤ safety · √(μ · g · R)`, R from GPS curvature.
- **Why P&G wins:** steady 25 km/h needs only ~0.1 kW at the wheels — far below the
  engine's efficient load, where BSFC is terrible. Pulsing at ~1.5 kW (efficient) then
  gliding engine-off delivers the same average power at far better BSFC.

Integration uses constant-accel per step: `v_new² = v² + 2·a·Δs`, `dt = Δs / v_mid`.

---

## 3. Parameters (all in `config.py`, documented + tunable)

Defaults are clearly-labelled literature values for an SEM prototype; replace with
measured data when available.

| Group | Param | Default | Notes / source |
|---|---|---|---|
| Vehicle | mass `m` | 85 kg | given (35 car + 50 driver) |
| | effective-mass factor | 1.04 | wheel/driveline rotational inertia |
| | frontal area `A` | 0.4624 m² | 0.68 × 0.68 |
| | drag coeff `Cd` | 0.25 | boxy-but-aero; ⇒ Cd·A ≈ 0.116 m². Tune. |
| | rolling resist `Crr` | 0.008 | eco tyre on asphalt (SEM low-rr tyres can be ~0.002). Tune. |
| Engine | `P_max` | 1491 W | 2 HP |
| | `P_pulse` | best-BSFC point (~0.8·P_max) | tunable |
| | `BSFC_min` | 320 g/kWh | small 4-stroke best point (range 300–450) |
| | BSFC model | min at load_opt≈0.8, rising at low load | hook for measured map |
| | `η_drive` | 0.90 | chain/transmission |
| | restart penalty | 0 g (+ min-glide-time guard) | avoids unrealistic fast cycling |
| Fuel | LHV | 43.5 MJ/kg | 98-octane gasoline |
| | density | 0.745 kg/L | for g ↔ mL reporting |
| Environment | `ρ_air` | 1.20 kg/m³ | ~205 m, ~25 °C |
| | `g` | 9.81 m/s² | |
| Grip | lateral `μ` | 0.8 | tunable |
| | corner safety | 0.90 | use 90 % of grip-limited speed |
| Competition | laps / time | 11 / 2100 s | Article 226 |
| | time safety margin | 0.04 | guard against DQ |

---

## 4. Architecture

| Module | Responsibility | Key interface |
|---|---|---|
| `config.py` | all tunable params + sources | dataclasses / dict |
| `track.py` | load CSV → per-segment distance, gradient (smoothed), curvature R, corner-cap envelope | `load_track(path) -> Track` |
| `vehicle.py` | force & engine/fuel physics (pure functions) | `net_force(...)`, `fuel_rate(...)` |
| `simulator.py` | forward integrator over segments given an engine policy; respects v-envelope | `simulate(track, policy, cfg) -> Telemetry` |
| `strategy.py` | drivable pulse-and-glide controller (V_low/V_high band, corner anticipation, hill-aware cuts) → executable strategy map | `pulse_glide_policy(params)` |
| `optimizer.py` | tune (V_low, V_high, …) to min 11-lap fuel s.t. time budget (grid + local refine) | `optimize(track, cfg) -> Result` |
| `dp_optimizer.py` | DP global optimum: state (position × speed), control = engine power; time via Lagrangian λ-sweep; periodic boundary → benchmark fuel & trajectory | `dp_optimum(track, cfg) -> Result` |
| `report.py` / `main.py` | run, plots, strategy table, totals | CLI entry |

Each file has one clear purpose and is independently testable.

### 4.1 Corner-aware speed envelope

Backward pass from corner caps using coast (and, if unavoidable, braking) deceleration →
`v_max(s)` limit curve. The P&G controller oscillates beneath this envelope; near a tight
bend the envelope forces an early engine cut so the car arrives at the corner at its cap.

### 4.2 Drivable strategy output

A table the driver/ECU can follow: per zone → `start_m, end_m, action (PULSE/GLIDE),
entry_speed, exit_speed`. Plus speed/engine plotted vs distance.

### 4.3 DP benchmark

Discretise (s, v); control = engine power (0 = glide, else efficient pulse). Cost = fuel.
Time budget handled by minimising `fuel + λ·time` and sweeping λ to hit the budget
(λ = marginal fuel-value of time; traces the fuel–time Pareto front). Periodic boundary
`v(start)=v(end)`. Reports the lowest-possible fuel and the % gap of the drivable P&G to it.

---

## 5. Outputs

- **Plot 1:** speed vs distance, engine-ON segments shaded, corner-cap envelope, elevation
  on secondary axis.
- **Plot 2:** cumulative fuel vs distance.
- **Plot 3:** DP-optimal vs drivable speed overlay (+ fuel gap).
- **Report:** fuel per lap (g & mL), ×11 total, equivalent km/L, lap & total time, average
  speed, margin to DQ, pulses/glides per lap, % gap to DP optimum.
- **Strategy table:** the per-zone pulse/glide plan.

---

## 6. Testing

- **Unit:** force terms vs hand calcs; corner-speed formula; CSV loader (lap length, closed
  loop); glide deceleration matches drag-only analytic; steady-state top speed matches power
  balance (`P = (½ρCdA v² + Crr m g)·v`).
- **Sanity invariants:** P&G fuel < constant-speed fuel; DP fuel ≤ P&G fuel; optimised
  average speed ≥ constraint; energy balance closes over a lap.
- **Validation target:** wheel power at steady 25 km/h ≈ 0.1 kW; full-power top speed
  ≈ 90 km/h with default params (both confirm the model is in the right regime).

---

## 7. File layout

```
config.py  track.py  vehicle.py  simulator.py  strategy.py
optimizer.py  dp_optimizer.py  report.py  main.py
data/silesia_ring.csv      plots/ (generated)
tests/                     requirements.txt  README.md
docs/specs/2026-06-20-fuel-strategy-design.md
```

## 8. Decisions locked during brainstorming

- Glide = **engine OFF + freewheel** (zero fuel, no engine braking).
- Parameters = **literature defaults, fully tunable**.
- Deliverable = **Python scripts + plots**.
- Target = **11 laps / 35 min** (≈ 25 km/h min average).
- Optimizer = **parametric P&G + DP global-optimum benchmark**.
- Cornering = **μ ≈ 0.8** default, tunable.
