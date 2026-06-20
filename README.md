# LAM Ecoquest — Eco-Marathon Burn-and-Coast Strategy Tool

A physics simulator + dynamic-programming optimiser that computes the **fuel-optimal
"burn-and-coast" (pulse-and-glide) driving strategy** for the Shell Eco-Marathon on the
**Silesia Ring**, for a prototype running a **Honda GX35**.

It answers: *when do I fire the engine, how hard, and how far do I glide* — to use the
least fuel while still completing **11 laps within 35 minutes** (Article 226).

---

## The result (default GX35 parameters)

```
Lap time     185.0 s   (avg 25.7 km/h, just under the 190.9 s/lap ceiling)
Fuel/lap     0.93 mL   ->  ~1420 km/L
Strategy     2 short engine pulses per lap; engine ON only ~5% of the lap
Over 11 laps 33.9 min (65 s margin) and ~10 mL total
```

**Both pulses fall on the two uphill sections** (the start-straight climb and the final
climb out of the ~880 m valley); the engine is **off for the entire downhill middle**,
where gravity does the work. The car never approaches the corner speed limits — at
Eco-Marathon speeds on this track, **the time budget, not cornering, is the binding
constraint**.

See `outputs/` for the track map, elevation/burn-zone plot, speed plan and the
fuel-vs-lap-time trade-off curve.

---

## Why pulse-and-glide (and why these numbers)

Holding a steady ~25 km/h needs only **~25–60 W**, but the GX35 makes ~1 kW and is only
efficient near its **~600 W operating point**. You cannot run it efficiently at cruise
power, so the fuel-optimal policy is **bang-bang**: burn in short bursts at the efficient
point, then shut the engine off and freewheel. Resistance is tiny (~4–5 N), so each glide
runs for hundreds of metres — hence only ~2 pulses per lap.

A subtle but important point: with a fixed-efficiency burst, the *fuel* is nearly the same
for any on/off pattern, so a naive optimiser produces useless high-frequency chatter. Real
engines can't restart dozens of times per lap, so the model charges a **restart penalty**
(`restart_fuel_g`) per engine start. That single parameter sets how many pulses you get;
the default gives a clean, drivable **2 pulses/lap**.

---

## Interactive web app

A motorsport-telemetry dashboard that drives the *same* validated optimiser live in the
browser — full parameter control panel, presets (default / calibrated-2025 / ½-Crr), an
interactive Pareto explorer (click a point to set your target), the burn/glide racing-line
map, speed & elevation traces, and a downloadable driver cheat-sheet.

```bash
pip install fastapi uvicorn        # in addition to the scientific stack below
python webapp/app.py               # -> open http://127.0.0.1:8000
```

Use the **FAST** solver while exploring (~8-10 s/run) and **ACCURATE** for the final plan.

## Install & run (CLI)

```bash
pip install numpy scipy matplotlib pyyaml      # standard scientific stack
python main.py                                  # run with defaults -> prints strategy, writes outputs/
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--margin 0.05` | keep 5% of the time budget in hand (default 3%) |
| `--target 188` | optimise for a specific lap time (s) instead of the race budget |
| `--laps 8` | change the lap count |
| `--restart 0.06` | tune the engine-restart penalty (fewer/longer pulses if larger) |
| `--config cal.yaml` | use measured parameters (see below) |
| `--save-config cal.yaml` | dump a fully-populated config template to edit |
| `--no-plots` | skip plot generation |

Outputs (in `outputs/`): `strategy.json`, `trajectory.csv` (distance/speed/engine per
metre — overlay it on telemetry), `track_map.png`, `elevation.png`, `speed.png`,
`pareto.png`, plus the printed driver cheat-sheet.

---

## Calibration — do this for accurate numbers

The defaults are **estimates**. The optimiser's *strategy* (where to burn/glide) is robust,
but the absolute *fuel* number depends on the parameters. A built-in sensitivity analysis
(printed each run) ranks what matters. For this car at ~25 km/h:

| Parameter | Fuel sensitivity (per +10%) | How to measure |
|-----------|------------------------------|----------------|
| **BSFC** (engine g/kWh) | **~+9%** — dominant | Burn a known fuel volume at the steady operating point over a known time |
| Cd·A (drag area) | ~+1% | Coast-down test (see below) |
| Vehicle mass | ~+1% | Scale |
| Crr (rolling) | ~+1% | Coast-down test |

**Takeaway: nail the engine's BSFC first** — at these speeds it dominates the fuel result;
aero/rolling polish barely move it.

**Coast-down test (gives Cd·A and Crr together):** on a flat, calm straight, get up to
speed, shut the engine and freewheel, and log speed vs time. Fit the deceleration to
`m·dv/dt = -½·ρ·Cd·A·v² - Crr·m·g`; the `v²` term gives Cd·A, the constant term gives Crr.

**Restart penalty:** measure the extra fuel a warm GX35 uses to restart and re-stabilise,
or just pick `restart_fuel_g` to match the pulse count you can realistically execute.

Put your measured values in a YAML file (start from `--save-config`) and pass `--config`.

---

## How it works (architecture)

| Module | Responsibility |
|--------|----------------|
| `ecomarathon/track.py` | Load CSV → uniform-step loop, gradient, curvature, corner speed caps |
| `ecomarathon/vehicle.py` | Drag + rolling + grade forces; GX35 burst force & fuel rate |
| `ecomarathon/sim.py` | Forward RK4 distance-domain integrator (physics core + validator) |
| `ecomarathon/optimize.py` | DP over (distance × speed × engine-state); λ-relaxation for the lap-time limit; period-1 cycle extraction; Pareto sweep |
| `ecomarathon/strategy.py` | Optimal trajectory → driver burn/coast cheat-sheet |
| `ecomarathon/report.py` | Printed summary, plots, fuel sensitivity |
| `main.py` | CLI |

The optimiser minimises `fuel + λ·time` by cyclic value iteration on a (distance × speed ×
engine-on/off) grid, with corner caps as hard state constraints. Bisecting/sweeping `λ`
hits the time limit and traces the fuel-vs-time front. The result is forced to a **period-1
cycle** (identical every lap) so it is actually drivable over 11 laps.

---

## Assumptions & limitations (read before trusting the absolute fuel figure)

- **Constant-power burst** (CVT-like). A fixed-gear GX35 follows a torque curve; the burst
  is an idealisation of running at the efficient operating point.
- **Constant BSFC** at the burst point (real BSFC varies with load/RPM).
- **Point-mass longitudinal model** — no tyre slip, transient aero, wind, or driver
  reaction/execution error. Build in margin; the plan assumes metre-perfect execution.
- **Corner caps** come from a single lateral-accel limit (`a_lat_max = 4 m/s²`). Validate
  against your tyres/handling; here they are not binding anyway.
- **Constant air density.** Adjust `env.rho` for temperature/altitude on race day.
- The reported fuel includes a modelled **restart fuel** per pulse — calibrate it.

---

## Tests

```bash
python -m pytest -q
```

19 tests: analytic glide distance, energy conservation, RK4 accuracy, fuel-rate units,
track preprocessing, and optimizer guarantees (meets the time limit, respects corner caps,
periodic cycle, sane fuel, and the independent simulator reproduces the optimizer's
fuel/time).
