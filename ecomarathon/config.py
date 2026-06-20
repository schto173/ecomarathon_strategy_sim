"""Configuration: all physical, engine, race and solver parameters with defaults.

The defaults are *starting estimates* for the LAM Ecoquest prototype + Honda GX35 on the
Silesia Ring. Parameters marked ``CALIBRATE`` strongly affect the fuel prediction and
should be replaced with measured values (see README "Calibration") for accuracy.

Anything here can be overridden from a YAML file via :func:`load_config`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class Vehicle:
    mass_car: float = 35.0              # kg, prototype incl. engine, no driver
    mass_driver: float = 50.0           # kg
    inertia_factor: float = 0.03        # rotating inertia (wheels) as a fraction of mass
    Cd: float = 0.18                    # CALIBRATE drag coefficient ("quite aerodynamic")
    frontal_area: float = 0.68 * 0.68   # m^2 (0.68 m wide x 0.68 m high bounding box)
    Crr: float = 0.0015                 # CALIBRATE rolling resistance coefficient (eco tyres)
    driveline_eff: float = 0.90         # wheel power / engine power while driving

    @property
    def mass(self) -> float:
        """Total moving mass (car + driver), kg."""
        return self.mass_car + self.mass_driver

    @property
    def CdA(self) -> float:
        """Drag area, m^2."""
        return self.Cd * self.frontal_area

    @property
    def m_eff(self) -> float:
        """Effective mass including rotating inertia, kg."""
        return self.mass * (1.0 + self.inertia_factor)


@dataclass
class Engine:
    """Honda GX35 modelled as a bang-bang source at one efficient operating point.

    During a "burn" the engine delivers a constant power at the wheels (CVT-like
    abstraction), capped by available traction at low speed. When OFF it is fully
    shut down and the driveline freewheels (zero fuel, zero drive force).
    """
    burn_power_wheel: float = 600.0     # W delivered at the wheels during a burn
    bsfc: float = 400.0                 # CALIBRATE g/kWh at that operating point (~21% thermal)
    max_traction_force: float = 150.0   # N drive-force cap (grip / structure) at low speed
    off_fuel_rate: float = 0.0          # g/s when OFF (0.0 = truly off + freewheel)
    restart_fuel_g: float = 0.005       # CALIBRATE fuel-equivalent cost of one engine start.
    #   Models restart enrichment + the impracticality of very frequent toggling. This is
    #   what turns the fuel-optimal solution from high-frequency chatter into executable
    #   pulse-and-glide; larger -> fewer, longer pulses. Set from a real restart measurement.

    def engine_power(self, driveline_eff: float) -> float:
        """Crank power required to deliver ``burn_power_wheel`` at the wheels (W)."""
        return self.burn_power_wheel / driveline_eff

    def fuel_rate_burn(self, driveline_eff: float) -> float:
        """Fuel mass flow while burning (g/s)."""
        p_kw = self.engine_power(driveline_eff) / 1000.0
        return self.bsfc * p_kw / 3600.0


@dataclass
class Fuel:
    lhv: float = 43.0e6     # J/kg lower heating value of RON98 petrol
    density: float = 0.745  # kg/L

    def grams_to_litres(self, grams: float) -> float:
        return (grams / 1000.0) / self.density

    def grams_to_ml(self, grams: float) -> float:
        return self.grams_to_litres(grams) * 1000.0


@dataclass
class Environment:
    rho: float = 1.20   # kg/m^3 air density (~20 C, near sea level / 205 m AMSL)
    g: float = 9.81     # m/s^2


@dataclass
class Race:
    """Shell Eco-Marathon Article 226 attempt constraints."""
    n_laps: int = 11
    total_time_limit: float = 2100.0    # s (35 minutes) for the whole attempt
    time_margin: float = 0.03           # keep this fraction of time in hand vs the limit

    @property
    def total_time_budget(self) -> float:
        """Time we actually aim to use across all laps (s), with safety margin."""
        return self.total_time_limit * (1.0 - self.time_margin)

    @property
    def lap_time_target(self) -> float:
        """Average lap-time target the optimiser aims at (s)."""
        return self.total_time_budget / self.n_laps


@dataclass
class Limits:
    a_lat_max: float = 2.0          # m/s^2 lateral accel -> corner speed caps; CALIBRATE
    v_max: float = 40.0 / 3.6       # m/s absolute safety speed cap
    v_min: float = 20.0 / 3.6        # m/s lower bound of the DP speed grid
    a_brake: float = 2.0            # m/s^2 service-braking decel (used only when forced)


@dataclass
class Solver:
    v_step: float = 0.25 / 3.6      # m/s speed-grid resolution for the DP
    substeps: int = 4               # RK4 sub-steps per track segment in the integrator
    dp_laps: int = 3                # concatenated laps for the periodic backward DP
    rollout_laps: int = 7           # forward laps simulated to reach the steady cycle
    avg_laps: int = 4               # laps averaged for steady metrics (even -> robust to period-2)
    lam_iters: int = 16             # bisection iterations on the time multiplier (lambda)
    allow_brake: bool = True        # allow a braking control where coasting cannot make a corner


@dataclass
class Config:
    vehicle: Vehicle = field(default_factory=Vehicle)
    engine: Engine = field(default_factory=Engine)
    fuel: Fuel = field(default_factory=Fuel)
    env: Environment = field(default_factory=Environment)
    race: Race = field(default_factory=Race)
    limits: Limits = field(default_factory=Limits)
    solver: Solver = field(default_factory=Solver)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_SECTIONS = {
    "vehicle": Vehicle, "engine": Engine, "fuel": Fuel, "env": Environment,
    "race": Race, "limits": Limits, "solver": Solver,
}


def config_from_dict(d: Dict[str, Any]) -> Config:
    """Build a Config, overriding only the keys present in ``d``."""
    kwargs = {}
    for name, cls in _SECTIONS.items():
        section = d.get(name, {}) or {}
        kwargs[name] = cls(**section)
    return Config(**kwargs)


def load_config(path: str) -> Config:
    """Load a Config from a YAML file (missing keys fall back to defaults)."""
    import yaml
    with open(path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    return config_from_dict(data)


def save_config(cfg: Config, path: str) -> None:
    """Write the full resolved Config to a YAML file (handy as a calibration template)."""
    import yaml
    with open(path, "w") as fh:
        yaml.safe_dump(cfg.to_dict(), fh, sort_keys=False)
