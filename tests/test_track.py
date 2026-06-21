"""Track preprocessing checks against the real Silesia Ring data."""
import os

import numpy as np
import pytest

from ecomarathon.track import load_track

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "silesia_ring.csv")


@pytest.fixture(scope="module")
def track():
    return load_track(DATA, a_lat_max=4.0, v_max=55 / 3.6)


def test_lap_length_and_uniform_step(track):
    assert track.lap_length == pytest.approx(1319.7, abs=1.0)
    assert track.ds.min() == pytest.approx(track.ds.max(), rel=1e-6)  # uniform
    assert track.ds.mean() == pytest.approx(1.0, abs=0.01)


def test_loop_is_closed(track):
    # First and last points should be adjacent (within one step) and same elevation.
    gap = np.hypot(track.x[0] - track.x[-1], track.y[0] - track.y[-1])
    assert gap < 1.5
    assert abs(track.elev[0] - track.elev[-1]) < 0.2


def test_gradient_is_periodic_and_bounded(track):
    assert abs(track.sin_theta.mean()) < 1e-3          # net climb per lap ~ 0
    assert track.sin_theta.max() < 0.03                # < 3% grade everywhere
    assert track.sin_theta.min() > -0.03


def test_corner_caps_positive_and_finite(track):
    assert np.all(track.v_cap_point > 0)
    assert np.all(np.isfinite(track.v_cap_point))
    assert track.v_cap_point.min() * 3.6 == pytest.approx(31.9, abs=1.0)


def test_eight_corners_detected(track):
    corners = track.corners(r_threshold=60.0)
    assert len(corners) == 8
    tightest = min(corners, key=lambda c: c[1])
    assert tightest[1] < 22.0          # ~20 m radius
    assert tightest[2] < 35.0          # ~32 km/h cap
