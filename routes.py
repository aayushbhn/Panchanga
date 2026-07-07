"""JSON API endpoints (POST): /astrology, /monthly-panchanga, /panchanga-range,
/panchanga-date, /notifications.
"""
from datetime import datetime, timedelta
import numpy as np
import pytz
from flask import request, jsonify

from webapp import app
from constants import *
from utils import *
from calculations import *
from helpers import *


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
        nak_idx        = _to_int_scalar(nakshatra_index_at(t_now, moon_sid=moon_sid))
        nakshatra_name = nakshatras[nak_idx]
        yoga_name      = yoga_names[_to_int_scalar(yoga_index_at(t_now, sun_sid=sun_sid, moon_sid=moon_sid))]
        karana_name    = karana_name_from_number(_to_int_scalar(karana_index_at(t_now, angle=angle)))

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
            significance=significance_text,
        )
        response_payload = order_day_payload(response_payload)
        response_payload["app_response"] = app_response
        response_payload["notifications"] = notifications_block
        return jsonify(response_payload)

    except Exception as e:
        return jsonify({"error": str(e)}), 400

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

        # Pre-warm sunrise/sunset & moonrise/moonset caches for the whole month in
        # two find_discrete passes (vs ~30 each) — identical values, far fewer
        # ephemeris/nutation evaluations. Sunrise must be warmed before the moon
        # pass (the moon windows are sunrise -> next sunrise).
        warm_month_sunrise_sunset(lat_r, lon_r, timezone_str, year, month)
        warm_month_moonrise_moonset(lat_r, lon_r, timezone_str, year, month)

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

            day_events = _slice_upcoming_spiritual_events(events_by_date, target_date.date(), days_ahead=7)
            day_app_response = build_app_response(
                day_data,
                day_events,
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
                "notifications": build_day_notifications(day_data, day_events),
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
            warm_month_sunrise_sunset(lat_r, lon_r, timezone_str, y, m)
            warm_month_moonrise_moonset(lat_r, lon_r, timezone_str, y, m)
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

            day_events = _slice_upcoming_spiritual_events(merged_events, target_date.date(), days_ahead=7)
            day_app_response = build_app_response(
                day_data,
                day_events,
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
                "notifications": build_day_notifications(day_data, day_events),
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


@app.route("/panchanga-calendar", methods=["POST"])
def panchanga_calendar_api():
    """Calendar-focused panchanga for a month or an arbitrary date range — festivals,
    tithis (English + Devanagari), vratas, subh/asubh muhurat, icon markers, and an
    auspicious-days highlight panel. Pass either {month, year} for a single gregorian
    month, or {start_date, end_date} (YYYY-MM-DD, max 366 days) for any range."""
    try:
        data = request.get_json(force=True)
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        month_system = (data.get("month_system") or "both").strip().lower()
        region = data.get("region")

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"error": "Invalid latitude or longitude."}), 400

        # Range from {month, year} (whole gregorian month) or explicit start/end dates.
        if data.get("month") and data.get("year"):
            month = int(data.get("month"))
            year = int(data.get("year"))
            if not (1 <= month <= 12):
                return jsonify({"error": "Invalid month. Must be between 1 and 12."}), 400
            if not (1900 <= year <= 2100):
                return jsonify({"error": "Invalid year. Must be between 1900 and 2100."}), 400
            start_date = datetime(year, month, 1).date()
            nxt = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
            end_date = (nxt - timedelta(days=1)).date()
        else:
            try:
                start_date = datetime.strptime(str(data.get("start_date")).strip(), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(data.get("end_date")).strip(), "%Y-%m-%d").date()
            except Exception:
                return jsonify({"error": "Provide either {month, year} or {start_date, end_date} in YYYY-MM-DD."}), 400
            if end_date < start_date:
                return jsonify({"error": "end_date must be on or after start_date."}), 400
            if not (1900 <= start_date.year <= 2100 and 1900 <= end_date.year <= 2100):
                return jsonify({"error": "Dates must be between years 1900 and 2100."}), 400

        if (end_date - start_date).days + 1 > 366:
            return jsonify({"error": "Date range too large (max 366 days)."}), 400

        # Deterministic for (request body, UTC day) → response-cacheable.
        cache_key = _response_cache_key("/panchanga-calendar", data)
        cached = _response_cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)
        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

        months, highlights = build_panchanga_calendar(
            lat_r, lon_r, timezone_str, start_date, end_date, month_system, region
        )

        response_dict = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            # `month_system` controls lunar FESTIVAL matching (both | amanta | purnimanta).
            # The calendar grid itself is grouped by the NEPALI SOLAR month (Saun/
            # Shrawan = Sun in Cancer), with Bikram Sambat day numbers — same basis as
            # the Nepali patro and the Shravan Somvar vrat.
            "month_system": month_system,
            "month_convention": "nepali_solar_sidereal",
            "note": ("Nepali solar months and BS day numbers are derived from the Sun's "
                     "sidereal sankranti at local noon; they may differ by ±1 day from "
                     "the official published patro at month boundaries. Tithis, festivals "
                     "and vratas are lunar."),
            "calendar": months,
            "highlights": highlights,
        }
        _response_cache_put(cache_key, response_dict)
        return jsonify(response_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 400
