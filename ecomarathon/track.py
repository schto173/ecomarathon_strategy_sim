"""Track loading and preprocessing.

Reads the Silesia Ring CSV and derives everything the simulator/optimiser needs:
per-segment length and gradient, point curvature, and the corner speed caps implied
by a lateral-acceleration limit.

The lap is treated as a closed loop of ``N`` points and ``N`` segments: segment ``i``
runs from point ``i`` to point ``(i+1) % N``. The final segment closes the loop back
to the start (the supplied data ends ~0.07 m from the start line).
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import numpy as np


def _wrap_pad(a: np.ndarray, pad: int) -> np.ndarray:
    return np.concatenate([a[-pad:], a, a[:pad]])


def _periodic_smooth(a: np.ndarray, window: int) -> np.ndarray:
    """Moving-average smooth with periodic (wraparound) boundaries."""
    if window <= 1:
        return a.astype(float).copy()
    k = np.ones(window) / window
    ext = _wrap_pad(a, window)
    sm = np.convolve(ext, k, mode="same")
    return sm[window:-window]


def _periodic_curvature(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Geometric curvature kappa(=1/R) at each point, using index as the parameter.

    Curvature is parameterisation-invariant, so differentiating w.r.t. sample index is
    fine. Wraparound padding keeps the start/finish seam continuous.
    """
    pad = 2
    xe, ye = _wrap_pad(x, pad), _wrap_pad(y, pad)
    dx, dy = np.gradient(xe), np.gradient(ye)
    ddx, ddy = np.gradient(dx), np.gradient(dy)
    denom = (dx * dx + dy * dy) ** 1.5
    denom = np.where(denom < 1e-9, 1e-9, denom)
    kappa = np.abs(dx * ddy - dy * ddx) / denom
    return kappa[pad:-pad]


@dataclass
class Track:
    """Preprocessed closed-loop track. All arrays have length N (one per point)."""
    s: np.ndarray            # cumulative distance from lap line (m), point-indexed
    x: np.ndarray            # UTM easting (m)
    y: np.ndarray            # UTM northing (m)
    lon: np.ndarray          # longitude (deg)
    lat: np.ndarray          # latitude (deg)
    elev: np.ndarray         # raw elevation (m AMSL)
    elev_s: np.ndarray       # smoothed elevation (m)
    ds: np.ndarray           # segment length i -> i+1 (m)
    sin_theta: np.ndarray    # sin(grade angle) per segment (+ uphill)
    cos_theta: np.ndarray    # cos(grade angle) per segment
    kappa: np.ndarray        # curvature per point (1/m)
    v_cap_point: np.ndarray  # corner speed cap per point (m/s)
    v_cap_seg: np.ndarray    # corner speed cap per segment = min of its endpoints (m/s)
    lap_length: float        # m (including the closing segment)

    @property
    def n(self) -> int:
        return len(self.s)

    def corners(self, r_threshold: float = 60.0):
        """List of (distance_m, radius_m, v_cap_kmh) at the apex of each tight corner."""
        R = np.where(self.kappa > 1e-6, 1.0 / self.kappa, np.inf)
        tight = R < r_threshold
        out, i, n = [], 0, self.n
        while i < n:
            if tight[i]:
                a = i
                while i < n and tight[i]:
                    i += 1
                seg = slice(a, i)
                apex = a + int(np.argmin(R[seg]))
                out.append((float(self.s[apex]), float(R[apex]),
                            float(self.v_cap_point[apex] * 3.6)))
            else:
                i += 1
        return out


def load_track(csv_path: str, a_lat_max: float, v_max: float,
               elev_smooth_window: int = 9, curv_smooth_window: int = 7) -> Track:
    """Load the track CSV and compute gradients, curvature and corner speed caps.

    The raw data is resampled onto a uniform ~1 m grid around the closed loop. This
    removes the very short closing segment (which otherwise produces a spurious
    gradient spike at the start/finish seam) and gives the DP a uniform step.

    Parameters
    ----------
    csv_path : path to the CSV with columns
        ``Distance from Lap Line (m), Elevation (m), UTMX, UTMY, LongX, LatY``.
    a_lat_max : lateral-acceleration limit (m/s^2) used for corner speed caps.
    v_max : absolute speed cap (m/s) applied on straights.
    """
    with open(csv_path, "r", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("Distance")]
    raw = np.array([[float(c) for c in r[:6]] for r in rows])
    s_raw, elev_r, x_r, y_r, lon_r, lat_r = (raw[:, 0], raw[:, 1], raw[:, 2],
                                             raw[:, 3], raw[:, 4], raw[:, 5])

    # Full loop length = arc length to the last point + the short connector back to start.
    d_close = float(np.hypot(x_r[0] - x_r[-1], y_r[0] - y_r[-1]))
    lap_length = float(s_raw[-1] + d_close)

    # Uniform resample onto N ~= lap_length segments of equal length.
    n = int(round(lap_length))
    s = np.arange(n) * (lap_length / n)
    x = np.interp(s, s_raw, x_r)
    y = np.interp(s, s_raw, y_r)
    lon = np.interp(s, s_raw, lon_r)
    lat = np.interp(s, s_raw, lat_r)
    elev = np.interp(s, s_raw, elev_r)
    ds = np.full(n, lap_length / n)
    nxt = np.arange(1, n + 1) % n

    # Gradient per segment from smoothed elevation (raw data has ~cm noise).
    elev_s = _periodic_smooth(elev, elev_smooth_window)
    delev = elev_s[nxt] - elev_s
    sin_theta = np.clip(delev / ds, -0.5, 0.5)
    cos_theta = np.sqrt(np.maximum(1.0 - sin_theta ** 2, 1e-6))

    # Curvature -> corner speed caps. v_cap = sqrt(a_lat / kappa), clipped to v_max.
    kappa = _periodic_smooth(_periodic_curvature(x, y), curv_smooth_window)
    with np.errstate(divide="ignore"):
        v_cap_point = np.where(kappa > 1e-6, np.sqrt(a_lat_max / kappa), v_max)
    v_cap_point = np.minimum(v_cap_point, v_max)
    v_cap_seg = np.minimum(v_cap_point, v_cap_point[nxt])

    return Track(s=s, x=x, y=y, lon=lon, lat=lat, elev=elev, elev_s=elev_s,
                 ds=ds, sin_theta=sin_theta, cos_theta=cos_theta, kappa=kappa,
                 v_cap_point=v_cap_point, v_cap_seg=v_cap_seg, lap_length=lap_length)
