"""Astronomical / time computations built on Skyfield + the de421 ephemeris:
sidereal longitudes, the five angas, planet positions, sunrise/moonrise, moon
phases, amanta/purnimanta months, adhik maas, muhurta windows, and the cached
ephemeris resources. Also holds the shared singletons (timescale, ephemeris,
timezone finder, IO thread pool, HTTP session).
"""
from datetime import datetime, timedelta
from functools import lru_cache
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
import calendar
import threading
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from skyfield.api import load, Topos
from skyfield.almanac import (
    find_discrete,
    sunrise_sunset,
    moon_phases,
    risings_and_settings,
)
from skyfield.framelib import ecliptic_frame
from timezonefinder import TimezoneFinder
import pytz

from constants import *
from constants import _lahiri_ayanamsa, _DURMUHURTA_SIG, _NO_DURMUHURTA
from utils import *

__all__ = [
    'EPH',
    'HTTP_SESSION',
    'IO_EXECUTOR',
    'TF',
    'TS',
    '_http_adapter',
    'cached_location',
    'cached_moon_phases_for_month',
    'cached_moonrise_moonset',
    'cached_observer',
    'cached_sunrise_sunset',
    'cached_timezone_str',
    'calculate_abhijit_muhurat',
    'calculate_amanta_purnimanta_month_fast',
    'calculate_brahma_muhurat',
    'calculate_choghadiya',
    'calculate_durmuhurta',
    'calculate_gulika_kaal',
    'calculate_rahu_kaal',
    'calculate_ritu',
    'calculate_tithi_and_paksha_from_angle',
    'calculate_varjyam',
    'calculate_yamaganda_kaal',
    'compute_angas_end_times',
    'compute_month_anga_end_times_batch',
    'detect_adhik_maas',
    'estimate_nakshatra_start_utc',
    'find_next_change_time',
    'geocentric_observer',
    'get_all_planet_positions',
    'get_moonrise_moonset_in_window',
    'get_sidereal_lons_geocentric',
    'get_sunrise_sunset',
    'karana_index_at',
    'karana_name_from_number',
    'last_event_before',
    'nakshatra_index_at',
    'precalculate_moon_phases_for_month',
    'sun_moon_angle_at',
    'sun_sidereal_rashi_at',
    'tithi_index_at',
    'tropical_to_sidereal',
    'tropical_to_sidereal_arr',
    'warm_month_moonrise_moonset',
    'warm_month_sunrise_sunset',
    'yoga_index_at',
]



# ============================================================
# 1) GLOBAL SINGLE-LOAD (BIGGEST SPEEDUP)
# ============================================================
TS = load.timescale()
EPH = load("de421.bsp")
TF = TimezoneFinder()

# Shared thread pool used to overlap blocking external HTTP calls (kundali /
# mantra reports) with the CPU-bound Skyfield computation. This only changes
# *when* the network calls run — the data they return is unchanged.
IO_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="panchanga-io")

# Shared HTTP session with a connection pool so repeated calls to the kundali /
# mantra hosts reuse a kept-alive TLS connection instead of paying a fresh
# handshake (~200 ms) every request. Thread-safe for concurrent use by the
# IO_EXECUTOR workers. No retries — preserves the single-attempt behavior of the
# previous urllib code so failure handling is unchanged.
HTTP_SESSION = requests.Session()
_http_adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
HTTP_SESSION.mount("https://", _http_adapter)
HTTP_SESSION.mount("http://", _http_adapter)

@lru_cache(maxsize=4096)
def cached_timezone_str(lat_r: float, lon_r: float):
    return TF.timezone_at(lng=lon_r, lat=lat_r)

@lru_cache(maxsize=4096)
def cached_location(lat_r: float, lon_r: float):
    return Topos(latitude_degrees=lat_r, longitude_degrees=lon_r)

@lru_cache(maxsize=4096)
def cached_observer(lat_r: float, lon_r: float):
    return EPH["earth"] + cached_location(lat_r, lon_r)

@lru_cache(maxsize=1)
def geocentric_observer():
    return EPH["earth"]

