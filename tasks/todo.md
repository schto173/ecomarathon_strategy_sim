# LAM Ecoquest — Eco-Marathon Energy Strategy Tool

## Goal
Python simulator + DP optimizer for the burn-and-coast (pulse-and-glide) strategy
on the Silesia Ring (1319.6 m lap). Minimise fuel subject to: 11 laps ≤ 2100 s.
Engine: Honda GX35; coasting = engine OFF + freewheel.

## Tasks
- [x] Capture decisions & analyse track (elevation, corners, feasibility)
- [x] Save clean track CSV (data/silesia_ring.csv)
- [x] config.py — parameters/defaults (vehicle, GX35, fuel, race, limits, solver)
- [x] track.py — load + gradient + curvature + corner speed caps
- [x] vehicle.py — resistance & engine force/fuel model
- [x] sim.py — forward distance-domain integrator (validator + rule-based)
- [x] optimize.py — DP optimal-control (bang-bang) + engine-state restart penalty + lambda sweep + period-1
- [x] strategy.py — convert optimal trajectory -> driver burn/coast cheat-sheet
- [x] report.py — plots + printed summary + sensitivity
- [x] main.py — CLI end-to-end
- [x] tests/ — physics, track, optimizer (19 tests, all pass incl. sim-vs-optimizer cross-check)
- [x] Run on real track; produce outputs/ + README
- [x] Verify all tests pass; sanity-check fuel numbers

## Interactive web app (webapp/)
- [x] FastAPI backend wrapping the validated optimiser (/api/init, /api/optimize)
- [x] Motorsport-telemetry frontend (Chakra Petch + JetBrains Mono, dark, burn=amber/glide=mint)
- [x] Full control panel (sliders) + presets (default / calibrated-2025 / halve-Crr) + FAST/ACCURATE
- [x] Plotly: racing-line burn/glide map, speed trace, elevation, clickable Pareto explorer
- [x] Driver cheat-sheet + CSV/JSON export
- [x] Verified in browser (Playwright): auto-run + preset switch re-optimise correctly
- Run: `python webapp/app.py` -> http://127.0.0.1:8000
- Fix during build: restart penalty 0.03->0.005 + min-fuel selection so it hits the time target
  in the low-power calibrated regime (was landing ~167 s instead of 185 s).

## DONE — final result (default GX35 params)
- 185.0 s/lap, 0.93 mL/lap (~1420 km/L), 2 pulses/lap, 65 s margin over 11 laps.
- Burns on both uphills, glide the downhill. Corners never binding (time budget is).
- Fuel sensitivity: BSFC dominates (+9%/+10%); aero/mass/Crr ~1% each -> calibrate BSFC first.

## Solved modeling issues
- Chatter (60 pulses) -> added engine on/off state + restart_fuel_g penalty -> executable pulse-and-glide.
- Period-2 limit cycles near bifurcations -> enforce period-1 via one-lap fixed-point on v_start.
- Non-monotonic lap_time(lambda) at bifurcation -> lambda sweep + slowest-feasible pick (+ local refine).
- Default restart_fuel_g=0.03 -> clean 2 pulses/lap.

## Key numbers
- Lap 1319.627 m; relief 3.26 m; max grad ±1.4%; 8 corners (tightest R~20 m -> ~32 km/h)
- Constraint: 2100 s / 11 laps -> 190.9 s/lap avg (~25 km/h). Default target with 3% margin.
- Steady cruise power ~25-60 W vs GX35 ~1 kW -> pulse-and-glide; ~3 pulses/lap, ~1 mL/lap (rough).

## Notes
- User first said "8 laps" but Article 226 says 11 laps / 35 min / 14.6 km -> using 11 (parameterised).
- All physics params are starting estimates -> calibrate (coast-down for CdA+Crr, steady burn for BSFC).
