"""Domain logic + personalization + response assembly: festivals/vratas/poojas,
mantra recommendations, event guidance and significance text, kundali fetch and
dosha-based recommendations, planetary transits, horoscope generation, the daily
panchanga assembly, upcoming-events scans, notification blocks, and the
chart-driven /notifications backend (transits, dasha, auspicious days, eclipses).
"""
import copy
import json
import threading
from functools import lru_cache
from datetime import datetime, timedelta
import numpy as np
import pytz
from skyfield.almanac import find_discrete, moon_phases
from skyfield.framelib import ecliptic_frame

from constants import *
from constants import (
    _NAVAGRAHA_VARIANT_ID, _KUNDALI_POOJA_CATALOG, _PLANET_ALIASES,
    _TITHI_NATURE_GUIDANCE, _MOON_SIGN_FLAVOR, _RITU_CLOSING,
    _TITHI_NATURE_AUSPICIOUS, _DAILY_TITLE_FESTIVAL, _DAILY_TITLE_AUSPICIOUS,
    _DAILY_TITLE_RIKTA, _DAILY_BODY_AUSPICIOUS, _DAILY_BODY_RIKTA, _FEST_BODY,
    _DASHA_YEARS, _DASHA_ORDER, _DASHA_YEAR_DAYS, _SIGNIFICANT_TRANSIT_PLANETS,
    _RASHI_SANSKRIT, _TARA_NAMES, _TARA_GOOD, _TARA_MEANING, _CHANDRA_GOOD,
)
from utils import *
from calculations import *

