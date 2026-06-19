from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import pytz
from functools import lru_cache
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
import threading
import copy
import hashlib
import json
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

app = Flask(__name__)

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

def _lahiri_ayanamsa(jd: float) -> float:
    """Lahiri (Chitrapaksha) ayanamsa in degrees for a given Julian Date."""
    T = (jd - 2451545.0) / 36525.0   # Julian centuries from J2000.0
    return 23.8531 + T * 1.3966       # 1.3966°/century ≈ 50.28″/year

AYANAMSA = _lahiri_ayanamsa(2451545.0 + 9610.0)  # approximate current-era fallback
KUNDALI_REPORT_URL = "https://recommendation.nepalirudraksha.com/api/astro/report/"
KUNDALI_TIMEOUT_SECONDS = 12

# ============================================================
# 2) NAMES / LISTS
# ============================================================
tithi_names = [
    "प्रथमा", "द्वितीया", "तृतीया", "चतुर्थी", "पञ्चमी", "षष्ठी",
    "सप्तमी", "अष्टमी", "नवमी", "दशमी", "एकादशी", "द्वादशी",
    "त्रयोदशी", "चतुर्दशी", "पूर्णिमा",
    "प्रथमा", "द्वितीया", "तृतीया", "चतुर्थी", "पञ्चमी", "षष्ठी",
    "सप्तमी", "अष्टमी", "नवमी", "दशमी", "एकादशी", "द्वादशी",
    "त्रयोदशी", "चतुर्दशी", "अमावस्या"
]

nakshatras = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra",
    "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
    "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

yoga_names = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shoola", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha",
    "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"
]

ritu_names = [
    "Vasanta (Spring)", "Grishma (Summer)", "Varsha (Monsoon)",
    "Sharad (Autumn)", "Hemanta (Pre-Winter)", "Shishira (Winter)"
]

months = [
    "Ashwin", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna",
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada"
]

rashi_names = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

RASHI_PROFILE = {
    "Aries": {"sanskrit": "Mesha", "lord": "Mangal (Mars)", "element": "Fire sign"},
    "Taurus": {"sanskrit": "Vrishabha", "lord": "Shukra (Venus)", "element": "Earth sign"},
    "Gemini": {"sanskrit": "Mithuna", "lord": "Budh (Mercury)", "element": "Air sign"},
    "Cancer": {"sanskrit": "Karka", "lord": "Chandra (Moon)", "element": "Water sign"},
    "Leo": {"sanskrit": "Simha", "lord": "Surya (Sun)", "element": "Fire sign"},
    "Virgo": {"sanskrit": "Kanya", "lord": "Budh (Mercury)", "element": "Earth sign"},
    "Libra": {"sanskrit": "Tula", "lord": "Shukra (Venus)", "element": "Air sign"},
    "Scorpio": {"sanskrit": "Vrishchika", "lord": "Mangal (Mars)", "element": "Water sign"},
    "Sagittarius": {"sanskrit": "Dhanu", "lord": "Guru (Jupiter)", "element": "Fire sign"},
    "Capricorn": {"sanskrit": "Makara", "lord": "Shani (Saturn)", "element": "Earth sign"},
    "Aquarius": {"sanskrit": "Kumbha", "lord": "Shani (Saturn)", "element": "Air sign"},
    "Pisces": {"sanskrit": "Meena", "lord": "Guru (Jupiter)", "element": "Water sign"},
}

SUN_RASHI_TO_LUNAR_MONTH = {
    "Pisces": "Chaitra",
    "Aries": "Vaishakha",
    "Taurus": "Jyeshtha",
    "Gemini": "Ashadha",
    "Cancer": "Shravana",
    "Leo": "Bhadrapada",
    "Virgo": "Ashwin",
    "Libra": "Kartika",
    "Scorpio": "Margashirsha",
    "Sagittarius": "Pausha",
    "Capricorn": "Magha",
    "Aquarius": "Phalguna",
}

