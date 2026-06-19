# Panchanga Notifications — Implementation Plan

**Project:** Nepa Rudraksha — Panchanga Notification System
**Owner:** Aayush Bhandari
**API:** `api.py` (Flask + Skyfield), consumed by the mobile app
**Last updated:** 2026-06-17
**Status:** Draft for review

---

## 1. Objective

Deliver location-aware, calendar-driven and chart-driven notifications to the mobile
app, powered entirely by the existing Panchanga API. The phone app is the **only**
consumer of the API. No additional backend service is introduced on the server side —
all server work is additive changes to `api.py`.

The notifications to ship:

1. **Daily auspicious-day alert** — tithi name + short description.
2. **Festival countdown** — 7-day, 3-day, and day-of messages with blog links and
   recommended Rudraksha mukhi.
3. **Shravan month Sunday/Monday alerts** — Maha Pooja advance notice (Sunday) and
   live-now alert (Monday).
4. **Significant transit beginning** — a major planet enters a new house in the
   user's chart.
5. **Dasha change** — user enters a new Mahadasha.
6. **Personal auspicious date** — best days for the user's specific chart.
7. **Eclipse alert** — lunar/solar eclipse affecting the user's chart.

---

## 2. Responsibility split

| Concern | Owner |
|---|---|
| Panchanga & astro computation | **API (`api.py`)** — stateless, compute only |
| Device tokens, push delivery (FCM/APNs) | **Phone app** |
| User location, birth details, send-time preference | **Phone app** |
| "Already notified" record (de-dupe change events) | **Phone app** |
| Scheduling when to fire a notification | **Phone app** |
| Notification copy / blog links / mukhi & livestream content | **API content tables** (single source of truth for all clients) |

The API never pushes. It returns notification-ready data; the app decides when to fire.

---

## 3. Location handling (core design rule)

Panchanga data is location-dependent:

- **Tithi rollover** happens at a single UTC instant, but the *local calendar date* it
  lands on differs by timezone (a festival can be Aug 9 in Nepal, Aug 8 in California).
- **Sunrise — and therefore every muhurta** (Brahma, Abhijit, Rahu Kaal, …) — depends on
  exact latitude/longitude.
- **Festival "day"** is determined by the sunrise-anchored tithi, so it is location-sensitive.

The API already solves this: it derives the timezone from `latitude`/`longitude` and
localizes the entire response.

**The single rule the app must follow:** send the user's **current coordinates on every
API call**. Store the device's last-known lat/lon, refresh it daily (or on significant
location change) before the scheduled call, and never hardcode a city. Travel is handled
automatically — the next call uses the new coordinates and returns correct data.

---

## 4. Current system audit

Single stateless Flask app, `api.py` (~4,400 lines), Skyfield + `de421.bsp`, deployed via
Docker/Vercel. The one functional endpoint is `/astrology` (POST), which accepts
`latitude`, `longitude`, optional `rashi`, and optional `birth_details`, and returns a
full daily panchanga localized to the location, plus a personalized horoscope/transit
reading when birth details are supplied.

### Already built (directly reusable)

| Capability | Function | Location |
|---|---|---|
| Daily tithi + significance text | `generate_significance`, `generate_daily_summary` | `api.py:1765`, `api.py:1826` |
| Festival countdown window | `get_upcoming_spiritual_events`, `get_upcoming_poojas` | `api.py:2569`, `api.py:2197` |
| Amanta/Purnimanta month (Shravan detection) | `calculate_amanta_purnimanta_month_fast` | `api.py:2047` |
| Transit → house from natal Moon sign | `_personalized_transits_from_kundali` | `api.py:3070` |
| Days until planet changes sign | `_compute_sign_changes` | `api.py:2999` |
| Current Mahadasha/Antardasha (name only) | (from external kundali API) | `api.py:3423` |
| Timezone & per-coordinate caching | `cached_timezone_str`, `round_coord` | `api.py:806`, `api.py:796` |

### Gaps to build