# Sunrise/sunset and moonrise/moonset are backed by plain dict caches (instead of
# lru_cache) so a single monthly find_discrete pass can pre-fill an entire month
# at once — see warm_month_sunrise_sunset / warm_month_moonrise_moonset. A cache
# miss still falls back to the exact per-day computation below, so any date not
# pre-warmed is computed lazily and identically. A `.cache_clear` attribute is
# attached to each so existing tooling that clears caches keeps working.
_SUNRISE_CACHE = {}
_MOONRISE_CACHE = {}
_RISE_CACHE_LOCK = threading.Lock()
_RISE_CACHE_MAX = 50000


def _rise_cache_put(cache, key, value):
    with _RISE_CACHE_LOCK:
        if key in cache:
            return
        if len(cache) >= _RISE_CACHE_MAX:
            cache.clear()
        cache[key] = value


def cached_sunrise_sunset(lat_r: float, lon_r: float, date_ymd: str, tz_name: str):
    key = (lat_r, lon_r, date_ymd, tz_name)
    with _RISE_CACHE_LOCK:
        cached = _SUNRISE_CACHE.get(key)
    if cached is not None:
        return cached
    tz = pytz.timezone(tz_name)
    y, m, d = map(int, date_ymd.split("-"))
    anchor_local = tz.localize(datetime(y, m, d, 12, 0, 0))
    location = cached_location(lat_r, lon_r)
    sunrise, sunset = get_sunrise_sunset(TS, EPH, location, tz, anchor_local)
    result = (sunrise.astimezone(pytz.utc), sunset.astimezone(pytz.utc))
    _rise_cache_put(_SUNRISE_CACHE, key, result)
    return result


cached_sunrise_sunset.cache_clear = lambda: _SUNRISE_CACHE.clear()


def cached_moonrise_moonset(lat_r: float, lon_r: float, date_ymd: str, tz_name: str):
    key = (lat_r, lon_r, date_ymd, tz_name)
    with _RISE_CACHE_LOCK:
        cached = _MOONRISE_CACHE.get(key)
    if cached is not None:
        return cached
    tz = pytz.timezone(tz_name)

    # Panchanga day = sunrise -> next sunrise
    sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)
    sunrise_local = sunrise_utc.astimezone(tz)

    next_ymd = _next_day_ymd(date_ymd)
    next_sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, next_ymd, tz_name)
    next_sunrise_local = next_sunrise_utc.astimezone(tz)

    location = cached_location(lat_r, lon_r)

    moonrise, moonset = get_moonrise_moonset_in_window(
        location=location,
        eph=EPH,
        ts=TS,
        tz=tz,
        start_local=sunrise_local,
        end_local=next_sunrise_local,
        # NOTE: if you want closer Drik, try -0.3 (upper-limb-ish),
        # but keep 0.0 if you want pure geometric center crossing:
        horizon_degrees=0.0,
    )

    mr_utc = moonrise.astimezone(pytz.utc) if moonrise else None
    ms_utc = moonset.astimezone(pytz.utc) if moonset else None
    result = (mr_utc, ms_utc)
    _rise_cache_put(_MOONRISE_CACHE, key, result)
    return result


cached_moonrise_moonset.cache_clear = lambda: _MOONRISE_CACHE.clear()


def warm_month_sunrise_sunset(lat_r, lon_r, tz_name, year, month, tail_days=8):
    """Pre-fill the sunrise/sunset cache for a whole month (+ tail) using ONE
    find_discrete pass instead of ~30 per-day searches. The almanac function and
    root finder are identical to cached_sunrise_sunset; only the search window
    differs, which does not move the converged event instants — so the cached
    values are identical to the per-day computation (verified byte-for-byte)."""
    tz = pytz.timezone(tz_name)
    ndays = calendar.monthrange(year, month)[1]
    location = cached_location(lat_r, lon_r)
    start_local = tz.localize(datetime(year, month, 1)) - timedelta(days=2)
    last = datetime(year, month, ndays) + timedelta(days=tail_days)
    end_local = tz.localize(datetime(last.year, last.month, last.day)) + timedelta(days=1)
    f = sunrise_sunset(EPH, location)
    times, events = find_discrete(
        TS.from_datetime(start_local.astimezone(pytz.utc)),
        TS.from_datetime(end_local.astimezone(pytz.utc)),
        f,
    )
    # Group by local date; last event of each kind wins, mirroring get_sunrise_sunset.
    by_date = {}
    for t, ev in zip(times, events):
        loc_dt = t.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz)
        rec = by_date.setdefault(loc_dt.date(), [None, None])
        if int(np.atleast_1d(ev)[0]) == 1:
            rec[0] = loc_dt
        else:
            rec[1] = loc_dt
    for d, (sr, ss) in by_date.items():
        if sr is None or ss is None:
            continue  # incomplete day → leave for the exact lazy fallback
        key = (lat_r, lon_r, d.strftime("%Y-%m-%d"), tz_name)
        _rise_cache_put(_SUNRISE_CACHE, key,
                        (sr.astimezone(pytz.utc), ss.astimezone(pytz.utc)))


