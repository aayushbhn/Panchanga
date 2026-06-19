# App Integration Guide — Panchanga Notifications

**Audience:** Mobile app team
**API:** the Panchanga API (`api.py`)
**Status:** All notification data below is **implemented and available now.**

This document describes exactly what the app receives and how to turn it into the
notifications in the product spec. The API computes everything; the app schedules and
delivers the pushes.

---

## 1. The two endpoints

| Endpoint | Method | Purpose | Cadence the app should call |
|---|---|---|---|
| `/astrology` | POST | Daily panchanga **+ calendar notifications** (Section 2) | **Daily**, at the user's preferred local time |
| `/notifications` | POST | **Personalized chart notifications** (Section 3) | **Weekly** (transits/dasha) and the app schedules future-dated local pushes |
| `/panchanga-range` | POST | Per-day panchanga for an **inclusive date range** (may span months) | On demand (calendar/range views) |

### `/panchanga-range`
Same per-day shape as `/monthly-panchanga`, but you pass a date range instead of a month.
```json
{
  "latitude": 27.7172,          // REQUIRED
  "longitude": 85.3240,         // REQUIRED
  "start_date": "2026-06-28",   // REQUIRED (YYYY-MM-DD, inclusive)
  "end_date": "2026-07-03",     // REQUIRED (YYYY-MM-DD, inclusive)
  "month_system": "both",       // optional
  "rashi": "Gemini",            // optional — personalized horoscope per day
  "name": "...", "date_of_birth": "...", "time_of_birth": "...",
  "birth_latitude": ..., "birth_longitude": ..., "birth_timezone": "..."  // optional
}
```
Returns `{ start_date, end_date, total_days, timezone, panchanga_data: [...], app_response: [...] }`
— `panchanga_data` is one full day object per date (tithi, nakshatra, muhurtas, festivals,
etc.), `app_response` is the per-day personalized block. **Validation:** `end_date` ≥
`start_date`, years 1900–2100, **max 366 days** per request.

### Golden rule — always send the user's **current** `latitude`/`longitude`
The API derives the timezone from coordinates and localizes everything. Refresh the device's
location daily before the call. This is what makes notifications fire on the correct **local
day** (a festival can be Aug 9 in Nepal, Aug 8 in the US).

### Birth chart uses **birth** location, not current location
For personalized data, send the `birth_*` fields. The API uses the **birth** location/timezone
for the chart and the **current** location for "today" — never mix them. Send `birth_timezone`
when you have it; otherwise it is auto-derived from the birth coordinates.

---

## 2. Request payloads

### `/astrology` (daily calendar notifications)
```json
{
  "latitude": 27.7172,          // REQUIRED — current location
  "longitude": 85.3240,         // REQUIRED — current location
  "month_system": "both"        // optional
}
```
Add the `birth_*` fields (below) too if you also want the personalized horoscope in the same
response — but the calendar `notifications` block does not need them.

### `/notifications` (personalized chart notifications)
```json
{
  "latitude": 27.7172,          // recommended — current location (for correct local "today")
  "longitude": 85.3240,         // recommended
  "date_of_birth": "2000-01-20",// REQUIRED (YYYY-MM-DD)
  "time_of_birth": "07:21",     // REQUIRED (HH:MM)
  "birth_latitude": 25.7103,    // REQUIRED
  "birth_longitude": 80.3222,   // REQUIRED
  "birth_timezone": "Asia/Kolkata", // recommended (else derived from birth coords)
  "transit_days": 45            // optional — transit look-ahead / imminent window
}
```
Missing birth fields → `400` with an explanatory `error`.

---

## 3. Section 2 — Calendar notifications (from `/astrology`)

The response contains a top-level **`notifications`** object:

```json
"notifications": {
  "daily_auspicious":  { ... },
  "festival_countdown": [ ... ],
  "shravan_event": null
}
```

### 3.1 Auspicious day alert (daily)
```json
"daily_auspicious": {
  "title": "🪔 A blessed पञ्चमी — make today count",
  "body":  "Magha (Pitru's star) colours the day. Your sharpest window is 08:36 AM–10:20 AM (Amrit Kaal). Open your Panchanga to time it right →",
  "tithi": "पञ्चमी",
  "nakshatra": "Magha"
}
```
**Fire:** every day. Use `title` + `body` directly. Copy changes daily and adapts to the
tithi nature (auspicious vs Rikta) and any festival.

