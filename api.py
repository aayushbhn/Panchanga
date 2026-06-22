"""Panchanga API — aggregator / entry point.

The implementation is split across focused modules:
    constants.py     — static data tables, lookup maps, config
    utils.py         — generic helpers, caches, formatting, description builders
    calculations.py  — Skyfield/ephemeris astronomy + cached resources + singletons
    helpers.py       — domain logic, personalization, response assembly
    webapp.py        — the shared Flask `app` instance
    routes.py        — JSON API endpoints
    views.py         — HTML page routes

This module re-exports the full public surface so that `api:app` (gunicorn),
the Docker/Vercel config, and every `api.<name>` reference in the bench/verify/
prof tooling keep working unchanged. It also registers all routes and starts the
background cache prewarm at import — identical behavior to the previous monolith.
"""
from datetime import datetime
import pytz

# Re-export everything so `api.<name>` continues to resolve exactly as before.
from constants import *          # noqa: F401,F403
from utils import *              # noqa: F401,F403
from calculations import *       # noqa: F401,F403
from helpers import *            # noqa: F401,F403

from webapp import app           # noqa: F401  (gunicorn entry: api:app)
import routes                    # noqa: F401  (registers JSON API routes on `app`)
import views                     # noqa: F401  (registers HTML page routes on `app`)


# ============================================================
# 15) STARTUP PREWARM
# ============================================================
def _prewarm():
    """Warm caches on a fresh worker so the first request doesn't pay one-time
    costs: the daily mantra fetch and Skyfield/NumPy lazy initialization.
    Runs in the background at import so it never blocks worker startup or
    serving. Failures are ignored — every path already degrades gracefully."""
    try:
        get_mantra_data()  # warms the per-day mantra lru_cache
    except Exception:
        pass
    try:
        # One throwaway compute warms Skyfield/NumPy lazy state and pages the
        # ephemeris into memory. Kathmandu is a sensible default origin.
        lat_r, lon_r = round_coord(27.7172), round_coord(85.3240)
        tz_name = cached_timezone_str(lat_r, lon_r)
        if tz_name:
            calculate_panchanga_for_date(lat_r, lon_r, datetime.now(), tz_name)
    except Exception:
        pass
    try:
        # Warm the day's transit calendar (user-independent, ~3s) so no
        # /notifications caller pays the boundary-search cost.
        _transit_calendar(datetime.now(pytz.utc))
    except Exception:
        pass


# Kick off prewarm in the background at import (covers gunicorn workers too).
IO_EXECUTOR.submit(_prewarm)

# ============================================================
# 16) RUN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True, port=5001)
