"""Generic, dependency-light utilities: coordinate rounding, numpy scalar
coercion, date/time helpers, response/scan caches, deterministic text pickers,
and muhurta description builders. No project imports beyond stdlib/numpy/pytz.
"""
from datetime import datetime, timedelta
import hashlib
import json
import threading
import numpy as np
import pytz

__all__ = [
    '_BIRTH_DETAIL_KEYS',
    '_RESPONSE_CACHE',
    '_RESPONSE_CACHE_LOCK',
    '_RESPONSE_CACHE_MAX',
    '_SCAN_CACHE',
    '_SCAN_CACHE_LOCK',
    '_SCAN_CACHE_MAX',
    '_as_np',
    '_desc_abhijit',
    '_desc_amrit_kaal',
    '_desc_brahma',
    '_desc_durmuhurta',
    '_desc_gulika',
    '_desc_rahu',
    '_desc_varjyam',
    '_desc_yamaganda',
    '_event_key',
    '_fmt_date',
    '_humanize_span',
    '_local_day_bounds_utc',
    '_next_day_ymd',
    '_next_month',
    '_ordinal',
    '_pretty_date',
    '_prev_month',
    '_request_has_birth_details',
    '_response_cache_get',
    '_response_cache_key',
    '_response_cache_put',
    '_scan_cache_get_or_compute',
    '_stable_pick',
    '_to_int_scalar',
    'format_dt_local',
    'format_time_with_date_if_needed',
    'round_coord',
]



# ------------------------------------------------------------
# Full-response cache (non-personalized requests only)
# ------------------------------------------------------------
# /panchanga-date and /monthly-panchanga compute at a fixed noon anchor, so for a
# given (raw request params, UTC day) the response is fully deterministic — when
# no birth details are supplied (no per-person kundali fetch). We cache the final
# response dict keyed on the exact request body + UTC day, so identical repeat
# requests skip the Skyfield compute entirely and return byte-identical JSON. The
# UTC-day component expires entries daily (matching the per-day mantra data).
_RESPONSE_CACHE = {}
_RESPONSE_CACHE_LOCK = threading.Lock()
_RESPONSE_CACHE_MAX = 512

_BIRTH_DETAIL_KEYS = ("date_of_birth", "time_of_birth", "birth_latitude", "birth_longitude")


def _request_has_birth_details(data):
    return any((data or {}).get(k) not in (None, "") for k in _BIRTH_DETAIL_KEYS)


def _response_cache_key(endpoint, data):
    """Stable key from the endpoint + exact request body + current UTC day."""
    return (
        endpoint,
        json.dumps(data, sort_keys=True, default=str),
        datetime.now(pytz.utc).strftime("%Y-%m-%d"),
    )


def _response_cache_get(key):
    with _RESPONSE_CACHE_LOCK:
        return _RESPONSE_CACHE.get(key)


def _response_cache_put(key, value):
    with _RESPONSE_CACHE_LOCK:
        if len(_RESPONSE_CACHE) >= _RESPONSE_CACHE_MAX:
            _RESPONSE_CACHE.clear()
        _RESPONSE_CACHE[key] = value


# ------------------------------------------------------------
# Scan cache (date-deterministic 7-day look-aheads)
# ------------------------------------------------------------
# get_upcoming_spiritual_events / get_upcoming_poojas scan future days using a
# noon anchor per date, so their result depends only on (location, from_date,
# window, month_system, UTC day) — NOT on the current instant. This lets the
# *live* /astrology endpoint reuse the heavy 7-day scan across same-day requests
# for a location, even though /astrology itself is not response-cached. Output is
# unchanged; the UTC-day component refreshes daily (matching the per-day mantra
# data embedded by calculate_panchanga_for_date).
_SCAN_CACHE = {}
_SCAN_CACHE_LOCK = threading.Lock()
_SCAN_CACHE_MAX = 4096


def _scan_cache_get_or_compute(key, compute):
    with _SCAN_CACHE_LOCK:
        cached = _SCAN_CACHE.get(key)
    if cached is not None:
        return cached
    value = compute()
    with _SCAN_CACHE_LOCK:
        if len(_SCAN_CACHE) >= _SCAN_CACHE_MAX:
            _SCAN_CACHE.clear()
        _SCAN_CACHE[key] = value
    return value


# ============================================================
# 4) PERFORMANCE CACHES / HELPERS
# ============================================================
def round_coord(x: float, places: int = 4) -> float:
    return round(x, places)

def _local_day_bounds_utc(tz, anchor_local):
    local_date = anchor_local.date()
    start_local = tz.localize(datetime(local_date.year, local_date.month, local_date.day, 0, 0, 0))
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(pytz.utc), end_local.astimezone(pytz.utc)

def _next_day_ymd(date_ymd: str) -> str:
    y, m, d = map(int, date_ymd.split("-"))
    return (datetime(y, m, d) + timedelta(days=1)).strftime("%Y-%m-%d")

# ============================================================
# 5) CORE MATH (SIDEREAL + ANGAS) — VECTORIZE for find_discrete()
# ============================================================
def _as_np(x):
    return np.asarray(x)

def _to_int_scalar(x):
    return int(np.atleast_1d(x)[0])

def _desc_brahma(start_str, end_str):
    return (
        f"Brahma Muhurta today runs from {start_str} to {end_str}. "
        "This is the most sacred period of the day, occurring approximately 1 hour 30 minutes before sunrise. "
        "The mind is naturally calm, the environment is pure, and spiritual energy is at its peak — making it "
        "ideal for meditation, mantra chanting, sadhana, and self-reflection. Even a short practice at this "
        "hour carries greater potency than longer efforts made later in the day."
    )