def warm_month_moonrise_moonset(lat_r, lon_r, tz_name, year, month, tail_days=8):
    """Pre-fill the moonrise/moonset cache for a whole month (+ tail) using ONE
    find_discrete pass for all moon rise/set transitions, then assigning the first
    rise and first set inside each panchanga day's [sunrise, next-sunrise] window —
    exactly what cached_moonrise_moonset does per day (verified byte-for-byte).
    Requires the sunrise cache to be warmed first."""
    tz = pytz.timezone(tz_name)
    ndays = calendar.monthrange(year, month)[1]
    location = cached_location(lat_r, lon_r)
    start_local = tz.localize(datetime(year, month, 1)) - timedelta(days=3)
    last = datetime(year, month, ndays) + timedelta(days=tail_days)
    end_local = tz.localize(datetime(last.year, last.month, last.day)) + timedelta(days=2)
    f = risings_and_settings(EPH, EPH["moon"], location, horizon_degrees=0.0)
    times, states = find_discrete(
        TS.from_datetime(start_local.astimezone(pytz.utc)),
        TS.from_datetime(end_local.astimezone(pytz.utc)),
        f,
    )
    events = [(t.utc_datetime().replace(tzinfo=pytz.utc), int(np.atleast_1d(s)[0]))
              for t, s in zip(times, states)]
    first = datetime(year, month, 1).date()
    cur = first
    enddate = (datetime(year, month, ndays) + timedelta(days=tail_days)).date()
    while cur <= enddate:
        ymd = cur.strftime("%Y-%m-%d")
        key = (lat_r, lon_r, ymd, tz_name)
        with _RISE_CACHE_LOCK:
            present = key in _MOONRISE_CACHE
        if not present:
            sr0 = cached_sunrise_sunset(lat_r, lon_r, ymd, tz_name)[0]
            sr1 = cached_sunrise_sunset(lat_r, lon_r, _next_day_ymd(ymd), tz_name)[0]
            mr = ms = None
            for dt, s in events:
                if dt <= sr0 or dt >= sr1:
                    continue
                if s == 1 and mr is None:
                    mr = dt
                elif s == 0 and ms is None:
                    ms = dt
            _rise_cache_put(_MOONRISE_CACHE, key, (mr, ms))
        cur += timedelta(days=1)

def tropical_to_sidereal_arr(tropical_deg, jd=None):
    ayanamsa = _lahiri_ayanamsa(jd) if jd is not None else AYANAMSA
    return (_as_np(tropical_deg) - ayanamsa) % 360.0

def tropical_to_sidereal(tropical_deg_scalar, jd=None):
    ayanamsa = _lahiri_ayanamsa(jd) if jd is not None else AYANAMSA
    return float((tropical_deg_scalar - ayanamsa) % 360.0)

def get_sidereal_lons_geocentric(t):
    earth = geocentric_observer()
    sun = EPH["sun"]
    moon = EPH["moon"]
    jd = float(np.atleast_1d(t.tt)[0])

    # Compute the observer's position once and reuse it for both bodies (one
    # ephemeris evaluation of Earth instead of two — numerically identical).
    observer_at_t = earth.at(t)
    sun_lon_trop = observer_at_t.observe(sun).apparent().frame_latlon(ecliptic_frame)[1].degrees
    moon_lon_trop = observer_at_t.observe(moon).apparent().frame_latlon(ecliptic_frame)[1].degrees

    sun_sid = tropical_to_sidereal_arr(sun_lon_trop, jd)
    moon_sid = tropical_to_sidereal_arr(moon_lon_trop, jd)
    return sun_sid, moon_sid

def sun_moon_angle_at(t):
    sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
    return (moon_sid - sun_sid) % 360.0

# The four anga index functions accept optional precomputed longitudes/angle so a
# caller that already has them (the per-instant panchanga computation) need not
# trigger another set of apparent-position observes. find_discrete() still calls
# these with only `t`, so the search behavior is unchanged.
def tithi_index_at(t, angle=None):
    if angle is None:
        angle = sun_moon_angle_at(t)
    return (np.floor(angle / TITHI_DEG).astype(int) + 1)  # 1..30