__all__ = [
    '_KUNDALI_CACHE',
    '_KUNDALI_CACHE_LOCK',
    '_KUNDALI_CACHE_MAX',
    '_assess_auspicious',
    '_best_window_phrase',
    '_bisect_boundary',
    '_build_auspicious_days',
    '_build_dasha_change',
    '_build_eclipses',
    '_build_horoscope_for_rashi',
    '_build_natal_house_map',
    '_build_real_horoscope_from_transits',
    '_build_transits',
    '_calculate_panchanga_for_date_uncached',
    '_clean_event_list',
    '_compose_prediction_lines',
    '_compute_sign_changes',
    '_compute_sign_changes_uncached',
    '_countdown_body',
    '_countdown_title',
    '_current_antardasha',
    '_derive_rashi_from_birth_details',
    '_detailed_transit_prediction',
    '_detect_doshas',
    '_eclipse_calendar',
    '_eclipse_calendar_uncached',
    '_event_deity',
    '_event_guidance',
    '_extract_rashi_name',
    '_festival_copy',
    '_fetch_kundali_report',
    '_fetch_mantra_data_cached',
    '_filter_upcoming_poojas_window',
    '_find_boundary',
    '_get_upcoming_poojas_uncached',
    '_get_upcoming_spiritual_events_uncached',
    '_is_birthday',
    '_is_negated',
    '_is_significant_vrata',
    '_moon_nak_sign_at',
    '_natal_chart_basics',
    '_normalize_planet',
    '_normalize_rashi',
    '_p',
    '_personalized_transits',
    '_personalized_transits_from_kundali',
    '_planet_sign_idx',
    '_precompute_month_events_and_poojas',
    '_short_why',
    '_sign_name',
    '_slice_upcoming_poojas',
    '_slice_upcoming_spiritual_events',
    '_spiritual_event_priority',
    '_transit_calendar',
    '_transit_calendar_uncached',
    '_transit_signal_for_horoscope',
    '_truthy_dosha',
    '_vimshottari_periods',
    'build_app_response',
    'build_notifications_block',
    'calculate_panchanga_for_date',
    'check_fixed_festivals',
    'generate_daily_summary',
    'generate_significance',
    'get_festivals_for_day',
    'get_kundali_pooja_recommendations',
    'get_mantra_data',
    'get_poojas_for_day',
    'get_recommended_mantras',
    'get_upcoming_poojas',
    'get_upcoming_spiritual_events',
    'get_vratas_for_day',
    'normalize_tithi_names',
    'order_day_payload',
    'paksha_allows',
]



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
        nak_name = nakshatras[_to_int_scalar(nakshatra_index_at(t, moon_sid=moon_sid))]

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
        vratas = get_vratas_for_day(tithi_name, paksha, day_of_week, nakshatras[_to_int_scalar(nakshatra_index_at(t, moon_sid=moon_sid))])
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

        # `muhurat` only needs the day's Abhijit + Brahma windows (a function of
        # sunrise/sunset alone), so build it directly instead of computing the full
        # panchanga for this date — byte-identical to a full compute's subh_muhurat,
        # but skips graha gochar, moonrise, varjyam, mantras, and the anga searches.
        sr_utc, ss_utc = cached_sunrise_sunset(lat_r, lon_r, target.strftime("%Y-%m-%d"), tz_name)
        sr_l = sr_utc.astimezone(tz)
        ss_l = ss_utc.astimezone(tz)
        abh_s, abh_e = calculate_abhijit_muhurat(sr_l, ss_l)
        brh_s, brh_e = calculate_brahma_muhurat(sr_l, ss_l)
        day_muhurat = [
            {"abhijit": [abh_s.strftime("%I:%M:%S %p"), abh_e.strftime("%I:%M:%S %p")], "description": _desc_abhijit(abh_s.strftime("%I:%M %p"), abh_e.strftime("%I:%M %p"))},
            {"brahma":  [brh_s.strftime("%I:%M:%S %p"),  brh_e.strftime("%I:%M:%S %p")],  "description": _desc_brahma(brh_s.strftime("%I:%M %p"),   brh_e.strftime("%I:%M %p"))},
        ]
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
            "muhurat": day_muhurat,
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

    nak_idx        = _to_int_scalar(nakshatra_index_at(t, moon_sid=moon_sid))
    nakshatra_name = nakshatras[nak_idx]
    yoga_name      = yoga_names[_to_int_scalar(yoga_index_at(t, sun_sid=sun_sid, moon_sid=moon_sid))]
    karana_name    = karana_name_from_number(_to_int_scalar(karana_index_at(t, angle=angle)))

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

    nak_name = nakshatras[moon_nak_idx]
    tara_meaning = _TARA_MEANING[tara_name]
    pretty = _pretty_date(date_obj.isoformat())
    house_ord = _ordinal(chandra_house)
    # Seed rotates phrasing per day (and per chart) while staying deterministic, so
    # the copy reads differently every day instead of the same boilerplate.
    seed = f"{date_obj.isoformat()}|{tara_name}|{nak_name}|{chandra_house}"
    fields = {
        "date": pretty, "tara": tara_name, "tara_meaning": tara_meaning,
        "nak": nak_name, "house": house_ord,
    }

    title_pool = AUSPICIOUS_TITLES if is_ausp else ROUTINE_TITLES
    body_pool = AUSPICIOUS_BODIES if is_ausp else ROUTINE_BODIES
    close_pool = AUSPICIOUS_DESC_CLOSE if is_ausp else ROUTINE_DESC_CLOSE

    description = (
        f"The Moon is in {nak_name} — {tara_name} Tara ({tara_meaning}) "
        f"from your birth star — and in your {house_ord} house from the Moon. "
        + _stable_pick(close_pool, seed + ":desc")
    )
    notification = {
        "title": _stable_pick(title_pool, seed + ":title").format(**fields),
        "body": _stable_pick(body_pool, seed + ":body").format(**fields),
    }
    return {
        "date": date_obj.isoformat(),
        "is_auspicious": is_ausp,
        "tara": tara_name,
        "tara_meaning": tara_meaning,
        "chandra_house": chandra_house,
        "moon_nakshatra": nak_name,
        "moon_sign": rashi_names[moon_sign_idx],
        "description": description,
        "notification": notification,
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
    # Top-level gated notification = today's own notification when today is auspicious.
    notification = today["notification"] if notify else None
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
        seed = f"{e['date']}|{e['type']}|{house}"
        efields = {"type": e["type"].lower(), "house": _ordinal(house), "sign": rashi_names[sign_idx]}
        upcoming.append({
            "type": e["type"],
            "subtype": e["subtype"],
            "date": e["date"],
            "sign": rashi_names[sign_idx],
            "house": house,
            "house_theme": theme,
            "days_until": days_until,
            "description": desc,
            # Per-eclipse notification (every entry carries title + body, like transits).
            "notification": {
                "title": _stable_pick(ECLIPSE_TITLES, seed + ":title").format(**efields),
                "body": f"{desc} {_stable_pick(ECLIPSE_CTAS, seed + ':cta')}",
            },
        })

    notify = bool(upcoming) and upcoming[0]["days_until"] <= notify_window
    # Top-level gated notification = the nearest eclipse's own notification.
    notification = upcoming[0]["notification"] if notify else None
    return {"notify": notify, "upcoming": upcoming, "notification": notification}


# ============================================================
# 17) PANCHANGA CALENDAR (/panchanga-calendar)
# ============================================================
# A lean, calendar-focused view (festivals, tithis, vratas, subh/asubh muhurat +
# icon markers + an "auspicious days" highlight panel). Reuses the same festival /
# tithi / muhurat machinery as the rest of the API but skips the heavy per-day
# extras (graha gochar, mantras, moonrise, anga end-times) so a whole month renders
# fast. Works over any date range, like /panchanga-range.
def _calendar_markers(tithi_number, paksha, nepali_solar_month, day_of_week, festivals):
    """Semantic tags the frontend maps to icons (trishul, snake, moon, …).
    Shravan Somvar follows the NEPALI SOLAR month (Sun in Cancer = Shrawan)."""
    fl = " ".join(f for f in (festivals or []) if f and f != "None").lower()
    is_shravan = nepali_solar_month == "Shrawan"
    out, seen = [], set()

    def add(m):
        if m not in seen:
            seen.add(m)
            out.append(m)

    if "shivaratri" in fl:
        add("shivaratri")
    if "nag panchami" in fl:
        add("nag_panchami")
    if is_shravan and day_of_week == "Monday":
        add("shravan_somvar")
    if tithi_number in (13, 28):
        add("pradosh")
    if tithi_number in (11, 26):
        add("ekadashi")
    if tithi_number == 15:
        add("purnima")
    if tithi_number == 30:
        add("amavasya")
    if tithi_number in (4, 19):
        add("chaturthi")
    if any(f and f != "None" for f in (festivals or [])):
        add("festival")
    return out


_CALENDAR_AUSPICIOUS_MARKERS = {
    "shravan_somvar", "nag_panchami", "pradosh", "purnima", "ekadashi", "shivaratri",
}


def _calendar_day_entry(lat_r, lon_r, tz_name, target, month_system, region):
    tz = pytz.timezone(tz_name)
    target_local = tz.localize(datetime(target.year, target.month, target.day, 12, 0))
    t = TS.from_datetime(target_local.astimezone(pytz.utc))

    sun_sid, moon_sid = get_sidereal_lons_geocentric(t)
    sun_sid = float(np.atleast_1d(sun_sid)[0])
    moon_sid = float(np.atleast_1d(moon_sid)[0])
    angle = (moon_sid - sun_sid) % 360.0
    tithi_number, paksha, tithi_dev = calculate_tithi_and_paksha_from_angle(angle)
    tithi_en = tithi_names_en[tithi_number - 1]
    nak_name = nakshatras[_to_int_scalar(nakshatra_index_at(t, moon_sid=moon_sid))]

    # Nepali solar (civil/Bikram Sambat) month = the rashi the Sun occupies.
    sun_rashi = rashi_names[int(sun_sid // 30) % 12]
    nepali_solar_month = SUN_RASHI_TO_NEPALI_SOLAR_MONTH[sun_rashi]
    bs_year = _calendar_bs_year(target)

    amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
        target_local, paksha, tz_name, lat_r, lon_r
    )
    day_of_week = target_local.strftime("%A")
    target_naive = datetime(target.year, target.month, target.day)

    fixed = check_fixed_festivals(target_naive)
    lunar = get_festivals_for_day(tithi_dev, paksha, amanta_month, purnimanta_month,
                                  region=region, month_system=month_system)
    festivals = [f for f in (fixed + lunar) if f and f != "None"]
    vratas = [v for v in get_vratas_for_day(tithi_dev, paksha, day_of_week, nak_name)
              if v and v != "None"]
    poojas = [
        {"name": p.get("name"), "reason": p.get("reason"), "variant_id": p.get("variant_id")}
        for p in get_poojas_for_day(tithi_number, paksha, amanta_month, day_of_week, fixed + lunar)
        if p.get("name") != "None"
    ]

    date_ymd = target.strftime("%Y-%m-%d")
    sr_utc, ss_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)
    sr = sr_utc.astimezone(tz)
    ss = ss_utc.astimezone(tz)
    weekday = target_naive.weekday()

    def win(a, b):
        return {"start": a.strftime("%I:%M %p"), "end": b.strftime("%I:%M %p")}

    ab_s, ab_e = calculate_abhijit_muhurat(sr, ss)
    br_s, br_e = calculate_brahma_muhurat(sr, ss)
    rk_s, rk_e = calculate_rahu_kaal(sr, ss, weekday)
    gk_s, gk_e = calculate_gulika_kaal(sr, ss, weekday)
    ym_s, ym_e = calculate_yamaganda_kaal(sr, ss, weekday)

    markers = _calendar_markers(tithi_number, paksha, nepali_solar_month, day_of_week, festivals)
    moon_phase = "full" if tithi_number == 15 else ("new" if tithi_number == 30 else None)
    auspicious = bool(festivals) or bool(set(markers) & _CALENDAR_AUSPICIOUS_MARKERS)

    return {
        "date": date_ymd,
        "day": target.day,
        "weekday": day_of_week,
        "tithi": tithi_en,
        "tithi_devanagari": tithi_dev,
        "tithi_number": tithi_number,
        "paksha": paksha,
        "nakshatra": nak_name,
        "nepali_solar_month": nepali_solar_month,
        "sun_rashi": sun_rashi,
        "bs_year": bs_year,
        "lunar_month": amanta_month,
        "festivals": festivals,
        "vratas": vratas,
        "poojas": poojas,
        "subh_muhurat": {"abhijit": win(ab_s, ab_e), "brahma": win(br_s, br_e)},
        "asubh_muhurat": {
            "rahu_kaal": win(rk_s, rk_e),
            "gulika_kaal": win(gk_s, gk_e),
            "yamaganda_kaal": win(ym_s, ym_e),
        },
        "markers": markers,
        "moon_phase": moon_phase,
        "is_auspicious_to_wear_rudraksha": auspicious,
        "in_range": True,
    }


def _calendar_bs_year(target):
    """Bikram Sambat year for a gregorian date (BS new year ~ Baishakh 1, mid-April)."""
    if target.month > 4 or (target.month == 4 and target.day >= 14):
        return target.year + 57
    return target.year + 56


def _calendar_sun_rashi_noon(lat_r, lon_r, tz_name, target):
    """Sidereal rashi of the Sun at local noon — used to find the sankranti
    (Nepali solar-month start) by stepping backward day by day."""
    tz = pytz.timezone(tz_name)
    tl = tz.localize(datetime(target.year, target.month, target.day, 12, 0))
    t = TS.from_datetime(tl.astimezone(pytz.utc))
    sun_sid, _ = get_sidereal_lons_geocentric(t)
    sun_sid = float(np.atleast_1d(sun_sid)[0])
    return rashi_names[int(sun_sid // 30) % 12]


def _calendar_day_highlights(entry):
    """Auspicious themes for the highlight panel for one day. Returns a list of
    (type, title). A Shravan Monday is always surfaced (the rudraksha headline),
    alongside at most one spiritual festival / tithi theme. Secular national days
    are excluded."""
    festivals = entry.get("festivals") or []
    markers = entry.get("markers") or []
    disp = LUNAR_MONTH_DISPLAY.get(entry.get("lunar_month"), entry.get("lunar_month"))
    spiritual = [f for f in festivals if f and f not in CALENDAR_SECULAR_FESTIVALS]
    out = []
    if "shravan_somvar" in markers:
        out.append(("shravan_somvar", "Shravan Somvar"))
    if spiritual:
        f = spiritual[0]
        fl = f.lower()
        if "nag panchami" in fl:
            out.append(("nag_panchami", f))
        elif "shivaratri" in fl:
            out.append(("shivaratri", f))
        else:
            out.append(("festival", f))
    elif "purnima" in markers:
        out.append(("purnima", f"{disp} Purnima"))
    elif "pradosh" in markers:
        out.append(("pradosh", "Pradosh Vrat"))
    elif "ekadashi" in markers:
        out.append(("ekadashi", "Ekadashi"))
    elif "amavasya" in markers:
        out.append(("amavasya", f"{disp} Amavasya"))
    return out


def build_panchanga_calendar(lat_r, lon_r, tz_name, start_date, end_date, month_system="both", region=None):
    """Return (calendar_month_blocks, highlights) for the inclusive date range."""
    import calendar as _cal

    # Months touched by the range (in order), so we can batch-warm sunrise/sunset.
    months_touched, seen = [], set()
    cur = start_date
    while cur <= end_date:
        ym = (cur.year, cur.month)
        if ym not in seen:
            seen.add(ym)
            months_touched.append(ym)
        cur += timedelta(days=1)
    for (y, m) in months_touched:
        try:
            warm_month_sunrise_sunset(lat_r, lon_r, tz_name, y, m, tail_days=1)
        except Exception:
            pass

    # Per-day lean entries.
    entries_by_date = {}
    d = start_date
    while d <= end_date:
        ent = _calendar_day_entry(lat_r, lon_r, tz_name, d, month_system, region)
        entries_by_date[ent["date"]] = ent
        d += timedelta(days=1)

    # One block per NEPALI SOLAR month (the Nepali patro layout): the grid shows the
    # Nepali month's days, big number = Nepali (Bikram Sambat) day, plus the gregorian
    # date. Cells are laid out Sunday-first by the gregorian weekday; leading days are
    # padded with null so the columns line up.
    ordered = [entries_by_date[k] for k in sorted(entries_by_date)]
    groups = []
    for ent in ordered:
        key = (ent["bs_year"], ent["nepali_solar_month"])
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(ent)

    months = []
    for (bs_year, nmonth), ents in groups:
        first = datetime.strptime(ents[0]["date"], "%Y-%m-%d").date()
        last = datetime.strptime(ents[-1]["date"], "%Y-%m-%d").date()
        # Find the sankranti (first gregorian day in this rashi) by stepping back, so
        # Nepali day numbers are anchored to the real month start even if the range
        # begins mid-month.
        sankranti = first
        for _ in range(40):
            prev = sankranti - timedelta(days=1)
            if _calendar_sun_rashi_noon(lat_r, lon_r, tz_name, prev) == ents[0]["sun_rashi"]:
                sankranti = prev
            else:
                break
        for ent in ents:
            dt = datetime.strptime(ent["date"], "%Y-%m-%d").date()
            ent["nepali_day"] = (dt - sankranti).days + 1
        # Sunday-first weekly grid over the in-range span of this month.
        start_pad = (first.weekday() + 1) % 7   # Python Mon=0..Sun=6 -> Sunday-first offset
        cells = [None] * start_pad + ents
        while len(cells) % 7:
            cells.append(None)
        weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)]
        disp = NEPALI_MONTH_DISPLAY.get(nmonth, nmonth)
        months.append({
            "nepali_month": nmonth,
            "nepali_month_display": disp,
            "bs_year": bs_year,
            "gregorian_span": f"{first.strftime('%b %d')} – {last.strftime('%b %d, %Y')}",
            "title": f"{disp} {bs_year}",
            "subtitle": NEPALI_MONTH_THEME.get(nmonth, "Sacred Nepali Month"),
            "month_basis": "nepali_solar_sidereal",
            "weeks": weeks,
        })

    # Auspicious-day highlight panel (date order). A day may surface its Shravan
    # Monday plus one spiritual festival/tithi theme; the first Shravan Monday is
    # labelled "First Shravan Somvar".
    highlights = []
    first_somvar = True
    d = start_date
    while d <= end_date:
        ent = entries_by_date.get(d.isoformat())
        d += timedelta(days=1)
        if not ent:
            continue
        for htype, title in _calendar_day_highlights(ent):
            if htype == "shravan_somvar":
                title = "First Shravan Somvar" if first_somvar else "Shravan Somvar"
                first_somvar = False
            content = CALENDAR_HIGHLIGHT_CONTENT.get(htype, CALENDAR_HIGHLIGHT_CONTENT["festival"])
            highlights.append({
                "date": ent["date"],
                "day": ent["day"],
                "nepali_day": ent.get("nepali_day"),
                "nepali_month": ent.get("nepali_solar_month"),
                "bs_year": ent.get("bs_year"),
                "weekday": ent["weekday"],
                "title": title,
                "tithi": ent["tithi"],
                "type": htype,
                "points": content["points"],
            })

    return months, highlights


__all__ += [
    "build_panchanga_calendar", "_calendar_day_entry", "_calendar_markers",
    "_calendar_day_highlights", "_calendar_bs_year", "_calendar_sun_rashi_noon",
]