def _desc_abhijit(start_str, end_str):
    return (
        f"Abhijit Muhurta today runs from {start_str} to {end_str}. "
        "This is the most powerful auspicious window of the daytime, falling around solar noon "
        "(the 8th of 15 daytime muhurtas). Ancient texts say it can override the negativity of "
        "other inauspicious periods. Ruled by Lord Vishnu, this is the ideal time to start important "
        "new work, sign agreements, begin journeys, or undertake anything of significance."
    )


def _desc_rahu(start_str, end_str, day_name):
    return (
        f"Rahu Kaal today runs from {start_str} to {end_str}. "
        f"On {day_name}, it falls in this window — the timing shifts each day. "
        "This period is ruled by Rahu, the shadow planet of illusion and sudden change. "
        "New ventures, important decisions, signings, and auspicious ceremonies are best avoided. "
        "Routine tasks may continue, and the period can be used for Rahu-related spiritual remedies."
    )


def _desc_gulika(start_str, end_str, day_name):
    return (
        f"Gulika Kaal today runs from {start_str} to {end_str}. "
        f"On {day_name}, Gulika (Mandi) — a sub-planet of Saturn — rules this window. "
        "It is considered malefic for starting activities related to wealth, relationships, and health. "
        "Business deals, investments, and important ceremonies are best postponed. The period is suitable "
        "for Saturn worship, completing existing tasks, and acts of service."
    )


def _desc_yamaganda(start_str, end_str, day_name):
    return (
        f"Yamaganda Kaal today runs from {start_str} to {end_str}. "
        f"On {day_name}, this inauspicious period falls in this slot. "
        "Associated with Yama, the lord of death and karma, it is traditionally avoided for new starts, "
        "travel, auspicious ceremonies, and important decisions. Use this window to complete pending "
        "tasks, reflect, or perform ancestor-related prayers rather than begin anything new."
    )


def _desc_amrit_kaal(windows, nakshatra_name):
    if windows:
        slots = " and ".join(f"{w[0]} – {w[1]}" for w in windows[:2])
        return (
            f"Amrit Kaal today occurs at {slots}, arising from the {nakshatra_name} nakshatra transit. "
            "'Amrit' means nectar — anything begun in this window carries heightened positive energy. "
            "It is ideal for starting new work, performing puja, beginning journeys, or taking medicine. "
            "Even short prayers or intentions set during Amrit Kaal give elevated results."
        )
    return (
        f"No Amrit Kaal window falls during today's active hours under {nakshatra_name} nakshatra. "
        "This is rare — focus on Abhijit Muhurta or other auspicious Choghadiya slots for important starts."
    )


def _desc_durmuhurta(windows, day_name):
    if not windows:
        return (
            f"No Durmuhurta today — {day_name} (Guruvar) is ruled by Jupiter and is entirely free of "
            "this inauspicious period, making it especially favorable for new starts and auspicious activities."
        )
    slots = " and ".join(f"{w[0]} – {w[1]}" for w in windows)
    return (
        f"Durmuhurta today falls between {slots}. "
        "These windows are ruled by malefic energies believed to create obstacles for new ventures, "
        "ceremonies, or major decisions. Routine work and protective spiritual practices are acceptable, "
        "but new starts, purchases, travel, and auspicious events should be postponed until the period passes."
    )


def _desc_varjyam(start_str, end_str, nakshatra_name):
    return (
        f"Varjyam today falls between {start_str} and {end_str}, based on the {nakshatra_name} nakshatra transit. "
        "'Varjyam' means 'to be avoided' — puja installations, surgeries, new starts, and major decisions "
        "are traditionally deferred during this window. Its timing shifts with each nakshatra. "
        "Existing tasks and routine work remain unaffected."
    )

# ============================================================
# 10) FORMATTING
# ============================================================
def format_time_with_date_if_needed(dt_local, base_date_ymd):
    if dt_local is None:
        return "N/A"
    base_date = datetime.strptime(base_date_ymd, "%Y-%m-%d").date()
    if dt_local.date() != base_date:
        return dt_local.strftime("%I:%M:%S %p, %b %d")
    return dt_local.strftime("%I:%M:%S %p")

def format_dt_local(dt_local):
    if dt_local is None:
        return "N/A"
    return dt_local.strftime("%I:%M %p, %b %d")

def _prev_month(year: int, month: int):
    return (year - 1, 12) if month == 1 else (year, month - 1)

def _next_month(year: int, month: int):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _stable_pick(options, seed_key):
    if not options:
        return ""
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _event_key(name):
    """Stable slug for a festival/event name → join key for app content
    (blog URL, recommended mukhi). e.g. 'Guru Purnima' -> 'guru_purnima'."""
    out = []
    for ch in str(name).lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "/"):
            out.append("_")
        # other punctuation (parentheses, etc.) is dropped
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _humanize_span(a, b):
    """Human 'X months Y days' between two date objects (a <= b)."""
    import calendar
    if b < a:
        a, b = b, a
    months = (b.year - a.year) * 12 + (b.month - a.month)
    days = b.day - a.day
    if days < 0:
        months -= 1
        pm = b.month - 1 or 12
        py = b.year if b.month > 1 else b.year - 1
        days += calendar.monthrange(py, pm)[1]
    parts = []
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days or not parts:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return " and ".join(parts)


def _pretty_date(iso_str):
    d = datetime.strptime(iso_str, "%Y-%m-%d").date()
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _fmt_date(dt):
    return dt.strftime("%Y-%m-%d") if dt else None