| Gap | Severity | Notes |
|---|---|---|
| Notification-shaped response block | Low | Pure assembly of existing data |
| Festival `days_away` + content hooks | Low | Add field + content table |
| Shravan Sun/Mon flags | Low | Detect + expose |
| Transit ingress dates incl. **Saturn** | Medium | `_compute_sign_changes` skips Saturn (`api.py:3000`) |
| Dasha **dates** (not just name) | Medium | Verify external API; else compute Vimshottari locally |
| Personal auspicious-day scoring | Medium | New scoring function |
| **Eclipse computation** | High | No eclipse code exists anywhere |

---

## 5. Endpoint strategy

Two endpoints, split by cadence and data dependency — **not** one giant route, and not
seven separate ones.

- **Calendar notifications (1–3) are embedded in the existing `/astrology` route** as a
  `notifications` block. The app already calls `/astrology` daily for the panchanga
  screen, and tithi/festival/month are already computed in that request — so this is free
  assembly with no extra call and no extra compute.
- **Personalized chart notifications (4–7) live behind one new `/notifications` route**
  (requires `birth_details`). They all derive from the same kundali, change rarely, and
  are polled weekly/monthly — grouping them lets the app make a single slow-cadence call
  and keeps heavy/net-new code (eclipse, Saturn-safe ingress) out of the daily hot path.

```
POST /astrology      → ...existing payload (unchanged)...
                       + notifications: { daily_auspicious, festival_countdown, shravan_event }

POST /notifications  → { transits: [...], dasha_change: {...},
                         auspicious_days: [...], eclipses: [...] }
```

> **Compatibility constraint:** the existing `/astrology` request parameters and response
> fields must not change. The `notifications` block is **purely additive**.

## 6. Part A — Server changes (`api.py`)

### A1. Add a `notifications` block to `/astrology` *(low effort, do first)* — ✅ DONE

Assemble a compact, notification-ready block so the app needs no business logic for the
calendar notifications. All inputs already exist.

**Implemented:** `_event_key` + `build_notifications_block` (`api.py`, after
`order_day_payload`). The block is attached after `order_day_payload` in the `/astrology`
route (alongside `app_response`) so the shared ordering function — and the monthly /
`/panchanga-date` endpoints that reuse it — are untouched. Existing request params and
response fields are unchanged; the block is purely additive. `blog_url` and
`recommended_mukhi` are returned as `null`, to be filled by A2/A3.

```json
"notifications": {
  "daily_auspicious": {
    "title": "Today is Ekadashi",
    "body": "A sacred day for fasting and Vishnu worship...",
    "tithi": "Ekadashi"
  },
  "festival_countdown": [
    {"festival": "Guru Purnima", "festival_key": "guru_purnima",
     "days_away": 3, "tithi_date": "2026-07-09",
     "blog_url": "https://...", "recommended_mukhi": "X"}
  ],
  "shravan_event": {
    "is_shravan": true, "weekday": "Sunday", "type": "advance_notice"
  }
}
```

Sources: `tithi_name`, `generate_significance` (`api.py:1765`),
`get_upcoming_spiritual_events` (`api.py:2569`), month from `api.py:2047`.

### A2. Festival countdown — explicit `days_away` + content hooks — ✅ MOSTLY DONE

- ✅ `days_away` and `festival_key` returned for each entry; list sorted ascending.
- ✅ Added `FESTIVAL_CONTENT` table (`api.py`, ~75 named festivals) with
  festival-specific `description`, a punchy `why_it_matters` (drives the notification
  body), and a traditional `recommended_mukhi`. `_festival_copy` prefers this table, then
  the event's own guidance, then the generic `_event_guidance` fallback — so named
  festivals (Ganga Dussehra, Guru Purnima, Dashain days…) no longer show a generic paksha
  description.
- ✅ **Decision confirmed:** content table lives in the API so copy ships without an app
  release.