def nakshatra_index_at(t, moon_sid=None):
    if moon_sid is None:
        _, moon_sid = get_sidereal_lons_geocentric(t)
    return (np.floor(moon_sid / NAK_DEG).astype(int) % 27)  # 0..26

def yoga_index_at(t, sun_sid=None, moon_sid=None):
    if sun_sid is None or moon_sid is None:
        sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
    yoga_val = (sun_sid + moon_sid) % 360.0
    return (np.floor(yoga_val / YOGA_DEG).astype(int) % 27)  # 0..26

def karana_index_at(t, angle=None):
    if angle is None:
        angle = sun_moon_angle_at(t)
    k = (np.floor(angle / KARANA_DEG).astype(int) + 1)  # 1..60
    return ((k - 1) % 60) + 1

def karana_name_from_number(k: int) -> str:
    if k == 1:
        return "Kimstughna"
    if 2 <= k <= 57:
        return KARANA_REPEATING[(k - 2) % 7]
    if k == 58:
        return "Shakuni"
    if k == 59:
        return "Chatushpada"
    return "Nagava"  # 60

# ============================================================
# 7) PANCHANGA CALCS (TITHI/PAKSHA etc)
# ============================================================
def calculate_tithi_and_paksha_from_angle(angle_deg: float):
    tithi_number = int(angle_deg // 12.0) + 1
    paksha = "Krishna Paksha" if tithi_number > 15 else "Shukla Paksha"
    tithi_name = tithi_names[tithi_number - 1]
    return tithi_number, paksha, tithi_name

def calculate_ritu(sun_sidereal_longitude: float):
    ritu_index = int(sun_sidereal_longitude // 60)
    return ritu_names[ritu_index % 6]


# ============================================================
# GRAHA GOCHAR  (all 9 Navagraha positions)
# ============================================================
def get_all_planet_positions(t):
    earth = geocentric_observer()
    planet_map = [
        ("Sun","sun"),("Moon","moon"),("Mars","mars"),("Mercury","mercury"),
        ("Jupiter","jupiter barycenter"),("Venus","venus"),("Saturn","saturn barycenter"),
    ]
    jd = float(np.atleast_1d(t.tt)[0])
    # Earth's position at t is the same for every body — compute it once.
    observer_at_t = earth.at(t)
    result = {}
    for name, body in planet_map:
        lon_trop = observer_at_t.observe(EPH[body]).apparent().frame_latlon(ecliptic_frame)[1].degrees
        lon_sid  = tropical_to_sidereal(float(np.atleast_1d(lon_trop)[0]), jd)
        rashi    = rashi_names[int(lon_sid // 30) % 12]
        result[name] = {
            "longitude":   round(lon_sid, 4),
            "rashi":       rashi,
            "significance": (f"Transiting {rashi} ({RASHI_NATURE_BRIEF[rashi]}), "
                             f"influencing {PLANET_GOVERNS[name]}."),
        }

    d = jd - 2451545.0
    rahu_trop = (125.044522 - 0.052953922 * d) % 360.0
    rahu_sid  = tropical_to_sidereal(rahu_trop, jd)
    ketu_sid  = (rahu_sid + 180.0) % 360.0
    for name, lon_sid in (("Rahu", rahu_sid), ("Ketu", ketu_sid)):
        rashi = rashi_names[int(lon_sid // 30) % 12]
        result[name] = {
            "longitude":   round(lon_sid, 4),
            "rashi":       rashi,
            "significance": (f"Transiting {rashi} ({RASHI_NATURE_BRIEF[rashi]}), "
                             f"influencing {PLANET_GOVERNS[name]}."),
        }
    return result


# ============================================================
# CHOGHADIYA
# ============================================================
def calculate_choghadiya(sunrise, sunset, next_sunrise, weekday):
    day_part   = (sunset - sunrise).total_seconds() / 8
    night_part = (next_sunrise - sunset).total_seconds() / 8

    def _slots(base, part, start_idx):
        out = []
        for i in range(8):
            name = CHOGHADIYA_NAMES[(start_idx + i) % 7]
            s = base + timedelta(seconds=part * i)
            e = base + timedelta(seconds=part * (i + 1))
            out.append({
                "name":        name,
                "quality":     CHOGHADIYA_QUALITY[name],
                "significance":CHOGHADIYA_SIGNIFICANCE[name],
                "start":       s.strftime("%I:%M %p"),
                "end":         e.strftime("%I:%M %p"),
            })
        return out

    return {
        "day":   _slots(sunrise,  day_part,   CHOGHADIYA_DAY_START[weekday]),
        "night": _slots(sunset,   night_part, CHOGHADIYA_NIGHT_START[weekday]),
    }

def calculate_durmuhurta(sunrise, sunset, weekday, day_name=""):
    muhurta = (sunset - sunrise).total_seconds() / 15
    indices = DURMUHURTA_INDEX[weekday]
    windows = []
    if indices:
        for idx in indices:
            s = sunrise + timedelta(seconds=muhurta * idx)
            e = s + timedelta(seconds=muhurta)
            windows.append([s.strftime("%I:%M %p"), e.strftime("%I:%M %p")])
    significance = _NO_DURMUHURTA if not windows else _DURMUHURTA_SIG
    return {
        "windows":     windows,
        "significance": significance,
        "description": _desc_durmuhurta(windows, day_name or "today"),
    }


# ============================================================
# NAKSHATRA START  (estimate from moon position + end time)
# ============================================================
def estimate_nakshatra_start_utc(moon_sid_deg, now_utc, nak_end_utc):
    deg_into = moon_sid_deg % NAK_DEG
    deg_left = NAK_DEG - deg_into
    if nak_end_utc and deg_left > 0:
        secs_left = (nak_end_utc - now_utc).total_seconds()
        if secs_left > 0:
            speed = deg_left / secs_left          # deg/sec
            return now_utc - timedelta(seconds=deg_into / speed)
    # fallback: average moon speed 13.2°/day
    return now_utc - timedelta(seconds=(deg_into / 13.2) * 86400)


# ============================================================
# VARJYAM
# ============================================================
def calculate_varjyam(nak_idx, nak_start_utc, nak_end_utc, tz, nakshatra_name=""):
    offset_g, dur_g = VARJYAM_TABLE[nak_idx]
    end = nak_end_utc if nak_end_utc else (nak_start_utc + timedelta(hours=25))
    ghati   = (end - nak_start_utc).total_seconds() / 60.0
    v_start = nak_start_utc + timedelta(seconds=ghati * offset_g)
    v_end   = v_start       + timedelta(seconds=ghati * dur_g)
    start_str = v_start.astimezone(tz).strftime("%I:%M %p")
    end_str   = v_end.astimezone(tz).strftime("%I:%M %p")
    nak_label = nakshatra_name or nakshatras[nak_idx]
    return {
        "start": start_str,
        "end":   end_str,
        "significance": ("Inauspicious window based on the current nakshatra. "
                         "Avoid starting new work, ceremonies, or important decisions during this time."),
        "description": _desc_varjyam(start_str, end_str, nak_label),
    }


# ============================================================
# ADHIK MAAS DETECTION
# ============================================================
def detect_adhik_maas(target_dt_local, amanta_month, tz_name, lat_r, lon_r):
    target_utc = target_dt_local.astimezone(pytz.utc)
    target_tt  = TS.from_datetime(target_utc).tt
    y, m = target_dt_local.year, target_dt_local.month

    ph = cached_moon_phases_for_month(y, m, tz_name)
    last_new = last_event_before(ph["new_tt"], ph["new_dt"], target_tt)
    if not last_new:
        return False, amanta_month

    last_new_tt = TS.from_datetime(last_new).tt
    prev_new = last_event_before(ph["new_tt"], ph["new_dt"], last_new_tt - 0.01)
    if not prev_new:
        py, pm = _prev_month(y, m)
        ph2 = cached_moon_phases_for_month(py, pm, tz_name)
        prev_new = last_event_before(ph2["new_tt"], ph2["new_dt"], last_new_tt - 0.01)
    if not prev_new:
        return False, amanta_month

    obs = cached_observer(lat_r, lon_r)
    if sun_sidereal_rashi_at(last_new, TS, EPH, obs) == sun_sidereal_rashi_at(prev_new, TS, EPH, obs):
        return True, f"Adhik {amanta_month}"
    return False, amanta_month


# ============================================================
# 8) SUNRISE / MOONRISE
# ============================================================
def get_sunrise_sunset(ts, eph, location, tz, anchor_local):
    f = sunrise_sunset(eph, location)
    start_utc, end_utc = _local_day_bounds_utc(tz, anchor_local)
    t0 = ts.from_datetime(start_utc)
    t1 = ts.from_datetime(end_utc)

    times, events = find_discrete(t0, t1, f)

    sunrise_time, sunset_time = None, None
    for t, event in zip(times, events):
        local_time = t.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz)
        if event == 1:
            sunrise_time = local_time
        elif event == 0:
            sunset_time = local_time

    return sunrise_time, sunset_time

def get_moonrise_moonset_in_window(location, eph, ts, tz, start_local, end_local, horizon_degrees=0.0):
    """
    Correct: initialize prev = f(t0) so first transition isn't missed.
    """
    if start_local.tzinfo is None or end_local.tzinfo is None:
        raise ValueError("start_local and end_local must be timezone-aware")

    t0 = ts.from_datetime(start_local.astimezone(pytz.utc))
    t1 = ts.from_datetime(end_local.astimezone(pytz.utc))

    f = risings_and_settings(eph, eph["moon"], location, horizon_degrees=horizon_degrees)

    # critical init:
    prev = bool(np.atleast_1d(f(t0))[0])

    times, states = find_discrete(t0, t1, f)

    moonrise_time = None
    moonset_time = None

    for t, s in zip(times, states):
        s = bool(np.atleast_1d(s)[0])
        if (prev is False) and (s is True) and moonrise_time is None:
            moonrise_time = t.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz)
        if (prev is True) and (s is False) and moonset_time is None:
            moonset_time = t.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz)
        prev = s

    return moonrise_time, moonset_time

# ============================================================
# 9) MUHURTA HELPERS
# ============================================================
def calculate_rahu_kaal(sunrise, sunset, day_of_week):
    day_duration = (sunset - sunrise).total_seconds()
    part = day_duration / 8
    rahu_period_index = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
    idx = rahu_period_index[day_of_week]
    start = sunrise + timedelta(seconds=part * idx)
    end = start + timedelta(seconds=part)
    return start, end

def calculate_gulika_kaal(sunrise, sunset, day_of_week):
    day_duration = (sunset - sunrise).total_seconds()
    part = day_duration / 8
    gulika_period_index = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0, 6: 6}
    idx = gulika_period_index[day_of_week]
    start = sunrise + timedelta(seconds=part * idx)
    end = start + timedelta(seconds=part)
    return start, end

def calculate_yamaganda_kaal(sunrise, sunset, day_of_week):
    day_duration = (sunset - sunrise).total_seconds()
    part = day_duration / 8
    yamaganda_period_index = {0: 3, 1: 2, 2: 1, 3: 0, 4: 6, 5: 5, 6: 4}
    idx = yamaganda_period_index[day_of_week]
    start = sunrise + timedelta(seconds=part * idx)
    end = start + timedelta(seconds=part)
    return start, end

def calculate_abhijit_muhurat(sunrise, sunset):
    day_duration = (sunset - sunrise).total_seconds()
    muhurta = day_duration / 15.0
    start = sunrise + timedelta(seconds=7 * muhurta)
    end = sunrise + timedelta(seconds=8 * muhurta)
    return start, end

def calculate_brahma_muhurat(sunrise, sunset):
    day_seconds = (sunset - sunrise).total_seconds()
    night_seconds = 24 * 3600 - day_seconds
    night_muhurta = night_seconds / 15.0
    start = sunrise - timedelta(seconds=2 * night_muhurta)
    end = sunrise - timedelta(seconds=1 * night_muhurta)
    return start, end

# ============================================================
# 11) MOON PHASE CACHE FOR MONTH (for amanta/purnimanta)
# ============================================================
@lru_cache(maxsize=2400)
def cached_moon_phases_for_month(year: int, month: int, tz_name: str):
    tz = pytz.timezone(tz_name)
    data = precalculate_moon_phases_for_month(TS, EPH, year, month, tz)

    new_dt = sorted([dt.replace(tzinfo=pytz.utc) for dt in data["all_new_moons"]])
    full_dt = sorted([dt.replace(tzinfo=pytz.utc) for dt in data["all_full_moons"]])

    new_tt = [TS.from_datetime(dt).tt for dt in new_dt]
    full_tt = [TS.from_datetime(dt).tt for dt in full_dt]
    return {"new_dt": new_dt, "new_tt": new_tt, "full_dt": full_dt, "full_tt": full_tt}

def last_event_before(tt_list, dt_list, target_tt):
    i = bisect_right(tt_list, target_tt) - 1
    return dt_list[i] if i >= 0 else None

def precalculate_moon_phases_for_month(ts, eph, year, month, tz):
    m0, y0 = month - 2, year
    while m0 <= 0:
        m0 += 12
        y0 -= 1

    m1, y1 = month + 2, year
    while m1 > 12:
        m1 -= 12
        y1 += 1

    t0 = ts.utc(y0, m0, 1)
    t1 = ts.utc(y1, m1, 1)

    phase_times, phases = find_discrete(t0, t1, moon_phases(eph))

    new_moons, full_moons = [], []
    for t, phase in zip(phase_times, phases):
        dt = t.utc_datetime().replace(tzinfo=pytz.utc)
        if phase == 0:
            new_moons.append(dt)
        elif phase == 2:
            full_moons.append(dt)

    return {"all_new_moons": new_moons, "all_full_moons": full_moons}

def sun_sidereal_rashi_at(dt_utc, ts, eph, observer):
    if dt_utc is None:
        return None
    if dt_utc.tzinfo is None:
        dt_utc = pytz.utc.localize(dt_utc)
    else:
        dt_utc = dt_utc.astimezone(pytz.utc)

    t = ts.from_datetime(dt_utc)
    sun_lon_trop = observer.at(t).observe(eph["sun"]).apparent().frame_latlon(ecliptic_frame)[1].degrees
    sun_lon_sid = tropical_to_sidereal(float(sun_lon_trop))
    rashi_index = int(sun_lon_sid // 30) % 12
    return rashi_names[rashi_index]

def calculate_amanta_purnimanta_month_fast(target_dt_local, paksha, tz_name, lat_r, lon_r):
    if target_dt_local.tzinfo is None:
        raise ValueError("target_dt_local must be timezone-aware")

    target_utc = target_dt_local.astimezone(pytz.utc)
    target_tt = TS.from_datetime(target_utc).tt

    y, m = target_dt_local.year, target_dt_local.month
    ph_cache = cached_moon_phases_for_month(y, m, tz_name)
    last_new = last_event_before(ph_cache["new_tt"], ph_cache["new_dt"], target_tt)

    if last_new is None:
        py, pm = _prev_month(y, m)
        ph_cache_prev = cached_moon_phases_for_month(py, pm, tz_name)
        last_new = last_event_before(ph_cache_prev["new_tt"], ph_cache_prev["new_dt"], target_tt)

    observer = cached_observer(lat_r, lon_r)

    if last_new:
        sun_rashi_new = sun_sidereal_rashi_at(last_new, TS, EPH, observer)
        amanta = SUN_RASHI_TO_LUNAR_MONTH.get(sun_rashi_new) or "Chaitra"
    else:
        amanta = "Chaitra"

    idx = months.index(amanta)
    purnimanta = months[(idx + 1) % 12] if paksha == "Krishna Paksha" else amanta
    return amanta, purnimanta

# ============================================================
# 12) find_discrete() CHANGE TIME (FIXED)
# ============================================================
def find_next_change_time(t0, t1, value_func, current_value, step_days=0.25):
    def f(t):
        # MUST return 1-D array when t is an array (our value_func is vectorized)
        return value_func(t)

    f.step_days = step_days

    times, values = find_discrete(t0, t1, f)

    cur = int(current_value)
    for tt, vv in zip(times, values):
        if _to_int_scalar(vv) != cur:
            return tt
    return None

def compute_angas_end_times(lat_r, lon_r, tz_name, date_ymd, now_local=None):
    tz = pytz.timezone(tz_name)

    sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)
    sunrise_local = sunrise_utc.astimezone(tz)

    y, m, d = map(int, date_ymd.split("-"))
    next_day_ymd = (datetime(y, m, d) + timedelta(days=1)).strftime("%Y-%m-%d")
    next_sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, next_day_ymd, tz_name)
    next_sunrise_local = next_sunrise_utc.astimezone(tz)

    if now_local is None:
        now_local = tz.localize(datetime(y, m, d, 12, 0, 0))
    else:
        now_local = now_local.astimezone(tz) if now_local.tzinfo else tz.localize(now_local)

    start_local = now_local if now_local >= sunrise_local else sunrise_local
    end_local = next_sunrise_local

    if start_local >= end_local:
        next2_ymd = (datetime(y, m, d) + timedelta(days=2)).strftime("%Y-%m-%d")
        next2_sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, next2_ymd, tz_name)
        end_local = next2_sunrise_utc.astimezone(tz)

    t_now = TS.from_datetime(start_local.astimezone(pytz.utc))
    t1 = TS.from_datetime(end_local.astimezone(pytz.utc))

    cur_tithi = _to_int_scalar(tithi_index_at(t_now))
    cur_nak = _to_int_scalar(nakshatra_index_at(t_now))
    cur_yoga = _to_int_scalar(yoga_index_at(t_now))
    cur_karana = _to_int_scalar(karana_index_at(t_now))

    tithi_end_t = find_next_change_time(t_now, t1, tithi_index_at, cur_tithi, step_days=0.125)
    nak_end_t   = find_next_change_time(t_now, t1, nakshatra_index_at, cur_nak, step_days=0.25)
    yoga_end_t  = find_next_change_time(t_now, t1, yoga_index_at, cur_yoga, step_days=0.25)
    kar_end_t   = find_next_change_time(t_now, t1, karana_index_at, cur_karana, step_days=0.125)

    def to_local(sf_time):
        if sf_time is None:
            return None
        return sf_time.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz)

    return {
        "tithi_end": to_local(tithi_end_t),
        "nakshatra_end": to_local(nak_end_t),
        "yoga_end": to_local(yoga_end_t),
        "karana_end": to_local(kar_end_t),
    }