### 3.2 Festival countdown
`festival_countdown` is a list **sorted ascending by `days_away`**. Each entry:
```json
{
  "festival": "Guru Purnima",
  "festival_key": "guru_purnima",
  "days_away": 3,
  "date": "2026-06-26",
  "title": "⏳ Guru Purnima is 3 days away",
  "body":  "Guru Purnima is in 3 days. Your 5 Mukhi is most powerful on this day — prepare now →",
  "description": "Guru Purnima honours the spiritual teacher (guru) ...",
  "recommended_mukhi": "5",
  "blog_url": null
}
```
The `body` is **stage-aware** and already matches the spec:
- **7 days out:** "Guru Purnima is 7 days away. … Here is how to prepare →"
- **≤3 days out:** "Guru Purnima is in 3 days. Your 5 Mukhi is most powerful on this day — prepare now →"
- **Day of (`days_away` 0):** "Today is Guru Purnima. … Here is your complete practice guide →"

**Fire:** when `days_away` ∈ {7, 3, 0} (or whatever marks you choose). Append `blog_url` once
the business fills it (see §6).

### 3.3 Shravan Maha Pooja (Sunday / Monday)
`shravan_event` is `null` except on **Sundays and Mondays of Shravan month**:
```json
"shravan_event": {
  "is_shravan": true,
  "weekday": "Sunday",          // or "Monday"
  "type": "advance_notice",     // Sunday; "live_now" on Monday
  "maha_pooja_time": null,      // business fills (e.g. "6:00 AM")
  "livestream_url": null,       // business fills
  "notification": {
    "title": "🔔 Tomorrow: 21 priests chant Rudri Paath live",
    "body":  "Tomorrow, 21 priests will chant Rudri Paath live. Nepa Rudraksha's Maha Pooja begins at [time]. Set your reminder →"
  }
}
```
- **Sunday (`advance_notice`)** and **Monday (`live_now`)** carry the spec copy.
- The Sunday body contains a literal **`[time]`** placeholder — the app substitutes
  `maha_pooja_time` (and attaches `livestream_url`) once the business sets them (see §6).

**Fire:** whenever `shravan_event` is non-null, fire its `notification`.

---

## 4. Section 3 — Personalized chart notifications (from `/notifications`)

Response shape:
```json
{
  "natal_moon_sign": "Gemini",
  "natal_nakshatra": "Ardra",
  "transits": [ ... ],          // nearest upcoming transit only (0 or 1 entry)
  "dasha_change": { ... },
  "auspicious_days": { ... },
  "eclipses": { ... }
}
```

### The gating contract (read this once)
`dasha_change`, `auspicious_days`, and `eclipses` each return a **`notify`** boolean and a
**`notification`** object that is **`null` unless the event is near**.
- **If `notify` is true** → fire `notification.title` + `notification.body`.
- **If `notify` is false** → do **not** push. The supporting data is still present so you can
  show it in a detail screen.

### 4.1 Significant transit beginning — `transits`
Returns **only the nearest upcoming transit** (the one worth a push), or `[]` if none.
```json
{
  "planet": "Mars",
  "current_sign": "Aries", "current_house": 11,
  "entered_current_sign_on": "2026-05-11",
  "next_sign": "Taurus", "next_house": 12,
  "next_ingress_date": "2026-06-21",
  "days_until_next_ingress": 2,
  "is_imminent": true,
  "current_effect": "...11th-house effect...",
  "next_effect": "...12th-house effect...",
  "recommended_mukhi": "3",
  "pooja_practices": { "deity": "...", "mantra": "...", "practices": [ ... ] },
  "summary": "Mars is placed in the 11th house ... transits to Vrishabha (Taurus) on June 21, 2026. Mars embodies ...",
  "notification": {
    "title": "🪐 Mars enters your 12th house",
    "body": "Mars is in your 11th house and on June 21, 2026 moves into your 12th house. ... Strengthen Mars with your 3 Mukhi. Tap to prepare →"
  }
}
```
**Fire:** when `is_imminent` is true (ingress within `transit_days`). On the day
`next_ingress_date` arrives, fire the `notification`; record it so it's sent once.

### 4.2 Dasha change — `dasha_change`
```json
{
  "notify": false,
  "current_mahadasha": { "lord": "Saturn", "start": "2016-04-16", "end": "2035-04-16", "duration_years": 19.0 },
  "current_antardasha": { "lord": "Sun", "start": "...", "end": "..." },
  "next_mahadasha": { "lord": "Mercury", "start": "2035-04-16" },
  "mahadasha_started_today": false,
  "days_until_next_mahadasha": 3223,
  "recommended_mukhi": "14",
  "notification": null
}
```
**Gate:** `notify` is true only when a new mahadasha **started today** or **begins within 7
days**. **Fire** the `notification` then. Otherwise show current dasha in a detail screen, no push.