- ⏳ **Remaining / to confirm by business:**
  - `recommended_mukhi` values are **traditional deity-based defaults — confirm against the
    Nepa Rudraksha catalogue.**
  - `blog_url` is intentionally left `null` (no fabricated links) — populate with real blog
    URLs per `festival_key`.
  - ~30 minor/regional festivals (Cheti Chand, Gangaur, Onam, Shakambhari, some Amavasya/
    Ekadashi variants) still use the accurate generic handler; add curated entries as needed.

### A3. Shravan Sunday/Monday flags

Detect `amanta_month == "Shravan"` and weekday in {Sunday, Monday}; expose in the
`shravan_event` block with `type` = `advance_notice` (Sunday) or `live_now` (Monday).
Maha Pooja livestream time/link lives in the API content table.

### A4. Transit ingress feed — fix Saturn *(medium)* — ✅ DONE (enriched)

Served by the new `/notifications` route (`transits` key), with `birth_details`. Returns
**only the single NEAREST upcoming transit** (one entry — the one worth a notification). All
significant planets (Mars, Jupiter, Saturn, Rahu, Ketu) are still computed and cached; only
the soonest ingress is surfaced. The entry carries full current+next detail, and both
`current_effect` and `next_effect` so the copy names both houses (current placement → the
move). Fields per entry:
- current sign + **current house** (from natal Moon), when it **entered** the current sign,
  **time in sign so far**, **duration in sign**, previous sign;
- **next sign + next house + next ingress date**, `days_until_next_ingress`, and
  `is_imminent` (within `transit_days`, default 45 — the notification trigger);
- `planet_nature`, house `effect` (uses `PLANET_HOUSE_INSIGHT`), `recommended_mukhi`,
  `pooja_practices`, a narrative `summary`, and ready-to-send `notification` copy.

Implementation: `_transit_calendar` finds each planet's sign boundaries by coarse-step +
**bisection on sampled positions**, so **retrograde is handled and Saturn is included** (the
old `_compute_sign_changes` skipped Saturn). The boundary search is user-independent, so it
is **cached once per UTC day** (and warmed in `_prewarm`); per-user only does the cheap house
mapping. Fast planets (Sun/Moon/Mercury/Venus) are excluded as non-significant.

> The app shows all planets in a transit view but fires a **notification only for
> `is_imminent`** entries. Ingress dates are ±1-day resolution.

Original analysis: `_compute_sign_changes`
(`api.py:2999`) currently **skips Saturn** (`api.py:3000`) because linear extrapolation
breaks on retrograde — but Saturn is the headline use case. Compute true ingress dates via
**bracket-and-bisect on the 30° sign boundary** (retrograde-safe). House derived from natal
Moon sign (`api.py:3070`).

```json
{"planet": "Saturn", "enters_sign": "Pisces", "enters_house": 10,
 "ingress_date": "2026-06-20",
 "effect": "A period of disciplined effort and lasting results begins.",
 "recommended_mukhi": "14"}
```

### Notification gating rule (applies to dasha, auspicious days, eclipses)

Each personalized section returns a `notify` boolean and a `notification` object that is
**null unless the event is actually near**. When `notify` is true the `notification` carries
a title + descriptive body. Windows:
- **Dasha:** notify if a new mahadasha started today or begins within **7 days**.
- **Auspicious days:** notify if **today** is auspicious for the chart.
- **Eclipses:** notify if the nearest eclipse is within **14 days**.

Supporting data (current dasha, `today` assessment, `upcoming` lists with descriptions) is
always returned so the app can display detail even when no push fires.

### A5. Dasha-change endpoint *(medium)* — ✅ DONE (gated)

Implemented **locally** (no external dependency) via `_vimshottari_periods` +
`_current_antardasha`, served by `/notifications` (`dasha_change` key). Computes the full
Vimshottari timeline from the natal Moon's nakshatra + birth time, and returns:
`current_mahadasha` (lord + start/end + duration), `current_antardasha`, `next_mahadasha`,
`mahadasha_started_today` (the notification trigger), `days_until_next_mahadasha`,
`recommended_mukhi`, and ready-to-send `notification` copy. No need to depend on
`KUNDALI_REPORT_URL` for dasha dates.

### A6. Personal auspicious-day scoring *(medium)* — ✅ DONE