@lru_cache(maxsize=600)
def compute_month_anga_end_times_batch(year, month, tz_name):
    """4 find_discrete calls over the full month instead of 30×4=120. ~10-15× speedup."""
    tz = pytz.timezone(tz_name)
    next_m = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    num_days = (next_m - datetime(year, month, 1)).days

    t0 = TS.from_datetime(
        tz.localize(datetime(year, month, 1, 0, 0)).astimezone(pytz.utc) - timedelta(hours=12)
    )
    t1 = TS.from_datetime(
        tz.localize(datetime(year, month, num_days, 23, 59)).astimezone(pytz.utc) + timedelta(days=3)
    )

    def _mf(func, step):
        f = lambda t: func(t)
        f.step_days = step
        return f

    t_tt, t_vv = find_discrete(t0, t1, _mf(tithi_index_at,     0.125))
    n_tt, n_vv = find_discrete(t0, t1, _mf(nakshatra_index_at, 0.25))
    y_tt, y_vv = find_discrete(t0, t1, _mf(yoga_index_at,      0.25))
    k_tt, k_vv = find_discrete(t0, t1, _mf(karana_index_at,    0.125))

    def _events(tt_arr, vv_arr, tz_):
        jds = [tt.tt for tt in tt_arr]
        dts = [tt.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz_) for tt in tt_arr]
        vals = [_to_int_scalar(vv) for vv in vv_arr]
        return jds, dts, vals

    t_jds, t_dts, t_vals = _events(t_tt, t_vv, tz)
    n_jds, n_dts, n_vals = _events(n_tt, n_vv, tz)
    y_jds, y_dts, y_vals = _events(y_tt, y_vv, tz)
    k_jds, k_dts, k_vals = _events(k_tt, k_vv, tz)

    def _next_after(jds, dts, vals, noon_jd, cur):
        cur = int(cur)
        for jd, dt, v in zip(jds, dts, vals):
            if jd > noon_jd and v != cur:
                return dt
        return None

    result = {}
    for day in range(1, num_days + 1):
        noon = TS.from_datetime(tz.localize(datetime(year, month, day, 12, 0)).astimezone(pytz.utc))
        nj = noon.tt
        result[datetime(year, month, day).strftime("%Y-%m-%d")] = {
            "tithi_end":     _next_after(t_jds, t_dts, t_vals, nj, _to_int_scalar(tithi_index_at(noon))),
            "nakshatra_end": _next_after(n_jds, n_dts, n_vals, nj, _to_int_scalar(nakshatra_index_at(noon))),
            "yoga_end":      _next_after(y_jds, y_dts, y_vals, nj, _to_int_scalar(yoga_index_at(noon))),
            "karana_end":    _next_after(k_jds, k_dts, k_vals, nj, _to_int_scalar(karana_index_at(noon))),
        }
    return result