### 4.3 Personal auspicious date — `auspicious_days`
```json
{
  "notify": false,
  "today": {
    "date": "2026-06-19", "is_auspicious": false,
    "tara": "Pratyari", "tara_meaning": "resistance (use caution)",
    "chandra_house": 3, "moon_nakshatra": "Magha", "moon_sign": "Leo",
    "description": "The Moon is in Magha — Pratyari Tara ... A routine day ..."
  },
  "upcoming": [ { "date": "2026-06-20", "tara": "Sadhaka", "description": "...", ... }, ... ],
  "notification": null
}
```
**Gate:** `notify` is true when **today** is auspicious for the chart → fire `notification`.
`upcoming` lists the auspicious days in the next 30 (each with a description) — use it to
schedule future local pushes or to populate a "best days" screen.

### 4.4 Eclipse alert — `eclipses`
```json
{
  "notify": false,
  "upcoming": [
    { "type": "Solar", "date": "2026-08-12", "sign": "Cancer", "house": 2,
      "house_theme": "income, speech and family resources", "days_until": 54,
      "description": "A solar eclipse falls in Cancer, your 2nd house ... focus on reflection, mantra, and charity." }
  ],
  "notification": null
}
```
**Gate:** `notify` is true when the nearest eclipse is **within 14 days** → fire
`notification`. Use `upcoming` to schedule a local push for each eclipse date.

---

## 5. App responsibilities (what the API does NOT do)

The API is stateless and never pushes. The app owns:
1. **Device tokens + push delivery** (FCM/APNs).
2. **Scheduling** — fire the daily `/astrology` pull + daily-alert at the user's preferred
   local time. Poll `/notifications` weekly; for `upcoming` eclipses/auspicious days, schedule
   future-dated **local** notifications so they fire even offline.
3. **De-duplication** — for one-time events (a transit ingress, a mahadasha start, an eclipse),
   keep a small "already sent" record keyed by event+date so it fires exactly once.
4. **Placeholder substitution** — replace `[time]` in the Shravan body with `maha_pooja_time`,
   and attach `blog_url` / `livestream_url` when present.
5. **Respecting the gates** — only push when `notify` is true (personalized) or when the
   relevant calendar field is present.

### Suggested per-notification trigger logic
| Spec notification | Source | Fire when |
|---|---|---|
| Auspicious day (daily) | `/astrology` → `notifications.daily_auspicious` | every day |
| Festival countdown | `/astrology` → `notifications.festival_countdown[]` | entry's `days_away` ∈ {7, 3, 0} |
| Shravan Sun/Mon | `/astrology` → `notifications.shravan_event` | field is non-null |
| Transit beginning | `/notifications` → `transits[0]` | `is_imminent` true, on `next_ingress_date` |
| Dasha change | `/notifications` → `dasha_change` | `notify` true |
| Personal auspicious | `/notifications` → `auspicious_days` | `notify` true (today), or schedule from `upcoming` |
| Eclipse | `/notifications` → `eclipses` | `notify` true, or schedule from `upcoming` |

---

## 6. Content the business must supply (currently `null`)

These fields are returned as `null` and should be filled (server-side content table is the
recommended home so updates ship without an app release):
- **`festival_countdown[].blog_url`** — the blog/practice-guide link per `festival_key`.
- **`festival_countdown[].recommended_mukhi`** — present for major festivals as **traditional
  defaults**; confirm against the Nepa Rudraksha catalogue.
- **`shravan_event.maha_pooja_time`** and **`livestream_url`** — the Maha Pooja start time and
  watch link.
- **`transits[].recommended_mukhi`** and **dasha `recommended_mukhi`** — navagraha-rudraksha
  defaults; confirm with the catalogue.

---

## 7. Coverage vs the product spec

| Spec item | Status |
|---|---|
| **2. Auspicious day alert (daily, tithi + short description)** | ✅ `daily_auspicious` |
| **2. Festival countdown (7 / 3 / day-of, blog, mukhi)** | ✅ `festival_countdown` (stage-aware copy; `blog_url` pending content) |
| **2. Shravan Sunday advance / Monday live** | ✅ `shravan_event` (time/link pending content) |
| **3. Significant transit beginning** | ✅ `transits` |
| **3. Dasha change** | ✅ `dasha_change` (gated 7 days) |
| **3. Personal auspicious date** | ✅ `auspicious_days` |
| **3. Eclipse alert** | ✅ `eclipses` (gated 14 days; solar **visibility** is a future refinement) |

Everything in the spec is available from the API today. Remaining work is **app-side
delivery/scheduling** and the **business content** in §6.