Served by `/notifications` (`auspicious_days` key). `_build_auspicious_days` scores each day
by **Tarabala** (count from janma nakshatra → one of 9 taras; Sampat/Kshema/Sadhaka/Mitra/
Ati-Mitra are good) **and Chandrabala** (Moon's house from janma rashi; 1/3/6/7/10/11 good).
A day is auspicious when both are favourable. Returns `today` (assessment + description),
`upcoming` (auspicious days in the next 30, each with a description), and a gated
`notification` (fires when today is auspicious).

### A7. Eclipse endpoint *(high — net-new)* — ✅ DONE

Served by `/notifications` (`eclipses` key). `_eclipse_calendar` (cached once per day,
user-independent) finds lunar eclipses via `skyfield.eclipselib.lunar_eclipses` and solar
eclipses via New Moons whose ecliptic latitude is near 0. `_build_eclipses` maps each
eclipse's sidereal longitude → the user's house, returns `upcoming` (type, date, sign, house,
description) and a gated `notification` (fires within 14 days). Verified against the real
Aug 12 2026 solar and Aug 28 2026 lunar eclipses.

> Future refinement: solar-eclipse **visibility** is location-specific; current logic flags
> the eclipse globally. Add a visibility check from the user's `lat`/`lon` if needed.

---

## 7. Part B — App integration

The app runs one scheduled job per user per day at the user's preferred local time, calls
the API with **current coordinates** + birth details, reads the response, and fires pushes.
For change-events it keeps a small local record to avoid repeats and schedules local
notifications for future dates.

| # | Notification | API call | Cadence | App logic | Depends on |
|---|---|---|---|---|---|
| 1 | Daily auspicious | `/astrology` | Daily | Fire `notifications.daily_auspicious` | A1 |
| 2 | Festival countdown | `/astrology` | Daily | If `days_away` in {7,3,0}, fire matching copy + blog link | A2 |
| 3 | Shravan Sun/Mon | `/astrology` | Daily | If `shravan_event` present, fire advance-notice (Sun) / live-now (Mon) | A3 |
| 4 | Transit beginning | `/notifications` | Weekly | If `ingress_date == today`, fire once; record it | A4 |
| 5 | Dasha change | `/notifications` | Weekly | If current-period start == today, fire once; record it | A5 |
| 6 | Personal auspicious | `/notifications` | Monthly | Schedule a local notification on each best-day | A6 |
| 7 | Eclipse | `/notifications` | Monthly | Schedule a local notification on each eclipse date | A7 |

**Cadence rationale:** calendar items need a daily call; transits/dasha/eclipses change
rarely, so the app polls weekly/monthly and schedules future-dated local notifications —
cheaper and resilient offline.

**Send-time scheduling:** the app stores each user's preferred local time and fires the
daily call/notification at that time using the device's local clock — no server scheduling
needed.

---

## 8. Build order & milestones

| Phase | Scope | Unlocks | Effort |
|---|---|---|---|
| **1** | A1, A2, A3 (response assembly + content table) | Notifications 1, 2, 3 | Low |
| **2** | A4 (Saturn-safe ingress) + A5 (dasha dates) | Notifications 4, 5 | Medium |
| **3** | A6 (auspicious scoring) | Notification 6 | Medium |
| **4** | A7 (eclipse module) | Notification 7 | High |

The only genuinely new *calculations* are eclipses (A7), Saturn-safe ingress dates (A4),
dasha dates (A5 — possibly just consuming the external API), and auspicious scoring (A6).
All calendar-notification data is already computed and only needs reshaping.

---

## 9. Open items / decisions

- [ ] Confirm whether `KUNDALI_REPORT_URL` returns the dasha timeline with dates (drives A5 scope).
- [ ] Finalize festival → blog URL + recommended-mukhi content table (A2).
- [ ] Finalize Shravan Maha Pooja livestream times/links (A3).
- [ ] Confirm app stores and refreshes current coordinates before each call (Section 3).
- [ ] Decide retention policy for the app's "already notified" record (Notifications 4, 5).