# ============================================================
# 2) FESTIVAL / VRATA / MESSAGES
# ============================================================
festival_mapping = {
    # --------------------
    # Solar / Fixed-date (Gregorian)
    # --------------------
    "Lohri": {"fixed_date": "January 13", "region": "Punjab, Haryana, Himachal"},
    "Makar Sankranti": {"fixed_date": "January 14"},
    "Pongal": {"fixed_date": "January 15", "region": "Tamil Nadu"},
    "Magh Bihu": {"fixed_date": "January 15", "region": "Assam"},
    "Republic Day (India)": {"fixed_date": "January 26"},
    "International Yoga Day": {"fixed_date": "June 21"},
    "Independence Day (India)": {"fixed_date": "August 15"},
    "Gandhi Jayanti": {"fixed_date": "October 2"},
    "Christmas": {"fixed_date": "December 25"},

    # --------------------
    # Magha
    # --------------------
    "Vasant Panchami": {"tithi": "पञ्चमी", "month": "Magha", "paksha": "Shukla Paksha"},
    "Ratha Saptami": {"tithi": "सप्तमी", "month": "Magha", "paksha": "Shukla Paksha"},
    "Jaya Ekadashi": {"tithi": "एकादशी", "month": "Magha", "paksha": "Shukla Paksha"},
    "Pradosh Vrat (Magha Shukla)": {"tithi": "त्रयोदशी", "month": "Magha", "paksha": "Shukla Paksha"},
    "Magha Purnima": {"tithi": "पूर्णिमा", "month": "Magha", "paksha": "Shukla Paksha"},
    "Mauni Amavasya": {"tithi": "अमावस्या", "month": "Magha", "paksha": "Krishna Paksha"},
    "Shattila Ekadashi": {"tithi": "एकादशी", "month": "Magha", "paksha": "Krishna Paksha"},

    # --------------------
    # Phalguna
    # --------------------
    "Maha Shivaratri": {"tithi": "चतुर्दशी", "month": "Phalguna", "paksha": "Krishna Paksha"},
    "Holika Dahan": {"tithi": "पूर्णिमा", "month": "Phalguna", "paksha": "Shukla Paksha", "note": "Night event"},
    "Holi": {"tithi": "पूर्णिमा", "month": "Phalguna", "paksha": "Shukla Paksha"},
    "Phalguna Amavasya": {"tithi": "अमावस्या", "month": "Phalguna", "paksha": "Krishna Paksha"},
    "Rang Panchami": {"tithi": "पञ्चमी", "month": "Phalguna", "paksha": "Krishna Paksha", "note": "Observed in some regions after Holi"},

    # --------------------
    # Chaitra
    # --------------------
    "Chaitra Navratri Begins": {"tithi": "प्रतिपदा", "month": "Chaitra", "paksha": "Shukla Paksha"},
    "Gudi Padwa": {"tithi": "प्रतिपदा", "month": "Chaitra", "paksha": "Shukla Paksha", "region": "Maharashtra"},
    "Ugadi": {"tithi": "प्रतिपदा", "month": "Chaitra", "paksha": "Shukla Paksha", "region": "Andhra Pradesh, Karnataka, Telangana"},
    "Cheti Chand": {"tithi": "द्वितीया", "month": "Chaitra", "paksha": "Shukla Paksha", "region": "Sindhi"},
    "Gangaur (Starts)": {"tithi": "तृतीया", "month": "Chaitra", "paksha": "Shukla Paksha", "region": "Rajasthan"},
    "Rama Navami": {"tithi": "नवमी", "month": "Chaitra", "paksha": "Shukla Paksha"},
    "Chaitra Purnima": {"tithi": "पूर्णिमा", "month": "Chaitra", "paksha": "Shukla Paksha"},
    "Hanuman Jayanti": {"tithi": "पूर्णिमा", "month": "Chaitra", "paksha": "Shukla Paksha"},
    "Chaitra Amavasya": {"tithi": "अमावस्या", "month": "Chaitra", "paksha": "Krishna Paksha"},

    # --------------------
    # Vaishakha
    # --------------------
    "Akshaya Tritiya": {"tithi": "तृतीया", "month": "Vaishakha", "paksha": "Shukla Paksha"},
    "Parashurama Jayanti": {"tithi": "तृतीया", "month": "Vaishakha", "paksha": "Shukla Paksha"},
    "Varuthini Ekadashi": {"tithi": "एकादशी", "month": "Vaishakha", "paksha": "Krishna Paksha"},
    "Narasimha Jayanti": {"tithi": "चतुर्दशी", "month": "Vaishakha", "paksha": "Shukla Paksha"},
    "Buddha Purnima (Vesak)": {"tithi": "पूर्णिमा", "month": "Vaishakha", "paksha": "Shukla Paksha"},
    "Vaishakha Amavasya": {"tithi": "अमावस्या", "month": "Vaishakha", "paksha": "Krishna Paksha"},
    "Sita Navami": {"tithi": "नवमी", "month": "Vaishakha", "paksha": "Shukla Paksha"},

    # --------------------
    # Jyeshtha
    # --------------------
    "Ganga Dussehra": {"tithi": "दशमी", "month": "Jyeshtha", "paksha": "Shukla Paksha"},
    "Nirjala Ekadashi": {"tithi": "एकादशी", "month": "Jyeshtha", "paksha": "Shukla Paksha"},
    "Vat Savitri Vrat": {"tithi": "अमावस्या", "month": "Jyeshtha", "paksha": "Krishna Paksha"},
    "Shani Jayanti": {"tithi": "अमावस्या", "month": "Jyeshtha", "paksha": "Krishna Paksha"},
    "Jyeshtha Purnima": {"tithi": "पूर्णिमा", "month": "Jyeshtha", "paksha": "Shukla Paksha"},

    # --------------------
    # Ashadha
    # --------------------
    "Devshayani Ekadashi (Ashadhi Ekadashi)": {"tithi": "एकादशी", "month": "Ashadha", "paksha": "Shukla Paksha"},
    "Jagannath Rath Yatra": {"tithi": "द्वितीया", "month": "Ashadha", "paksha": "Shukla Paksha", "region": "Odisha"},
    "Guru Purnima": {"tithi": "पूर्णिमा", "month": "Ashadha", "paksha": "Shukla Paksha"},
    "Ashadha Amavasya": {"tithi": "अमावस्या", "month": "Ashadha", "paksha": "Krishna Paksha"},

    # --------------------
    # Shravana
    # --------------------
    "Nag Panchami": {"tithi": "पञ्चमी", "month": "Shravana", "paksha": "Shukla Paksha"},
    "Shravana Putrada Ekadashi": {"tithi": "एकादशी", "month": "Shravana", "paksha": "Shukla Paksha"},
    "Varalakshmi Vratam": {"weekday_rule": "Friday before Shravana Purnima", "month": "Shravana", "region": "South India"},
    "Raksha Bandhan": {"tithi": "पूर्णिमा", "month": "Shravana", "paksha": "Shukla Paksha"},
    "Shravana Somvar Vrat (Mondays)": {"weekday": "Monday", "month": "Shravana", "note": "Occurs on all Mondays in Shravana"},
    "Hariyali Teej": {"tithi": "तृतीया", "month": "Shravana", "paksha": "Shukla Paksha", "region": "North India"},
    "Shravana Amavasya": {"tithi": "अमावस्या", "month": "Shravana", "paksha": "Krishna Paksha"},

    # --------------------
    # Bhadrapada
    # --------------------
    "Hartalika Teej": {"tithi": "तृतीया", "month": "Bhadrapada", "paksha": "Shukla Paksha"},
    "Ganesh Chaturthi": {"tithi": "चतुर्थी", "month": "Bhadrapada", "paksha": "Shukla Paksha"},
    "Rishi Panchami": {"tithi": "पञ्चमी", "month": "Bhadrapada", "paksha": "Shukla Paksha"},
    "Radha Ashtami": {"tithi": "अष्टमी", "month": "Bhadrapada", "paksha": "Shukla Paksha"},
    "Parsva Ekadashi": {"tithi": "एकादशी", "month": "Bhadrapada", "paksha": "Shukla Paksha"},
    "Anant Chaturdashi": {"tithi": "चतुर्दशी", "month": "Bhadrapada", "paksha": "Shukla Paksha"},
    "Krishna Janmashtami": {"tithi": "अष्टमी", "month": "Bhadrapada", "paksha": "Krishna Paksha"},
    "Aja Ekadashi": {"tithi": "एकादशी", "month": "Bhadrapada", "paksha": "Krishna Paksha"},
    "Bhadrapada Amavasya": {"tithi": "अमावस्या", "month": "Bhadrapada", "paksha": "Krishna Paksha"},
    "Onam (Thiruvonam – Nakshatra-based)": {
        "nakshatra": "Shravana", "month": "Bhadrapada", "region": "Kerala",
        "note": "Nakshatra-based; do not rely only on tithi"
    },

    # --------------------
    # Ashwin
    # --------------------
    "Mahalaya Amavasya": {"tithi": "अमावस्या", "month": "Ashwin", "paksha": "Krishna Paksha"},
    "Navratri Begins": {"tithi": "प्रतिपदा", "month": "Ashwin", "paksha": "Shukla Paksha"},
    "Durga Saptami": {"tithi": "सप्तमी", "month": "Ashwin", "paksha": "Shukla Paksha"},
    "Durga Ashtami": {"tithi": "अष्टमी", "month": "Ashwin", "paksha": "Shukla Paksha"},
    "Mahanavami": {"tithi": "नवमी", "month": "Ashwin", "paksha": "Shukla Paksha"},
    "Dussehra (Vijayadashami)": {"tithi": "दशमी", "month": "Ashwin", "paksha": "Shukla Paksha"},
    "Sharad Purnima (Kojagrat Brata)": {"tithi": "पूर्णिमा", "month": "Ashwin", "paksha": "Shukla Paksha"},

    # Nepal Dashain
    "Dashain (Ghatasthapana)": {"tithi": "प्रतिपदा", "month": "Ashwin", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Dashain (Fulpati)": {"tithi": "सप्तमी", "month": "Ashwin", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Dashain (Maha Ashtami)": {"tithi": "अष्टमी", "month": "Ashwin", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Dashain (Maha Navami)": {"tithi": "नवमी", "month": "Ashwin", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Dashain (Vijaya Dashami / Tika)": {"tithi": "दशमी", "month": "Ashwin", "paksha": "Shukla Paksha", "region": "Nepal"},

    # --------------------
    # Kartika
    # --------------------
    "Karwa Chauth": {"tithi": "चतुर्थी", "month": "Kartika", "paksha": "Krishna Paksha"},
    "Ahoi Ashtami": {"tithi": "अष्टमी", "month": "Kartika", "paksha": "Krishna Paksha"},
    "Dhanteras": {"tithi": "त्रयोदशी", "month": "Kartika", "paksha": "Krishna Paksha"},
    "Naraka Chaturdashi": {"tithi": "चतुर्दशी", "month": "Kartika", "paksha": "Krishna Paksha"},
    "Diwali (Lakshmi Puja)": {"tithi": "अमावस्या", "month": "Kartika", "paksha": "Krishna Paksha"},
    "Govardhan Puja / Annakut": {"tithi": "प्रतिपदा", "month": "Kartika", "paksha": "Shukla Paksha"},
    "Bhai Dooj": {"tithi": "द्वितीया", "month": "Kartika", "paksha": "Shukla Paksha"},
    "Chhath Puja": {"tithi": "षष्ठी", "month": "Kartika", "paksha": "Shukla Paksha", "region": "Bihar, UP, Nepal Terai"},
    "Devuthani Ekadashi (Tulsi Vivah)": {"tithi": "एकादशी", "month": "Kartika", "paksha": "Shukla Paksha"},
    "Tulsi Vivah": {"tithi": "एकादशी", "month": "Kartika", "paksha": "Shukla Paksha"},
    "Kartika Purnima": {"tithi": "पूर्णिमा", "month": "Kartika", "paksha": "Shukla Paksha"},
    "Dev Deepawali": {"tithi": "पूर्णिमा", "month": "Kartika", "paksha": "Shukla Paksha", "note": "Often celebrated at Varanasi"},

    # Nepal: Tihar
    "Tihar (Kag Tihar)": {"tithi": "त्रयोदशी", "month": "Kartika", "paksha": "Krishna Paksha", "region": "Nepal"},
    "Tihar (Kukur Tihar)": {"tithi": "चतुर्दशी", "month": "Kartika", "paksha": "Krishna Paksha", "region": "Nepal"},
    "Tihar (Lakshmi Puja)": {"tithi": "अमावस्या", "month": "Kartika", "paksha": "Krishna Paksha", "region": "Nepal"},
    "Tihar (Gai Tihar / Govardhan Puja)": {"tithi": "प्रतिपदा", "month": "Kartika", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Tihar (Bhai Tika)": {"tithi": "द्वितीया", "month": "Kartika", "paksha": "Shukla Paksha", "region": "Nepal"},

    # --------------------
    # Margashirsha
    # --------------------
    "Gita Jayanti / Mokshada Ekadashi": {"tithi": "एकादशी", "month": "Margashirsha", "paksha": "Shukla Paksha"},
    "Vivah Panchami": {"tithi": "पञ्चमी", "month": "Margashirsha", "paksha": "Shukla Paksha"},
    "Dattatreya Jayanti": {"tithi": "पूर्णिमा", "month": "Margashirsha", "paksha": "Shukla Paksha"},
    "Margashirsha Amavasya": {"tithi": "अमावस्या", "month": "Margashirsha", "paksha": "Krishna Paksha"},

    # --------------------
    # Pausha
    # --------------------
    "Paush Putrada Ekadashi": {"tithi": "एकादशी", "month": "Pausha", "paksha": "Shukla Paksha"},
    "Makar Sankranti (Solar) Reminder": {"fixed_date": "January 14", "note": "Same as Makar Sankranti"},
    "Shakambhari Navratri Begins": {"tithi": "अष्टमी", "month": "Pausha", "paksha": "Shukla Paksha", "note": "Regional/Tradition-based"},
    "Pausha Purnima": {"tithi": "पूर्णिमा", "month": "Pausha", "paksha": "Shukla Paksha"},
    "Pausha Amavasya": {"tithi": "अमावस्या", "month": "Pausha", "paksha": "Krishna Paksha"},
}

vrata_mapping = {
    # ---- Core monthly vrats ----
    "Ekadashi (Monthly)": {
        "tithi": "एकादशी", "paksha": "Both",
        "deity": "Lord Vishnu", "significance": "Fasting for spiritual growth and Vishnu worship"
    },
    "Pradosh Vrat (Monthly)": {
        "tithi": "त्रयोदशी", "paksha": "Both",
        "deity": "Lord Shiva", "significance": "Fasting for happiness, prosperity, and well-being"
    },
    "Sankashti Chaturthi (Monthly)": {
        "tithi": "चतुर्थी", "paksha": "Krishna Paksha",
        "deity": "Lord Ganesha", "significance": "Removing obstacles and gaining wisdom"
    },
    "Vinayaka Chaturthi (Monthly)": {
        "tithi": "चतुर्थी", "paksha": "Shukla Paksha",
        "deity": "Lord Ganesha", "significance": "Wisdom, prosperity, and success"
    },
    "Purnima Vrat (Monthly)": {
        "tithi": "पूर्णिमा", "paksha": "Shukla Paksha",
        "deity": "Vishnu / Lakshmi", "significance": "Health, prosperity, and auspiciousness"
    },
    "Amavasya Vrat (Monthly)": {
        "tithi": "अमावस्या", "paksha": "Krishna Paksha",
        "deity": "Pitru Devatas", "significance": "Peace of ancestors and tarpan"
    },
    "Masik Shivaratri (Monthly)": {
        "tithi": "चतुर्दशी", "paksha": "Krishna Paksha",
        "deity": "Lord Shiva", "significance": "Monthly Shivaratri observance"
    },
    "Kalashtami (Monthly)": {
        "tithi": "अष्टमी", "paksha": "Krishna Paksha",
        "deity": "Lord Bhairava", "significance": "Protection and fearlessness"
    },

    # ---- Weekday vrats ----
    "Somvar Vrat": {
        "day_of_week": "Monday",
        "deity": "Lord Shiva", "significance": "For devotion, calmness and wish-fulfillment"
    },
    "Mangalvar Vrat": {
        "day_of_week": "Tuesday",
        "deity": "Hanuman / Durga", "significance": "Courage, protection, and strength"
    },
    "Budhvar Vrat": {
        "day_of_week": "Wednesday",
        "deity": "Ganesha / Vishnu", "significance": "Wisdom, learning, and clarity"
    },
    "Guruvar Vrat": {
        "day_of_week": "Thursday",
        "deity": "Brihaspati (Jupiter)", "significance": "Prosperity, education and spiritual progress"
    },
    "Shukravar Vrat": {
        "day_of_week": "Friday",
        "deity": "Goddess Lakshmi", "significance": "Wealth, harmony and blessings"
    },
    "Shanivar Vrat": {
        "day_of_week": "Saturday",
        "deity": "Lord Shani", "significance": "Relief from obstacles and Shani dosha"
    },
    "Ravivar Vrat": {
        "day_of_week": "Sunday",
        "deity": "Surya (Sun)", "significance": "Vitality, confidence and health"
    },

    # ---- Special named ekadashis ----
    "Vaikunta Ekadashi": {
        "tithi": "एकादशी", "month": "Margashirsha", "paksha": "Shukla Paksha",
        "deity": "Lord Vishnu", "significance": "Vaikuntha-dwara opening; highly auspicious"
    },
    "Nirjala Ekadashi": {
        "tithi": "एकादशी", "month": "Jyeshtha", "paksha": "Shukla Paksha",
        "deity": "Lord Vishnu", "significance": "Strict fast; purification and blessings"
    },
    "Devshayani Ekadashi": {
        "tithi": "एकादशी", "month": "Ashadha", "paksha": "Shukla Paksha",
        "deity": "Lord Vishnu", "significance": "Start of Chaturmas"
    },
    "Devuthani Ekadashi": {
        "tithi": "एकादशी", "month": "Kartika", "paksha": "Shukla Paksha",
        "deity": "Lord Vishnu", "significance": "End of Chaturmas; Vishnu awakens"
    },
    "Jaya Ekadashi": {
        "tithi": "एकादशी", "month": "Magha", "paksha": "Shukla Paksha",
        "deity": "Lord Vishnu", "significance": "Purification and victory over negativity"
    },
    "Mokshada Ekadashi": {
        "tithi": "एकादशी", "month": "Margashirsha", "paksha": "Shukla Paksha",
        "deity": "Lord Vishnu", "significance": "Liberation-focused ekadashi"
    },

    # ---- Month-specific vrats ----
    "Karwa Chauth": {
        "tithi": "चतुर्थी", "month": "Kartika", "paksha": "Krishna Paksha",
        "deity": "Shiva-Parvati", "significance": "For husband’s long life (tradition)"
    },
    "Ahoi Ashtami": {
        "tithi": "अष्टमी", "month": "Kartika", "paksha": "Krishna Paksha",
        "deity": "Goddess Ahoi", "significance": "Well-being of children"
    },
    "Rishi Panchami Vrat": {
        "tithi": "पञ्चमी", "month": "Bhadrapada", "paksha": "Shukla Paksha",
        "deity": "Saptarishi", "significance": "Purification and penance"
    },
    "Vat Savitri Vrat": {
        "tithi": "अमावस्या", "month": "Jyeshtha", "paksha": "Krishna Paksha",
        "deity": "Savitri", "significance": "For spouse well-being (tradition)"
    },
}

messages = {
    # Paksha messages
    "Shukla Paksha": "Today is a time for growth and new beginnings. You may find opportunities to start new projects, cultivate positive habits, and embrace new possibilities.",
    "Krishna Paksha": "This is a period for reflection, introspection, and release. Let go of what no longer serves you, slow down, and focus inward to renew your energy.",

    # Nakshatra messages
    "Ashwini": "Ashwini Nakshatra brings vitality and healing. This is a great day to focus on your health, engage in physical activities, and embrace new ideas with enthusiasm.",
    "Bharani": "Bharani Nakshatra encourages resilience and patience. Use this energy to manage responsibilities and approach challenges with determination.",
    "Krittika": "Krittika Nakshatra fosters transformation. Let go of the old and embrace positive changes; it's a day to sharpen your skills and stay focused.",
    "Rohini": "Rohini brings abundance and beauty. It's a great day for creative pursuits and nurturing meaningful connections with loved ones.",
    "Mrigashira": "The inquisitive nature of Mrigashira encourages exploration. Seek out new knowledge and keep an open mind to fresh perspectives.",
    "Ardra": "Ardra Nakshatra invites inner clarity and introspection. Embrace emotional healing and find strength through self-awareness.",
    "Punarvasu": "With Punarvasu’s energy, today is about renewal and optimism. Revisit old ideas with fresh enthusiasm and look for growth opportunities.",
    "Pushya": "Pushya Nakshatra fosters kindness and nurturing. Consider reaching out to loved ones, practicing compassion, and engaging in self-care.",
    "Ashlesha": "Ashlesha brings depth and insight. Use this energy for introspection, unraveling hidden thoughts, and understanding complex emotions.",
    "Magha": "Magha Nakshatra encourages honoring traditions. It’s a day for respecting your roots, reflecting on heritage, and embracing wisdom from the past.",
    "Purva Phalguni": "Purva Phalguni inspires creativity and joy. Enjoy leisure, spend time with friends, and let your playful side come forward.",
    "Uttara Phalguni": "Uttara Phalguni supports dedication and responsibility. Focus on organizing your life and building stable foundations.",
    "Hasta": "Hasta Nakshatra brings dexterity and precision. Pay attention to details today, and work on improving your skills.",
    "Chitra": "Chitra Nakshatra is associated with creativity. Let your artistic and innovative side shine today.",
    "Swati": "Swati encourages independence and flexibility. Take the time to pursue personal growth and adapt to changing situations.",
    "Vishakha": "Vishakha Nakshatra fosters determination and focus. Channel this energy into achieving long-term goals.",
    "Anuradha": "Anuradha encourages devotion and loyalty. Use this day to strengthen bonds and show appreciation to those around you.",
    "Jyeshtha": "Jyeshtha Nakshatra emphasizes strength and leadership. Stand confidently in your decisions and be a source of support for others.",
    "Mula": "Mula Nakshatra encourages you to explore deep truths. Seek knowledge and wisdom to understand complex situations.",
    "Purva Ashadha": "Purva Ashadha inspires confidence and ambition. Pursue your goals with vigor and believe in your potential.",
    "Uttara Ashadha": "Uttara Ashadha fosters determination. Today is ideal for taking responsibility and making steady progress.",
    "Shravana": "Shravana Nakshatra emphasizes learning and listening. Take time to gather information and practice humility.",
    "Dhanishta": "Dhanishta Nakshatra brings social energy. Engage in teamwork and share your talents with others.",
    "Shatabhisha": "Shatabhisha Nakshatra encourages introspection and healing. It’s a good day to focus on inner peace and well-being.",
    "Purva Bhadrapada": "Purva Bhadrapada fosters spiritual growth. Reflect on life’s deeper meaning and seek transformative insights.",
    "Uttara Bhadrapada": "Uttara Bhadrapada emphasizes patience and endurance. Work steadily and keep a calm mind.",
    "Revati": "Revati Nakshatra brings compassion and generosity. Engage in acts of kindness and support those in need.",

    # Moon sign messages
    "Aries": "With the Moon in Aries, it's a day for bold actions and new beginnings. Embrace your inner courage and take initiative.",
    "Taurus": "The Taurus Moon encourages stability and comfort. Focus on creating a peaceful environment and nurturing close relationships.",
    "Gemini": "With the Moon in Gemini, communication flows easily. It's a great time for socializing, learning, and sharing ideas.",
    "Cancer": "The Cancer Moon supports emotional depth and connection. Focus on family, home, and nurturing your inner self.",
    "Leo": "With the Moon in Leo, express your confidence and passion. This is a day to stand out and pursue what excites you.",
    "Virgo": "The Virgo Moon supports organizing and planning. Use this energy to create order in your life and focus on details.",
    "Libra": "With the Moon in Libra, harmony and balance take center stage. Spend time cultivating peaceful and fair relationships.",
    "Scorpio": "The Scorpio Moon brings intensity and transformation. Focus on understanding deeper emotions and renewing your inner strength.",
    "Sagittarius": "The Sagittarius Moon brings optimism and adventure. Explore new ideas, travel, or engage in learning experiences.",
    "Capricorn": "With the Moon in Capricorn, focus on your ambitions and responsibilities. Work steadily toward your long-term goals.",
    "Aquarius": "The Aquarius Moon encourages innovation and independence. Embrace unique ideas and connect with like-minded people.",
    "Pisces": "The Pisces Moon enhances intuition and compassion. Take time for self-reflection and explore your creative side.",

    # Yoga messages
    "Vishkambha": "Today brings strength and resilience. Overcome obstacles with courage and perseverance.",
    "Priti": "Priti Yoga promotes harmony and joy. Focus on building positive relationships and sharing happiness.",
    "Ayushman": "Ayushman Yoga brings health and vitality. Dedicate time to physical well-being and mental peace.",
    "Saubhagya": "Saubhagya Yoga brings luck and success. Trust your abilities and pursue your goals with confidence.",
    "Shobhana": "Shobhana Yoga enhances beauty and creativity. Engage in artistic activities and express your uniqueness.",
    "Atiganda": "Atiganda suggests caution. Avoid conflict and focus on maintaining inner peace.",
    "Sukarma": "Sukarma Yoga supports good deeds. Take time to help others and make positive contributions.",
    "Dhriti": "Dhriti brings patience and endurance. Take a calm approach to challenges and stay focused.",
    "Shoola": "Shoola suggests a day for introspection. Reflect on personal goals and identify areas for growth.",
    "Ganda": "Ganda promotes inner strength. Tackle difficult tasks with a resilient spirit.",
    "Vriddhi": "Vriddhi Yoga supports growth and prosperity. Focus on expanding your knowledge and skills.",
    "Dhruva": "Dhruva Yoga fosters stability. Use this time to establish a strong foundation for future goals.",
    "Vyaghata": "Vyaghata warns of potential obstacles. Move carefully and avoid unnecessary risks.",
    "Harshana": "Harshana brings joy and positivity. Surround yourself with uplifting people and experiences.",
    "Vajra": "Vajra suggests a day for spiritual insight. Engage in meditation or reflect on your deeper purpose.",
    "Siddhi": "Siddhi Yoga brings success and accomplishment. Trust your skills and work toward your goals.",
    "Vyatipata": "Vyatipata suggests caution. Avoid major decisions and be mindful of your surroundings.",
    "Variyana": "Variyana Yoga fosters clarity. It's a good day for introspection and setting clear intentions.",
    "Parigha": "Parigha indicates caution. Avoid conflicts and focus on peaceful activities.",
    "Shiva": "Shiva Yoga fosters transformation. Embrace change and seek personal growth.",
    "Siddha": "Siddha Yoga supports achievement. Work hard and trust that your efforts will yield results.",
    "Sadhya": "Sadhya encourages progress. Take steady steps toward your goals with determination.",
    "Shubha": "Shubha brings auspiciousness. It’s a favorable time for new endeavors and positive actions.",
    "Shukla": "Shukla enhances clarity. Use this time to make thoughtful decisions and express gratitude.",
    "Brahma": "Brahma Yoga supports wisdom and creativity. Engage in intellectual or artistic pursuits.",
    "Indra": "Indra brings authority. Step into a leadership role and pursue your goals boldly.",
    "Vaidhriti": "Vaidhriti suggests patience. Avoid impulsive actions and remain calm.",
}

# ============================================================
# 3) EXTENDED LOOKUP TABLES
# ============================================================

# Tithi nature cycles every 5: Nanda, Bhadra, Jaya, Rikta, Poorna
TITHI_NATURE_NAMES = ["Nanda", "Bhadra", "Jaya", "Rikta", "Poorna"]

# Nakshatra ruling planets (Vimshottari order)
NAKSHATRA_LORDS = [
    "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
    "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
    "Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
]

# Nakshatra presiding deities
NAKSHATRA_DEITIES = [
    "Ashwini Kumaras","Yama","Agni","Brahma","Soma","Rudra","Aditi","Brihaspati","Nagas",
    "Pitru","Bhaga","Aryaman","Savitar","Vishvakarma","Vayu","Indra-Agni","Mitra","Indra",
    "Nirrti","Apah","Vishvedevas","Vishnu","Ashta Vasus","Varuna",
    "Aja Ekapada","Ahir Budhnya","Pushan",
]

# Choghadiya — 7-name cycle
CHOGHADIYA_NAMES   = ["Udveg","Char","Labh","Amrit","Kaal","Shubh","Rog"]
CHOGHADIYA_QUALITY = {
    "Udveg":"Inauspicious","Char":"Neutral","Labh":"Auspicious",
    "Amrit":"Highly Auspicious","Kaal":"Inauspicious","Shubh":"Auspicious","Rog":"Inauspicious",
}
# Python weekday Mon=0, Sun=6
CHOGHADIYA_DAY_START   = {0:3, 1:6, 2:2, 3:5, 4:1, 5:4, 6:0}
CHOGHADIYA_NIGHT_START = {0:1, 1:4, 2:6, 3:0, 4:3, 5:2, 6:5}

# Durmuhurta: 0-indexed muhurta positions out of 15 daytime muhurtas
DURMUHURTA_INDEX = {
    0:[14], 1:[0,1], 2:[7], 3:[], 4:[9], 5:[7,8], 6:[6,7],
}

# Varjyam: (start_ghati, duration_ghati) out of 60 ghatis per nakshatra
# Indexed same as nakshatras list (0=Ashwini … 26=Revati)
VARJYAM_TABLE = [
    (13,4),(12,4),(21,4),(26,4),(18,4),(24,4),(22,4),(19,4),(12,4),
    ( 6,4),( 5,4),( 8,4),(11,4),(17,4),(17,4),(14,4),( 2,4),( 0,4),
    (13,4),( 4,4),( 9,4),(23,4),(19,4),(24,4),( 7,4),(12,4),(27,4),
]

# Choghadiya slot significance
CHOGHADIYA_SIGNIFICANCE = {
    "Amrit":  "Most auspicious. Begin important work, perform puja, start journeys, sign agreements, take medicine. Highly favorable for all activities.",
    "Shubh":  "Auspicious. Good for marriages, religious ceremonies, business dealings, and all positive ventures.",
    "Labh":   "Favorable for business, trade, financial transactions, and wealth-related activities. Good for starting new ventures.",
    "Char":   "Neutral — best for travel, movement, and short journeys. Routine work is fine; avoid major new starts.",
    "Udveg":  "Inauspicious. Avoid new beginnings, business decisions, and travel. Can be used cautiously for government-related tasks (Sun rules this).",
    "Kaal":   "Very inauspicious. Avoid all auspicious activities, new work, and travel. Refrain from important decisions.",
    "Rog":    "Inauspicious. Risk of illness, disputes, and setbacks. Avoid health-related procedures, new ventures, and important tasks.",
}

# Tithi nature guidance
TITHI_NATURE_SIGNIFICANCE = {
    "Nanda":  "Nanda (Joyful) — ideal for celebrations, new initiatives, social gatherings, and all auspicious beginnings.",
    "Bhadra": "Bhadra (Auspicious) — supports education, important ceremonies, constructive work, and stable undertakings.",
    "Jaya":   "Jaya (Victorious) — lends strength to bold action, competition, and overcoming challenges.",
    "Rikta":  "Rikta (Hollow) — avoid major new starts. Best used for completing existing work, routine tasks, and introspection.",
    "Poorna": "Poorna (Complete) — abundant energy for fulfilling goals, completing projects, giving thanks, and festive celebration.",
}

# Nakshatra pada significance
NAKSHATRA_PADA_DESC = [
    "First pada — initiating energy; favorable for new starts and fresh intentions.",
    "Second pada — stabilizing energy; good for building, consolidating, and steady progress.",
    "Third pada — expanding energy; supports communication, relationships, and creative expression.",
    "Fourth pada — deepening energy; favorable for spiritual practice, rest, and transitions.",
]

# Planetary transit significance
PLANET_GOVERNS = {
    "Sun":     "soul, authority, vitality, career, and government matters",
    "Moon":    "mind, emotions, health, relationships, and daily life",
    "Mars":    "energy, courage, conflict, property, and physical drive",
    "Mercury": "communication, intellect, commerce, and learning",
    "Jupiter": "wisdom, expansion, wealth, spirituality, and children",
    "Venus":   "love, beauty, luxury, artistic pursuits, and relationships",
    "Saturn":  "discipline, karma, longevity, challenges, and long-term outcomes",
    "Rahu":    "ambition, materialism, foreign connections, and worldly desires",
    "Ketu":    "spirituality, liberation, detachment, and past-life karma",
}
RASHI_NATURE_BRIEF = {
    "Aries":"initiating and bold","Taurus":"stable and material","Gemini":"communicative and adaptable",
    "Cancer":"nurturing and emotional","Leo":"confident and expressive","Virgo":"analytical and service-oriented",
    "Libra":"harmonious and diplomatic","Scorpio":"intense and transformative",
    "Sagittarius":"expansive and philosophical","Capricorn":"disciplined and ambitious",
    "Aquarius":"innovative and independent","Pisces":"intuitive and spiritual",
}

# Yoga auspiciousness
YOGA_AUSPICIOUS = {
    "Vishkambha":False,"Priti":True,"Ayushman":True,"Saubhagya":True,
    "Shobhana":True,"Atiganda":False,"Sukarma":True,"Dhriti":True,
    "Shoola":False,"Ganda":False,"Vriddhi":True,"Dhruva":True,
    "Vyaghata":False,"Harshana":True,"Vajra":True,"Siddhi":True,
    "Vyatipata":False,"Variyana":True,"Parigha":False,"Shiva":True,
    "Siddha":True,"Sadhya":True,"Shubha":True,"Shukla":True,
    "Brahma":True,"Indra":True,"Vaidhriti":False,
}

# Maps Navagraha planet names to deity names as returned by the mantra API
PLANET_TO_DEITY_NAME = {
    "Sun":     "Surya",
    "Moon":    "Chandra",
    "Mars":    "Skanda (Kartikeya)",
    "Mercury": "Vishnu (Budha)",
    "Jupiter": "Brihaspati (Guru)",
    "Venus":   "Shukracharya",
    "Saturn":  "Shani",
    "Rahu":    "Bhairava (Rahu)",
    "Ketu":    "Ganesha (Ketu)",
}

WEEKDAY_PLANET = {
    "Sunday":    "Sun",
    "Monday":    "Moon",
    "Tuesday":   "Mars",
    "Wednesday": "Mercury",
    "Thursday":  "Jupiter",
    "Friday":    "Venus",
    "Saturday":  "Saturn",
}

MANTRA_API_URL = "https://nepa-app-uat.nepalirudraksha.com/api/v2/mantra/deities/with-mantras"

# ============================================================
# 3.5) MANTRA FETCH & RECOMMENDATION
# ============================================================
@lru_cache(maxsize=7)
def _fetch_mantra_data_cached(_date_str: str):
    """Fetch mantra/deity data from the mantras API, cached once per calendar day.
    Raises on failure so lru_cache does not store the error result."""
    resp = HTTP_SESSION.get(MANTRA_API_URL, headers={"Accept": "application/json"}, timeout=10)
    resp.raise_for_status()  # match urllib: non-2xx raises (so the error isn't cached)
    return json.loads(resp.content.decode("utf-8")).get("data") or []


def get_mantra_data():
    """Return mantra data, silently returning [] if the API is unreachable."""
    try:
        return _fetch_mantra_data_cached(datetime.now(pytz.utc).strftime("%Y-%m-%d"))
    except Exception:
        return []


def get_recommended_mantras(day_of_week, nakshatra_name, tithi_number, paksha,
                             yoga_name, festivals, mantra_data):
    """Return 3–4 mantras recommended based on today's panchanga.

    Priority order:
    1. Day ruling planet  (always included)
    2. Nakshatra lord     (if distinct from the day lord)
    3. Tithi / festival   (Chaturthi→Ganesha, Ekadashi→Vishnu, Pradosh→Bhairava …)
    4. Protective fill    (inauspicious yoga→Ganesha; else Jupiter for universal wisdom;
                           final fill by paksha if still under 3)
    """
    deity_map = {d["name"]: d for d in (mantra_data or [])}

    selected = []   # list of (priority, mantra_dict)
    seen_deity = set()

    def _add(deity_name, reason, priority):
        if not deity_name or deity_name in seen_deity or deity_name not in deity_map:
            return
        deity = deity_map[deity_name]
        if not deity.get("mantras"):
            return
        m = deity["mantras"][0]
        selected.append((priority, {
            "mantra_id":     m["id"],
            "title":         m["title"],
            "deity":         deity_name,
            "deity_id":      deity["id"],
            "reason":        reason,
            "mantra_details": m.get("mantra_details", ""),
            "description":   m.get("description", ""),
        }))
        seen_deity.add(deity_name)

    # 1. Day ruling planet
    day_planet = WEEKDAY_PLANET.get(day_of_week, "")
    if day_planet:
        _add(PLANET_TO_DEITY_NAME.get(day_planet, ""),
             f"Ruling planet of {day_of_week}", 0)

    # 2. Nakshatra lord
    if nakshatra_name in nakshatras:
        nak_lord = NAKSHATRA_LORDS[nakshatras.index(nakshatra_name)]
        _add(PLANET_TO_DEITY_NAME.get(nak_lord, ""),
             f"Lord of {nakshatra_name} nakshatra", 1)

    # 3. Tithi / festival context
    ctx_deity = ctx_reason = None
    if tithi_number in (4, 19):
        ctx_deity, ctx_reason = "Ganesha (Ketu)", "Chaturthi — auspicious for Ganesha worship"
    elif tithi_number in (11, 26):
        ctx_deity, ctx_reason = "Vishnu (Budha)", "Ekadashi — sacred to Lord Vishnu"
    elif tithi_number == 15:
        ctx_deity, ctx_reason = "Chandra", "Purnima — full moon blessings"
    elif tithi_number == 30:
        ctx_deity, ctx_reason = "Ganesha (Ketu)", "Amavasya — ancestor peace and Ketu"
    elif tithi_number in (13, 28):
        ctx_deity, ctx_reason = "Bhairava (Rahu)", "Pradosh Trayodashi — Bhairava / Shiva worship"
    elif tithi_number in (8, 23):
        ctx_deity, ctx_reason = "Bhairava (Rahu)", "Ashtami — auspicious for Bhairava worship"
    else:
        for f in (festivals or []):
            fl = f.lower()
            if any(k in fl for k in ("ganesh", "chaturthi", "vinayaka")):
                ctx_deity, ctx_reason = "Ganesha (Ketu)", f"Festival: {f}"; break
            if any(k in fl for k in ("krishna", "janmashtami", "ekadashi", "vishnu", "rama navami")):
                ctx_deity, ctx_reason = "Vishnu (Budha)", f"Festival: {f}"; break
            if any(k in fl for k in ("shivaratri", "pradosh")):
                ctx_deity, ctx_reason = "Bhairava (Rahu)", f"Festival: {f}"; break
            if any(k in fl for k in ("sankranti", "pongal", "ratha saptami")):
                ctx_deity, ctx_reason = "Surya", f"Festival: {f}"; break
            if "guru purnima" in fl:
                ctx_deity, ctx_reason = "Brihaspati (Guru)", f"Festival: {f}"; break

    if ctx_deity:
        _add(ctx_deity, ctx_reason, 2)

    # 4a. Inauspicious yoga → Ganesha for protection
    if len(selected) < 3 and not YOGA_AUSPICIOUS.get(yoga_name, True):
        _add("Ganesha (Ketu)", f"{yoga_name} Yoga — seek Ganesha's protection", 3)

    # 4b. Jupiter fills universally — brings wisdom and auspiciousness
    if len(selected) < 3:
        _add("Brihaspati (Guru)", "Universal: wisdom and auspiciousness (Jupiter)", 4)

    # 4c. Paksha-appropriate final fill
    if len(selected) < 3:
        fill = "Vishnu (Budha)" if paksha == "Shukla Paksha" else "Shani"
        _add(fill, f"Supportive mantra for {paksha}", 5)

    selected.sort(key=lambda x: x[0])
    return [s[1] for s in selected[:4]]


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

def _next_day_ymd(date_ymd: str) -> str:
    y, m, d = map(int, date_ymd.split("-"))
    return (datetime(y, m, d) + timedelta(days=1)).strftime("%Y-%m-%d")

@lru_cache(maxsize=50000)
def cached_sunrise_sunset(lat_r: float, lon_r: float, date_ymd: str, tz_name: str):
    tz = pytz.timezone(tz_name)
    y, m, d = map(int, date_ymd.split("-"))
    anchor_local = tz.localize(datetime(y, m, d, 12, 0, 0))
    location = cached_location(lat_r, lon_r)
    sunrise, sunset = get_sunrise_sunset(TS, EPH, location, tz, anchor_local)
    return sunrise.astimezone(pytz.utc), sunset.astimezone(pytz.utc)

@lru_cache(maxsize=50000)
def cached_moonrise_moonset(lat_r: float, lon_r: float, date_ymd: str, tz_name: str):
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
    return mr_utc, ms_utc

# ============================================================
# 5) CORE MATH (SIDEREAL + ANGAS) — VECTORIZE for find_discrete()
# ============================================================
def _as_np(x):
    return np.asarray(x)

def _to_int_scalar(x):
    return int(np.atleast_1d(x)[0])

def tropical_to_sidereal_arr(tropical_deg, jd=None):
    ayanamsa = _lahiri_ayanamsa(jd) if jd is not None else AYANAMSA
    return (_as_np(tropical_deg) - ayanamsa) % 360.0

def tropical_to_sidereal(tropical_deg_scalar, jd=None):
    ayanamsa = _lahiri_ayanamsa(jd) if jd is not None else AYANAMSA
    return float((tropical_deg_scalar - ayanamsa) % 360.0)

# --- Anga widths
TITHI_DEG = 12.0
NAK_DEG = 360.0 / 27.0
YOGA_DEG = 360.0 / 27.0
KARANA_DEG = 6.0

def get_sidereal_lons_geocentric(t):
    earth = geocentric_observer()
    sun = EPH["sun"]
    moon = EPH["moon"]
    jd = float(np.atleast_1d(t.tt)[0])

    sun_lon_trop = earth.at(t).observe(sun).apparent().frame_latlon(ecliptic_frame)[1].degrees
    moon_lon_trop = earth.at(t).observe(moon).apparent().frame_latlon(ecliptic_frame)[1].degrees

    sun_sid = tropical_to_sidereal_arr(sun_lon_trop, jd)
    moon_sid = tropical_to_sidereal_arr(moon_lon_trop, jd)
    return sun_sid, moon_sid

def sun_moon_angle_at(t):
    sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
    return (moon_sid - sun_sid) % 360.0

def tithi_index_at(t):
    angle = sun_moon_angle_at(t)
    return (np.floor(angle / TITHI_DEG).astype(int) + 1)  # 1..30

def nakshatra_index_at(t):
    _, moon_sid = get_sidereal_lons_geocentric(t)
    return (np.floor(moon_sid / NAK_DEG).astype(int) % 27)  # 0..26

def yoga_index_at(t):
    sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
    yoga_val = (sun_sid + moon_sid) % 360.0
    return (np.floor(yoga_val / YOGA_DEG).astype(int) % 27)  # 0..26

def karana_index_at(t):
    angle = sun_moon_angle_at(t)
    k = (np.floor(angle / KARANA_DEG).astype(int) + 1)  # 1..60
    return ((k - 1) % 60) + 1

# ============================================================
# 6) KARANA NAME MAP
# ============================================================
KARANA_REPEATING = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]

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

def normalize_tithi_names(tithi_name: str) -> set:
    s = {tithi_name}
    if tithi_name == "प्रथमा":
        s.add("प्रतिपदा")
    if tithi_name == "प्रतिपदा":
        s.add("प्रथमा")
    return s

def paksha_allows(details_paksha, today_paksha):
    return details_paksha in ("Both", "All") or details_paksha == today_paksha

def check_fixed_festivals(current_date_naive: datetime):
    found = []
    for festival, details in festival_mapping.items():
        if "fixed_date" not in details:
            continue
        festival_date = datetime.strptime(details["fixed_date"], "%B %d")
        if current_date_naive.month == festival_date.month and current_date_naive.day == festival_date.day:
            found.append(festival)
    return found

def get_festivals_for_day(
    tithi_name,
    paksha,
    amanta_month,
    purnimanta_month,
    region=None,
    month_system="both",
):
    possible_tithis = normalize_tithi_names(tithi_name)
    month_system = (month_system or "both").strip().lower()
    out = []
    for festival, details in festival_mapping.items():
        if "fixed_date" in details:
            continue
        if "tithi" not in details or "month" not in details or "paksha" not in details:
            continue
        if details["tithi"] in possible_tithis and details["paksha"] == paksha:
            if month_system == "amanta":
                month_match = details["month"] == amanta_month
            elif month_system == "purnimanta":
                month_match = details["month"] == purnimanta_month
            else:
                month_match = details["month"] in (purnimanta_month, amanta_month)
            if month_match:
                out.append(festival)
    return out

def get_vratas_for_day(tithi_name, paksha, day_of_week, nakshatra_name=None):
    possible_tithis = normalize_tithi_names(tithi_name)
    found = []
    for vrata, details in vrata_mapping.items():
        if "tithi" in details:
            if details["tithi"] in possible_tithis and paksha_allows(details.get("paksha", "Both"), paksha):
                found.append(vrata)
        if "day_of_week" in details:
            if details["day_of_week"] == day_of_week:
                found.append(vrata)
    # de-dupe
    out, seen = [], set()
    for x in found:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def _p(name, pid, vid, reason):
    details = POOJA_DETAILS.get(pid, {})
    return {
        "name": name,
        "id": pid,
        "variant_id": vid,
        "reason": reason,
        "deity": details.get("deity", ""),
        "about": details.get("about", ""),
        "ritual_sequence": details.get("ritual_sequence", []),
    }


POOJA_DETAILS = {
    "7468622348530": {  # Maha Shivaratri Pooja at Pashupatinath
        "deity": "Lord Shiva",
        "about": "A sacred all-night vigil puja performed at Pashupatinath Temple on Maha Shivaratri, one of the most auspicious nights of the year. Lord Shiva is worshipped in his Pashupati form with Rudrabhishek, bilva archana, and Shiva stotrams chanted through four praharas (night watches).",
        "ritual_sequence": [
            "Sankalpa (declaration of intent) before sunset",
            "First prahara: Rudrabhishek with water, milk, and honey",
            "Second prahara: Bilva patra archana and Shiva Sahasranama",
            "Third prahara: Bel leaf offering and oil deepam lighting",
            "Fourth prahara: Final abhishek and Maha Aarti at dawn",
            "Break fast after sunrise darshan",
        ],
    },
    "9035889672434": {  # Masik Shivaratri Pooja at Pashupatinath
        "deity": "Lord Shiva",
        "about": "Monthly Shivaratri (Masik Shivaratri) puja observed on Krishna Paksha Chaturdashi each month at Pashupatinath. A smaller yet significant Shiva worship for regular devotees seeking blessings for health, peace, and removal of obstacles.",
        "ritual_sequence": [
            "Evening bath and clean white or grey clothes",
            "Light deepam with sesame oil or ghee",
            "Offer bilva (bel) leaves in sets of three with Om Namah Shivaya",
            "Perform Rudrabhishek or simple milk abhishek",
            "Chant Shiva Panchakshara stotram 108 times",
            "Night vigil or at least stay awake until midnight",
        ],
    },
    "7465529606386": {  # Karya Siddhi Ganesh Pooja
        "deity": "Lord Ganesha",
        "about": "Dedicated to Lord Ganesha, the remover of obstacles, this puja is performed on Chaturthi tithis for success in new endeavors, clearing blockages, and obtaining Ganesha's blessings before starting any important work or journey.",
        "ritual_sequence": [
            "Place Ganesha idol or image facing east",
            "Offer red flowers, durva grass, and modak (sweet dumpling)",
            "Light 5 lamps with ghee and incense",
            "Recite Ganesh Atharvashirsha or Ganesh Stotram",
            "Take sankalpa for your specific intent or obstacle",
            "Offer coconut and distribute prasad",
        ],
    },
    "8820054950130": {  # Lakshmi Kuber Pooja
        "deity": "Goddess Lakshmi & Lord Kubera",
        "about": "A prosperity puja combining worship of Goddess Lakshmi (abundance, wealth) and Lord Kubera (treasury, material success). Performed on auspicious tithis like Purnima, Dhanteras, and Trayodashi to attract financial stability and remove wealth blockages.",
        "ritual_sequence": [
            "Clean altar and place Lakshmi and Kubera yantras or idols",
            "Offer yellow flowers, turmeric, and sandalwood paste",
            "Light ghee deepam and incense",
            "Chant Lakshmi Ashtakam and Kubera Dhana Mantra",
            "Offer coins and sweets as prasad",
            "Conclude with aarti and seek blessings for abundance",
        ],
    },
    "7465532653810": {  # Rudra Abishek Pooja
        "deity": "Lord Shiva",
        "about": "Rudrabhishek is a powerful Shiva puja where the Shivalinga is bathed with Panchamrita (milk, curd, ghee, honey, sugar) and sacred substances while Shri Rudram is chanted. It is especially performed on Krishna Pradosh for removing planetary afflictions and bringing peace.",
        "ritual_sequence": [
            "Purify the Shivalinga with clean water",
            "Abhishek with milk while chanting Namakam (Shri Rudram)",
            "Abhishek with curd while chanting Chamakam",
            "Abhishek with ghee, honey, and sugar sequentially",
            "Apply vibhuti (sacred ash) and bilva leaves",
            "Perform Shiva aarti and pradakshina",
        ],
    },
    "7465524363506": {  # Laxmi Narayan Pooja
        "deity": "Lord Vishnu & Goddess Lakshmi",
        "about": "A joint worship of Lord Vishnu and Goddess Lakshmi performed on Ekadashi, Purnima, and Trayodashi. It invokes divine grace for prosperity, domestic harmony, and spiritual merit. Especially significant on Ekadashi for Vishnu bhaktas.",
        "ritual_sequence": [
            "Fast or eat only sattvic food from the previous day",
            "Decorate altar with yellow/golden flowers and tulsi",
            "Offer tulsi leaves, lotus flowers, and panchamrita",
            "Chant Vishnu Sahasranama or Lakshmi Ashtottaram",
            "Read Ekadashi Mahatmya if observing Ekadashi",
            "Perform aarti and distribute prasad after sunset",
        ],
    },
    "8817900945650": {  # Shri Durga Saptshati Chandi Path
        "deity": "Goddess Durga",
        "about": "Chandi Path (Durga Saptashati) is a 700-verse recitation from Markandeya Purana glorifying Goddess Durga's victories over evil. It is recited during Navaratri and Navami for protection, victory over adversaries, and divine feminine grace.",
        "ritual_sequence": [
            "Take morning bath and wear clean red or white clothes",
            "Light deepam and incense before Durga image",
            "Recite Kavach, Argala, and Keelakam before the path",
            "Chant all 13 chapters of Durga Saptashati sequentially",
            "Offer red flowers and fruits",
            "Conclude with Aarti and Devi Mahatmya concluding shloka",
        ],
    },
    "8955542700274": {  # Kaal Bhairav and Shakti Maha Puja
        "deity": "Lord Kaal Bhairav & Shakti",
        "about": "A tantric puja to Lord Kaal Bhairav (fierce form of Shiva) and Shakti performed on Krishna Ashtami. It is believed to protect from enemies, negative energies, and fear, and to strengthen the mind against obstacles and delays.",
        "ritual_sequence": [
            "Perform puja in the evening or night hours",
            "Offer black sesame seeds, black flowers, and red hibiscus",
            "Light mustard oil lamp",
            "Chant Bhairav Ashtakam or Bhairav Kavach",
            "Offer alcohol or dark sweets as naivedyam per tradition",
            "Take protection sankalpa and seek removal of fear and obstacles",
        ],
    },
    "7465527705842": {  # Navagraha Shanti Pooja with Hawan
        "deity": "Navagraha (The Nine Planets)",
        "about": "Navagraha Shanti is a comprehensive puja and hawan (fire ritual) performed to pacify and balance the energies of all nine planets — Surya, Chandra, Mangal, Budh, Guru, Shukra, Shani, Rahu, and Ketu. It is especially recommended on birthdays and during challenging planetary periods (dashas) or doshas, to harmonize planetary influences, remove obstacles, and invite health, prosperity, and peace for the year ahead.",
        "ritual_sequence": [
            "Sankalpa (declaration of intent) for planetary peace and well-being",
            "Invocation (avahana) of all nine Grahas with their bija mantras",
            "Navagraha homa (hawan) with the prescribed samidha and dravya for each planet",
            "Recitation of the Navagraha Stotram and individual graha mantras",
            "Offering of nine grains, cloths, and colours associated with each planet",
            "Purnahuti (final offering) and aarti seeking the blessings of all Grahas",
            "Distribution of prasad and tying of a protective thread",
        ],
    },
}

def get_poojas_for_day(tithi_number, paksha, amanta_month, day_of_week, festival_list):
    poojas = []
    festival_set = set(festival_list)
    is_shukla  = paksha == "Shukla Paksha"
    is_krishna = paksha == "Krishna Paksha"

    # 1. Maha Shivaratri — Phalguna Krishna Chaturdashi
    is_maha_shiv = tithi_number == 29 and is_krishna and amanta_month in ("Phalguna", "Adhik Phalguna")
    if is_maha_shiv:
        poojas.append(_p("Maha Shivaratri Pooja at Pashupatinath",
                         "7468622348530", "42124272730354", "Maha Shivaratri (Phalguna Krishna Chaturdashi)"))

    # 2. Masik Shivaratri — Krishna Chaturdashi every other month
    if tithi_number == 29 and is_krishna and not is_maha_shiv:
        poojas.append(_p("Masik Shivaratri Pooja at Pashupatinath",
                         "9035889672434", "49098993008882", "Masik Shivaratri (Krishna Chaturdashi)"))

    # 3. Karya Siddhi Ganesh — Shukla Chaturthi OR Mangal Chaturthi (Tuesday + any Chaturthi)
    if tithi_number == 4 and is_shukla:
        reason = ("Mangal Chaturthi (Tuesday + Shukla Chaturthi)" if day_of_week == "Tuesday"
                  else "Shukla Paksha Chaturthi")
        poojas.append(_p("Karya Siddhi Ganesh Pooja", "7465529606386", "42114181464306", reason))
    elif tithi_number == 19 and day_of_week == "Tuesday":
        poojas.append(_p("Karya Siddhi Ganesh Pooja", "7465529606386", "42114181464306",
                         "Mangal Chaturthi (Tuesday + Krishna Chaturthi)"))

    # 4. Lakshmi Kuber — specific tithis + key festivals
    _LK_FEST = {"Dhanteras":"Dhanteras","Diwali (Lakshmi Puja)":"Diwali",
                "Tihar (Lakshmi Puja)":"Tihar Lakshmi Puja","Akshaya Tritiya":"Akshaya Tritiya"}
    lk_reason = None
    if tithi_number == 15:
        lk_reason = "Purnima"
    elif tithi_number == 30:
        lk_reason = "Amavasya (Aausi)"
    elif tithi_number == 13 and is_shukla:
        lk_reason = "Shukla Trayodashi"
    elif tithi_number == 28 and is_krishna:
        lk_reason = "Krishna Trayodashi"
    elif tithi_number == 5 and is_shukla:
        lk_reason = "Shukla Panchami"
    elif tithi_number == 20 and is_krishna:
        lk_reason = "Krishna Panchami"
    else:
        for f, label in _LK_FEST.items():
            if f in festival_set:
                lk_reason = label
                break
    if lk_reason:
        poojas.append(_p("Lakshmi Kuber Pooja", "8820054950130", "47901573153010", lk_reason))

    # 5. Rudra Abishek — Krishna Pradosh (Krishna Trayodashi, tithi 28)
    if tithi_number == 28 and is_krishna:
        poojas.append(_p("Rudra Abishek Pooja", "7465532653810", "42114187985138",
                         "Krishna Pradosh (Krishna Paksha Trayodashi)"))

    # 6. Laxmi Narayan — Shukla Ekadashi, Purnima, Shukla Trayodashi
    ln_reason = None
    if tithi_number == 11 and is_shukla:
        ln_reason = "Shukla Paksha Ekadashi"
    elif tithi_number == 13 and is_shukla:
        ln_reason = "Shukla Paksha Trayodashi"
    elif tithi_number == 15:
        ln_reason = "Purnima"
    if ln_reason:
        poojas.append(_p("Laxmi Narayan Pooja", "7465524363506", "42114162000114", ln_reason))

    # 7. Shri Durga Saptshati — Navaratri days OR Navami (any paksha)
    is_navaratri = amanta_month in ("Chaitra", "Ashwin") and is_shukla and 1 <= tithi_number <= 9
    if is_navaratri:
        poojas.append(_p("Shri Durga Saptshati Chandi Path", "8817900945650", "47892681785586",
                         f"Navaratri ({amanta_month} Shukla)"))
    elif tithi_number in (9, 24):
        poojas.append(_p("Shri Durga Saptshati Chandi Path", "8817900945650", "47892681785586",
                         f"Navami ({paksha})"))

    # 8. Kaal Bhairav and Shakti Maha Puja — Krishna Ashtami
    if tithi_number == 23 and is_krishna:
        poojas.append(_p("Kaal Bhairav and Shakti Maha Puja", "8955542700274", "48729126895858",
                         "Krishna Paksha Ashtami"))

    return poojas if poojas else [{"name": "None", "id": None, "variant_id": None, "reason": None}]


# ============================================================
# KUNDLI-BASED POOJA RECOMMENDATIONS
# Driven by the birth chart (dasha lords + doshas) and the birthday,
# independent of the calendar-based poojas in get_poojas_for_day().
# ============================================================

# TODO: replace the Navagraha variant id below with the real Shopify variant id
# (only the product id 7465527705842 was provided).
_NAVAGRAHA_VARIANT_ID = "42114175566066"

# pooja_key -> (display name, product_id, variant_id) — reuses the existing catalog.
_KUNDALI_POOJA_CATALOG = {
    "laxmi_narayan":       ("Laxmi Narayan Pooja",                "7465524363506", "42114162000114"),
    "rudra_abishek":       ("Rudra Abishek Pooja",                "7465532653810", "42114187985138"),
    "kaal_bhairav":        ("Kaal Bhairav and Shakti Maha Puja",  "8955542700274", "48729126895858"),
    "lakshmi_kuber":       ("Lakshmi Kuber Pooja",                "8820054950130", "47901573153010"),
    "karya_siddhi_ganesh": ("Karya Siddhi Ganesh Pooja",          "7465529606386", "42114181464306"),
    "navagraha_shanti":    ("Navagraha Shanti Pooja with Hawan",  "7465527705842", "42114175566066"),
}

# Natal/transit planet (canonical English) -> remedial pooja from the catalog.
PLANET_TO_POOJA = {
    "Sun":     "laxmi_narayan",
    "Moon":    "rudra_abishek",
    "Mars":    "kaal_bhairav",
    "Mercury": "laxmi_narayan",
    "Jupiter": "laxmi_narayan",
    "Venus":   "lakshmi_kuber",
    "Saturn":  "rudra_abishek",
    "Rahu":    "kaal_bhairav",
    "Ketu":    "karya_siddhi_ganesh",
}

# Sanskrit/English planet name variants -> canonical English name.
_PLANET_ALIASES = {
    "sun": "Sun", "surya": "Sun", "ravi": "Sun",
    "moon": "Moon", "chandra": "Moon", "soma": "Moon",
    "mars": "Mars", "mangal": "Mars", "mangala": "Mars", "kuja": "Mars", "angaraka": "Mars",
    "mercury": "Mercury", "budh": "Mercury", "budha": "Mercury",
    "jupiter": "Jupiter", "guru": "Jupiter", "brihaspati": "Jupiter", "brhaspati": "Jupiter",
    "venus": "Venus", "shukra": "Venus", "sukra": "Venus",
    "saturn": "Saturn", "shani": "Saturn", "sani": "Saturn",
    "rahu": "Rahu",
    "ketu": "Ketu",
}


def _normalize_planet(name):
    if not name:
        return None
    key = str(name).strip().lower()
    if key in _PLANET_ALIASES:
        return _PLANET_ALIASES[key]
    for alias, canon in _PLANET_ALIASES.items():
        if alias in key:
            return canon
    return None


def _is_birthday(dob_str, today_str):
    """True if today (YYYY-MM-DD) matches the birth month/day. Feb-29 births fall on
    Feb 29 in leap years, else Mar 1."""
    if not dob_str or not today_str:
        return False
    try:
        dob = datetime.strptime(str(dob_str)[:10], "%Y-%m-%d").date()
        today = datetime.strptime(str(today_str)[:10], "%Y-%m-%d").date()
    except Exception:
        return False
    if dob.month == 2 and dob.day == 29:
        if today.month == 2 and today.day == 29:
            return True
        import calendar
        return today.month == 3 and today.day == 1 and not calendar.isleap(today.year)
    return dob.month == today.month and dob.day == today.day


def _truthy_dosha(value):
    """Best-effort: does this value indicate a dosha is PRESENT? (schema unknown)."""
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in ("", "no", "false", "none", "absent", "not present", "nil", "0")
    if isinstance(value, dict):
        for flag in ("present", "is_present", "has_dosha", "exists", "applicable", "status"):
            if flag in value:
                return _truthy_dosha(value.get(flag))
        return bool(value)
    if isinstance(value, list):
        return any(_truthy_dosha(v) for v in value)
    return bool(value)


def _is_negated(text):
    """True if a free-text dosha label is phrased as absent (e.g. 'No Manglik')."""
    t = " " + str(text).strip().lower() + " "
    return any(tok in t for tok in (" no ", " not ", " none ", " absent", " nil ", " n/a ", " false ", " without "))


def _detect_doshas(kundali_result):
    """Best-effort dosha detection against an unknown report schema.
    Returns list of (label, pooja_key). Safe (returns []) if nothing matches."""
    if not isinstance(kundali_result, dict):
        return []
    found, seen = [], set()

    def record(label, pooja_key):
        if label not in seen:
            seen.add(label)
            found.append((label, pooja_key))

    # 1) explicit named flag keys
    key_rules = [
        (("manglik", "is_manglik", "mangal_dosha", "mangal_dosh", "kuja_dosha", "angarak_dosha"),
         "Manglik (Mangal) dosha", "kaal_bhairav"),
        (("sade_sati", "shani_sade_sati", "sadhe_sati", "shani_dosha", "saturn_dosha"),
         "Shani Sade Sati / Shani dosha", "rudra_abishek"),
        (("kaal_sarp_dosha", "kaalsarp", "kaal_sarp", "kal_sarp", "kala_sarpa_dosha"),
         "Kaal Sarp dosha", "navagraha_shanti"),
    ]
    for keys, label, pooja_key in key_rules:
        for k in keys:
            if k in kundali_result and _truthy_dosha(kundali_result.get(k)):
                record(label, pooja_key)
                break

    # 2) a general "doshas" collection (list or dict) scanned by name
    name_rules = [
        (("manglik", "mangal", "kuja", "angarak"), "Manglik (Mangal) dosha", "kaal_bhairav"),
        (("sade sati", "sadhe sati", "sade-sati", "shani", "saturn"), "Shani Sade Sati / Shani dosha", "rudra_abishek"),
        (("kaal sarp", "kaalsarp", "kal sarp", "kaal sarpa", "kala sarpa"), "Kaal Sarp dosha", "navagraha_shanti"),
    ]
    container = kundali_result.get("doshas")
    items = []
    if isinstance(container, list):
        items = container
    elif isinstance(container, dict):
        items = [name for name, val in container.items() if _truthy_dosha(val)]
    for it in items:
        if isinstance(it, str):
            text = it
        elif isinstance(it, dict):
            if any(f in it for f in ("present", "is_present", "has_dosha", "exists", "applicable", "status")) \
                    and not _truthy_dosha(it):
                continue
            text = " ".join(str(it.get(k, "")) for k in ("name", "type", "dosha", "title"))
        else:
            continue
        if _is_negated(text):
            continue
        tl = text.lower()
        for subs, label, pooja_key in name_rules:
            if any(s in tl for s in subs):
                record(label, pooja_key)
    return found


def get_kundali_pooja_recommendations(kundali_result, birth_details, day_data):
    """Recommend poojas from the birth chart (dasha lords + doshas) and the birthday.
    Independent of the calendar-based upcoming_poojas. Returns a self-describing dict."""
    recs = {}  # product_id -> entry

    def add(pooja_key, reason, priority):
        name, pid, vid = _KUNDALI_POOJA_CATALOG[pooja_key]
        if pid in recs:
            if reason not in recs[pid]["_reasons"]:
                recs[pid]["_reasons"].append(reason)
            recs[pid]["_priority"] = min(recs[pid]["_priority"], priority)
            return
        entry = _p(name, pid, vid, reason)
        entry["_reasons"] = [reason]
        entry["_priority"] = priority
        recs[pid] = entry

    birth_details = birth_details or {}
    dob = str(birth_details.get("date_of_birth") or "").strip()
    today = str((day_data or {}).get("date") or "").strip()
    is_birthday = _is_birthday(dob, today)

    if is_birthday:
        add("navagraha_shanti",
            "Birthday — Navagraha Shanti Pooja to balance all nine planets and bless the year ahead.", 0)

    for label, pooja_key in _detect_doshas(kundali_result):
        add(pooja_key, f"{label} — remedial pooja.", 1)

    if isinstance(kundali_result, dict):
        maha = _normalize_planet((kundali_result.get("current_mahadasha") or {}).get("name"))
        antar = _normalize_planet((kundali_result.get("current_antardasha") or {}).get("name"))
        if maha and maha in PLANET_TO_POOJA:
            add(PLANET_TO_POOJA[maha],
                f"Current Mahadasha lord ({maha}) — strengthen and pacify its influence.", 2)
        if antar and antar in PLANET_TO_POOJA and antar != maha:
            add(PLANET_TO_POOJA[antar],
                f"Current Antardasha lord ({antar}) — support the running sub-period.", 3)

    ordered = sorted(recs.values(), key=lambda e: (e["_priority"], e["name"]))
    for e in ordered:
        e["reason"] = " ".join(e.pop("_reasons"))
        e.pop("_priority", None)

    if not dob and not isinstance(kundali_result, dict):
        status = "no_birth_details"
    elif not ordered:
        status = "no_recommendation"
    else:
        status = "ok"

    return {
        "status": status,
        "is_birthday": is_birthday,
        "recommendations": ordered,
        "note": ("Recommendations are derived from your birth chart (current dasha lords, doshas) "
                 "and birthday. They are independent of the calendar-based upcoming poojas."),
    }


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
    result = {}
    for name, body in planet_map:
        lon_trop = earth.at(t).observe(EPH[body]).apparent().frame_latlon(ecliptic_frame)[1].degrees
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


# ============================================================
# DURMUHURTA
# ============================================================
_DURMUHURTA_SIG = ("Avoid starting new ventures, ceremonies, travel, or signing agreements. "
                   "Routine work and spiritual practice are acceptable during this period.")
_NO_DURMUHURTA  = "No Durmuhurta today — Thursday (Guruvar) is auspicious and free of this inauspicious period."

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

EVENT_DEITY_MAP = {
    "ekadashi":      {"name": "Lord Vishnu",                 "description": "Ekadashi is dedicated to Lord Vishnu, the preserver of the universe. Fasting and prayer on this day invoke his blessings for spiritual merit, mental purification, and liberation."},
    "pradosh":       {"name": "Lord Shiva",                  "description": "Pradosh Vrat is dedicated to Lord Shiva. Twilight worship during Pradosh dissolves sins, grants inner peace, and removes obstacles through Shiva's transformative grace."},
    "chaturthi":     {"name": "Lord Ganesha",                "description": "Chaturthi is dedicated to Lord Ganesha, the remover of obstacles and bestower of wisdom. Worship seeks his blessings for new beginnings, clarity, and smooth progress."},
    "sankashti":     {"name": "Lord Ganesha",                "description": "Sankashti Chaturthi is dedicated to Lord Ganesha who grants deliverance from troubles. Devotees fast through the day and break it after moonrise with Ganesha's blessings."},
    "vinayaka":      {"name": "Lord Ganesha",                "description": "Vinayaka Chaturthi honors Lord Ganesha as the first deity of all auspicious beginnings. Worship on this day brings wisdom, success, and the removal of all obstacles."},
    "purnima":       {"name": "Lord Vishnu / Chandra Deva",  "description": "Purnima is associated with Lord Vishnu and Chandra Deva (the Moon). The full moon amplifies spiritual energy, making it ideal for gratitude, charity, and Satya Narayan puja."},
    "amavasya":      {"name": "Pitru Devatas (Ancestors)",   "description": "Amavasya is sacred to the Pitru Devatas — departed ancestral souls. Tarpan and charitable acts on this day bring peace to ancestors and help relieve karmic debts."},
    "navaratri":     {"name": "Goddess Durga (Navadurga)",   "description": "Navaratri celebrates Goddess Durga in her nine divine forms. Each day invokes a different aspect of Shakti for protection, strength, wisdom, and victory over negativity."},
    "navratri":      {"name": "Goddess Durga (Navadurga)",   "description": "Navratri celebrates Goddess Durga's nine forms. Daily puja, fasting, and scripture reading channel her Shakti energy for courage, protection, and inner transformation."},
    "shivaratri":    {"name": "Lord Shiva",                  "description": "Maha Shivaratri honors Lord Shiva through an all-night vigil, fasting, and abhishek. It is considered the most powerful night of the year for Shiva devotion and inner transformation."},
    "janmashtami":   {"name": "Lord Krishna",                "description": "Janmashtami celebrates the birth of Lord Krishna. Midnight vigil, fasting, and bhajan on this night are believed to grant devotion, joy, and protection from negativity."},
    "krishna":       {"name": "Lord Krishna",                "description": "Lord Krishna, the eighth avatar of Vishnu, embodies divine joy, wisdom, and love. Worship invokes his guidance for dharmic living, inner clarity, and devotional practice."},
    "rama navami":   {"name": "Lord Rama",                   "description": "Rama Navami celebrates the birth of Lord Rama, the ideal king and seventh avatar of Vishnu. Worship invokes his blessings for righteousness, family harmony, and courage."},
    "guru purnima":  {"name": "Brihaspati / Adi Guru",       "description": "Guru Purnima honors the lineage of spiritual teachers. Gratitude offered to one's Guru strengthens the guru-disciple bond and opens the channel for wisdom and grace."},
    "ganesh":        {"name": "Lord Ganesha",                "description": "This festival is dedicated to Lord Ganesha, the first deity worshipped before any auspicious undertaking. He grants wisdom, prosperity, and the removal of all obstacles."},
    "dussehra":      {"name": "Goddess Durga / Lord Rama",   "description": "Dussehra marks Rama's victory over Ravana and Durga's over Mahishasura — the triumph of righteousness over evil. A powerful day for courage, renewal, and gratitude."},
    "vijayadashami": {"name": "Goddess Durga / Lord Rama",   "description": "Vijayadashami celebrates divine victory. Beginning new learning, skills, or ventures on this day is considered especially auspicious and blessed."},
    "diwali":        {"name": "Goddess Lakshmi",             "description": "Diwali's Lakshmi Puja is dedicated to Goddess Lakshmi, the deity of wealth and abundance. Lighting diyas and performing puja invites her blessings of prosperity and light."},
    "vasant panchami": {"name": "Goddess Saraswati",         "description": "Vasant Panchami is dedicated to Goddess Saraswati, the deity of knowledge, arts, and wisdom. Students and creators seek her blessings for learning, eloquence, and creativity."},
    "raksha bandhan": {"name": "Lord Vishnu / Indra Deva",   "description": "Raksha Bandhan invokes divine protection through the sacred thread. It is associated with Lord Vishnu's protection and the strength of the sibling bond."},
    "akshaya tritiya": {"name": "Lord Vishnu / Lakshmi",     "description": "Akshaya Tritiya is one of the most auspicious days of the year, sacred to Vishnu and Lakshmi. 'Akshaya' means imperishable — any virtuous act done today yields unending merit."},
    "kalashtami":    {"name": "Lord Kala Bhairava",          "description": "Kalashtami, the Ashtami of Krishna Paksha, is dedicated to Lord Kala Bhairava, the fierce protective form of Shiva. Worship invokes his protection, courage, and the removal of fear and hidden obstacles."},
    "durga ashtami": {"name": "Goddess Durga",               "description": "Durga Ashtami honors Goddess Durga in her warrior Shakti form. Worship on this day invokes strength, protection, and victory over inner and outer obstacles."},
    "radha ashtami": {"name": "Radha Rani",                  "description": "Radha Ashtami celebrates the birth of Radha Rani, the beloved of Lord Krishna and embodiment of pure devotion. Worship deepens bhakti, love, and grace."},
    "ashtami":       {"name": "Goddess Durga / Lord Bhairava","description": "Ashtami, the 8th tithi, carries Shakti energy — Shukla Ashtami is sacred to Goddess Durga, while Krishna Ashtami (Kalashtami) honors Lord Bhairava. The day supports strength, protection, and courage."},
}


def _event_deity(event_name, paksha=None):
    """Return the primary deity associated with a spiritual event."""
    e = (event_name or "").lower()
    for key, deity in EVENT_DEITY_MAP.items():
        if key in e:
            return deity
    if paksha == "Shukla Paksha":
        return {
            "name": "Lord Vishnu",
            "description": "Shukla Paksha is governed by the growing Moon and associated with Lord Vishnu, supporting growth, new beginnings, and all constructive actions.",
        }
    return {
        "name": "Lord Shiva / Pitru Devatas",
        "description": "Krishna Paksha, the waning lunar fortnight, is associated with introspection, ancestor reverence, and the transformative energy of Lord Shiva.",
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
# DYNAMIC SIGNIFICANCE TEXT
# ============================================================
_TITHI_NATURE_GUIDANCE = {
    "Nanda":  "Its Nanda (joyful) nature makes it ideal for celebrations, new initiatives, and social connections.",
    "Bhadra": "Its Bhadra (auspicious) nature supports ceremonies, education, and all forms of constructive work.",
    "Jaya":   "Its Jaya (victorious) nature lends strength to decisive action — good for challenges and breaking through obstacles.",
    "Rikta":  "Its Rikta (hollow) nature advises stepping back from major new starts; focus on completing existing work and introspection.",
    "Poorna": "Its Poorna (complete) nature brings fullness — an excellent time to wrap up goals, give thanks, and celebrate completions.",
}
_MOON_SIGN_FLAVOR = {
    "Aries":"driving initiative and the courage to act decisively",
    "Taurus":"grounding energy in patience, beauty, and material comfort",
    "Gemini":"quickening the mind and opening channels of communication",
    "Cancer":"drawing attention to home, family, and emotional nourishment",
    "Leo":"fueling creative expression, confidence, and the desire to lead",
    "Virgo":"sharpening analytical thinking and a desire for order and service",
    "Libra":"cultivating harmony, aesthetic refinement, and balanced relationships",
    "Scorpio":"intensifying emotional depth, intuition, and transformative insight",
    "Sagittarius":"expanding the horizons of knowledge, faith, and adventure",
    "Capricorn":"anchoring ambitions in discipline and steady long-term effort",
    "Aquarius":"sparking originality, humanitarian instincts, and independent thinking",
    "Pisces":"dissolving boundaries and heightening spiritual receptivity and empathy",
}
_RITU_CLOSING = {
    "Vasanta (Spring)":    "The spring season amplifies this with its sense of renewal and fresh starts.",
    "Grishma (Summer)":    "The summer's intensity invites focused, purposeful activity.",
    "Varsha (Monsoon)":    "The monsoon's cleansing quality deepens whatever you undertake today.",
    "Sharad (Autumn)":     "Autumn's crisp clarity makes this a productive season for study and focused work.",
    "Hemanta (Pre-Winter)":"The pre-winter season turns energy inward — ideal for family warmth and spiritual study.",
    "Shishira (Winter)":   "Winter's quiet depth supports meditation, study, and building inner reserves.",
}

def generate_significance(tithi_name, tithi_nature, paksha, nakshatra_name,
                          nakshatra_lord, yoga_name, moon_sign, sun_sign,
                          ritu, day_of_week, festivals, vratas, is_adhik_maas=False):
    sentences = []
    clean_festivals = [f for f in (festivals or []) if f != "None"]
    clean_vratas    = [v for v in (vratas or [])    if v != "None"]

    if is_adhik_maas:
        sentences.append(
            "This day falls within an Adhik Maas — a rare intercalary lunar month — "
            "making any act of charity, worship, or self-discipline especially potent."
        )

    if clean_festivals:
        joined = (clean_festivals[0] if len(clean_festivals) == 1
                  else ", ".join(clean_festivals[:-1]) + f" and {clean_festivals[-1]}")
        sentences.append(
            f"Today marks {joined}, lending particular sanctity and festive significance to this day."
        )

    paksha_phrase = ("the growing light of the waxing Moon" if "Shukla" in paksha
                     else "the deepening stillness of the waning Moon")
    sentences.append(
        f"Under {paksha_phrase}, it is {tithi_name} Tithi. "
        + _TITHI_NATURE_GUIDANCE[tithi_nature]
    )

    sentences.append(
        f"The Moon moves through {nakshatra_name} Nakshatra — overseen by {nakshatra_lord} "
        f"and the deity {NAKSHATRA_DEITIES[nakshatras.index(nakshatra_name)]} — in {moon_sign}, "
        f"{_MOON_SIGN_FLAVOR[moon_sign]}."
    )

    if YOGA_AUSPICIOUS.get(yoga_name, True):
        sentences.append(
            f"{yoga_name} Yoga graces the day with its auspicious influence, "
            "supporting well-intentioned actions and devotional practice."
        )
    else:
        sentences.append(
            f"{yoga_name} Yoga calls for mindfulness today — avoid impulsive decisions "
            "and give careful thought before beginning anything significant."
        )

    sentences.append(
        f"The Sun is currently in {sun_sign}, shaping the broader seasonal backdrop for this period."
    )

    if clean_vratas:
        vrata_str = (clean_vratas[0] if len(clean_vratas) == 1
                     else " and ".join(clean_vratas[:2]))
        sentences.append(
            f"Devotees observing {vrata_str} will find the day's energies supportive "
            "of deep worship and inner focus."
        )

    if ritu in _RITU_CLOSING:
        sentences.append(_RITU_CLOSING[ritu])

    return " ".join(sentences)

def generate_daily_summary(d):
    """Generate concise, render-friendly daily summary text (Markdown bullets)."""
    festivals = [f for f in (d.get("festival_today") or []) if f != "None"]
    vratas = [v for v in (d.get("vrata_today") or []) if v != "None"]
    poojas = [p for p in (d.get("pooja_today") or []) if p.get("name") != "None"]
    subh = d.get("subh_muhurat") or []
    asubh = d.get("asubh_muhurat") or []
    amrit = d.get("amrit_kaal") or {}
    durmuhurta = d.get("durmuhurta") or {}
    varjyam = d.get("varjyam") or {}

    best_times = []
    for m in subh:
        if "abhijit" in m:
            best_times.append(f"Abhijit Muhurta: {m['abhijit'][0]} - {m['abhijit'][1]}")
        if "brahma" in m:
            best_times.append(f"Brahma Muhurta: {m['brahma'][0]} - {m['brahma'][1]}")
    for w in amrit.get("windows", []):
        best_times.append(f"Amrit Kaal: {w[0]} - {w[1]}")

    avoid_times = []
    for m in asubh:
        if "rahu" in m:
            avoid_times.append(f"Rahu Kaal: {m['rahu'][0]} - {m['rahu'][1]}")
        if "gulika" in m:
            avoid_times.append(f"Gulika Kaal: {m['gulika'][0]} - {m['gulika'][1]}")
        if "yamaganda" in m:
            avoid_times.append(f"Yamaganda: {m['yamaganda'][0]} - {m['yamaganda'][1]}")
    for w in durmuhurta.get("windows", []):
        avoid_times.append(f"Durmuhurta: {w[0]} - {w[1]}")
    if varjyam.get("start"):
        avoid_times.append(f"Varjyam: {varjyam['start']} - {varjyam['end']}")

    lines = [
        f"Day Overview: {d.get('day_of_week','')} ({d.get('date','')}) - {d.get('tithi','')} ({d.get('paksha','')}).",
        f"Overall Energy: {d.get('significance','') or 'Balanced day; proceed with clarity and discipline.'}",
        f"Best Times: {', '.join(best_times[:4]) if best_times else 'No major auspicious window identified.'}",
        f"Times to Avoid: {', '.join(avoid_times[:5]) if avoid_times else 'No major inauspicious window identified.'}",
        f"Festivals/Vratas: {', '.join((festivals + vratas)[:4]) if (festivals or vratas) else 'None specific today.'}",
        f"Suggested Pooja: {poojas[0]['name']} - {poojas[0].get('reason','')}" if poojas else "Suggested Pooja: No specific pooja recommended today.",
    ]
    return "\n".join([f"- {line}" for line in lines])


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

def _prev_month(year: int, month: int):
    return (year - 1, 12) if month == 1 else (year, month - 1)

def _next_month(year: int, month: int):
    return (year + 1, 1) if month == 12 else (year, month + 1)

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


def get_upcoming_poojas(lat_r, lon_r, tz_name, from_date, days_ahead=7, month_system="both"):
    """Returns poojas for next days_ahead days after from_date.
    Result is date-deterministic, so it is memoized per (location, from_date,
    window, month_system, UTC day) — see _scan_cache_get_or_compute."""
    key = ("poojas", lat_r, lon_r, tz_name, from_date.isoformat(), days_ahead, month_system,
           datetime.now(pytz.utc).strftime("%Y-%m-%d"))
    return _scan_cache_get_or_compute(
        key,
        lambda: _get_upcoming_poojas_uncached(lat_r, lon_r, tz_name, from_date, days_ahead, month_system),
    )


def _get_upcoming_poojas_uncached(lat_r, lon_r, tz_name, from_date, days_ahead=7, month_system="both"):
    tz = pytz.timezone(tz_name)
    result = []
    for offset in range(1, days_ahead + 1):
        target = from_date + timedelta(days=offset)
        target_local = tz.localize(datetime(target.year, target.month, target.day, 12, 0))
        t = TS.from_datetime(target_local.astimezone(pytz.utc))

        sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
        sun_sid  = float(np.atleast_1d(sun_sid)[0])
        moon_sid = float(np.atleast_1d(moon_sid)[0])
        angle = (moon_sid - sun_sid) % 360.0
        tithi_number, paksha, tithi_name = calculate_tithi_and_paksha_from_angle(angle)

        amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
            target_local, paksha, tz_name, lat_r, lon_r
        )
        day_of_week = target_local.strftime("%A")

        fixed = check_fixed_festivals(target)
        lunar = get_festivals_for_day(tithi_name, paksha, amanta_month, purnimanta_month,
                                      month_system=month_system)
        all_festivals = fixed + lunar

        poojas = get_poojas_for_day(tithi_number, paksha, amanta_month, day_of_week, all_festivals)
        has_poojas = not (len(poojas) == 1 and poojas[0]["name"] == "None")
        if has_poojas:
            date_key = target.strftime("%Y-%m-%d")
            try:
                sr_utc, ss_utc = cached_sunrise_sunset(lat_r, lon_r, date_key, tz_name)
                sr_l = sr_utc.astimezone(tz)
                ss_l = ss_utc.astimezone(tz)
                abh_s, abh_e = calculate_abhijit_muhurat(sr_l, ss_l)
                brh_s, brh_e = calculate_brahma_muhurat(sr_l, ss_l)
                day_muhurat = [
                    {"abhijit": [abh_s.strftime("%I:%M:%S %p"), abh_e.strftime("%I:%M:%S %p")], "description": _desc_abhijit(abh_s.strftime("%I:%M %p"), abh_e.strftime("%I:%M %p"))},
                    {"brahma":  [brh_s.strftime("%I:%M:%S %p"), brh_e.strftime("%I:%M:%S %p")], "description": _desc_brahma(brh_s.strftime("%I:%M %p"),  brh_e.strftime("%I:%M %p"))},
                ]
            except Exception:
                day_muhurat = []
            result.append({
                "date":         date_key,
                "day_of_week":  day_of_week,
                "tithi":        tithi_name,
                "tithi_number": tithi_number,
                "paksha":       paksha,
                "muhurat":      day_muhurat,
                "poojas":       poojas,
            })
    return result


def _precompute_month_events_and_poojas(lat_r, lon_r, tz_name, year, month, month_system="both"):
    """Single-pass computation of spiritual events and poojas for a month + 7 extra days.

    Returns (events_by_date, poojas_by_date) where keys are 'YYYY-MM-DD' strings.
    Replaces 30 redundant overlapping calls in the monthly loop with one pass.
    """
    import calendar
    num_days = calendar.monthrange(year, month)[1]
    from_date = datetime(year, month, 1).date()
    tz = pytz.timezone(tz_name)

    events_by_date = {}
    poojas_by_date = {}

    for offset in range(num_days + 7):
        target = from_date + timedelta(days=offset)
        target_local = tz.localize(datetime(target.year, target.month, target.day, 12, 0))
        t = TS.from_datetime(target_local.astimezone(pytz.utc))

        sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
        sun_sid  = float(np.atleast_1d(sun_sid)[0])
        moon_sid = float(np.atleast_1d(moon_sid)[0])
        angle = (moon_sid - sun_sid) % 360.0
        tithi_number, paksha, tithi_name = calculate_tithi_and_paksha_from_angle(angle)
        amanta_month_val, purnimanta_month_val = calculate_amanta_purnimanta_month_fast(
            target_local, paksha, tz_name, lat_r, lon_r
        )
        day_of_week = target_local.strftime("%A")
        nak_name = nakshatras[_to_int_scalar(nakshatra_index_at(t))]

        fixed   = check_fixed_festivals(target)
        lunar   = get_festivals_for_day(tithi_name, paksha, amanta_month_val, purnimanta_month_val,
                                        month_system=month_system)
        vratas  = get_vratas_for_day(tithi_name, paksha, day_of_week, nak_name)
        poojas  = get_poojas_for_day(tithi_number, paksha, amanta_month_val, day_of_week, fixed + lunar)

        date_key = target.strftime("%Y-%m-%d")

        # compute lightweight muhurat for this day
        try:
            sr_utc, ss_utc = cached_sunrise_sunset(lat_r, lon_r, date_key, tz_name)
            tz_obj = pytz.timezone(tz_name)
            sr_local = sr_utc.astimezone(tz_obj)
            ss_local = ss_utc.astimezone(tz_obj)
            abh_s, abh_e = calculate_abhijit_muhurat(sr_local, ss_local)
            brh_s, brh_e = calculate_brahma_muhurat(sr_local, ss_local)
            day_muhurat = [
                {"abhijit": [abh_s.strftime("%I:%M:%S %p"), abh_e.strftime("%I:%M:%S %p")], "description": _desc_abhijit(abh_s.strftime("%I:%M %p"), abh_e.strftime("%I:%M %p"))},
                {"brahma":  [brh_s.strftime("%I:%M:%S %p"), brh_e.strftime("%I:%M:%S %p")], "description": _desc_brahma(brh_s.strftime("%I:%M %p"),  brh_e.strftime("%I:%M %p"))},
            ]
        except Exception:
            day_muhurat = []

        # --- spiritual events entry ---
        festivals    = (fixed + lunar) or ["None"]
        vratas_list  = vratas or ["None"]
        clean_f  = _clean_event_list(festivals)
        clean_v  = [v for v in _clean_event_list(vratas_list) if _is_significant_vrata(v)]
        event_titles = clean_f + clean_v
        if event_titles:
            event_title = event_titles[0]
            guidance = _event_guidance(event_title, paksha)
            events_by_date[date_key] = {
                "date":                  date_key,
                "day":                   day_of_week,
                "tithi":                 tithi_name,
                "paksha":                paksha,
                "event":                 event_title,
                "all_events":            event_titles,
                "deity":                 _event_deity(event_title, paksha),
                "description":           guidance.get("description", ""),
                "why_it_matters":        guidance["why_it_matters"],
                "who_should_use_it":     guidance["who_should_use_it"],
                "recommended_practices": guidance["recommended_practices"],
                "avoid_practices":       guidance["avoid_practices"],
                "muhurat":               day_muhurat,
                "suggested_pooja":       next(
                    (p for p in poojas if p.get("name") != "None"),
                    {"name": "None", "reason": ""},
                ),
            }

        # --- poojas entry ---
        has_poojas = not (len(poojas) == 1 and poojas[0]["name"] == "None")
        if has_poojas:
            poojas_by_date[date_key] = {
                "date":         date_key,
                "day_of_week":  day_of_week,
                "tithi":        tithi_name,
                "tithi_number": tithi_number,
                "paksha":       paksha,
                "muhurat":      day_muhurat,
                "poojas":       poojas,
            }

    return events_by_date, poojas_by_date


def _slice_upcoming_spiritual_events(events_by_date, from_date, days_ahead=7):
    """Return upcoming spiritual events from a precomputed dict, matching get_upcoming_spiritual_events output."""
    result = []
    for offset in range(1, days_ahead + 1):
        target = from_date + timedelta(days=offset)
        entry = events_by_date.get(target.strftime("%Y-%m-%d"))
        if entry:
            result.append(entry)
    result.sort(key=lambda r: (_spiritual_event_priority(r), r.get("date", "")))
    return result[:7] if len(result) > 7 else result[:max(3, len(result))]


def _slice_upcoming_poojas(poojas_by_date, from_date, days_ahead=7):
    """Return upcoming poojas from a precomputed dict, matching get_upcoming_poojas output."""
    result = []
    for offset in range(1, days_ahead + 1):
        target = from_date + timedelta(days=offset)
        entry = poojas_by_date.get(target.strftime("%Y-%m-%d"))
        if entry:
            result.append(entry)
    return result


def _filter_upcoming_poojas_window(upcoming_poojas, base_date_str, min_day=3, max_day=7):
    if not upcoming_poojas or not base_date_str:
        return []
    try:
        base_date = datetime.strptime(base_date_str, "%Y-%m-%d").date()
    except Exception:
        return []

    window = []
    for item in upcoming_poojas:
        try:
            d = datetime.strptime((item or {}).get("date", ""), "%Y-%m-%d").date()
        except Exception:
            continue
        delta = (d - base_date).days
        if min_day <= delta <= max_day:
            window.append(item)
    return window


def _clean_event_list(values):
    return [v for v in (values or []) if v and v != "None"]


# Tithis significant enough to surface in Upcoming Spiritual Events even without a
# named festival on that day. Matched as case-insensitive substrings against vrata names
# (e.g. "Kalashtami (Monthly)" -> ashtami, "Sankashti Chaturthi (Monthly)" -> chaturthi,
# "Purnima Vrat (Monthly)" -> purnima, "Amavasya Vrat (Monthly)" -> amavasya).
SIGNIFICANT_VRATA_KEYWORDS = ("ekadashi", "pradosh", "ashtami", "chaturthi", "purnima", "amavasya")


def _is_significant_vrata(name):
    n = (name or "").lower()
    return any(k in n for k in SIGNIFICANT_VRATA_KEYWORDS)


def _event_guidance(event_name, paksha):
    e = (event_name or "").lower()
    if "ekadashi" in e:
        return {
            "description": "Ekadashi is the eleventh lunar day (tithi) observed twice a month — once in each paksha. It is one of the most sacred days in Vaishnava tradition, dedicated to Lord Vishnu. Devotees observe a fast from grains and lentils, engaging in prayer, scripture reading, and japa to purify the mind and accumulate spiritual merit.",
            "why_it_matters": "Ekadashi supports discipline, clarity, and deep Vishnu bhakti through mindful fasting.",
            "who_should_use_it": "People seeking mental detox, devotion, or sattvic routine alignment.",
            "recommended_practices": [
                "Observe partial or full fast as per health and family tradition.",
                "Chant Vishnu mantras, read Gita, and do evening diya offering.",
                "Keep speech gentle and spend more time in japa or prayer."
            ],
            "avoid_practices": [
                "Heavy tamasic meals, over-stimulation, and avoidable conflict.",
                "Unnecessary arguments and impulsive commitments."
            ],
        }
    if "pradosh" in e:
        return {
            "description": "Pradosh Vrat is observed on the 13th tithi (Trayodashi) of both Shukla and Krishna Paksha, in the twilight hours (Pradosh Kala — approximately 1.5 hours after sunset). It is a powerful Shiva vrat believed to absolve sins, restore health, and bring peace to the family. The twilight window is considered especially potent for Shiva worship.",
            "why_it_matters": "Pradosh is a Shiva-focused twilight vrata known for purification and removal of obstacles.",
            "who_should_use_it": "Devotees seeking emotional balance, karmic cleansing, and family harmony.",
            "recommended_practices": [
                "Perform Shiva puja in the evening with bilva leaves and deepam.",
                "Chant Om Namah Shivaya or Shiva stotram during Pradosh kala.",
                "Keep food light and end the day with gratitude and silence."
            ],
            "avoid_practices": [
                "Anger, harsh speech, and rushing through evening worship.",
                "Starting avoidable confrontational tasks during twilight."
            ],
        }
    if "ashtami" in e and "janma" not in e:
        if paksha == "Krishna Paksha":
            return {
                "description": "Kalashtami falls on the Ashtami (8th tithi) of Krishna Paksha each month and is dedicated to Lord Kala Bhairava, the fierce protective form of Lord Shiva. It is observed for courage, protection from negative forces, and the removal of fear and hidden obstacles.",
                "why_it_matters": "Krishna Ashtami (Kalashtami) invokes Bhairava's protection — clearing fear, negativity, and hidden obstacles.",
                "who_should_use_it": "Those seeking protection, courage, or relief from persistent fear and obstacles.",
                "recommended_practices": [
                    "Light a mustard-oil or sesame-oil lamp before Bhairava in the evening.",
                    "Chant the Bhairava or Shiva mantra and offer black sesame.",
                    "Keep food light and observe a calm, disciplined day.",
                ],
                "avoid_practices": [
                    "Anger, harsh speech, and reckless risk-taking.",
                    "Non-vegetarian food and intoxicants.",
                ],
            }
        return {
            "description": "Shukla Ashtami (the 8th tithi of the waxing fortnight) is sacred to Goddess Durga in her Shakti form, observed as Masik Durga Ashtami. It is a day for invoking strength, protection, and victory over inner and outer obstacles.",
            "why_it_matters": "Shukla Ashtami channels Durga's Shakti for strength, protection, and resolve.",
            "who_should_use_it": "Devotees seeking courage, protection, and spiritual strength.",
            "recommended_practices": [
                "Offer red flowers, kumkum, and incense to Goddess Durga.",
                "Recite Durga Chalisa or a Devi stotram.",
                "Observe a light sattvic fast if health permits.",
            ],
            "avoid_practices": [
                "Tamasic food, alcohol, and conflict.",
                "Negative or harsh speech.",
            ],
        }
    if "sankashti" in e or "chaturthi" in e:
        return {
            "description": "Sankashti Chaturthi falls on the 4th lunar day of Krishna Paksha each month. 'Sankashti' means 'deliverance from troubles.' It is dedicated to Lord Ganesha — the remover of obstacles. Devotees fast through the day and break it after moonrise, having sighted the moon and offered prayers.",
            "why_it_matters": "Sankashti Chaturthi is associated with Lord Ganesha for removing blockages and stabilizing intent.",
            "who_should_use_it": "Those facing delays, stress, or new beginnings needing support.",
            "recommended_practices": [
                "Offer durva and modak to Ganesha and read Sankashti vrat katha.",
                "Take sankalpa for one concrete personal obstacle.",
                "Prefer moonrise prayer if observed in your tradition."
            ],
            "avoid_practices": [
                "Overcommitting and scattered decision making.",
                "Breaking fast casually without mindful closure."
            ],
        }
    if "purnima" in e:
        return {
            "description": "Purnima is the full moon tithi, considered the most auspicious lunar phase in the Hindu calendar. It is associated with the culmination of energy, abundance, and heightened spiritual potency. Many major festivals and observances coincide with Purnima.",
            "why_it_matters": "Full moon amplifies intentions and is an ideal time for gratitude, giving, and Satya Narayan puja.",
            "who_should_use_it": "Devotees of Vishnu, Shiva, and those seeking emotional fullness or abundance.",
            "recommended_practices": [
                "Offer white flowers and milk to the moon at moonrise.",
                "Perform Satya Narayan puja or Vishnu archana.",
                "Donate food or clothes as an act of gratitude.",
            ],
            "avoid_practices": ["Arguments and major disputes.", "Starting new medical procedures."],
        }
    if "amavasya" in e or "ausi" in e:
        return {
            "description": "Amavasya (New Moon) is the 30th tithi, considered sacred for ancestor worship (Pitru Tarpan). The no-moon night is believed to be when the veil between the living and ancestors is thinnest. Offerings made on this day benefit departed souls.",
            "why_it_matters": "Amavasya is the most potent day for ancestor offerings and karmic clearing of ancestral debts.",
            "who_should_use_it": "Anyone with family karma, grief, or a wish to honor departed ancestors.",
            "recommended_practices": [
                "Perform Pitru Tarpan (water offering with sesame) in the morning.",
                "Donate food to Brahmins or poor in memory of ancestors.",
                "Light a deepam and offer prayers for departed family members.",
            ],
            "avoid_practices": ["Festive celebrations and major new purchases.", "Late-night outings."],
        }
    if "navaratri" in e:
        return {
            "description": "Navaratri ('Nine Nights') is a nine-day festival celebrating the divine feminine — Goddess Durga in her nine forms (Navadurga). Observed twice a year (Chaitra and Sharad), it involves daily puja, fasting, Devi stotram, and Garba/Dandiya in many communities.",
            "why_it_matters": "Navaratri channels Shakti energy for purification, courage, and victory over inner and outer obstacles.",
            "who_should_use_it": "All devotees, especially those seeking strength, protection, or spiritual transformation.",
            "recommended_practices": [
                "Worship Navadurga forms daily with flowers, kumkum, and incense.",
                "Recite Durga Saptashati or Devi Mahatmya.",
                "Observe partial fast (fruit and milk only) if health permits.",
            ],
            "avoid_practices": ["Non-vegetarian food and alcohol.", "Tamasic entertainment during the nine days."],
        }
    if paksha == "Shukla Paksha":
        return {
            "description": "Shukla Paksha is the waxing phase of the lunar fortnight — from new moon to full moon. It is considered auspicious for new beginnings, starting projects, rituals of growth, and constructive action. Energy builds during this phase.",
            "why_it_matters": "Shukla Paksha supports growth, expansion, and constructive starts.",
            "who_should_use_it": "People planning new initiatives or devotional commitments.",
            "recommended_practices": [
                "Set clear intentions and begin one high-value task.",
                "Offer morning prayer and maintain disciplined routine.",
            ],
            "avoid_practices": ["Overthinking and procrastination."],
        }
    return {
        "description": "Krishna Paksha is the waning lunar fortnight — from full moon to new moon. It is a time for inward reflection, releasing what no longer serves, completing unfinished work, and ancestor remembrance. Spiritual discipline in this phase yields deep inner purification.",
        "why_it_matters": "This lunar phase supports release, introspection, and spiritual reset.",
        "who_should_use_it": "Anyone needing reflection, emotional grounding, or closure.",
        "recommended_practices": [
            "Complete pending tasks and reduce noise in your schedule.",
            "Do short meditation, mantra, and gratitude reflection."
        ],
        "avoid_practices": ["Impulsive high-risk decisions and avoidable friction."],
    }


def _spiritual_event_priority(row):
    text = " ".join([row.get("event", "")] + (row.get("all_events") or [])).lower()
    if "ekadashi" in text:
        return 0
    if "pradosh" in text:
        return 1
    if "ashtami" in text:
        return 2
    if row.get("all_events"):
        return 3
    if "festival" in text or "jayanti" in text or "purnima" in text:
        return 4
    return 5


def get_upcoming_spiritual_events(lat_r, lon_r, tz_name, from_date, days_ahead=7, month_system="both"):
    """Return festival/vrata-rich upcoming spiritual events for app use.
    Date-deterministic, so memoized per (location, from_date, window,
    month_system, UTC day) — this is the bulk of /astrology's compute."""
    key = ("events", lat_r, lon_r, tz_name, from_date.isoformat(), days_ahead, month_system,
           datetime.now(pytz.utc).strftime("%Y-%m-%d"))
    return _scan_cache_get_or_compute(
        key,
        lambda: _get_upcoming_spiritual_events_uncached(lat_r, lon_r, tz_name, from_date, days_ahead, month_system),
    )


def _get_upcoming_spiritual_events_uncached(lat_r, lon_r, tz_name, from_date, days_ahead=7, month_system="both"):
    tz = pytz.timezone(tz_name)
    result = []
    for offset in range(1, days_ahead + 1):
        target = from_date + timedelta(days=offset)
        target_local = tz.localize(datetime(target.year, target.month, target.day, 12, 0))
        t = TS.from_datetime(target_local.astimezone(pytz.utc))

        sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
        sun_sid = float(np.atleast_1d(sun_sid)[0])
        moon_sid = float(np.atleast_1d(moon_sid)[0])
        angle = (moon_sid - sun_sid) % 360.0
        tithi_number, paksha, tithi_name = calculate_tithi_and_paksha_from_angle(angle)

        amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
            target_local, paksha, tz_name, lat_r, lon_r
        )
        day_of_week = target_local.strftime("%A")
        fixed = check_fixed_festivals(target)
        lunar = get_festivals_for_day(tithi_name, paksha, amanta_month, purnimanta_month, month_system=month_system)
        vratas = get_vratas_for_day(tithi_name, paksha, day_of_week, nakshatras[_to_int_scalar(nakshatra_index_at(t))])
        festivals = (fixed + lunar) or ["None"]
        vratas = vratas or ["None"]
        poojas = get_poojas_for_day(tithi_number, paksha, amanta_month, day_of_week, fixed + lunar)

        clean_festivals = _clean_event_list(festivals)
        clean_vratas = [v for v in _clean_event_list(vratas) if _is_significant_vrata(v)]
        event_titles = clean_festivals + clean_vratas
        if not event_titles:
            continue
        event_title = event_titles[0]
        guidance = _event_guidance(event_title, paksha)

        day_panchanga = calculate_panchanga_for_date(lat_r, lon_r, datetime(target.year, target.month, target.day), tz_name)
        result.append({
            "date": target.strftime("%Y-%m-%d"),
            "day": day_of_week,
            "tithi": tithi_name,
            "paksha": paksha,
            "event": event_title,
            "all_events": event_titles,
            "deity": _event_deity(event_title, paksha),
            "description": guidance.get("description", ""),
            "why_it_matters": guidance["why_it_matters"],
            "who_should_use_it": guidance["who_should_use_it"],
            "recommended_practices": guidance["recommended_practices"],
            "avoid_practices": guidance["avoid_practices"],
            "muhurat": day_panchanga.get("subh_muhurat") or [],
            "suggested_pooja": next((p for p in poojas if p.get("name") != "None"), {"name": "None", "reason": ""}),
        })

    result.sort(key=lambda r: (_spiritual_event_priority(r), r.get("date", "")))
    if len(result) > 7:
        return result[:7]
    # Ensure at least 3 entries in app list, but never beyond 7-day scan window.
    return result[:max(3, len(result))]


def _normalize_rashi(rashi_value):
    if not rashi_value:
        return None
    raw = str(rashi_value).strip().lower()
    for name in rashi_names:
        if raw == name.lower():
            return name
    alias = {
        "aries": "Aries", "aires": "Aries",
        "mesha": "Aries", "vrishabha": "Taurus", "mithuna": "Gemini", "karka": "Cancer",
        "simha": "Leo", "kanya": "Virgo", "tula": "Libra", "vrishchika": "Scorpio",
        "dhanu": "Sagittarius", "makara": "Capricorn", "kumbha": "Aquarius", "aquarious": "Aquarius", "meena": "Pisces",
    }
    return alias.get(raw)


def _build_horoscope_for_rashi(rashi, day_data):
    if not rashi:
        return None
    profile = RASHI_PROFILE.get(rashi, {"lord": "", "element": "", "sanskrit": rashi})
    month_day = ""
    try:
        month_day = datetime.strptime(day_data.get("date", ""), "%Y-%m-%d").strftime("%b %d")
    except Exception:
        month_day = day_data.get("date", "")
    return {
        "month_day": month_day,
        "rashi": rashi,
        "sanskrit": profile.get("sanskrit", ""),
        "lord": profile.get("lord", ""),
        "element": profile.get("element", ""),
        "message": "",
    }


HOUSE_THEMES = {
    1: "self, vitality and identity",
    2: "income, speech and family resources",
    3: "effort, communication and siblings",
    4: "home, inner peace and property",
    5: "creativity, children and intelligence",
    6: "workload, health routine and competition",
    7: "partnerships and one-to-one dynamics",
    8: "transformation, vulnerability and hidden matters",
    9: "dharma, teachers and long-term blessings",
    10: "career, responsibility and public role",
    11: "gains, network and wish-fulfillment",
    12: "rest, isolation, overseas and closure",
}

PLANET_TRANSIT_EFFECT = {
    "Sun": "highlights leadership, visibility and ego themes",
    "Moon": "changes emotional tone, comfort and responsiveness quickly",
    "Mars": "adds drive and urgency; watch impulsiveness and conflict",
    "Mercury": "improves planning, messaging, learning and negotiations",
    "Jupiter": "supports growth, wisdom and constructive expansion",
    "Venus": "supports harmony, relationships, art and comfort",
    "Saturn": "demands discipline, patience and sustainable structure",
    "Rahu": "amplifies desires, ambition and unconventional moves",
    "Ketu": "pushes detachment, introspection and spiritual filtering",
}

PLANET_PRIORITY = {
    "Saturn": 0, "Jupiter": 1, "Rahu": 2, "Ketu": 3,
    "Sun": 4, "Moon": 5, "Mars": 6, "Mercury": 7, "Venus": 8
}

HOUSE_NAME_TO_NUM = {
    "first_house": 1, "second_house": 2, "third_house": 3, "fourth_house": 4,
    "fifth_house": 5, "sixth_house": 6, "seventh_house": 7, "eighth_house": 8,
    "ninth_house": 9, "tenth_house": 10, "eleventh_house": 11, "twelfth_house": 12,
}

RASHI_TONE = {
    "Aries": {"open": "Bold momentum surrounds you", "strength": "courage and initiative"},
    "Taurus": {"open": "A steady rhythm works in your favor", "strength": "patience and grounded judgment"},
    "Gemini": {"open": "Your mind is quick and alert today", "strength": "communication and adaptability"},
    "Cancer": {"open": "Emotional sensitivity runs high", "strength": "care, intuition, and protective instincts"},
    "Leo": {"open": "Your presence is noticeable today", "strength": "leadership and confidence"},
    "Virgo": {"open": "Details matter more than usual", "strength": "analysis and practical execution"},
    "Libra": {"open": "Balance becomes your main advantage", "strength": "diplomacy and fair judgment"},
    "Scorpio": {"open": "Inner intensity is strong", "strength": "focus and strategic depth"},
    "Sagittarius": {"open": "A wider vision guides your choices", "strength": "optimism and principle-driven action"},
    "Capricorn": {"open": "Responsibility takes center stage", "strength": "discipline and long-term thinking"},
    "Aquarius": {"open": "Independent thinking shapes your day", "strength": "innovation and objectivity"},
    "Pisces": {"open": "Your intuition speaks clearly", "strength": "compassion and spiritual sensitivity"},
}


def _stable_pick(options, seed_key):
    if not options:
        return ""
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def _transit_signal_for_horoscope(personalized_transits):
    """Return net signed signals per domain: positive = supportive, negative = challenging."""
    signals = {"career": 0, "money": 0, "relationship": 0, "health": 0, "mind": 0}
    benefics = {"Jupiter", "Venus", "Mercury"}
    malefics = {"Saturn", "Mars", "Rahu", "Ketu"}

    for t in personalized_transits:
        p = t["planet"]
        h = t["house_from_rashi"]
        w = 1 if p in benefics else (-1 if p in malefics else 0)

        if h in (10, 11) or p == "Jupiter":
            signals["career"] += w if w != 0 else 1
        if h == 6 or p == "Saturn":
            signals["career"] -= 1

        if h in (2, 11) or p in ("Jupiter", "Venus"):
            signals["money"] += w if w != 0 else 1
        if h in (8, 12) or p in ("Rahu", "Saturn"):
            signals["money"] -= 1

        if h in (5, 7) or p in ("Venus", "Moon"):
            signals["relationship"] += w if w != 0 else 1
        if h in (6, 12) or p in ("Mars", "Saturn", "Ketu"):
            signals["relationship"] -= 1

        if h in (1, 6, 8) and w < 0:
            signals["health"] -= 1
        if h == 1 and w > 0:
            signals["health"] += 1

        if h in (1, 4) or p in ("Moon", "Mercury"):
            signals["mind"] += w if w != 0 else 1
        if h in (8, 12) or p in ("Rahu", "Ketu", "Saturn"):
            signals["mind"] -= 1

    return signals


def _compose_prediction_lines(rashi, signals, seed_base):
    """Create richer, non-static lines from weighted signals."""
    tone = RASHI_TONE.get(rashi, {"open": "The day carries mixed energies", "strength": "clarity"})

    openers = [
        f"{tone['open']}, and your natural {tone['strength']} can give you an edge.",
        f"The day begins with noticeable shifts; lean on your {tone['strength']} to stay centered.",
        f"Planetary movement favors a thoughtful approach, especially through your {tone['strength']}.",
    ]

    work_pos = [
        "Career momentum is supportive; use clarity and confidence to push forward key tasks.",
        "Your equation with seniors and decision-makers improves — a direct, respectful approach can open doors.",
        "Professional opportunities are more accessible today; act on what has been pending too long.",
    ]
    work_neg = [
        "Workplace pressure or authority friction may rise; stay composed and avoid reactive decisions.",
        "Career progress may feel blocked; focus on preparation rather than pushing prematurely.",
        "Pending work can pile up if multitasking replaces focused effort — choose one priority at a time.",
    ]
    work_neu = [
        "Professional tasks can move forward if you keep communication precise and deadlines realistic.",
        "Work output is moderate; consistent effort matters more than bursts of enthusiasm.",
        "Avoid multitasking; steady, focused progress will outperform scattered attempts today.",
    ]

    money_pos = [
        "Financial matters are looking up; a pending gain, payment, or practical opportunity may arrive.",
        "Income channels are active; review pending dues and follow up on money owed to you.",
        "Spending discipline today can translate into a noticeably stronger position over the coming week.",
    ]
    money_neg = [
        "Unplanned expenses or financial strain may surface; avoid impulsive commitments and large purchases.",
        "Money matters need careful handling; review contracts before signing and verify figures before acting.",
        "Financial leakage is possible through careless spending or poorly timed investments — pause and verify.",
    ]
    money_neu = [
        "Handle finances with consistency; gradual gains are more likely than sudden jumps.",
        "Money matters improve through practical planning rather than risky shortcuts.",
        "Keep spending within a clear plan; no dramatic moves, just steady, reliable management.",
    ]

    relation_pos = [
        "Close relationships carry warmth today; meaningful conversations and connection are well-supported.",
        "Romantic and family bonds can deepen through honest, affectionate communication.",
        "Partnership matters tend to improve when you lead with patience and genuine appreciation.",
    ]
    relation_neg = [
        "Relationship dynamics may feel tense; avoid ego-based arguments and give space where needed.",
        "Misunderstandings in close bonds are possible — listen fully before reacting.",
        "Marital or partner stress may rise; prioritize calm over being right.",
    ]
    relation_neu = [
        "In close relationships, speak gently; small misunderstandings can be resolved with patience.",
        "Romantic and family conversations need emotional maturity more than quick reactions.",
        "Marital dynamics may feel sensitive; listen first and avoid ego-based arguments.",
    ]

    health_pos = [
        "Physical energy is relatively stable; a disciplined routine and rest will reinforce this.",
        "Vitality supports you well today; maintain your pace without overdoing any single exertion.",
        "Health trends are calm; consistent meals, sleep, and gentle activity keep this positive.",
    ]
    health_neg = [
        "Stress may translate into physical fatigue; protect sleep, hydration, and meal timing carefully.",
        "Energy can dip unexpectedly; avoid overexertion and do not ignore early signs of strain.",
        "Mind-body balance needs attention; a simple, steady routine is better than pushing hard.",
    ]
    health_neu = [
        "Energy fluctuates through the day, so pace yourself and avoid unnecessary confrontation.",
        "Mind-body balance needs a consistent rhythm; keep routine predictable.",
        "Rest, hydration, and measured effort are your best tools regardless of what the day brings.",
    ]

    close_pos = [
        "Job seekers can receive a meaningful lead, callback, or useful connection today.",
        "A calm, disciplined approach today sets up stronger momentum over the next few days.",
        "Harness the positive current carefully — composed action now yields durable rewards.",
    ]
    close_neg = [
        "Stay away from unethical shortcuts; short-term gains today can create long-term complications.",
        "Avoid risky decisions, protect health and reputation, and prioritize what you can control.",
        "A patient, grounded stance today protects what matters most across the days ahead.",
    ]
    close_neu = [
        "Stay away from unethical actions; short-term gains can create long-term complications.",
        "A calm, disciplined approach today sets up stronger results over the next few days.",
        "Measured, consistent decisions will serve you better than reactive or impulsive ones.",
    ]

    def _pick_domain(pos_pool, neg_pool, neu_pool, score, key):
        tone_key = "pos" if score > 0 else ("neg" if score < 0 else "neu")
        pool = pos_pool if score > 0 else (neg_pool if score < 0 else neu_pool)
        return _stable_pick(pool, seed_base + f":{key}:{tone_key}")

    lines = [
        _stable_pick(openers, seed_base + ":open"),
        _pick_domain(work_pos, work_neg, work_neu, signals["career"], "work"),
        _pick_domain(money_pos, money_neg, money_neu, signals["money"], "money"),
        _pick_domain(relation_pos, relation_neg, relation_neu, signals["relationship"], "rel"),
        _pick_domain(health_pos, health_neg, health_neu, signals["health"], "health"),
        _pick_domain(close_pos, close_neg, close_neu, sum(signals.values()), "close"),
    ]

    # Keep exactly 5 lines, prioritising domains with the strongest absolute signal.
    priority = sorted(
        [
            ("work", abs(signals["career"]), lines[1]),
            ("money", abs(signals["money"]), lines[2]),
            ("relation", abs(signals["relationship"]), lines[3]),
            ("health", abs(signals["health"]), lines[4]),
        ],
        key=lambda x: x[1],
        reverse=True,
    )
    return [lines[0]] + [p[2] for p in priority[:3]] + [lines[5]]


TRANSIT_POOJA_PRACTICES = {
    "Sun": {
        "deity": "Surya Deva",
        "mantra": "Om Hraam Hreem Hraum Sah Suryaya Namah",
        "practices": [
            "Offer water to the rising sun (Surya Arghya) daily — cupped in both hands, released facing east.",
            "Chant Aditya Hridayam or Surya Ashtakam every morning.",
            "Donate wheat, jaggery, or copper items on Sundays.",
            "Light a ghee deepam facing east at sunrise for clarity and authority.",
        ],
    },
    "Moon": {
        "deity": "Chandra Deva (via Lord Shiva)",
        "mantra": "Om Shraam Shreem Shraum Sah Chandramashe Namah",
        "practices": [
            "Offer milk and white flowers to Shiva on Mondays (Somvar Puja).",
            "Chant Chandra Kavach or Shiva stotrams for emotional balance.",
            "Donate white rice, milk, or silver on Mondays.",
            "Observe Somvar Vrat (Monday fast) for mental peace and intuition.",
        ],
    },
    "Mars": {
        "deity": "Hanuman / Mangal Deva",
        "mantra": "Om Kraam Kreem Kraum Sah Bhaumaya Namah",
        "practices": [
            "Recite Hanuman Chalisa on Tuesdays for courage and protection.",
            "Donate red lentils (masoor dal), copper, or jaggery on Tuesdays.",
            "Light a mustard oil lamp before Hanuman's image.",
            "Channel Mars energy into physical discipline — exercise, yoga, or structured work.",
        ],
    },
    "Mercury": {
        "deity": "Lord Vishnu / Budha Deva",
        "mantra": "Om Braam Breem Braum Sah Budhaya Namah",
        "practices": [
            "Donate green gram (moong dal) or green vegetables on Wednesdays.",
            "Recite Vishnu Sahasranama for intelligence and communication clarity.",
            "Light a camphor lamp and offer green items at the altar.",
            "Keep speech truthful and avoid agreements made in haste.",
        ],
    },
    "Jupiter": {
        "deity": "Brihaspati / Lord Vishnu",
        "mantra": "Om Graam Greem Graum Sah Gurave Namah",
        "practices": [
            "Offer yellow flowers and turmeric to Vishnu or Guru on Thursdays.",
            "Donate yellow cloth, books, or gold on Thursdays (Brihaspati Vrat).",
            "Recite Guru Stotram or Vishnu Sahasranama.",
            "Show reverence to teachers, elders, and spiritual guides.",
        ],
    },
    "Venus": {
        "deity": "Goddess Lakshmi / Shukra Deva",
        "mantra": "Om Draam Dreem Draum Sah Shukraya Namah",
        "practices": [
            "Offer white flowers, milk sweets, and lotus to Lakshmi on Fridays.",
            "Donate white rice, sugar, dairy, or silk on Fridays.",
            "Recite Lakshmi Ashtakam or Shri Suktam.",
            "Keep your home and workspace clean, fragrant, and aesthetically pleasing.",
        ],
    },
    "Saturn": {
        "deity": "Shani Deva",
        "mantra": "Om Praam Preem Praum Sah Shanaischaraya Namah",
        "practices": [
            "Light a sesame oil (til tel) lamp under a Peepal tree on Saturdays.",
            "Donate black sesame seeds, iron, mustard oil, or dark blue cloth on Saturdays.",
            "Recite Shani Stotram, Shani Chalisa, or Shani Kavach.",
            "Serve the poor, elderly, or disabled — Saturn rewards sincere service.",
        ],
    },
    "Rahu": {
        "deity": "Goddess Durga / Kaal Bhairav",
        "mantra": "Om Bhraam Bhreem Bhraum Sah Rahave Namah",
        "practices": [
            "Offer blue flowers and durva grass on Saturdays or Rahu Kaal period.",
            "Recite Durga Kavach or Kalabhairav Ashtakam for protection.",
            "Donate black sesame, mustard, or dark blue cloth on Saturdays.",
            "Avoid impulsive decisions; counter Rahu's restlessness through daily meditation.",
        ],
    },
    "Ketu": {
        "deity": "Lord Ganesha / Skanda",
        "mantra": "Om Sraam Sreem Sraum Sah Ketave Namah",
        "practices": [
            "Worship Lord Ganesha with durva grass and modak on Tuesdays or Chaturthi.",
            "Recite Ganesha Atharvashirsha for inner clarity and spiritual discernment.",
            "Donate multi-coloured cloth, sesame, or blankets to the needy.",
            "Practice silent meditation and detachment from outcome — Ketu rewards inner work.",
        ],
    },
}


def _compute_sign_changes(graha_gochar: dict, base_jd: float) -> dict:
    """Estimate days until each planet changes sign. The result is a pure function
    of base_jd (positions come from get_all_planet_positions at base_jd and +7;
    graha_gochar supplies only the always-identical planet key set), so it is
    memoized per base_jd. This is ~30% of personalized monthly compute. A deepcopy
    is returned so the read-only consumers can never corrupt the cache."""
    cache_key = ("signchg", round(float(base_jd), 6))
    return copy.deepcopy(_scan_cache_get_or_compute(
        cache_key, lambda: _compute_sign_changes_uncached(graha_gochar, base_jd)
    ))


def _compute_sign_changes_uncached(graha_gochar: dict, base_jd: float) -> dict:
    _SKIP = {"Saturn"}  # retrogrades before next ingress; linear extrapolation fails
    try:
        pos_today = get_all_planet_positions(TS.tt_jd(base_jd))
        pos_7 = get_all_planet_positions(TS.tt_jd(base_jd + 7.0))
    except Exception:
        return {}

    result = {}
    for planet in graha_gochar:
        if planet in _SKIP:
            continue
        try:
            cur_lon = float(pos_today[planet]["longitude"])
            lon_7   = float(pos_7[planet]["longitude"])
            motion_7 = lon_7 - cur_lon
            if motion_7 > 180:
                motion_7 -= 360
            elif motion_7 < -180:
                motion_7 += 360

            daily_motion = motion_7 / 7.0
            if abs(daily_motion) < 1e-6:
                continue

            if daily_motion > 0:
                degrees_left = 30.0 - (cur_lon % 30.0)
                next_idx = (int(cur_lon // 30) + 1) % 12
            else:
                degrees_left = cur_lon % 30.0
                next_idx = (int(cur_lon // 30) - 1) % 12

            days = max(1, round(degrees_left / abs(daily_motion)))
            result[planet] = {"days": days, "next_sign": rashi_names[next_idx]}
        except Exception:
            continue
    return result


def _personalized_transits(rashi, graha_gochar, sign_changes=None):
    if not rashi or not graha_gochar:
        return []
    base_idx = rashi_names.index(rashi)
    sc = sign_changes or {}
    output = []
    for planet, info in graha_gochar.items():
        trans_rashi = info.get("rashi")
        if trans_rashi not in rashi_names:
            continue
        house = ((rashi_names.index(trans_rashi) - base_idx) % 12) + 1
        house_theme = HOUSE_THEMES.get(house, "key life areas")
        planet_effect = PLANET_TRANSIT_EFFECT.get(planet, "shifts the tone of this house")
        change = sc.get(planet, {})
        output.append({
            "planet": planet,
            "transit_rashi": trans_rashi,
            "house_from_rashi": house,
            "house_theme": house_theme,
            "planet_effect": planet_effect,
            "days_until_sign_change": change.get("days"),
            "next_sign": change.get("next_sign"),
            "pooja_practices": TRANSIT_POOJA_PRACTICES.get(planet, {}),
            "message": (
                f"{planet} transiting {trans_rashi} is in your house {house}. "
                f"It activates {house_theme} and {planet_effect}."
            )
        })
    output.sort(key=lambda x: (x["house_from_rashi"], PLANET_PRIORITY.get(x["planet"], 99)))
    return output


def _personalized_transits_from_kundali(kundali_result, graha_gochar, sign_changes=None):
    # Vedic Gochar tradition: count transit houses from Janma Rashi (natal Moon sign),
    # not from Lagna. Fall back to Lagna only if Moon sign is unavailable.
    base_rashi = (
        _extract_rashi_name((kundali_result or {}).get("rashi"))
        or _extract_rashi_name((kundali_result or {}).get("lagna"))
    )
    if not base_rashi:
        return []

    natal_house_map = _build_natal_house_map(kundali_result)
    sc = sign_changes or {}
    output = []
    base_idx = rashi_names.index(base_rashi)
    for planet, info in (graha_gochar or {}).items():
        trans_rashi = (info or {}).get("rashi")
        if trans_rashi not in rashi_names:
            continue
        house = ((rashi_names.index(trans_rashi) - base_idx) % 12) + 1
        natal_info = natal_house_map.get(planet, {})
        natal_house = natal_info.get("natal_house")
        natal_sign = natal_info.get("natal_sign")
        movement_text = ""
        if natal_house:
            movement_text = f" In your birth chart, {planet} is in house {natal_house} ({natal_sign or 'natal sign unavailable'})."
        change = sc.get(planet, {})
        output.append({
            "planet": planet,
            "transit_rashi": trans_rashi,
            "house_from_rashi": house,
            "house_theme": HOUSE_THEMES.get(house, "key life areas"),
            "planet_effect": PLANET_TRANSIT_EFFECT.get(planet, "shifts the tone of this house"),
            "natal_house": natal_house,
            "natal_sign": natal_sign,
            "days_until_sign_change": change.get("days"),
            "next_sign": change.get("next_sign"),
            "pooja_practices": TRANSIT_POOJA_PRACTICES.get(planet, {}),
            "message": (
                f"{planet} transiting {trans_rashi} is in your house {house}.{movement_text} "
                f"It activates {HOUSE_THEMES.get(house, 'key life areas')}."
            ).strip(),
        })

    output.sort(key=lambda x: (x["house_from_rashi"], PLANET_PRIORITY.get(x["planet"], 99)))
    return output


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _extract_rashi_name(value):
    if not value:
        return None
    plain = str(value).split("(", 1)[0].strip()
    return _normalize_rashi(plain)


# Process-local cache of successful kundali reports, keyed on the exact request
# payload plus a UTC day stamp. The upstream report only changes day-to-day at
# the resolution this API exposes (mahadasha/antardasha span months/years), so a
# same-day cache returns identical data while avoiding a repeated blocking POST.
# Only successful responses are cached, so transient failures still retry exactly
# as before.
_KUNDALI_CACHE = {}
_KUNDALI_CACHE_LOCK = threading.Lock()
_KUNDALI_CACHE_MAX = 2048


def _fetch_kundali_report(birth_details, fallback_tz_name, person_name=None):
    required = ["date_of_birth", "time_of_birth", "birth_latitude", "birth_longitude"]
    if not birth_details or any(birth_details.get(k) in (None, "") for k in required):
        return {"ok": False, "status": "birth_details_not_provided", "result": None}

    time_str = str(birth_details.get("time_of_birth", "")).strip()
    if len(time_str) == 5:
        time_str = f"{time_str}:00"

    # The birth chart MUST use the BIRTH location's timezone, not the user's
    # current-location timezone. Prefer an explicit birth_timezone; otherwise
    # derive it from the birth coordinates. Only fall back to the current-location
    # tz (fallback_tz_name) as a last resort if that derivation fails — sending the
    # current tz with foreign birth coordinates produces a wrong chart (e.g. a US
    # birth read with an India timezone).
    birth_tz = birth_details.get("birth_timezone")
    if not birth_tz:
        try:
            birth_tz = cached_timezone_str(
                round_coord(float(birth_details.get("birth_latitude"))),
                round_coord(float(birth_details.get("birth_longitude"))),
            )
        except Exception:
            birth_tz = None
    birth_tz = birth_tz or fallback_tz_name or "Asia/Kathmandu"

    payload = {
        "name": person_name or "Panchanga User",
        "date": str(birth_details.get("date_of_birth")).strip(),
        "time": time_str,
        "latitude": str(birth_details.get("birth_latitude")).strip(),
        "longitude": str(birth_details.get("birth_longitude")).strip(),
        "timezone": birth_tz,
        "user_currency": str(birth_details.get("user_currency") or "INR"),
    }

    # Cache key: full payload (sorted) + current UTC day → refreshes daily.
    cache_key = (
        tuple(sorted(payload.items())),
        datetime.now(pytz.utc).strftime("%Y-%m-%d"),
    )
    with _KUNDALI_CACHE_LOCK:
        cached = _KUNDALI_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        # data=<exact bytes> (not json=) so the request body is byte-identical to
        # the previous urllib call; raise_for_status() mirrors urllib raising on
        # non-2xx, keeping the kundali_api_error path unchanged.
        response = HTTP_SESSION.post(
            KUNDALI_REPORT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=KUNDALI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        raw = response.content.decode("utf-8")
        parsed = json.loads(raw or "{}")
        if not parsed.get("ok") or not isinstance(parsed.get("result"), dict):
            return {"ok": False, "status": "kundali_api_failed", "result": None}
        result = {"ok": True, "status": "ok", "result": parsed.get("result")}
    except Exception:
        return {"ok": False, "status": "kundali_api_error", "result": None}

    # Cache successful results only (failures keep retrying as before).
    with _KUNDALI_CACHE_LOCK:
        if len(_KUNDALI_CACHE) >= _KUNDALI_CACHE_MAX:
            _KUNDALI_CACHE.clear()
        _KUNDALI_CACHE[cache_key] = result
    return result


def _build_natal_house_map(kundali_result):
    house_map = {}
    planets_in_houses = (kundali_result or {}).get("planets_in_houses") or {}
    for house_key, planets in planets_in_houses.items():
        if not isinstance(planets, list):
            continue
        house_num = HOUSE_NAME_TO_NUM.get(house_key)
        if not house_num:
            continue
        for p in planets:
            pname = (p or {}).get("name")
            if pname:
                house_map[pname] = {
                    "natal_house": house_num,
                    "natal_sign": (p or {}).get("sidereal_sign"),
                }
    return house_map


def _derive_rashi_from_birth_details(birth_details, fallback_tz_name):
    required = ["date_of_birth", "time_of_birth", "birth_latitude", "birth_longitude"]
    if not birth_details or any(birth_details.get(k) in (None, "") for k in required):
        return None
    try:
        birth_dt = datetime.strptime(
            f"{birth_details['date_of_birth']} {birth_details['time_of_birth']}",
            "%Y-%m-%d %H:%M",
        )
        tz_name = birth_details.get("birth_timezone") or fallback_tz_name
        tz = pytz.timezone(tz_name)
        local_dt = tz.localize(birth_dt)
        t_birth = TS.from_datetime(local_dt.astimezone(pytz.utc))
        _, moon_sid = get_sidereal_lons_geocentric(t_birth)
        moon_sid = float(np.atleast_1d(moon_sid)[0])
        return rashi_names[int(moon_sid // 30) % 12]
    except Exception:
        return None


PLANET_HOUSE_INSIGHT = {
    ("Saturn", 1):  "Saturn transiting the 1st house demands long-term self-discipline; health routines and lifestyle restructuring become important.",
    ("Saturn", 4):  "Saturn here can create domestic responsibilities or property-related delays; steady effort at home brings eventual stability.",
    ("Saturn", 7):  "Saturn in the 7th brings karmic lessons through partnerships; patience in relationships is tested and rewarded over time.",
    ("Saturn", 8):  "Deep restructuring of shared resources and hidden matters; longevity improves with honest self-examination.",
    ("Saturn", 10): "Career advancement requires consistent diligence; authority recognition arrives slowly but durably.",
    ("Saturn", 12): "A period of karmic closure; old debts and unresolved patterns surface for resolution.",
    ("Jupiter", 1): "Personal wisdom, vitality, and confidence expand; a generally auspicious period for new beginnings.",
    ("Jupiter", 4): "Blessings flow into home, family, and emotional foundations; property and domestic happiness improve.",
    ("Jupiter", 5): "Strongly favors creative output, children, education, and sharp intelligence; one of the best transit positions.",
    ("Jupiter", 7): "Partnership and marriage prospects improve; existing relationships can grow with shared purpose.",
    ("Jupiter", 9): "Peak dharmic support — luck, long-distance opportunity, and spiritual guidance align simultaneously.",
    ("Jupiter", 10): "Career recognition, ethical leadership, and professional expansion are well-supported.",
    ("Jupiter", 11): "Gains, wish-fulfillment, and fruitful networking reach a positive peak.",
    ("Mars", 1):   "High physical drive and assertiveness; channel energy productively and avoid unnecessary confrontations.",
    ("Mars", 8):   "Sudden changes and unexpected disruptions are possible; avoid risky physical activities and speculative investments.",
    ("Mars", 10):  "Ambition surges and career actions accelerate; guard against impulsiveness with superiors.",
    ("Rahu", 1):   "Strong transformation of self-image and identity; ambition rises but requires ethical grounding.",
    ("Rahu", 10):  "Unconventional career opportunities may open; be cautious of shortcuts that compromise reputation.",
    ("Rahu", 7):   "Complex relationship dynamics may surface; watch for deception in partnerships.",
    ("Ketu", 5):   "Detachment from past creative or romantic patterns; a good period for spiritual study.",
    ("Ketu", 12):  "Strong karmic connection to liberation; spiritual growth, foreign links, and closure of past-life patterns.",
    ("Venus", 7):  "Romance, partnership harmony, and relationship milestones tend to peak during this transit.",
    ("Venus", 2):  "Financial comfort, family harmony, and aesthetic pleasures are favored.",
    ("Sun", 10):   "Leadership visibility and public recognition are at their peak; use authority responsibly and honestly.",
    ("Sun", 1):    "Identity and ego themes dominate; leadership energy is high but must be directed carefully.",
}

def _detailed_transit_prediction(planet, transit_rashi, house):
    intro = f"{planet.upper()} is in {transit_rashi} in your {_ordinal(house)} House."
    favorable_houses = {1, 2, 3, 5, 6, 9, 10, 11}
    difficult_houses = {4, 7, 8, 12}
    benefics = {"Jupiter", "Venus", "Moon", "Mercury"}
    malefics = {"Saturn", "Rahu", "Ketu", "Mars", "Sun"}

    score = 0
    if house in favorable_houses:
        score += 1
    if house in difficult_houses:
        score -= 1
    if planet in benefics:
        score += 1
    if planet in malefics:
        score -= 1

    if score >= 1:
        tone = "good"
    elif score <= -1:
        tone = "bad"
    else:
        tone = "mixed"

    opening_by_tone = {
        "good": [
            "A very supportive and progressive period is opening for you.",
            "This looks like a rewarding phase with visible progress and good momentum.",
        ],
        "bad": [
            "This can be a difficult and sensitive period, so stay alert and composed.",
            "This is a challenging phase and may bring pressure if decisions are rushed.",
        ],
        "mixed": [
            "This is a mixed period where discipline will decide outcomes.",
            "Results can be moderate in this phase, with both opportunities and caution points.",
        ],
    }

    house_good = {
        1: "Your confidence and initiative can rise, and people may notice your presence.",
        2: "Money planning, savings discipline, and practical family decisions can improve stability.",
        3: "Efforts, communication, and short travels can bring encouraging movement.",
        4: "Inner balance is possible through calm home routines and emotional maturity.",
        5: "Creative output, studies, and intelligent decisions can support success.",
        6: "You may overcome competitors and manage pending workload with strength.",
        7: "Partnership matters can improve through patience, respect, and direct communication.",
        8: "With maturity, this period can deepen insight and strengthen resilience.",
        9: "Luck, guidance, and long-distance opportunities can support you well.",
        10: "Career growth, recognition, and support from seniors may increase.",
        11: "Gains, networking, and fulfillment of key goals are strongly indicated.",
        12: "Spiritual growth, closure, and inner healing can become meaningful themes.",
    }
    house_bad = {
        1: "Mood swings and impatience can affect judgment if reactions are not controlled.",
        2: "Financial leakage, harsh speech, and family tension need careful handling.",
        3: "Communication gaps, ego clashes, and unproductive travel can create stress.",
        4: "Domestic unease and emotional restlessness may disturb peace at home.",
        5: "Speculation, romance misunderstandings, or children-related worry may rise.",
        6: "Health strain and work pressure may increase if routine is neglected.",
        7: "Relationship friction, partner stress, or contract disputes may surface.",
        8: "Sudden obstacles, anxiety, and vulnerability in plans may trouble you.",
        9: "Luck may feel delayed; travel and mentor-related plans can face hurdles.",
        10: "Professional pressure, authority conflicts, or reputation risks need caution.",
        11: "Expected gains may slow, and social misunderstandings can create disappointment.",
        12: "Expenses, sleep disturbance, and mental overthinking can increase.",
    }
    house_mixed = {
        1: "Personal focus sharpens when inner resistance is acknowledged alongside your strengths.",
        2: "Financial management and family communication need balance — steady, measured effort pays off.",
        3: "Communication and short efforts produce moderate movement; filter carefully before acting.",
        4: "Domestic rhythms may be uneven; emotional steadiness rather than forced change helps most.",
        5: "Creative and intellectual potential is real but needs realistic expectations to fully open.",
        6: "Work demands and health routine need balanced attention — neither can be ignored for long.",
        7: "Partnerships require clear expectations; neither forcing closeness nor withdrawing serves well.",
        8: "Hidden matters and transitions unfold; composed engagement avoids unnecessary turbulence.",
        9: "Guidance and opportunity are available but may come with conditions or timing delays.",
        10: "Professional progress is possible but not automatic; disciplined effort is the deciding factor.",
        11: "Partial gains are likely; selective networking and quality over quantity improve outcomes.",
        12: "Reflection is productive; avoid excessive isolation while allowing necessary rest.",
    }

    planet_good = {
        "Sun": "Leadership energy is strong; used wisely, it can improve influence and authority.",
        "Moon": "Emotional intuition can become a strength and improve your public rapport.",
        "Mars": "You may feel bold and action-oriented, helping you defeat delays and opposition.",
        "Mercury": "Smart planning and communication can unlock useful opportunities.",
        "Jupiter": "This supports growth, blessings, guidance, and ethical progress.",
        "Venus": "Relationship harmony, comfort, and attraction factors can improve.",
        "Saturn": "Consistent effort can produce lasting and practical results.",
        "Rahu": "Strategic ambition can open unconventional opportunities when handled ethically.",
        "Ketu": "Spiritual clarity and sharper inner judgment can improve your decision quality.",
    }
    planet_bad = {
        "Sun": "Ego clashes with seniors or authority figures should be strictly avoided.",
        "Moon": "Emotional instability may cloud decisions, so avoid impulsive reactions.",
        "Mars": "Anger, argument, or rash actions can damage progress if not controlled.",
        "Mercury": "Miscommunication and financial misjudgment can create avoidable issues.",
        "Jupiter": "Overconfidence or excessive optimism can lead to impractical choices.",
        "Venus": "Attachment, indulgence, or relationship imbalance may invite trouble.",
        "Saturn": "Delays and pressure can test patience; persistence is required.",
        "Rahu": "Confusion, over-risk, and reputation-sensitive behavior need close monitoring.",
        "Ketu": "Detachment from practical duties can hurt outcomes if basics are ignored.",
    }

    caution_line = {
        "good": "Stay grounded and disciplined so this positive phase gives full results.",
        "bad": "Avoid risky decisions, control temper, and protect health and reputation.",
        "mixed": "Take measured actions, avoid extremes, and focus on consistency over speed.",
    }

    opening = _stable_pick(opening_by_tone[tone], f"{planet}:{house}:tone")
    if tone == "good":
        body = f"{house_good.get(house, '')} {planet_good.get(planet, '')}"
    elif tone == "bad":
        body = f"{house_bad.get(house, '')} {planet_bad.get(planet, '')}"
    else:
        body = f"{house_mixed.get(house, '')} {planet_good.get(planet, '')}"

    specific = PLANET_HOUSE_INSIGHT.get((planet, house), "")
    insight_part = f" {specific}" if specific else ""

    return f"{intro} {opening} {body}{insight_part} {caution_line[tone]}".replace("  ", " ").strip()


def _build_real_horoscope_from_transits(rashi, day_data, personalized_transits, person_name=None, kundali_result=None):
    if not rashi:
        return None
    base = _build_horoscope_for_rashi(rashi, day_data)
    core = [t for t in personalized_transits if t["planet"] in ("Saturn", "Jupiter", "Rahu", "Ketu", "Sun", "Moon", "Mars")]
    top = core[:4] if core else personalized_transits[:4]
    if not top:
        base["title"] = f"{base['sanskrit']} Rashifal | {base['rashi']} Prediction"
        base["subtitle"] = f"{base['sanskrit']} Rashi"
        base["intro"] = "Know what Nepa Rudraksha predicts for the day."
        base["chandrabalam"] = "Neutral"
        base["prediction"] = "Today is moderate. Stay calm, complete essentials, and avoid rushed decisions."
        base["message"] = base["prediction"]
        return base

    positive = 0
    caution = 0
    for t in top:
        p = t["planet"]
        h = t["house_from_rashi"]
        if p in ("Jupiter", "Venus") or h in (1, 5, 9, 10, 11):
            positive += 1
        if p in ("Saturn", "Rahu", "Ketu", "Mars") or h in (6, 8, 12):
            caution += 1

    signals = _transit_signal_for_horoscope(personalized_transits)
    transit_signature = "|".join(
        [f"{t['planet']}:{t['transit_rashi']}:{t['house_from_rashi']}" for t in top]
    )
    seed_base = f"{day_data.get('date','')}|{rashi}|{transit_signature}"
    lines = _compose_prediction_lines(rashi, signals, seed_base)
    if isinstance(kundali_result, dict):
        current_mahadasha = (kundali_result.get("current_mahadasha") or {}).get("name")
        current_antardasha = (kundali_result.get("current_antardasha") or {}).get("name")
        if current_mahadasha and current_antardasha:
            lines.append(
                f"You are running {current_mahadasha}-{current_antardasha} dasha, so keep decisions practical and disciplined."
            )

    if positive >= caution + 1:
        chandrabalam = "Thumbs Up"
    elif caution >= positive + 2:
        chandrabalam = "Thumbs Down"
    else:
        chandrabalam = "Mixed"

    who = f"{person_name} — " if person_name else ""
    prediction = " ".join(lines)
    base["title"] = f"{base['sanskrit']} Rashifal | {base['rashi']} Prediction"
    base["subtitle"] = f"{base['sanskrit']} Rashi"
    base["intro"] = f"{who}know what Nepa Rudraksha predicts for the day."
    base["chandrabalam"] = chandrabalam
    base["prediction"] = prediction
    base["message"] = prediction
    base["key_points"] = lines
    return base


def build_app_response(day_data, upcoming_spiritual_events, rashi=None, person_name=None, birth_details=None, fallback_tz_name="Asia/Kathmandu", upcoming_poojas=None, precomputed_kundali_data=None, precomputed_general_horoscope=None):
    """App-only response payload so existing root fields remain unchanged."""
    festivals = _clean_event_list(day_data.get("festival_today"))
    vratas = _clean_event_list(day_data.get("vrata_today"))
    primary_event = (festivals + vratas + [day_data.get("tithi", "Spiritual Day")])[0]
    today_guidance = _event_guidance(primary_event, day_data.get("paksha"))
    pooja = next((p for p in (day_data.get("pooja_today") or []) if p.get("name") != "None"), None)
    if pooja:
        pooja_brief = {
            "id": pooja.get("id"),
            "name": pooja.get("name"),
            "reason": pooja.get("reason", ""),
            "variant_id": pooja.get("variant_id"),
            "event_context": primary_event,
            "date": day_data.get("date"),
        }
    else:
        pooja_brief = {"id": None, "name": "None", "reason": "", "variant_id": None, "event_context": primary_event, "date": day_data.get("date")}
    requested_rashi = _normalize_rashi(rashi)
    if precomputed_kundali_data is not None:
        kundali_data = precomputed_kundali_data
    else:
        kundali_data = _fetch_kundali_report(birth_details or {}, fallback_tz_name, person_name)
    kundali_result = kundali_data.get("result") if kundali_data.get("ok") else None

    graha_gochar = day_data.get("graha_gochar") or {}
    # Compute sign changes once (one extra planet position call at JD+1)
    try:
        date_str = day_data.get("date", "")
        base_jd = float(TS.from_datetime(
            pytz.timezone(fallback_tz_name).localize(
                datetime.strptime(date_str, "%Y-%m-%d").replace(hour=12)
            ).astimezone(pytz.utc)
        ).tt) if date_str else None
    except Exception:
        base_jd = None
    sign_changes = _compute_sign_changes(graha_gochar, base_jd) if base_jd else {}

    personalized_transits = _personalized_transits_from_kundali(kundali_result, graha_gochar, sign_changes)
    # Mirror the Janma Rashi-first priority used in _personalized_transits_from_kundali
    transit_base_rashi = (
        _extract_rashi_name((kundali_result or {}).get("rashi"))
        or _extract_rashi_name((kundali_result or {}).get("lagna"))
    )
    effective_horoscope_rashi = requested_rashi or transit_base_rashi

    # Fall back to rashi-based transits when no kundali is available
    if not personalized_transits and effective_horoscope_rashi:
        personalized_transits = _personalized_transits(effective_horoscope_rashi, graha_gochar, sign_changes)

    for t in personalized_transits:
        t["detailed_prediction"] = _detailed_transit_prediction(
            t.get("planet"), t.get("transit_rashi"), int(t.get("house_from_rashi", 0) or 0)
        )

    real_today_horoscope = _build_real_horoscope_from_transits(
        effective_horoscope_rashi,
        day_data,
        _personalized_transits(effective_horoscope_rashi, graha_gochar, sign_changes),
        person_name,
        kundali_result,
    ) if effective_horoscope_rashi else {
        "status": "no_rashi_provided",
        "message": "No rashi provided and kundali rashi unavailable. Send `rashi` or full birth details.",
    }

    if precomputed_general_horoscope is not None:
        general_all = precomputed_general_horoscope
    else:
        general_all = []
        for item_rashi in rashi_names:
            r_transits = _personalized_transits(item_rashi, graha_gochar, sign_changes)
            general_all.append(_build_real_horoscope_from_transits(item_rashi, day_data, r_transits))

    return {
        "today_spiritual_guidance": {
            "title": primary_event,
            "date": day_data.get("date"),
            "day": day_data.get("day_of_week"),
            "deity": _event_deity(primary_event, day_data.get("paksha")),
            "muhurat_hint": (day_data.get("subh_muhurat") or [{}])[0],
            "why_it_matters": today_guidance["why_it_matters"],
            "who_should_use_it": today_guidance["who_should_use_it"],
            "recommended_practices": today_guidance["recommended_practices"],
            "avoid_practices": today_guidance["avoid_practices"],
            "suggested_pooja_for_the_day": pooja_brief,
        },
        "upcoming_spiritual_events_week": upcoming_spiritual_events,
        "upcoming_poojas": _filter_upcoming_poojas_window(
            upcoming_poojas or [],
            day_data.get("date"),
            min_day=3,
            max_day=7,
        ),
        "personalized_pooja_recommendations": get_kundali_pooja_recommendations(
            kundali_result, birth_details, day_data
        ),
        "personalized_planetary_transits": personalized_transits,
        "today_horoscope": real_today_horoscope,
        "general_horoscope_all_rashi": general_all,
        "recommended_mantras": day_data.get("recommended_mantras") or [],
        "personalization_meta": {
            "effective_rashi_for_horoscope": effective_horoscope_rashi,
            "horoscope_status": "ok" if effective_horoscope_rashi else "no_rashi_provided",
            "personalized_transit_base_rashi": transit_base_rashi,
            "personalized_transit_reference": "lagna_or_rashi",
            "personalized_transit_status": "ok" if transit_base_rashi else kundali_data.get("status"),
            "kundali_source": "recommendation.nepalirudraksha.com/api/astro/report",
            "kundali_api_status": kundali_data.get("status"),
            "required_birth_details_for_personalized_transits": [
                "date_of_birth (YYYY-MM-DD)",
                "time_of_birth (HH:MM or HH:MM:SS, 24h)",
                "birth_latitude",
                "birth_longitude",
                "birth_timezone (optional)"
            ] if not transit_base_rashi else [],
        },
    }


def order_day_payload(d):
    """Return a stable key order for day-level payloads."""
    return {
        "date": d.get("date"),
        "day_of_week": d.get("day_of_week"),
        "time_zone": d.get("time_zone"),
        "month_system": d.get("month_system"),
        "tithi": d.get("tithi"),
        "tithi_number": d.get("tithi_number"),
        "tithi_nature": d.get("tithi_nature"),
        "tithi_nature_significance": d.get("tithi_nature_significance"),
        "tithi_end": d.get("tithi_end"),
        "paksha": d.get("paksha"),
        "nakshatra": d.get("nakshatra"),
        "nakshatra_pada": d.get("nakshatra_pada"),
        "nakshatra_lord": d.get("nakshatra_lord"),
        "nakshatra_deity": d.get("nakshatra_deity"),
        "nakshatra_pada_significance": d.get("nakshatra_pada_significance"),
        "nakshatra_end": d.get("nakshatra_end"),
        "yoga": d.get("yoga"),
        "yoga_end": d.get("yoga_end"),
        "karana": d.get("karana"),
        "karana_end": d.get("karana_end"),
        "moon_sign": d.get("moon_sign"),
        "sun_sign": d.get("sun_sign"),
        "ritu": d.get("ritu"),
        "amanta_month": d.get("amanta_month"),
        "purnimanta_month": d.get("purnimanta_month"),
        "adhik_maas": d.get("adhik_maas"),
        "vikram_samvat": d.get("vikram_samvat"),
        "shaka_samvat": d.get("shaka_samvat"),
        "sunrise": d.get("sunrise"),
        "sunset": d.get("sunset"),
        "moonrise": d.get("moonrise"),
        "moonset": d.get("moonset"),
        "day_duration": d.get("day_duration"),
        "subh_muhurat": d.get("subh_muhurat"),
        "asubh_muhurat": d.get("asubh_muhurat"),
        "amrit_kaal": d.get("amrit_kaal"),
        "durmuhurta": d.get("durmuhurta"),
        "varjyam": d.get("varjyam"),
        "choghadiya": d.get("choghadiya"),
        "festival_today": d.get("festival_today"),
        "vrata_today": d.get("vrata_today"),
        "pooja_today": d.get("pooja_today"),
        "graha_gochar": d.get("graha_gochar"),
        "significance": d.get("significance"),
        "daily_summary": d.get("daily_summary"),
        "sun_moon_angle": d.get("sun_moon_angle"),
        "sun_sidereal": d.get("sun_sidereal"),
    }


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


# --- Festival content table (A2) ---------------------------------------------
# Curated, festival-SPECIFIC copy so a notification never describes a generic
# paksha when it should describe the actual festival. Keyed by the exact name
# used in `festival_mapping`. Looked up first; `_event_guidance` is the fallback.
#
#   description       — 1–2 sentences, factual, shown in the app detail view.
#   why_it_matters    — one punchy sentence; drives the notification tap.
#   recommended_mukhi — traditional deity→Rudraksha association. THESE ARE
#                       DEFAULTS — confirm against the Nepa Rudraksha catalogue.
#   blog_url          — left None; fill with the real blog link per festival.
FESTIVAL_CONTENT = {
    # ---- Secular / national / solar fixed-date ----
    "Makar Sankranti": {"description": "Makar Sankranti marks the Sun's entry into Capricorn (Makara) and the start of its northward journey (Uttarayana). It is a harvest festival celebrated with til-gud, kite-flying, and holy river dips.", "why_it_matters": "The Sun turns northward — an auspicious turning point for new beginnings and Surya worship.", "recommended_mukhi": "12"},
    "International Yoga Day": {"description": "International Yoga Day celebrates yoga's gift of physical, mental, and spiritual wellbeing. It falls on the summer solstice, the longest day of the year.", "why_it_matters": "A global day to reset body and mind through yoga and breath.", "recommended_mukhi": None},
    "Lohri": {"description": "Lohri is a Punjabi winter harvest festival celebrated around a bonfire with songs, dance, and offerings of til, gud, and popcorn to the fire.", "why_it_matters": "A bonfire festival marking the end of peak winter and the coming harvest.", "recommended_mukhi": None},
    "Pongal": {"description": "Pongal is the four-day Tamil harvest festival thanking the Sun god for a bountiful crop, celebrated by boiling the season's first rice.", "why_it_matters": "A Tamil thanksgiving to Surya for the harvest's abundance.", "recommended_mukhi": "12"},
    "Magh Bihu": {"description": "Magh Bihu (Bhogali Bihu) is Assam's harvest festival of feasting and community bonfires (Meji), marking the end of the harvesting season.", "why_it_matters": "Assam's harvest feast — gratitude, fire, and community.", "recommended_mukhi": None},
    "Republic Day (India)": {"description": "Republic Day commemorates the day the Constitution of India came into effect in 1950.", "why_it_matters": "India honours the Constitution and its republic.", "recommended_mukhi": None},
    "Independence Day (India)": {"description": "Independence Day marks India's freedom from colonial rule in 1947.", "why_it_matters": "India celebrates its freedom and unity.", "recommended_mukhi": None},
    "Gandhi Jayanti": {"description": "Gandhi Jayanti honours the birth of Mahatma Gandhi and his message of truth and non-violence.", "why_it_matters": "A day of truth, non-violence, and service.", "recommended_mukhi": None},
    "Christmas": {"description": "Christmas celebrates the birth of Jesus Christ with worship, family gatherings, and giving.", "why_it_matters": "A day of peace, giving, and togetherness.", "recommended_mukhi": None},

    # ---- Magha ----
    "Vasant Panchami": {"description": "Vasant Panchami heralds spring and is dedicated to Goddess Saraswati, the deity of knowledge, music, and arts. Devotees wear yellow and bless books and instruments.", "why_it_matters": "Saraswati's day — ideal to begin learning, music, or any new study.", "recommended_mukhi": "4"},
    "Ratha Saptami": {"description": "Ratha Saptami marks the Sun god turning his chariot northward and is observed with dawn river baths and Surya arghya for health and vitality.", "why_it_matters": "A Surya festival for health, vitality, and radiant energy.", "recommended_mukhi": "12"},
    "Magha Purnima": {"description": "Magha Purnima is the full moon of Magha, considered highly meritorious for holy dips, charity, and Satyanarayan puja.", "why_it_matters": "A full moon prized for sacred bathing, charity, and merit.", "recommended_mukhi": "10"},
    "Mauni Amavasya": {"description": "Mauni Amavasya is the new moon of Magha observed in silence (mauna), with holy river baths — the most sacred bathing day of the Kumbh.", "why_it_matters": "The holiest bathing day — silence, sacred dips, and inner stillness.", "recommended_mukhi": None},

    # ---- Phalguna ----
    "Maha Shivaratri": {"description": "Maha Shivaratri, 'the Great Night of Shiva,' is the most important Shaivite festival. Devotees observe night-long vigil, fasting, and continuous Shiva worship with bilva, milk, and Om Namah Shivaya.", "why_it_matters": "Shiva's greatest night — night-long worship for liberation and inner awakening.", "recommended_mukhi": "1"},
    "Holika Dahan": {"description": "Holika Dahan is the eve of Holi when bonfires are lit to celebrate the burning of Holika and the triumph of devotion over evil.", "why_it_matters": "The bonfire of good over evil, on the eve of Holi.", "recommended_mukhi": None},
    "Holi": {"description": "Holi is the festival of colours marking the arrival of spring and the victory of good over evil, celebrated with colours, sweets, and joy.", "why_it_matters": "The festival of colours — joy, renewal, and the win of good over evil.", "recommended_mukhi": None},
    "Rang Panchami": {"description": "Rang Panchami, observed five days after Holi in some regions, is a day of colour-play believed to invoke divine energies.", "why_it_matters": "A second day of colour, invoking divine vibrancy.", "recommended_mukhi": None},

    # ---- Chaitra ----
    "Chaitra Navratri Begins": {"description": "Chaitra Navratri begins the nine-day worship of Goddess Durga's nine forms in spring, often culminating in Rama Navami.", "why_it_matters": "Nine nights of Shakti worship begin — strength, protection, and renewal.", "recommended_mukhi": "9"},
    "Gudi Padwa": {"description": "Gudi Padwa is the Marathi New Year, marked by raising the auspicious 'gudi' flag for prosperity and victory.", "why_it_matters": "The Marathi New Year — a fresh start raised on the gudi.", "recommended_mukhi": None},
    "Ugadi": {"description": "Ugadi is the New Year for Andhra, Karnataka, and Telangana, welcomed with the six-flavoured Ugadi pachadi symbolising life's blend of experiences.", "why_it_matters": "A South Indian New Year — embracing all of life's flavours.", "recommended_mukhi": None},
    "Rama Navami": {"description": "Rama Navami celebrates the birth of Lord Rama, the seventh avatar of Vishnu, with Ramayana recitals, bhajans, and fasting.", "why_it_matters": "Lord Rama's birth — dharma, righteousness, and devotion.", "recommended_mukhi": "10"},
    "Chaitra Purnima": {"description": "Chaitra Purnima is the first full moon of the Hindu lunar year, sacred to Hanuman and Chitragupta.", "why_it_matters": "The year's first full moon — devotion to Hanuman and gratitude.", "recommended_mukhi": "11"},
    "Hanuman Jayanti": {"description": "Hanuman Jayanti celebrates the birth of Lord Hanuman, the embodiment of strength, devotion, and selfless service. Devotees recite the Hanuman Chalisa and offer sindoor.", "why_it_matters": "Hanuman's birth — for courage, strength, and protection from adversity.", "recommended_mukhi": "11"},

    # ---- Vaishakha ----
    "Akshaya Tritiya": {"description": "Akshaya Tritiya is one of the most auspicious days of the year — 'akshaya' means never-diminishing. Any venture, investment, or charity begun today is believed to grow perpetually. Gold buying is traditional.", "why_it_matters": "The day of never-ending prosperity — ideal to invest, buy gold, or begin anew.", "recommended_mukhi": "7"},
    "Parashurama Jayanti": {"description": "Parashurama Jayanti marks the birth of Lord Parashurama, the sixth avatar of Vishnu, often coinciding with Akshaya Tritiya.", "why_it_matters": "The birth of Vishnu's warrior-sage avatar.", "recommended_mukhi": "10"},
    "Narasimha Jayanti": {"description": "Narasimha Jayanti celebrates Vishnu's fierce half-man, half-lion avatar who appeared to protect his devotee Prahlada and destroy evil.", "why_it_matters": "Vishnu's fierce protector form — for courage and removal of fear.", "recommended_mukhi": "10"},
    "Buddha Purnima (Vesak)": {"description": "Buddha Purnima marks the birth, enlightenment, and parinirvana of Gautama Buddha — all said to fall on this full moon. A day of meditation, compassion, and charity.", "why_it_matters": "The Buddha's day — meditation, compassion, and inner peace.", "recommended_mukhi": None},
    "Sita Navami": {"description": "Sita Navami (Janaki Navami) celebrates the appearance of Goddess Sita, observed by married women for marital harmony.", "why_it_matters": "Goddess Sita's day — devotion, purity, and marital harmony.", "recommended_mukhi": None},

    # ---- Jyeshtha ----
    "Ganga Dussehra": {"description": "Ganga Dussehra celebrates the descent of the sacred river Ganga from heaven to earth. Devotees take holy dips and offer prayers, believed to wash away ten kinds of sins.", "why_it_matters": "The day Ganga descended to earth — sacred bathing that cleanses ten sins.", "recommended_mukhi": None},
    "Nirjala Ekadashi": {"description": "Nirjala Ekadashi is the most austere of all Ekadashis, observed with a complete waterless fast. It is believed to grant the merit of all 24 Ekadashis of the year.", "why_it_matters": "The hardest Ekadashi — a waterless fast that carries the merit of all 24.", "recommended_mukhi": "10"},
    "Vat Savitri Vrat": {"description": "Vat Savitri Vrat is observed by married women who worship the banyan tree and recall Savitri's devotion that won back her husband's life, praying for their husbands' longevity.", "why_it_matters": "A wife's vrat for her husband's long life, around the sacred banyan.", "recommended_mukhi": "2"},
    "Shani Jayanti": {"description": "Shani Jayanti marks the birth of Lord Shani (Saturn). Devotees offer oil, black sesame, and prayers to pacify Saturn's karmic influence.", "why_it_matters": "Saturn's birthday — pacify Shani and ease karmic hardships.", "recommended_mukhi": "14"},
    "Jyeshtha Purnima": {"description": "Jyeshtha Purnima is the full moon of Jyeshtha, associated with Vat Purnima and Vishnu worship.", "why_it_matters": "A full moon for Vishnu worship and marital wellbeing.", "recommended_mukhi": "10"},

    # ---- Ashadha ----
    "Devshayani Ekadashi (Ashadhi Ekadashi)": {"description": "Devshayani Ekadashi begins Chaturmas, the four-month period when Lord Vishnu is said to enter cosmic sleep. A major Ekadashi for fasting and Vishnu bhakti.", "why_it_matters": "Vishnu enters cosmic sleep — the start of the sacred Chaturmas.", "recommended_mukhi": "10"},
    "Jagannath Rath Yatra": {"description": "Rath Yatra is the grand chariot festival of Lord Jagannath at Puri, when the deities are pulled through the streets on towering chariots.", "why_it_matters": "Lord Jagannath rides out — darshan that is said to liberate.", "recommended_mukhi": "10"},
    "Guru Purnima": {"description": "Guru Purnima honours the spiritual teacher (guru) and the sage Vyasa. Disciples express gratitude and seek blessings; it is the most powerful day to begin or deepen sadhana under a guru's grace.", "why_it_matters": "The day to honour your guru — discipleship, gratitude, and spiritual initiation.", "recommended_mukhi": "5"},

    # ---- Shravana ----
    "Nag Panchami": {"description": "Nag Panchami is dedicated to the serpent gods (Nagas). Devotees offer milk and prayers for protection from snake-related fears and for family wellbeing.", "why_it_matters": "Worship of the Nagas — protection, fertility, and removal of Kaal Sarp afflictions.", "recommended_mukhi": "8"},
    "Shravana Putrada Ekadashi": {"description": "Putrada Ekadashi is observed by couples praying for progeny and the wellbeing of children, with fasting and Vishnu worship.", "why_it_matters": "An Ekadashi for the blessing and protection of children.", "recommended_mukhi": "10"},
    "Varalakshmi Vratam": {"description": "Varalakshmi Vratam is observed by married women worshipping Goddess Lakshmi for prosperity, health, and family wellbeing.", "why_it_matters": "Goddess Lakshmi's vrat — for prosperity and family wellbeing.", "recommended_mukhi": "7"},
    "Raksha Bandhan": {"description": "Raksha Bandhan celebrates the bond between brothers and sisters; sisters tie a rakhi wishing protection and prosperity for their brothers.", "why_it_matters": "The sacred thread of sibling love and protection.", "recommended_mukhi": None},
    "Shravana Somvar Vrat (Mondays)": {"description": "The Mondays of Shravana are the most sacred days for Shiva worship in the year, observed with fasting, abhishekam, and Rudri paath.", "why_it_matters": "Shravan Monday — the most powerful day of the year to worship Shiva.", "recommended_mukhi": "1"},
    "Hariyali Teej": {"description": "Hariyali Teej welcomes the monsoon and is dedicated to Goddess Parvati, observed by women with swings, songs, and fasting for marital bliss.", "why_it_matters": "Parvati's monsoon festival — for love and marital happiness.", "recommended_mukhi": "Gauri Shankar"},

    # ---- Bhadrapada ----
    "Hartalika Teej": {"description": "Hartalika Teej is a rigorous fast observed by women for Goddess Parvati, commemorating her penance to win Lord Shiva, prayed for marital happiness.", "why_it_matters": "Parvati's vrat for an ideal union — devotion and marital bliss.", "recommended_mukhi": "Gauri Shankar"},
    "Ganesh Chaturthi": {"description": "Ganesh Chaturthi celebrates the birth of Lord Ganesha, the remover of obstacles. Clay idols are installed and worshipped for up to ten days before immersion.", "why_it_matters": "Ganesha's birth — the supreme day to clear obstacles and begin afresh.", "recommended_mukhi": "8"},
    "Rishi Panchami": {"description": "Rishi Panchami honours the seven great sages (Saptarishi), observed for purification and gratitude to the rishis.", "why_it_matters": "A day to honour the seven sages and seek purification.", "recommended_mukhi": None},
    "Radha Ashtami": {"description": "Radha Ashtami celebrates the appearance of Radha, the divine consort of Krishna and embodiment of devotion.", "why_it_matters": "Radha's day — pure, selfless divine love.", "recommended_mukhi": None},
    "Anant Chaturdashi": {"description": "Anant Chaturdashi is dedicated to Lord Vishnu as Ananta; devotees tie the sacred Anant thread, and Ganesh idols are immersed on this day.", "why_it_matters": "Worship of the infinite Vishnu — protection through the Anant sutra.", "recommended_mukhi": "10"},
    "Krishna Janmashtami": {"description": "Janmashtami celebrates the midnight birth of Lord Krishna. Devotees fast until midnight, sing bhajans, and reenact his childhood leelas.", "why_it_matters": "Krishna's birth at midnight — devotion, joy, and divine grace.", "recommended_mukhi": "10"},

    # ---- Ashwin (Navratri / Dashain) ----
    "Mahalaya Amavasya": {"description": "Mahalaya Amavasya marks the end of Pitru Paksha and the start of Devi Paksha, the most important day for ancestor offerings (Tarpan).", "why_it_matters": "The supreme day for ancestor tarpan, on the eve of Navratri.", "recommended_mukhi": None},
    "Navratri Begins": {"description": "Sharad Navratri begins the nine-night worship of Goddess Durga in her nine forms, the year's greatest celebration of Shakti.", "why_it_matters": "Nine nights of the Goddess begin — Shakti, victory, and transformation.", "recommended_mukhi": "9"},
    "Durga Ashtami": {"description": "Durga Ashtami (Maha Ashtami) is the most powerful day of Navratri, when Goddess Durga's fierce energy is worshipped with Kanya puja and special havan.", "why_it_matters": "Navratri's most powerful day — Durga's fierce, protective Shakti.", "recommended_mukhi": "9"},
    "Mahanavami": {"description": "Mahanavami is the ninth day of Navratri, completing the Goddess worship with Ayudha puja and grand havan before Vijayadashami.", "why_it_matters": "The culmination of Navratri — victory of the Goddess.", "recommended_mukhi": "9"},
    "Dussehra (Vijayadashami)": {"description": "Vijayadashami celebrates Rama's victory over Ravana and Durga's over Mahishasura — the triumph of good over evil. Beginning new learning or ventures today is highly auspicious.", "why_it_matters": "The day of victory — the most auspicious time to begin anything new.", "recommended_mukhi": "9"},
    "Sharad Purnima (Kojagrat Brata)": {"description": "Sharad Purnima is the harvest full moon when the moon's rays are believed to shower nectar (amrit). Kheer is left under the moonlight and Lakshmi is worshipped through the night.", "why_it_matters": "The nectar full moon — Lakshmi's blessings and healing moonlight.", "recommended_mukhi": "7"},
    "Dashain (Ghatasthapana)": {"description": "Ghatasthapana begins Nepal's Dashain, when the sacred kalash is established and jamara (barley) is sown to invoke Goddess Durga for the fifteen-day festival.", "why_it_matters": "Dashain begins — the kalash is set and the Goddess is invoked.", "recommended_mukhi": "9"},
    "Dashain (Fulpati)": {"description": "Fulpati, the seventh day of Dashain, brings the sacred procession of flowers, leaves, and jamara into the home and the Dashain Ghar.", "why_it_matters": "Dashain's sacred greenery arrives — the festival intensifies.", "recommended_mukhi": "9"},
    "Dashain (Maha Ashtami)": {"description": "Maha Ashtami is the most intense day of Dashain, when Durga's fierce form Kali is worshipped, traditionally with animal sacrifice or symbolic offerings.", "why_it_matters": "Dashain's fiercest day — the worship of Kali's power.", "recommended_mukhi": "9"},
    "Dashain (Maha Navami)": {"description": "Maha Navami completes the Durga worship of Dashain with grand puja, including the worship of tools and instruments (Vishwakarma puja).", "why_it_matters": "The ninth day of Dashain — the culmination of Goddess worship.", "recommended_mukhi": "9"},
    "Dashain (Vijaya Dashami / Tika)": {"description": "Vijaya Dashami is the climax of Nepal's Dashain, when elders give tika and jamara with blessings, celebrating the victory of the goddess over evil.", "why_it_matters": "Dashain's blessing day — tika, jamara, and the triumph of good.", "recommended_mukhi": "9"},

    # ---- Kartika (Diwali / Tihar) ----
    "Karwa Chauth": {"description": "Karwa Chauth is a day-long fast observed by married women, from sunrise until moonrise, for the long life and wellbeing of their husbands.", "why_it_matters": "A wife's fast for her husband's long life, broken at moonrise.", "recommended_mukhi": "2"},
    "Dhanteras": {"description": "Dhanteras opens the Diwali festival and is dedicated to Dhanvantari and Lakshmi. Buying gold, silver, or utensils today is believed to multiply wealth.", "why_it_matters": "The wealth day of Diwali — invite Lakshmi and prosperity home.", "recommended_mukhi": "7"},
    "Naraka Chaturdashi": {"description": "Naraka Chaturdashi (Chhoti Diwali) celebrates Krishna's slaying of the demon Narakasura; an early oil bath is said to remove impurities.", "why_it_matters": "The eve of Diwali — cleansing and the win over darkness.", "recommended_mukhi": None},
    "Diwali (Lakshmi Puja)": {"description": "Diwali, the festival of lights, celebrates Rama's return to Ayodhya and the worship of Goddess Lakshmi for wealth and prosperity. Homes glow with diyas.", "why_it_matters": "The festival of lights — Lakshmi's night for wealth, light, and new beginnings.", "recommended_mukhi": "7"},
    "Govardhan Puja / Annakut": {"description": "Govardhan Puja recalls Krishna lifting Mount Govardhan to shelter villagers; a mountain of food (annakut) is offered in gratitude.", "why_it_matters": "Gratitude to Krishna and nature's abundance.", "recommended_mukhi": "10"},
    "Bhai Dooj": {"description": "Bhai Dooj celebrates the bond between brothers and sisters; sisters apply tika and pray for their brothers' long life.", "why_it_matters": "The sibling bond honoured with tika and blessings.", "recommended_mukhi": None},
    "Chhath Puja": {"description": "Chhath Puja is a rigorous four-day festival worshipping the Sun god and Chhathi Maiya with arghya offered at sunrise and sunset, standing in water.", "why_it_matters": "Devotion to Surya — health, longevity, and family prosperity.", "recommended_mukhi": "12"},
    "Devuthani Ekadashi (Tulsi Vivah)": {"description": "Devuthani Ekadashi marks Lord Vishnu awakening from cosmic sleep, ending Chaturmas. The auspicious wedding season and Tulsi Vivah begin.", "why_it_matters": "Vishnu awakens — Chaturmas ends and the wedding season opens.", "recommended_mukhi": "10"},
    "Tulsi Vivah": {"description": "Tulsi Vivah ceremonially weds the Tulsi plant to Lord Vishnu (Shaligram), marking the start of the Hindu wedding season.", "why_it_matters": "The sacred Tulsi–Vishnu wedding that opens the marriage season.", "recommended_mukhi": "10"},
    "Kartika Purnima": {"description": "Kartika Purnima (Dev Diwali) is the full moon when gods are said to descend to the Ganga; holy dips and lamp offerings bring great merit.", "why_it_matters": "The gods' festival of lights — sacred dips and luminous merit.", "recommended_mukhi": "1"},
    "Dev Deepawali": {"description": "Dev Deepawali, the 'Diwali of the Gods,' lights thousands of lamps along the Varanasi ghats on Kartika Purnima.", "why_it_matters": "Varanasi's ghats ablaze with lamps for the gods.", "recommended_mukhi": "1"},
    "Tihar (Lakshmi Puja)": {"description": "On the third day of Nepal's Tihar, homes are lit and decorated to welcome Goddess Lakshmi for wealth and prosperity.", "why_it_matters": "Tihar's Lakshmi night — light, wealth, and blessings.", "recommended_mukhi": "7"},
    "Tihar (Bhai Tika)": {"description": "Bhai Tika concludes Tihar, when sisters give a seven-coloured tika and garland to brothers, praying for their long life.", "why_it_matters": "The sister–brother blessing that crowns Tihar.", "recommended_mukhi": None},

    # ---- Margashirsha / Pausha ----
    "Gita Jayanti / Mokshada Ekadashi": {"description": "Gita Jayanti marks the day Krishna delivered the Bhagavad Gita to Arjuna; Mokshada Ekadashi is observed for liberation and ancestral upliftment.", "why_it_matters": "The Gita's birthday — wisdom, dharma, and the path to liberation.", "recommended_mukhi": "10"},
    "Vivah Panchami": {"description": "Vivah Panchami celebrates the divine wedding of Lord Rama and Goddess Sita, observed with reenactments and prayers for marital harmony.", "why_it_matters": "The Rama–Sita wedding day — devotion and marital harmony.", "recommended_mukhi": "10"},
    "Dattatreya Jayanti": {"description": "Dattatreya Jayanti celebrates the birth of Lord Dattatreya, the combined form of Brahma, Vishnu, and Shiva, revered as the supreme guru.", "why_it_matters": "The birth of the supreme guru — Brahma, Vishnu, and Shiva as one.", "recommended_mukhi": "5"},
}


def _festival_copy(name, paksha, fallback_desc="", fallback_why=""):
    """Festival-specific copy: prefer the curated FESTIVAL_CONTENT table, then any
    description already computed for the event, then the generic guidance. Returns
    (description, why_it_matters, recommended_mukhi)."""
    content = FESTIVAL_CONTENT.get(name)
    if content:
        return (content.get("description", ""),
                content.get("why_it_matters", ""),
                content.get("recommended_mukhi"))
    if fallback_desc or fallback_why:
        return fallback_desc, fallback_why, None
    g = _event_guidance(name, paksha)
    return g.get("description", ""), g.get("why_it_matters", ""), None


# --- Notification copy templates --------------------------------------------
# Real panchanga data is injected into these, and _stable_pick rotates the
# phrasing per day (seeded by date + nakshatra), so the text changes every day
# and reads like a person wrote it — without an LLM in the request path.
_TITHI_NATURE_AUSPICIOUS = {"Nanda", "Bhadra", "Jaya", "Poorna"}

_DAILY_TITLE_FESTIVAL = [
    "🪔 {festival} is here — today's practice matters",
    "🎉 It's {festival} — don't let today's blessings pass",
    "🙏 {festival} today — here's how to honour it",
]
_DAILY_TITLE_AUSPICIOUS = [
    "✨ {tithi} today — a strong day to begin",
    "🌟 {tithi} today: the timing is on your side",
    "🪔 A blessed {tithi} — make today count",
    "🌸 {tithi} today — step forward with intent",
]
_DAILY_TITLE_RIKTA = [
    "🌖 {tithi} today — finish, don't start",
    "🍃 {tithi}: a day to complete and reflect",
    "🧘 {tithi} today — slow down and clear the deck",
]
_DAILY_BODY_AUSPICIOUS = [
    "The Moon rides {nakshatra}{deity}. {window}Tap for today's Panchanga and the right moment to act →",
    "With the Moon in {nakshatra}{deity}, today favours new work, puja, and bold moves. {window}See what's most auspicious →",
    "{nakshatra}{deity} colours the day. {window}Open your Panchanga to time it right →",
]
_DAILY_BODY_RIKTA = [
    "The Moon sits in {nakshatra}{deity}. Today rewards finishing pending work and quiet sadhana over fresh starts. See what to do — and what to avoid →",
    "With the Moon in {nakshatra}{deity}, hold off on big launches — complete, clear, and reflect instead. {window}Tap for today's guidance →",
]
_FEST_BODY = [
    "{why} Tap to see how to prepare →",
    "{why} Here's how to get ready →",
    "{why} Open the practice guide →",
]


def _best_window_phrase(amrit_windows, abhijit_window):
    """Pick the day's headline auspicious window for the daily alert copy."""
    if amrit_windows:
        w = amrit_windows[0]
        if isinstance(w, (list, tuple)) and len(w) == 2:
            return f"Your sharpest window is {w[0]}–{w[1]} (Amrit Kaal). "
    if abhijit_window:
        return f"Your sharpest window is {abhijit_window} (Abhijit Muhurat). "
    return ""


def _countdown_title(festival, days_away):
    if days_away == 0:
        return f"🎉 Today is {festival}"
    if days_away == 1:
        return f"⏳ {festival} is tomorrow — get ready"
    return f"⏳ {festival} is {days_away} days away"


def _countdown_body(festival, days_away, why, mukhi):
    """Stage-aware festival countdown copy, matching the 7 / 3 / day-of spec:
    far out → 'how to prepare'; near (≤3 days) → the user's power Mukhi; day-of →
    'complete practice guide'."""
    if days_away == 0:
        return f"Today is {festival}. {why} Here is your complete practice guide →"
    if days_away <= 3:
        when = "tomorrow" if days_away == 1 else f"in {days_away} days"
        if mukhi:
            return (f"{festival} is {when}. Your {mukhi} Mukhi is most powerful on this day — "
                    f"prepare now →")
        return f"{festival} is {when}. {why} Here's how to prepare →"
    return f"{festival} is {days_away} days away. {why} Here is how to prepare →"


def _short_why(why_it_matters, description):
    """First, punchy sentence to drive the tap — prefer why_it_matters."""
    text = (why_it_matters or "").strip() or (description or "").strip()
    if not text:
        return ""
    # Keep it to the first sentence so the notification body stays scannable.
    for sep in (". ", "। "):
        if sep in text:
            return text.split(sep)[0].strip() + "."
    return text


def build_notifications_block(tithi_name, tithi_nature, paksha, nakshatra_name,
                              nakshatra_deity, festival_today, upcoming_spiritual_events,
                              amrit_windows, abhijit_window, amanta_month,
                              day_of_week, today_ymd):
    """Assemble a compact, notification-ready block for the mobile app.

    Purely additive — derived entirely from values already computed for the
    /astrology response, so it adds no extra astronomical work. Copy is
    generated from the day's real data (tithi nature, nakshatra + its deity, the
    headline auspicious window, and each event's own why_it_matters), with
    phrasing rotated deterministically per day — so it reads like human writing
    and changes daily, not boilerplate.

    Content hooks (blog_url, recommended_mukhi) are left null here; they are
    populated from the API content table in a later phase (A2/A3)."""
    seed = f"{today_ymd}|{nakshatra_name}"
    deity = f" ({nakshatra_deity}'s star)" if nakshatra_deity else ""
    window = _best_window_phrase(amrit_windows, abhijit_window)

    # --- 1) Daily auspicious alert (click-worthy, dynamic) ---
    real_festivals = [f for f in (festival_today or []) if f and f != "None"]
    if real_festivals:
        lead = real_festivals[0]
        title = _stable_pick(_DAILY_TITLE_FESTIVAL, seed).format(festival=lead)
    elif tithi_nature in _TITHI_NATURE_AUSPICIOUS:
        title = _stable_pick(_DAILY_TITLE_AUSPICIOUS, seed).format(tithi=tithi_name)
    else:  # Rikta
        title = _stable_pick(_DAILY_TITLE_RIKTA, seed).format(tithi=tithi_name)

    body_pool = _DAILY_BODY_AUSPICIOUS if tithi_nature in _TITHI_NATURE_AUSPICIOUS else _DAILY_BODY_RIKTA
    body = _stable_pick(body_pool, seed).format(
        nakshatra=nakshatra_name, deity=deity, window=window
    )
    daily_auspicious = {
        "title": title,
        "body": body,
        "tithi": tithi_name,
        "nakshatra": nakshatra_name,
    }

    # --- 2) Festival countdown (ascending by days_away, with real descriptions) ---
    try:
        today_date = datetime.strptime(today_ymd, "%Y-%m-%d").date()
    except Exception:
        today_date = None
    countdown = []
    # Day-of (0 days): today's real festivals → festival-specific copy.
    for fest in real_festivals:
        desc, why_full, mukhi = _festival_copy(fest, paksha)
        why = _short_why(why_full, desc)
        countdown.append({
            "festival": fest,
            "festival_key": _event_key(fest),
            "days_away": 0,
            "date": today_ymd,
            "title": _countdown_title(fest, 0),
            "body": _countdown_body(fest, 0, why, mukhi),
            "description": desc,
            "blog_url": None,
            "recommended_mukhi": mukhi,
        })
    # Upcoming festivals/events within the existing scan window.
    for ev in (upcoming_spiritual_events or []):
        name = (ev or {}).get("event")
        date_str = (ev or {}).get("date")
        if not name or name == "None" or not date_str or today_date is None:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        days_away = (d - today_date).days
        if days_away <= 0:
            continue
        # Prefer curated festival copy; fall back to the event's own guidance text.
        desc, why_full, mukhi = _festival_copy(
            name, ev.get("paksha") or paksha,
            fallback_desc=ev.get("description", ""),
            fallback_why=ev.get("why_it_matters", ""),
        )
        why = _short_why(why_full, desc)
        countdown.append({
            "festival": name,
            "festival_key": _event_key(name),
            "days_away": days_away,
            "date": date_str,
            "title": _countdown_title(name, days_away),
            "body": _countdown_body(name, days_away, why, mukhi),
            "description": desc,
            "blog_url": None,
            "recommended_mukhi": mukhi,
        })
    # Ascending: soonest festival first.
    countdown.sort(key=lambda c: (c["days_away"], c["festival"]))

    # --- 3) Shravan month Sunday/Monday Maha Pooja alert ---
    # maha_pooja_time / livestream_url are business content — the app substitutes
    # them into the "[time]" / link placeholders when set.
    shravan_event = None
    if amanta_month and "Shravan" in str(amanta_month):
        if day_of_week == "Sunday":
            shravan_event = {
                "is_shravan": True,
                "weekday": "Sunday",
                "type": "advance_notice",
                "maha_pooja_time": None,
                "livestream_url": None,
                "notification": {
                    "title": "🔔 Tomorrow: 21 priests chant Rudri Paath live",
                    "body": ("Tomorrow, 21 priests will chant Rudri Paath live. Nepa "
                             "Rudraksha's Maha Pooja begins at [time]. Set your reminder →"),
                },
            }
        elif day_of_week == "Monday":
            shravan_event = {
                "is_shravan": True,
                "weekday": "Monday",
                "type": "live_now",
                "maha_pooja_time": None,
                "livestream_url": None,
                "notification": {
                    "title": "🟢 We are live now — Rudri Paath",
                    "body": ("We are live now. 21 priests chanting Rudri Paath — Nepa "
                             "Rudraksha Maha Pooja. Watch and receive the blessings →"),
                },
            }

    return {
        "daily_auspicious": daily_auspicious,
        "festival_countdown": countdown,
        "shravan_event": shravan_event,
    }


# ============================================================
# 13) DAILY PANCHANGA (for monthly endpoint)
# ============================================================
def calculate_panchanga_for_date(latitude, longitude, target_date_naive, tz_name, month_system="both", precomputed_end_times=None):
    """The panchanga core is deterministic per (location, date, month_system, UTC
    day) and does NOT depend on birth details — so memoize it. This lets
    *personalized* requests (which bypass the full-response cache) still reuse the
    heavy Skyfield compute, even across different users hitting the same
    date/location, and lets repeated monthly requests reuse all 30 per-day
    computes. A deepcopy is returned so callers can never mutate the cached
    object."""
    # Distinct prefix per end-time source so the /panchanga-date path (per-date
    # compute_angas_end_times) and the monthly path (batch end times) never share
    # a cache entry — each is internally consistent, output unchanged.
    prefix = "panchanga_m" if precomputed_end_times is not None else "panchanga"
    key = (prefix, round_coord(latitude), round_coord(longitude), target_date_naive.strftime("%Y-%m-%d"),
           tz_name, month_system, datetime.now(pytz.utc).strftime("%Y-%m-%d"))
    cached = _scan_cache_get_or_compute(
        key,
        lambda: _calculate_panchanga_for_date_uncached(
            latitude, longitude, target_date_naive, tz_name, month_system, precomputed_end_times
        ),
    )
    return copy.deepcopy(cached)


def _calculate_panchanga_for_date_uncached(latitude, longitude, target_date_naive, tz_name, month_system="both", precomputed_end_times=None):
    lat_r = round_coord(latitude)
    lon_r = round_coord(longitude)

    tz = pytz.timezone(tz_name)
    target_date_local = tz.localize(datetime(target_date_naive.year, target_date_naive.month, target_date_naive.day, 12, 0, 0))

    # Use GEOCENTRIC for angas & rashi (closer to Drik)
    t = TS.from_datetime(target_date_local.astimezone(pytz.utc))
    sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
    sun_sid = float(np.atleast_1d(sun_sid)[0])
    moon_sid = float(np.atleast_1d(moon_sid)[0])

    angle = (moon_sid - sun_sid) % 360.0
    tithi_number, paksha, tithi_name = calculate_tithi_and_paksha_from_angle(angle)

    nak_idx        = _to_int_scalar(nakshatra_index_at(t))
    nakshatra_name = nakshatras[nak_idx]
    yoga_name      = yoga_names[_to_int_scalar(yoga_index_at(t))]
    karana_name    = karana_name_from_number(_to_int_scalar(karana_index_at(t)))

    moon_sign      = rashi_names[int(moon_sid // 30) % 12]
    sun_sign       = rashi_names[int(sun_sid  // 30) % 12]
    ritu           = calculate_ritu(sun_sid)
    tithi_nature   = TITHI_NATURE_NAMES[(tithi_number - 1) % 5]
    nakshatra_pada = int((moon_sid % NAK_DEG) / (NAK_DEG / 4)) + 1
    nakshatra_lord   = NAKSHATRA_LORDS[nak_idx]
    nakshatra_deity  = NAKSHATRA_DEITIES[nak_idx]

    graha_gochar = get_all_planet_positions(t)

    date_ymd     = target_date_naive.strftime("%Y-%m-%d")
    weekday      = target_date_naive.weekday()
    next_date_ymd = (target_date_naive + timedelta(days=1)).strftime("%Y-%m-%d")

    sunrise_utc, sunset_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)
    sunrise = sunrise_utc.astimezone(tz)
    sunset  = sunset_utc.astimezone(tz)
    next_sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, next_date_ymd, tz_name)
    next_sunrise = next_sunrise_utc.astimezone(tz)

    mr_utc, ms_utc = cached_moonrise_moonset(lat_r, lon_r, date_ymd, tz_name)
    moonrise = mr_utc.astimezone(tz) if mr_utc else None
    moonset  = ms_utc.astimezone(tz) if ms_utc else None

    rahu_start,     rahu_end     = calculate_rahu_kaal(sunrise, sunset, weekday)
    gulika_start,   gulika_end   = calculate_gulika_kaal(sunrise, sunset, weekday)
    yamaganda_start,yamaganda_end= calculate_yamaganda_kaal(sunrise, sunset, weekday)
    abhijit_start,  abhijit_end  = calculate_abhijit_muhurat(sunrise, sunset)
    brahma_start,   brahma_end   = calculate_brahma_muhurat(sunrise, sunset)

    choghadiya  = calculate_choghadiya(sunrise, sunset, next_sunrise, weekday)
    durmuhurta  = calculate_durmuhurta(sunrise, sunset, weekday, target_date_local.strftime("%A"))

    current_year  = target_date_naive.year
    current_month = target_date_naive.month
    if current_month < 4:
        vikram_samvat = (current_year - 1) + 57
        shaka_samvat  = (current_year - 1) - 78
    else:
        vikram_samvat = current_year + 57
        shaka_samvat  = current_year - 78

    amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
        target_date_local, paksha, tz_name, lat_r, lon_r
    )
    is_adhik, amanta_month_display = detect_adhik_maas(
        target_date_local, amanta_month, tz_name, lat_r, lon_r
    )

    def tithi_context_at(local_dt):
        t_local = TS.from_datetime(local_dt.astimezone(pytz.utc))
        ss, ms = get_sidereal_lons_geocentric(t_local)
        ss = float(np.atleast_1d(ss)[0]); ms = float(np.atleast_1d(ms)[0])
        ang = (ms - ss) % 360.0
        _, p_local, tn_local = calculate_tithi_and_paksha_from_angle(ang)
        am_local, pm_local   = calculate_amanta_purnimanta_month_fast(local_dt, p_local, tz_name, lat_r, lon_r)
        return tn_local, p_local, am_local, pm_local

    def festivals_for_instant(local_dt):
        tn, p, am, pm = tithi_context_at(local_dt)
        return get_festivals_for_day(tn, p, am, pm, month_system=month_system)

    def nisita_time_for_date():
        su = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)[1]
        ns = cached_sunrise_sunset(lat_r, lon_r, next_date_ymd, tz_name)[0]
        sl = su.astimezone(tz); nsl = ns.astimezone(tz)
        return sl + (nsl - sl) / 2

    fixed_list  = check_fixed_festivals(target_date_naive)
    nisita_list = festivals_for_instant(nisita_time_for_date())
    lunar_list  = nisita_list if nisita_list else festivals_for_instant(sunrise_utc.astimezone(tz))

    all_festivals  = fixed_list + lunar_list
    festival_today = all_festivals if all_festivals else ["None"]

    vrata_list = get_vratas_for_day(tithi_name, paksha, target_date_local.strftime("%A"), nakshatra_name)
    vrata_today = vrata_list if vrata_list else ["None"]

    pooja_today = get_poojas_for_day(tithi_number, paksha, amanta_month,
                                     target_date_local.strftime("%A"), all_festivals)

    if precomputed_end_times is not None:
        end_times = precomputed_end_times
    else:
        end_times = compute_angas_end_times(lat_r, lon_r, tz_name, date_ymd, now_local=target_date_local)

    nak_end_local = end_times["nakshatra_end"]
    nak_end_utc   = nak_end_local.astimezone(pytz.utc) if nak_end_local else None
    now_utc       = target_date_local.astimezone(pytz.utc)
    nak_start_utc = estimate_nakshatra_start_utc(moon_sid, now_utc, nak_end_utc)
    varjyam       = calculate_varjyam(nak_idx, nak_start_utc, nak_end_utc, tz, nakshatra_name)

    amrit_windows = [[s["start"], s["end"]] for s in choghadiya["day"] + choghadiya["night"]
                     if s["name"] == "Amrit"]
    amrit_kaal = {
        "windows": amrit_windows,
        "significance": ("Most auspicious window of the day based on lunar nakshatra. "
                         "Begin important work, perform puja, start journeys, or take medicine "
                         "during Amrit Kaal for the best results."),
        "description": _desc_amrit_kaal(amrit_windows, nakshatra_name),
    }

    significance_text = generate_significance(
        tithi_name, tithi_nature, paksha, nakshatra_name, nakshatra_lord,
        yoga_name, moon_sign, sun_sign, ritu,
        target_date_local.strftime("%A"), festival_today, vrata_today, is_adhik
    )
    day_duration = (sunset - sunrise).total_seconds() / 3600

    recommended_mantras = get_recommended_mantras(
        target_date_local.strftime("%A"),
        nakshatra_name,
        tithi_number,
        paksha,
        yoga_name,
        festival_today,
        get_mantra_data(),
    )

    return {
        "date": date_ymd,
        "day_of_week": target_date_local.strftime("%A"),
        # --- Five Angas ---
        "tithi": tithi_name,
        "tithi_end": format_dt_local(end_times["tithi_end"]),
        "tithi_number": tithi_number,
        "tithi_nature": tithi_nature,
        "tithi_nature_significance": TITHI_NATURE_SIGNIFICANCE[tithi_nature],
        "paksha": paksha,
        "nakshatra": nakshatra_name,
        "nakshatra_end": format_dt_local(end_times["nakshatra_end"]),
        "nakshatra_pada": nakshatra_pada,
        "nakshatra_pada_significance": NAKSHATRA_PADA_DESC[nakshatra_pada - 1],
        "nakshatra_lord": nakshatra_lord,
        "nakshatra_deity": nakshatra_deity,
        "karana": karana_name,
        "karana_end": format_dt_local(end_times["karana_end"]),
        "yoga": yoga_name,
        "yoga_end": format_dt_local(end_times["yoga_end"]),
        # --- Signs & Seasons ---
        "moon_sign": moon_sign,
        "sun_sign": sun_sign,
        "ritu": ritu,
        # --- Lunar Calendar ---
        "amanta_month": amanta_month_display,
        "purnimanta_month": purnimanta_month,
        "adhik_maas": is_adhik,
        "vikram_samvat": vikram_samvat,
        "shaka_samvat": shaka_samvat,
        # --- Raw angles ---
        "sun_moon_angle": angle,
        "sun_sidereal": sun_sid,
        # --- Solar/Lunar times ---
        "sunrise": sunrise.strftime("%I:%M:%S %p"),
        "sunset":  sunset.strftime("%I:%M:%S %p"),
        "moonrise": format_time_with_date_if_needed(moonrise, date_ymd),
        "moonset":  format_time_with_date_if_needed(moonset,  date_ymd),
        "day_duration": f"{day_duration:.2f} hours",
        # --- Planetary transits ---
        "graha_gochar": graha_gochar,
        # --- Festivals / Vratas / Poojas ---
        "festival_today": festival_today,
        "vrata_today": vrata_today,
        "pooja_today": pooja_today,
        # --- Significance ---
        "significance": significance_text,
        # --- Muhurats ---
        "subh_muhurat": [
            {"abhijit": [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")], "description": _desc_abhijit(abhijit_start.strftime("%I:%M %p"), abhijit_end.strftime("%I:%M %p"))},
            {"brahma":  [brahma_start.strftime("%I:%M:%S %p"),  brahma_end.strftime("%I:%M:%S %p")],  "description": _desc_brahma(brahma_start.strftime("%I:%M %p"),   brahma_end.strftime("%I:%M %p"))},
        ],
        "asubh_muhurat": [
            {"rahu":      [rahu_start.strftime("%I:%M:%S %p"),      rahu_end.strftime("%I:%M:%S %p")],      "description": _desc_rahu(rahu_start.strftime("%I:%M %p"),           rahu_end.strftime("%I:%M %p"),      target_date_local.strftime("%A"))},
            {"gulika":    [gulika_start.strftime("%I:%M:%S %p"),    gulika_end.strftime("%I:%M:%S %p")],    "description": _desc_gulika(gulika_start.strftime("%I:%M %p"),       gulika_end.strftime("%I:%M %p"),    target_date_local.strftime("%A"))},
            {"yamaganda": [yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")], "description": _desc_yamaganda(yamaganda_start.strftime("%I:%M %p"), yamaganda_end.strftime("%I:%M %p"), target_date_local.strftime("%A"))},
        ],
        "choghadiya":  choghadiya,
        "durmuhurta":  durmuhurta,
        "amrit_kaal":  amrit_kaal,
        "varjyam":     varjyam,
        "recommended_mantras": recommended_mantras,
    }
    result["daily_summary"] = generate_daily_summary(result)
    return result

# ============================================================
# 14) ROUTES
# ============================================================
@app.route("/astrology", methods=["POST"])
def astrology_api_view():
    try:
        data = request.get_json(force=True)

        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        month_system = (data.get("month_system") or "both").strip().lower()
        requested_rashi = data.get("rashi")
        person_name = data.get("name")
        birth_details = {
            "date_of_birth": data.get("date_of_birth"),
            "time_of_birth": data.get("time_of_birth"),
            "birth_latitude": data.get("birth_latitude"),
            "birth_longitude": data.get("birth_longitude"),
            "birth_timezone": data.get("birth_timezone"),
        }

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid latitude or longitude."}), 400

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)

        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

        # Kick off the blocking kundali fetch now so it overlaps the Skyfield
        # compute below; resolved at build_app_response time (data unchanged).
        kundali_future = IO_EXECUTOR.submit(
            _fetch_kundali_report, birth_details, timezone_str, person_name
        )

        tz = pytz.timezone(timezone_str)
        now_local = datetime.now(tz)
        date_ymd = now_local.strftime("%Y-%m-%d")

        # Anga end times (vectorized-safe)
        end_times = compute_angas_end_times(lat_r, lon_r, timezone_str, date_ymd, now_local=now_local)

        # Current angas at now (geocentric)
        t_now = TS.from_datetime(now_local.astimezone(pytz.utc))
        sun_sid, moon_sid = get_sidereal_lons_geocentric(t_now)
        sun_sid  = float(np.atleast_1d(sun_sid)[0])
        moon_sid = float(np.atleast_1d(moon_sid)[0])

        angle = (moon_sid - sun_sid) % 360.0
        tithi_number, paksha, tithi_name = calculate_tithi_and_paksha_from_angle(angle)
        nak_idx        = _to_int_scalar(nakshatra_index_at(t_now))
        nakshatra_name = nakshatras[nak_idx]
        yoga_name      = yoga_names[_to_int_scalar(yoga_index_at(t_now))]
        karana_name    = karana_name_from_number(_to_int_scalar(karana_index_at(t_now)))

        moon_sign       = rashi_names[int(moon_sid // 30) % 12]
        sun_sign        = rashi_names[int(sun_sid  // 30) % 12]
        ritu            = calculate_ritu(sun_sid)
        tithi_nature    = TITHI_NATURE_NAMES[(tithi_number - 1) % 5]
        nakshatra_pada  = int((moon_sid % NAK_DEG) / (NAK_DEG / 4)) + 1
        nakshatra_lord  = NAKSHATRA_LORDS[nak_idx]
        nakshatra_deity = NAKSHATRA_DEITIES[nak_idx]
        graha_gochar    = get_all_planet_positions(t_now)

        weekday      = now_local.weekday()
        next_date_ymd = (now_local.date() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Sunrise/Sunset, Moonrise/Moonset
        sunrise_utc, sunset_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, timezone_str)
        sunrise = sunrise_utc.astimezone(tz)
        sunset  = sunset_utc.astimezone(tz)
        next_sunrise_utc, _ = cached_sunrise_sunset(lat_r, lon_r, next_date_ymd, timezone_str)
        next_sunrise = next_sunrise_utc.astimezone(tz)

        mr_utc, ms_utc = cached_moonrise_moonset(lat_r, lon_r, date_ymd, timezone_str)
        moonrise = mr_utc.astimezone(tz) if mr_utc else None
        moonset  = ms_utc.astimezone(tz) if ms_utc else None

        # Muhurats
        rahu_start,     rahu_end     = calculate_rahu_kaal(sunrise, sunset, weekday)
        gulika_start,   gulika_end   = calculate_gulika_kaal(sunrise, sunset, weekday)
        yamaganda_start,yamaganda_end= calculate_yamaganda_kaal(sunrise, sunset, weekday)
        abhijit_start,  abhijit_end  = calculate_abhijit_muhurat(sunrise, sunset)
        brahma_start,   brahma_end   = calculate_brahma_muhurat(sunrise, sunset)

        choghadiya = calculate_choghadiya(sunrise, sunset, next_sunrise, weekday)
        durmuhurta = calculate_durmuhurta(sunrise, sunset, weekday, now_local.strftime("%A"))
        amrit_windows = [[s["start"], s["end"]] for s in choghadiya["day"] + choghadiya["night"]
                         if s["name"] == "Amrit"]
        amrit_kaal = {
            "windows": amrit_windows,
            "significance": ("Most auspicious window of the day based on lunar nakshatra. "
                             "Begin important work, perform puja, start journeys, or take medicine "
                             "during Amrit Kaal for the best results."),
            "description": _desc_amrit_kaal(amrit_windows, nakshatra_name),
        }

        current_year  = now_local.year
        current_month = now_local.month
        if current_month < 4:
            vikram_samvat = (current_year - 1) + 57
            shaka_samvat  = (current_year - 1) - 78
        else:
            vikram_samvat = current_year + 57
            shaka_samvat  = current_year - 78

        amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
            now_local, paksha, timezone_str, lat_r, lon_r
        )
        is_adhik, amanta_month_display = detect_adhik_maas(
            now_local, amanta_month, timezone_str, lat_r, lon_r
        )

        fixed_list = check_fixed_festivals(now_local.replace(tzinfo=None))
        lunar_list = get_festivals_for_day(tithi_name, paksha, amanta_month, purnimanta_month,
                                           month_system=month_system)
        all_festivals  = fixed_list + lunar_list
        festival_today = all_festivals if all_festivals else ["None"]

        vrata_today = get_vratas_for_day(tithi_name, paksha, now_local.strftime("%A"), nakshatra_name)
        vrata_today = vrata_today if vrata_today else ["None"]

        pooja_today = get_poojas_for_day(tithi_number, paksha, amanta_month,
                                         now_local.strftime("%A"), all_festivals)
        recommended_mantras = get_recommended_mantras(
            now_local.strftime("%A"),
            nakshatra_name,
            tithi_number,
            paksha,
            yoga_name,
            festival_today,
            get_mantra_data(),
        )
        upcoming_poojas = get_upcoming_poojas(
            lat_r, lon_r, timezone_str, now_local.date(), days_ahead=7,
            month_system=month_system
        )

        nak_end_local = end_times["nakshatra_end"]
        nak_end_utc   = nak_end_local.astimezone(pytz.utc) if nak_end_local else None
        now_utc_dt    = now_local.astimezone(pytz.utc)
        nak_start_utc = estimate_nakshatra_start_utc(moon_sid, now_utc_dt, nak_end_utc)
        varjyam       = calculate_varjyam(nak_idx, nak_start_utc, nak_end_utc, tz, nakshatra_name)

        day_duration = (sunset - sunrise).total_seconds() / 3600
        significance_text = generate_significance(
            tithi_name, tithi_nature, paksha, nakshatra_name, nakshatra_lord,
            yoga_name, moon_sign, sun_sign, ritu,
            now_local.strftime("%A"), festival_today, vrata_today, is_adhik
        )

        response_payload = {
            # --- Five Angas ---
            "tithi":           tithi_name,
            "tithi_end":       format_dt_local(end_times["tithi_end"]),
            "tithi_number":    tithi_number,
            "tithi_nature":    tithi_nature,
            "tithi_nature_significance": TITHI_NATURE_SIGNIFICANCE[tithi_nature],
            "paksha":          paksha,
            "nakshatra":       nakshatra_name,
            "nakshatra_end":   format_dt_local(end_times["nakshatra_end"]),
            "nakshatra_pada":  nakshatra_pada,
            "nakshatra_pada_significance": NAKSHATRA_PADA_DESC[nakshatra_pada - 1],
            "nakshatra_lord":  nakshatra_lord,
            "nakshatra_deity": nakshatra_deity,
            "karana":          karana_name,
            "karana_end":      format_dt_local(end_times["karana_end"]),
            "yoga":            yoga_name,
            "yoga_end":        format_dt_local(end_times["yoga_end"]),
            # --- Signs & Seasons ---
            "moon_sign":  moon_sign,
            "sun_sign":   sun_sign,
            "ritu":       ritu,
            # --- Lunar Calendar ---
            "amanta_month":     amanta_month_display,
            "purnimanta_month": purnimanta_month,
            "adhik_maas":       is_adhik,
            "vikram_samvat":    vikram_samvat,
            "shaka_samvat":     shaka_samvat,
            # --- Raw angles ---
            "sun_moon_angle": angle,
            "sun_sidereal":   sun_sid,
            # --- Date/Time ---
            "day_of_week":  now_local.strftime("%A"),
            "date":         date_ymd,
            "day_duration": f"{day_duration:.2f} hours",
            "time_zone":    timezone_str,
            "month_system": month_system,
            # --- Solar/Lunar times ---
            "sunrise":  sunrise.strftime("%I:%M:%S %p"),
            "sunset":   sunset.strftime("%I:%M:%S %p"),
            "moonrise": format_time_with_date_if_needed(moonrise, date_ymd),
            "moonset":  format_time_with_date_if_needed(moonset,  date_ymd),
            # --- Planetary transits ---
            "graha_gochar": graha_gochar,
            # --- Festivals / Vratas / Poojas ---
            "festival_today":  festival_today,
            "vrata_today":     vrata_today,
            "pooja_today":     pooja_today,
            "upcoming_poojas": upcoming_poojas,
            "recommended_mantras": recommended_mantras,  # consumed by build_app_response; excluded from order_day_payload
            # --- Significance ---
            "significance": significance_text,
            # --- Muhurats ---
            "subh_muhurat": [
                {"abhijit": [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")], "description": _desc_abhijit(abhijit_start.strftime("%I:%M %p"), abhijit_end.strftime("%I:%M %p"))},
                {"brahma":  [brahma_start.strftime("%I:%M:%S %p"),  brahma_end.strftime("%I:%M:%S %p")],  "description": _desc_brahma(brahma_start.strftime("%I:%M %p"),   brahma_end.strftime("%I:%M %p"))},
            ],
            "asubh_muhurat": [
                {"rahu":      [rahu_start.strftime("%I:%M:%S %p"),      rahu_end.strftime("%I:%M:%S %p")],      "description": _desc_rahu(rahu_start.strftime("%I:%M %p"),           rahu_end.strftime("%I:%M %p"),      now_local.strftime("%A"))},
                {"gulika":    [gulika_start.strftime("%I:%M:%S %p"),    gulika_end.strftime("%I:%M:%S %p")],    "description": _desc_gulika(gulika_start.strftime("%I:%M %p"),       gulika_end.strftime("%I:%M %p"),    now_local.strftime("%A"))},
                {"yamaganda": [yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")], "description": _desc_yamaganda(yamaganda_start.strftime("%I:%M %p"), yamaganda_end.strftime("%I:%M %p"), now_local.strftime("%A"))},
            ],
            "choghadiya":    choghadiya,
            "durmuhurta":    durmuhurta,
            "amrit_kaal":    amrit_kaal,
            "varjyam":       varjyam,
            "daily_summary": generate_daily_summary({
                "day_of_week": now_local.strftime("%A"), "date": date_ymd,
                "paksha": paksha, "amanta_month": amanta_month_display,
                "vikram_samvat": vikram_samvat, "shaka_samvat": shaka_samvat,
                "adhik_maas": is_adhik, "tithi": tithi_name,
                "tithi_number": tithi_number, "tithi_nature": tithi_nature,
                "tithi_nature_significance": TITHI_NATURE_SIGNIFICANCE[tithi_nature],
                "tithi_end": format_dt_local(end_times["tithi_end"]),
                "nakshatra": nakshatra_name, "nakshatra_pada": nakshatra_pada,
                "nakshatra_pada_significance": NAKSHATRA_PADA_DESC[nakshatra_pada - 1],
                "nakshatra_end": format_dt_local(end_times["nakshatra_end"]),
                "nakshatra_lord": nakshatra_lord,
                "yoga": yoga_name, "yoga_end": format_dt_local(end_times["yoga_end"]),
                "karana": karana_name, "karana_end": format_dt_local(end_times["karana_end"]),
                "moon_sign": moon_sign, "sun_sign": sun_sign, "ritu": ritu,
                "sunrise": sunrise.strftime("%I:%M:%S %p"),
                "sunset": sunset.strftime("%I:%M:%S %p"),
                "moonrise": format_time_with_date_if_needed(moonrise, date_ymd),
                "moonset": format_time_with_date_if_needed(moonset, date_ymd),
                "day_duration": f"{day_duration:.2f} hours",
                "significance": significance_text,
                "festival_today": festival_today, "vrata_today": vrata_today,
                "pooja_today": pooja_today, "graha_gochar": graha_gochar,
                "subh_muhurat": [
                    {"abhijit": [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")]},
                    {"brahma": [brahma_start.strftime("%I:%M:%S %p"), brahma_end.strftime("%I:%M:%S %p")]},
                ],
                "asubh_muhurat": [
                    {"rahu": [rahu_start.strftime("%I:%M:%S %p"), rahu_end.strftime("%I:%M:%S %p")]},
                    {"gulika": [gulika_start.strftime("%I:%M:%S %p"), gulika_end.strftime("%I:%M:%S %p")]},
                    {"yamaganda": [yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")]},
                ],
                "choghadiya": choghadiya, "durmuhurta": durmuhurta,
                "amrit_kaal": amrit_kaal, "varjyam": varjyam,
            }),
        }
        upcoming_spiritual_events = get_upcoming_spiritual_events(
            lat_r, lon_r, timezone_str, now_local.date(), days_ahead=7, month_system=month_system
        )
        app_response = build_app_response(
            response_payload, upcoming_spiritual_events, requested_rashi, person_name, birth_details, timezone_str, upcoming_poojas,
            precomputed_kundali_data=kundali_future.result(),
        )
        notifications_block = build_notifications_block(
            tithi_name, tithi_nature, paksha, nakshatra_name, nakshatra_deity,
            festival_today, upcoming_spiritual_events,
            amrit_windows, f"{abhijit_start.strftime('%I:%M %p')}–{abhijit_end.strftime('%I:%M %p')}",
            amanta_month, now_local.strftime("%A"), date_ymd,
        )
        response_payload = order_day_payload(response_payload)
        response_payload["app_response"] = app_response
        response_payload["notifications"] = notifications_block
        return jsonify(response_payload)

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/monthly-panchanga-page")
def monthly_panchanga_page():
    return render_template("monthly_panchanga.html")

@app.route("/panchanga-page")
def panchanga_page():
    return render_template("panchanga.html")

@app.route("/monthly-panchanga", methods=["POST"])
def monthly_panchanga_api():
    try:
        data = request.get_json(force=True)
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        month = int(data.get("month", datetime.now().month))
        year = int(data.get("year", datetime.now().year))
        month_system = (data.get("month_system") or "both").strip().lower()
        requested_rashi = data.get("rashi")
        person_name = data.get("name")
        birth_details = {
            "date_of_birth": data.get("date_of_birth"),
            "time_of_birth": data.get("time_of_birth"),
            "birth_latitude": data.get("birth_latitude"),
            "birth_longitude": data.get("birth_longitude"),
            "birth_timezone": data.get("birth_timezone"),
        }

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid latitude or longitude."}), 400
        if not (1 <= month <= 12):
            return jsonify({"error": "Invalid month. Must be between 1 and 12."}), 400
        if not (1900 <= year <= 2100):
            return jsonify({"error": "Invalid year. Must be between 1900 and 2100."}), 400

        # Non-personalized requests are deterministic for (request body, UTC day):
        # serve an identical cached response and skip the full-month compute.
        cacheable = not _request_has_birth_details(data)
        cache_key = _response_cache_key("/monthly-panchanga", data) if cacheable else None
        if cache_key is not None:
            cached = _response_cache_get(cache_key)
            if cached is not None:
                return jsonify(cached)

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)

        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

        # Fetch kundali once (birth data is static across all days) and let the
        # blocking call overlap the cache pre-warm + batch compute below.
        kundali_future = IO_EXECUTOR.submit(
            _fetch_kundali_report, birth_details, timezone_str, person_name
        )

        # Warm moon phase cache
        cached_moon_phases_for_month(year, month, timezone_str)
        py, pm = _prev_month(year, month)
        cached_moon_phases_for_month(py, pm, timezone_str)

        # Days in month
        first_day = datetime(year, month, 1)
        next_month = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        num_days = (next_month - first_day).days

        # Pre-warm sunrise/sunset & moonrise/moonset caches
        for day in range(1, num_days + 1):
            d = datetime(year, month, day)
            date_ymd = d.strftime("%Y-%m-%d")
            cached_sunrise_sunset(lat_r, lon_r, date_ymd, timezone_str)
            cached_moonrise_moonset(lat_r, lon_r, date_ymd, timezone_str)

        # Batch-compute all anga end times (4 find_discrete calls vs 30×4=120)
        batch_end_times = compute_month_anga_end_times_batch(year, month, timezone_str)

        # Resolve the kundali fetch started above (it ran during the warm-up).
        precomputed_kundali = kundali_future.result()

        # Precompute spiritual events & poojas for the entire month + 7-day tail in one pass
        events_by_date, poojas_by_date = _precompute_month_events_and_poojas(
            lat_r, lon_r, timezone_str, year, month, month_system
        )

        monthly_data = []
        monthly_app_response = []
        for day in range(1, num_days + 1):
            target_date = datetime(year, month, day)
            date_key = target_date.strftime("%Y-%m-%d")
            day_data = calculate_panchanga_for_date(
                latitude,
                longitude,
                target_date,
                timezone_str,
                month_system=month_system,
                precomputed_end_times=batch_end_times.get(date_key),
            )

            # General horoscope depends only on graha_gochar (changes daily with Moon)
            # but all 12 rashis share the same planetary positions — compute once per day
            gochar = day_data.get("graha_gochar")
            day_general_horoscope = [
                _build_real_horoscope_from_transits(r, day_data, _personalized_transits(r, gochar))
                for r in rashi_names
            ]

            day_app_response = build_app_response(
                day_data,
                _slice_upcoming_spiritual_events(events_by_date, target_date.date(), days_ahead=7),
                requested_rashi,
                person_name,
                birth_details,
                timezone_str,
                _slice_upcoming_poojas(poojas_by_date, target_date.date(), days_ahead=7),
                precomputed_kundali_data=precomputed_kundali,
                precomputed_general_horoscope=day_general_horoscope,
            )
            monthly_app_response.append({
                "date": day_data.get("date"),
                "day": day_data.get("day_of_week"),
                "app_response": day_app_response,
            })
            monthly_data.append(order_day_payload(day_data))

        response_dict = {
            "month": month,
            "year": year,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "total_days": num_days,
            "panchanga_data": monthly_data,
            "app_response": monthly_app_response,
        }
        if cache_key is not None:
            _response_cache_put(cache_key, response_dict)
        return jsonify(response_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/panchanga-range", methods=["POST"])
def panchanga_range_api():
    """Panchanga for an inclusive date range (start_date..end_date) at given
    coordinates. Same per-day shape as /monthly-panchanga, but for an arbitrary
    range that may span multiple months."""
    try:
        data = request.get_json(force=True)
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        month_system = (data.get("month_system") or "both").strip().lower()
        requested_rashi = data.get("rashi")
        person_name = data.get("name")
        birth_details = {
            "date_of_birth": data.get("date_of_birth"),
            "time_of_birth": data.get("time_of_birth"),
            "birth_latitude": data.get("birth_latitude"),
            "birth_longitude": data.get("birth_longitude"),
            "birth_timezone": data.get("birth_timezone"),
        }

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid latitude or longitude."}), 400

        start_raw = str(data.get("start_date") or "").strip()
        end_raw = str(data.get("end_date") or "").strip()
        try:
            start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
        except Exception:
            return jsonify({"error": "start_date and end_date are required in YYYY-MM-DD format."}), 400
        if end_date < start_date:
            return jsonify({"error": "end_date must be on or after start_date."}), 400
        if not (1900 <= start_date.year <= 2100 and 1900 <= end_date.year <= 2100):
            return jsonify({"error": "Dates must be between years 1900 and 2100."}), 400
        MAX_RANGE_DAYS = 366
        total_days = (end_date - start_date).days + 1
        if total_days > MAX_RANGE_DAYS:
            return jsonify({"error": f"Date range too large (max {MAX_RANGE_DAYS} days)."}), 400

        # Non-personalized requests are deterministic for (request body, UTC day):
        # serve an identical cached response and skip the full-range compute.
        cacheable = not _request_has_birth_details(data)
        cache_key = _response_cache_key("/panchanga-range", data) if cacheable else None
        if cache_key is not None:
            cached = _response_cache_get(cache_key)
            if cached is not None:
                return jsonify(cached)

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)
        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

        # Fetch kundali once (birth data is static across all days); overlap it with
        # the per-month warm-up + batch compute below.
        kundali_future = IO_EXECUTOR.submit(
            _fetch_kundali_report, birth_details, timezone_str, person_name
        )

        # Warm + batch every (year, month) the range touches, then merge. The 7-day
        # tail baked into each month's event/pooja precompute covers the upcoming
        # window for days near a month boundary.
        months = []
        seen = set()
        cur = start_date
        while cur <= end_date:
            ym = (cur.year, cur.month)
            if ym not in seen:
                seen.add(ym)
                months.append(ym)
            cur = (cur.replace(year=cur.year + 1, month=1, day=1) if cur.month == 12
                   else cur.replace(month=cur.month + 1, day=1))

        merged_batch, merged_events, merged_poojas = {}, {}, {}
        for (y, m) in months:
            cached_moon_phases_for_month(y, m, timezone_str)
            py, pm = _prev_month(y, m)
            cached_moon_phases_for_month(py, pm, timezone_str)
            merged_batch.update(compute_month_anga_end_times_batch(y, m, timezone_str))
            ev, pj = _precompute_month_events_and_poojas(lat_r, lon_r, timezone_str, y, m, month_system)
            merged_events.update(ev)
            merged_poojas.update(pj)

        precomputed_kundali = kundali_future.result()

        range_data = []
        range_app_response = []
        d = start_date
        while d <= end_date:
            target_date = datetime(d.year, d.month, d.day)
            date_key = target_date.strftime("%Y-%m-%d")
            day_data = calculate_panchanga_for_date(
                latitude, longitude, target_date, timezone_str,
                month_system=month_system,
                precomputed_end_times=merged_batch.get(date_key),
            )

            gochar = day_data.get("graha_gochar")
            day_general_horoscope = [
                _build_real_horoscope_from_transits(r, day_data, _personalized_transits(r, gochar))
                for r in rashi_names
            ]

            day_app_response = build_app_response(
                day_data,
                _slice_upcoming_spiritual_events(merged_events, target_date.date(), days_ahead=7),
                requested_rashi,
                person_name,
                birth_details,
                timezone_str,
                _slice_upcoming_poojas(merged_poojas, target_date.date(), days_ahead=7),
                precomputed_kundali_data=precomputed_kundali,
                precomputed_general_horoscope=day_general_horoscope,
            )
            range_app_response.append({
                "date": day_data.get("date"),
                "day": day_data.get("day_of_week"),
                "app_response": day_app_response,
            })
            range_data.append(order_day_payload(day_data))
            d += timedelta(days=1)

        response_dict = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "total_days": total_days,
            "panchanga_data": range_data,
            "app_response": range_app_response,
        }
        if cache_key is not None:
            _response_cache_put(cache_key, response_dict)
        return jsonify(response_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/panchanga-date", methods=["POST"])
def panchanga_date_api():
    """Panchanga for a single given date (day, month, year) at given coordinates."""
    try:
        data = request.get_json(force=True)
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        day = int(data.get("day"))
        month = int(data.get("month"))
        year = int(data.get("year"))
        month_system = (data.get("month_system") or "both").strip().lower()
        requested_rashi = data.get("rashi")
        person_name = data.get("name")
        birth_details = {
            "date_of_birth": data.get("date_of_birth"),
            "time_of_birth": data.get("time_of_birth"),
            "birth_latitude": data.get("birth_latitude"),
            "birth_longitude": data.get("birth_longitude"),
            "birth_timezone": data.get("birth_timezone"),
        }

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid latitude or longitude."}), 400
        if not (1 <= month <= 12):
            return jsonify({"error": "Invalid month. Must be between 1 and 12."}), 400
        if not (1900 <= year <= 2100):
            return jsonify({"error": "Invalid year. Must be between 1900 and 2100."}), 400

        try:
            target_date = datetime(year, month, day)
        except ValueError:
            return jsonify({"error": "Invalid date (e.g. day out of range for month)."}), 400

        # Non-personalized requests are deterministic for (request body, UTC day):
        # serve an identical cached response and skip the Skyfield compute.
        cacheable = not _request_has_birth_details(data)
        cache_key = _response_cache_key("/panchanga-date", data) if cacheable else None
        if cache_key is not None:
            cached = _response_cache_get(cache_key)
            if cached is not None:
                return jsonify(cached)

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)

        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

        # Overlap the blocking kundali fetch with the Skyfield compute below.
        kundali_future = IO_EXECUTOR.submit(
            _fetch_kundali_report, birth_details, timezone_str, person_name
        )

        panchanga_data = calculate_panchanga_for_date(
            latitude,
            longitude,
            target_date,
            timezone_str,
            month_system=month_system,
        )

        upcoming_poojas = get_upcoming_poojas(
            lat_r, lon_r, timezone_str, target_date.date(), days_ahead=7,
            month_system=month_system
        )
        upcoming_spiritual_events = get_upcoming_spiritual_events(
            lat_r, lon_r, timezone_str, target_date.date(), days_ahead=7,
            month_system=month_system
        )
        app_response = build_app_response(
            panchanga_data, upcoming_spiritual_events, requested_rashi, person_name, birth_details, timezone_str, upcoming_poojas,
            precomputed_kundali_data=kundali_future.result(),
        )
        panchanga_data = order_day_payload(panchanga_data)

        response_dict = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "panchanga_data": panchanga_data,
            "upcoming_poojas": upcoming_poojas,
            "app_response": app_response,
        }
        if cache_key is not None:
            _response_cache_put(cache_key, response_dict)
        return jsonify(response_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ============================================================
# 14b) PERSONALIZED NOTIFICATIONS  (/notifications route — A4/A5)
# ============================================================
# Self-contained on Skyfield + birth details — no dependency on the external
# kundali API. Natal Moon sign, transit ingresses, and the Vimshottari dasha are
# all computed locally and deterministically.

# Navagraha Rudraksha associations (traditional) — CONFIRM against the
# Nepa Rudraksha catalogue before relying on these in production copy.
PLANET_MUKHI = {
    "Sun": "12", "Moon": "2", "Mars": "3", "Mercury": "4", "Jupiter": "5",
    "Venus": "13", "Saturn": "14", "Rahu": "8", "Ketu": "9",
}

# Mahadasha character — one phrase per dasha lord, used in the notification body.
DASHA_GUIDANCE = {
    "Sun": "a period of leadership, recognition, and stepping into authority",
    "Moon": "a period of emotional depth, nurturing, and public connection",
    "Mars": "a period of energy, courage, and decisive action",
    "Mercury": "a period of learning, communication, and commerce",
    "Jupiter": "a period of growth, wisdom, and expanding good fortune",
    "Venus": "a period of comfort, relationships, creativity, and pleasure",
    "Saturn": "a period of discipline, hard work, and lasting, hard-won results",
    "Rahu": "a period of ambition, sudden change, and unconventional gains",
    "Ketu": "a period of detachment, spirituality, and turning inward",
}

# Vimshottari mahadasha sequence and lengths (years); total = 120.
DASHA_SEQUENCE = [("Ketu", 7), ("Venus", 20), ("Sun", 6), ("Moon", 10), ("Mars", 7),
                  ("Rahu", 18), ("Jupiter", 16), ("Saturn", 19), ("Mercury", 17)]
_DASHA_YEARS = dict(DASHA_SEQUENCE)
_DASHA_ORDER = [p for p, _ in DASHA_SEQUENCE]
_DASHA_YEAR_DAYS = 365.2425

# Slow movers only — fast planets (Sun/Moon/Mercury/Venus) change sign too often
# to be a "significant transit beginning".
_SIGNIFICANT_TRANSIT_PLANETS = ["Mars", "Jupiter", "Saturn", "Rahu", "Ketu"]


def _natal_chart_basics(birth_details, fallback_tz_name):
    """Compute natal Moon position locally from birth details. Returns None if
    required birth details are missing/invalid."""
    required = ["date_of_birth", "time_of_birth", "birth_latitude", "birth_longitude"]
    if not birth_details or any(birth_details.get(k) in (None, "") for k in required):
        return None
    dob = str(birth_details["date_of_birth"]).strip()
    tob = str(birth_details["time_of_birth"]).strip()
    birth_dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            birth_dt = datetime.strptime(f"{dob} {tob}", fmt)
            break
        except Exception:
            continue
    if birth_dt is None:
        return None
    # Prefer an explicit birth_timezone; otherwise derive it from the birth
    # coordinates (more correct than the current-location tz), then fall back.
    tz_name = birth_details.get("birth_timezone")
    if not tz_name:
        try:
            tz_name = cached_timezone_str(
                round_coord(float(birth_details["birth_latitude"])),
                round_coord(float(birth_details["birth_longitude"])),
            )
        except Exception:
            tz_name = None
    tz_name = tz_name or fallback_tz_name or "Asia/Kathmandu"
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Kathmandu")
    birth_utc = tz.localize(birth_dt).astimezone(pytz.utc)
    t_birth = TS.from_datetime(birth_utc)
    _, moon_sid = get_sidereal_lons_geocentric(t_birth)
    moon_sid = float(np.atleast_1d(moon_sid)[0])
    nak_idx = int(moon_sid // NAK_DEG) % 27
    return {
        "moon_sid": moon_sid,
        "moon_sign": rashi_names[int(moon_sid // 30) % 12],
        "moon_sign_idx": int(moon_sid // 30) % 12,
        "nak_idx": nak_idx,
        "nak_name": nakshatras[nak_idx],
        "nak_fraction": (moon_sid % NAK_DEG) / NAK_DEG,
        "birth_utc": birth_utc,
    }


# General nature of each planet — used in the transit summary text.
PLANET_NATURE = {
    "Mars": "Mars embodies strength, passion, courage, and ambition. It governs aggression, drive, and the competitive spirit, often bringing sudden bursts of energy and action.",
    "Jupiter": "Jupiter is the great benefic — the planet of wisdom, expansion, fortune, and higher knowledge. It blesses growth, optimism, learning, and dharma.",
    "Saturn": "Saturn is the cosmic taskmaster — the planet of discipline, patience, and hard-won results. It rewards perseverance and structure while testing through delay and responsibility.",
    "Rahu": "Rahu is the shadowy north node of ambition and obsession — worldly desire, innovation, and unconventional paths, marked by sudden rises and disruptions.",
    "Ketu": "Ketu is the shadowy south node of detachment and liberation — spirituality, intuition, past-life karma, and letting go of the material.",
}

# Sanskrit (Vedic) names for the signs, shown alongside the English name.
_RASHI_SANSKRIT = {
    "Aries": "Mesha", "Taurus": "Vrishabha", "Gemini": "Mithuna", "Cancer": "Karka",
    "Leo": "Simha", "Virgo": "Kanya", "Libra": "Tula", "Scorpio": "Vrishchika",
    "Sagittarius": "Dhanu", "Capricorn": "Makara", "Aquarius": "Kumbha", "Pisces": "Meena",
}


def _sign_name(idx):
    eng = rashi_names[idx]
    sans = _RASHI_SANSKRIT.get(eng)
    return f"{sans} ({eng})" if sans else eng


def _planet_sign_idx(planet, dt):
    return int(get_all_planet_positions(TS.from_datetime(dt))[planet]["longitude"] // 30) % 12


def _bisect_boundary(planet, a, b):
    """a < b with sign(a) != sign(b). Return the first datetime (≈1-day resolution)
    where the sign equals sign(b) — i.e. the ingress instant."""
    target = _planet_sign_idx(planet, b)
    for _ in range(22):
        if (b - a).total_seconds() <= 86400:
            break
        mid = a + (b - a) / 2
        if _planet_sign_idx(planet, mid) == target:
            b = mid
        else:
            a = mid
    return b


def _find_boundary(planet, start_dt, direction, max_days=1000, step=10):
    """Find the sign-change boundary forward (+1) or backward (-1) from start_dt.
    Coarse-steps then bisects, so retrograde motion is handled (positions are
    sampled, not extrapolated). Returns the ingress datetime, or None."""
    base = _planet_sign_idx(planet, start_dt)
    prev_dt = start_dt
    d = step
    while d <= max_days:
        cur_dt = start_dt + direction * timedelta(days=d)
        if _planet_sign_idx(planet, cur_dt) != base:
            return (_bisect_boundary(planet, prev_dt, cur_dt) if direction > 0
                    else _bisect_boundary(planet, cur_dt, prev_dt))
        prev_dt = cur_dt
        d += step
    return None


def _transit_calendar(now_utc):
    """Per-planet current sign, when it entered, and its next ingress. This is
    user-INDEPENDENT (pure function of the date), so it is cached once per UTC
    day and shared across all users. The per-user house mapping happens later."""
    key = ("transit_cal", now_utc.strftime("%Y-%m-%d"))
    return _scan_cache_get_or_compute(key, lambda: _transit_calendar_uncached(now_utc))


def _transit_calendar_uncached(now_utc):
    cal = {}
    for p in _SIGNIFICANT_TRANSIT_PLANETS:
        cur_idx = _planet_sign_idx(p, now_utc)
        nb = _find_boundary(p, now_utc, +1)
        eb = _find_boundary(p, now_utc, -1)
        next_idx = _planet_sign_idx(p, nb + timedelta(days=1)) if nb else None
        prev_idx = _planet_sign_idx(p, eb - timedelta(days=2)) if eb else None
        cal[p] = {
            "current_sign_idx": cur_idx,
            "entered_date": eb.date().isoformat() if eb else None,
            "prev_sign_idx": prev_idx,
            "next_sign_idx": next_idx,
            "next_ingress_date": nb.date().isoformat() if nb else None,
        }
    return cal


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


def _build_transits(natal_moon_idx, now_utc, today_date, imminent_days=45):
    """Full current+next transit detail for each significant planet, mapped to the
    user's houses from the natal Moon sign. `is_imminent` marks ingresses within
    `imminent_days` — the app fires the transit notification for those."""
    cal = _transit_calendar(now_utc)
    out = []
    for p in _SIGNIFICANT_TRANSIT_PLANETS:
        info = cal.get(p) or {}
        cur_idx = info.get("current_sign_idx")
        if cur_idx is None:
            continue
        cur_house = ((cur_idx - natal_moon_idx) % 12) + 1
        entered = info.get("entered_date")
        next_iso = info.get("next_ingress_date")
        next_idx = info.get("next_sign_idx")
        next_house = ((next_idx - natal_moon_idx) % 12) + 1 if next_idx is not None else None

        time_in_sign = _humanize_span(datetime.strptime(entered, "%Y-%m-%d").date(), today_date) if entered else None
        duration_in_sign = (_humanize_span(datetime.strptime(entered, "%Y-%m-%d").date(),
                                           datetime.strptime(next_iso, "%Y-%m-%d").date())
                            if entered and next_iso else None)
        days_until = (datetime.strptime(next_iso, "%Y-%m-%d").date() - today_date).days if next_iso else None
        is_imminent = days_until is not None and 0 <= days_until <= imminent_days

        # Summary in the requested narrative style.
        summary_parts = [f"{p} is placed in the {_ordinal(cur_house)} house from your Moon sign."]
        if entered:
            summary_parts.append(f"{p} entered {_sign_name(cur_idx)} on {_pretty_date(entered)}.")
        if duration_in_sign and next_iso and next_idx is not None:
            summary_parts.append(
                f"After {duration_in_sign} of transit in {rashi_names[cur_idx]}, "
                f"{p} transits to {_sign_name(next_idx)} on {_pretty_date(next_iso)}.")
        summary_parts.append(PLANET_NATURE.get(p, ""))
        summary = " ".join(s for s in summary_parts if s)

        # Effect for BOTH the current house (where it is now) and the next house
        # (where it's heading) so the description never describes one while naming
        # the other.
        def _house_effect(house):
            if house is None:
                return None
            return PLANET_HOUSE_INSIGHT.get((p, house)) or (
                f"{p} {PLANET_TRANSIT_EFFECT.get(p, 'shifts the tone of this house')}, "
                f"activating {HOUSE_THEMES.get(house, 'key life areas')}.")
        current_effect = _house_effect(cur_house)
        next_effect = _house_effect(next_house)
        mukhi = PLANET_MUKHI.get(p)

        # Notification body names both houses: current placement → upcoming move.
        if next_house and next_iso:
            notif_body = (
                f"{p} is in your {_ordinal(cur_house)} house and on {_pretty_date(next_iso)} "
                f"moves into your {_ordinal(next_house)} house. {next_effect} "
                f"Strengthen {p} with your {mukhi} Mukhi. Tap to prepare →")
            notif_title = f"🪐 {p} enters your {_ordinal(next_house)} house"
        else:
            notif_body = (f"{p} is transiting your {_ordinal(cur_house)} house. {current_effect} "
                          f"Strengthen {p} with your {mukhi} Mukhi. Tap to learn more →")
            notif_title = f"🪐 {p} in your {_ordinal(cur_house)} house"

        out.append({
            "planet": p,
            "planet_nature": PLANET_NATURE.get(p, ""),
            # current placement
            "current_sign": rashi_names[cur_idx],
            "current_sign_sanskrit": _RASHI_SANSKRIT.get(rashi_names[cur_idx]),
            "current_house": cur_house,
            "current_house_theme": HOUSE_THEMES.get(cur_house, "key life areas"),
            "entered_current_sign_on": entered,
            "time_in_current_sign": time_in_sign,
            "duration_in_current_sign": duration_in_sign,
            "prev_sign": rashi_names[info["prev_sign_idx"]] if info.get("prev_sign_idx") is not None else None,
            # next transit (ingress)
            "next_sign": rashi_names[next_idx] if next_idx is not None else None,
            "next_sign_sanskrit": _RASHI_SANSKRIT.get(rashi_names[next_idx]) if next_idx is not None else None,
            "next_house": next_house,
            "next_house_theme": HOUSE_THEMES.get(next_house, "key life areas") if next_house else None,
            "next_ingress_date": next_iso,
            "days_until_next_ingress": days_until,
            "is_imminent": is_imminent,
            # guidance / content — both current and upcoming house effects
            "current_effect": current_effect,
            "next_effect": next_effect,
            "recommended_mukhi": mukhi,
            "pooja_practices": TRANSIT_POOJA_PRACTICES.get(p, {}),
            "summary": summary,
            "notification": {
                "title": notif_title,
                "body": notif_body,
            },
        })
    # Only the single NEAREST upcoming transit is returned — that's the one worth
    # a notification. (All planets are still computed/cached; we just surface one.)
    out.sort(key=lambda x: x["days_until_next_ingress"] if x["days_until_next_ingress"] is not None else 99999)
    return out[:1]


def _vimshottari_periods(moon_sid, nak_idx, nak_fraction, birth_utc, now_utc):
    """Build the Vimshottari mahadasha timeline from birth and return
    (current_period, next_period, all_periods)."""
    start_lord = NAKSHATRA_LORDS[nak_idx]
    periods = []
    cursor = birth_utc
    # The birth mahadasha is already part-elapsed; only its balance remains.
    first_years = _DASHA_YEARS[start_lord] * (1.0 - nak_fraction)
    end = cursor + timedelta(days=first_years * _DASHA_YEAR_DAYS)
    periods.append({"lord": start_lord, "start": cursor, "end": end})
    cursor = end
    i = _DASHA_ORDER.index(start_lord)
    # Keep appending until at least one period STARTS after 'now' — this
    # guarantees the period containing now (current) and the one after it (next)
    # are both present, regardless of how long the current mahadasha runs.
    while periods[-1]["start"] <= now_utc and len(periods) < 40:
        i = (i + 1) % 9
        lord = _DASHA_ORDER[i]
        end = cursor + timedelta(days=_DASHA_YEARS[lord] * _DASHA_YEAR_DAYS)
        periods.append({"lord": lord, "start": cursor, "end": end})
        cursor = end

    current = nxt = None
    for j, pp in enumerate(periods):
        if pp["start"] <= now_utc < pp["end"]:
            current = pp
            nxt = periods[j + 1] if j + 1 < len(periods) else None
            break
    return current, nxt, periods


def _current_antardasha(maha, now_utc):
    """Sub-period (antardasha) of the running mahadasha, proportional to 120y."""
    if not maha:
        return None
    total_days = (maha["end"] - maha["start"]).total_seconds() / 86400.0
    start_i = _DASHA_ORDER.index(maha["lord"])
    cursor = maha["start"]
    for k in range(9):
        sub_lord = _DASHA_ORDER[(start_i + k) % 9]
        sub_days = total_days * (_DASHA_YEARS[sub_lord] / 120.0)
        end = cursor + timedelta(days=sub_days)
        if cursor <= now_utc < end:
            return {"lord": sub_lord, "start": cursor, "end": end}
        cursor = end
    return None


def _fmt_date(dt):
    return dt.strftime("%Y-%m-%d") if dt else None


def _build_dasha_change(basics, now_utc, today_date):
    current, nxt, _ = _vimshottari_periods(
        basics["moon_sid"], basics["nak_idx"], basics["nak_fraction"],
        basics["birth_utc"], now_utc,
    )
    if not current:
        return None
    antar = _current_antardasha(current, now_utc)
    lord = current["lord"]
    duration_years = round((current["end"] - current["start"]).total_seconds() / 86400.0 / _DASHA_YEAR_DAYS, 1)
    started_today = current["start"].date() == today_date
    days_until_next = (nxt["start"].date() - today_date).days if nxt else None
    mukhi = PLANET_MUKHI.get(lord)
    guidance = DASHA_GUIDANCE.get(lord, "a significant new life period")

    # Gate: a dasha-CHANGE alert only fires when a new mahadasha has just begun
    # (today) or begins within the next 7 days. Otherwise → no notification.
    notify = started_today or (days_until_next is not None and 0 <= days_until_next < 7)
    notification = None
    if started_today:
        notification = {
            "title": f"✨ You have entered {lord} Mahadasha",
            "body": (f"You have entered your {lord} Mahadasha — {guidance}. This "
                     f"~{duration_years}-year period shapes your path ahead. Strengthen "
                     f"{lord} with your {mukhi} Mukhi. Tap for what to expect →"),
        }
    elif notify and nxt:
        nlord = nxt["lord"]
        nmukhi = PLANET_MUKHI.get(nlord)
        nguid = DASHA_GUIDANCE.get(nlord, "a significant new life period")
        day_word = "tomorrow" if days_until_next == 1 else f"in {days_until_next} days"
        notification = {
            "title": f"✨ {nlord} Mahadasha begins {day_word}",
            "body": (f"You are about to enter your {nlord} Mahadasha on "
                     f"{_pretty_date(_fmt_date(nxt['start']))} — {nguid}. Prepare by "
                     f"strengthening {nlord} with your {nmukhi} Mukhi. Tap to learn more →"),
        }

    return {
        "notify": notify,
        "current_mahadasha": {
            "lord": lord,
            "start": _fmt_date(current["start"]),
            "end": _fmt_date(current["end"]),
            "duration_years": duration_years,
        },
        "current_antardasha": ({
            "lord": antar["lord"],
            "start": _fmt_date(antar["start"]),
            "end": _fmt_date(antar["end"]),
        } if antar else None),
        "next_mahadasha": ({"lord": nxt["lord"], "start": _fmt_date(nxt["start"])} if nxt else None),
        "mahadasha_started_today": started_today,
        "days_until_next_mahadasha": days_until_next,
        "recommended_mukhi": mukhi,
        "notification": notification,
    }


# ---- A6: Personal auspicious days (Tarabala + Chandrabala) -----------------
_TARA_NAMES = ["Janma", "Sampat", "Vipat", "Kshema", "Pratyari", "Sadhaka", "Vadha", "Mitra", "Ati-Mitra"]
_TARA_GOOD = {2, 4, 6, 8, 9}  # Sampat, Kshema, Sadhaka, Mitra, Ati-Mitra (1-indexed)
_TARA_MEANING = {
    "Janma": "your birth star (mixed — take care of health)",
    "Sampat": "wealth and prosperity",
    "Vipat": "obstacles (use caution)",
    "Kshema": "well-being and success",
    "Pratyari": "resistance (use caution)",
    "Sadhaka": "accomplishment of goals",
    "Vadha": "difficulty (use caution)",
    "Mitra": "friendly support",
    "Ati-Mitra": "strong support and ease",
}
_CHANDRA_GOOD = {1, 3, 6, 7, 10, 11}  # favourable Moon houses from janma rashi


def _moon_nak_sign_at(dt_utc):
    _, moon_sid = get_sidereal_lons_geocentric(TS.from_datetime(dt_utc))
    moon_sid = float(np.atleast_1d(moon_sid)[0])
    return int(moon_sid // NAK_DEG) % 27, int(moon_sid // 30) % 12


def _assess_auspicious(janma_nak_idx, janma_sign_idx, dt_utc, date_obj):
    moon_nak_idx, moon_sign_idx = _moon_nak_sign_at(dt_utc)
    count = ((moon_nak_idx - janma_nak_idx) % 27) + 1
    tara = ((count - 1) % 9) + 1
    tara_name = _TARA_NAMES[tara - 1]
    chandra_house = ((moon_sign_idx - janma_sign_idx) % 12) + 1
    is_ausp = (tara in _TARA_GOOD) and (chandra_house in _CHANDRA_GOOD)
    description = (
        f"The Moon is in {nakshatras[moon_nak_idx]} — {tara_name} Tara ({_TARA_MEANING[tara_name]}) "
        f"from your birth star — and in your {_ordinal(chandra_house)} house from the Moon. "
        + ("A favourable day for important decisions, new beginnings, travel, or spiritual practice."
           if is_ausp else
           "A routine day — not specially marked for new beginnings.")
    )
    return {
        "date": date_obj.isoformat(),
        "is_auspicious": is_ausp,
        "tara": tara_name,
        "tara_meaning": _TARA_MEANING[tara_name],
        "chandra_house": chandra_house,
        "moon_nakshatra": nakshatras[moon_nak_idx],
        "moon_sign": rashi_names[moon_sign_idx],
        "description": description,
    }


def _build_auspicious_days(basics, tz, today_date, days=30):
    jn, js = basics["nak_idx"], basics["moon_sign_idx"]

    def at_noon(date_obj):
        noon_local = tz.localize(datetime(date_obj.year, date_obj.month, date_obj.day, 12, 0))
        return noon_local.astimezone(pytz.utc)

    today = _assess_auspicious(jn, js, at_noon(today_date), today_date)
    upcoming = []
    for d in range(1, days + 1):
        day = today_date + timedelta(days=d)
        a = _assess_auspicious(jn, js, at_noon(day), day)
        if a["is_auspicious"]:
            upcoming.append(a)

    notify = today["is_auspicious"]
    notification = None
    if notify:
        notification = {
            "title": "🌟 Today is especially auspicious for you",
            "body": (f"{today['description']} A strong day for important decisions or starting "
                     f"something new. Tap for guidance →"),
        }
    return {"notify": notify, "today": today, "upcoming": upcoming, "notification": notification}


# ---- A7: Eclipses -----------------------------------------------------------
def _eclipse_calendar(now_utc, days=180):
    """Upcoming eclipses (lunar + solar) — user-INDEPENDENT, cached once per day.
    Returns list of {type, subtype, date, sidereal_lon}."""
    key = ("eclipses", now_utc.strftime("%Y-%m-%d"), days)
    return _scan_cache_get_or_compute(key, lambda: _eclipse_calendar_uncached(now_utc, days))


def _eclipse_calendar_uncached(now_utc, days):
    from skyfield import eclipselib
    t0 = TS.from_datetime(now_utc)
    t1 = TS.from_datetime(now_utc + timedelta(days=days))
    out = []
    # Lunar eclipses (built-in).
    try:
        times, kinds, _details = eclipselib.lunar_eclipses(t0, t1, EPH)
        for ti, k in zip(times, kinds):
            _, moon_sid = get_sidereal_lons_geocentric(ti)
            out.append({
                "type": "Lunar",
                "subtype": eclipselib.LUNAR_ECLIPSES[int(k)],
                "date": ti.utc_datetime().date().isoformat(),
                "sidereal_lon": float(np.atleast_1d(moon_sid)[0]),
            })
    except Exception:
        pass
    # Solar eclipses: a New Moon whose ecliptic latitude is near 0 (eclipse occurs
    # somewhere on Earth). Visibility at the user's location is a future refinement.
    try:
        earth = geocentric_observer()
        ph_t, ph_v = find_discrete(t0, t1, moon_phases(EPH))
        for ti, pv in zip(ph_t, ph_v):
            if int(pv) != 0:  # 0 = New Moon
                continue
            lat = earth.at(ti).observe(EPH["moon"]).apparent().frame_latlon(ecliptic_frame)[0].degrees
            if abs(float(np.atleast_1d(lat)[0])) <= 1.5:
                _, moon_sid = get_sidereal_lons_geocentric(ti)
                out.append({
                    "type": "Solar",
                    "subtype": "Solar",
                    "date": ti.utc_datetime().date().isoformat(),
                    "sidereal_lon": float(np.atleast_1d(moon_sid)[0]),
                })
    except Exception:
        pass
    out.sort(key=lambda e: e["date"])
    return out


def _build_eclipses(basics, now_utc, today_date, days=180, notify_window=14):
    natal_moon_idx = basics["moon_sign_idx"]
    upcoming = []
    for e in _eclipse_calendar(now_utc, days):
        edate = datetime.strptime(e["date"], "%Y-%m-%d").date()
        days_until = (edate - today_date).days
        if days_until < 0:
            continue
        sign_idx = int(e["sidereal_lon"] // 30) % 12
        house = ((sign_idx - natal_moon_idx) % 12) + 1
        theme = HOUSE_THEMES.get(house, "key life areas")
        desc = (f"A {e['type'].lower()} eclipse falls in {rashi_names[sign_idx]}, your "
                f"{_ordinal(house)} house ({theme}), on {_pretty_date(e['date'])}. Eclipses are "
                f"a time to pause — avoid starting new ventures and focus on reflection, mantra, "
                f"and charity.")
        upcoming.append({
            "type": e["type"],
            "subtype": e["subtype"],
            "date": e["date"],
            "sign": rashi_names[sign_idx],
            "house": house,
            "house_theme": theme,
            "days_until": days_until,
            "description": desc,
        })

    notify = bool(upcoming) and upcoming[0]["days_until"] <= notify_window
    notification = None
    if notify:
        e = upcoming[0]
        notification = {
            "title": f"🌑 A {e['type'].lower()} eclipse affects your {_ordinal(e['house'])} house",
            "body": f"{e['description']} Tap for what to do →",
        }
    return {"notify": notify, "upcoming": upcoming, "notification": notification}


@app.route("/notifications", methods=["POST"])
def notifications_api_view():
    """Personalized, chart-driven notifications (A4 transits, A5 dasha).
    Requires birth_details. A6 (auspicious days) and A7 (eclipses) are returned
    as empty lists until those phases land. The app polls this weekly/monthly and
    fires on ingress_date / mahadasha start / (later) eclipse dates."""
    try:
        data = request.get_json(force=True)
        birth_details = {
            "date_of_birth": data.get("date_of_birth"),
            "time_of_birth": data.get("time_of_birth"),
            "birth_latitude": data.get("birth_latitude"),
            "birth_longitude": data.get("birth_longitude"),
            "birth_timezone": data.get("birth_timezone"),
        }
        # Timezone for the user's LOCAL "today" (so alerts fire on the right day):
        # explicit timezone → derived from current lat/lon → birth tz → Kathmandu.
        tz_name = data.get("timezone")
        if not tz_name and data.get("latitude") is not None and data.get("longitude") is not None:
            try:
                tz_name = cached_timezone_str(
                    round_coord(float(data.get("latitude"))),
                    round_coord(float(data.get("longitude"))),
                )
            except Exception:
                tz_name = None
        tz_name = tz_name or birth_details.get("birth_timezone") or "Asia/Kathmandu"
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.timezone("Asia/Kathmandu")

        basics = _natal_chart_basics(birth_details, tz_name)
        if basics is None:
            return jsonify({
                "error": "birth_details required: date_of_birth (YYYY-MM-DD), "
                         "time_of_birth (HH:MM), birth_latitude, birth_longitude."
            }), 400

        now_utc = datetime.now(pytz.utc)
        today_date = now_utc.astimezone(tz).date()
        transit_days = int(data.get("transit_days", 45))

        transits = _build_transits(basics["moon_sign_idx"], now_utc, today_date, imminent_days=transit_days)
        dasha_change = _build_dasha_change(basics, now_utc, today_date)
        auspicious_days = _build_auspicious_days(basics, tz, today_date)
        eclipses = _build_eclipses(basics, now_utc, today_date)

        return jsonify({
            "natal_moon_sign": basics["moon_sign"],
            "natal_nakshatra": basics["nak_name"],
            "transits": transits,
            "dasha_change": dasha_change,
            "auspicious_days": auspicious_days,
            "eclipses": eclipses,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400


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
    app.run(debug=True,port=5001)
