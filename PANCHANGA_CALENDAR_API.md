# `/panchanga-calendar` — Developer Guide

How to consume the `POST /panchanga-calendar` response to render the **Shravan calendar**
UI (month grid + "Auspicious Day To Wear Rudraksha" panel).

> The calendar is grouped by the **Nepali solar month** (Bikram Sambat — e.g. *Shravan/Saun*),
> which is the basis of the Nepali patro and the *Shravan Somvar* vrat. Tithis, festivals and
> vratas inside it are **lunar** (astronomically correct). The big number in each grid cell is
> the **Nepali day** (Saun 1–32); the small corner number is the **Gregorian date**.

---

## 1. Request

```jsonc
POST /panchanga-calendar
Content-Type: application/json

// Option A — a whole Gregorian month:
{ "latitude": 27.7103, "longitude": 85.3222, "month": 8, "year": 2026 }

// Option B — any inclusive date range (≤ 366 days), like /panchanga-range:
{ "latitude": 27.7103, "longitude": 85.3222,
  "start_date": "2026-07-17", "end_date": "2026-08-16" }
```
Optional: `month_system` (`both` | `amanta` | `purnimanta`, default `both`) controls lunar
**festival** matching; `region` (reserved).

> To render one clean Nepali month (as in the design), pass its Gregorian span, e.g. Shravan
> 2083 = `start_date: "2026-07-17"`, `end_date: "2026-08-16"`. A `{month, year}` that straddles
> two Nepali months (August does) returns **two** blocks.

---

## 2. Top-level response

| Field | Type | Meaning |
|---|---|---|
| `start_date`, `end_date` | string (`YYYY-MM-DD`) | Echoed range. |
| `latitude`, `longitude`, `timezone` | number / string | Location used; IANA tz derived from coords. |
| `month_system` | string | Lunar festival-matching system in effect. |
| `month_convention` | string | Always `"nepali_solar_sidereal"` — how months & day numbers are reckoned. |
| `note` | string | The ±1-day boundary caveat (see §7). |
| **`calendar`** | array | One **month block** per Nepali solar month (§3). Render one grid per block. |
| **`highlights`** | array | The left **"auspicious days"** panel (§5). |

---

## 3. A `calendar[]` block  → the month grid + header

```jsonc
{
  "nepali_month": "Shrawan",          // canonical key
  "nepali_month_display": "Shravan",  // ← use for the header title
  "bs_year": 2083,                    // Bikram Sambat year
  "gregorian_span": "Jul 17 – Aug 16, 2026",
  "title": "Shravan 2083",            // ready-made title (Nepali month + BS year)
  "subtitle": "Sacred Month of Lord Shiva",   // ← header subtitle
  "month_basis": "nepali_solar_sidereal",
  "weeks": [ [cell|null × 7], ... ]   // Sunday-first rows; see §4
}
```

**Header** (`Shravan (August) 2026` / `Sacred Month Of Lord Shiva` in the design):
- Line 1 → `nepali_month_display` + the Gregorian month/year. You can show `title`
  (`"Shravan 2083"`) directly, or compose the design's exact look as
  `` `${nepali_month_display} (${gregorianMonth}) ${gregorianYear}` `` using `gregorian_span`.
- Line 2 → `subtitle`.

**Grid** — `weeks` is an array of rows, each row is **exactly 7 entries, Sunday → Saturday**
(columns `SUN MON TUE WED THU FRI SAT`). An entry is either a **day cell** (§4) or `null`
(empty leading/trailing slot — render an empty box). No date math needed: iterate `weeks`,
then each row's 7 slots in order.

---

## 4. A day **cell** → one calendar box

```jsonc
{
  "nepali_day": 4,                 // ← BIG number in the box (Saun 4)
  "date": "2026-07-20",            // ← small corner: Gregorian date
  "day": 20,                       //    Gregorian day-of-month (= corner number)
  "weekday": "Monday",
  "tithi": "Saptami",              // ← tithi label under the number
  "tithi_devanagari": "सप्तमी",
  "tithi_number": 7,               //    1–15 Shukla, 16–30 Krishna
  "paksha": "Shukla Paksha",
  "nakshatra": "Hasta",
  "nepali_solar_month": "Shrawan",
  "sun_rashi": "Cancer",
  "bs_year": 2083,
  "lunar_month": "Ashadha",        //    lunar (amanta) month — informational
  "festivals": [],                 // ← festival name(s) for the cell's sub-label
  "vratas": ["Somvar Vrat"],       //    vrat/barta names
  "poojas": [ {"name","reason","variant_id"} ],   // suggested poojas (Shopify variant_id)
  "subh_muhurat": { "abhijit": {"start","end"}, "brahma": {"start","end"} },
  "asubh_muhurat": { "rahu_kaal":{...}, "gulika_kaal":{...}, "yamaganda_kaal":{...} },
  "markers": ["shravan_somvar"],   // ← drives the ICONS + highlight tint (§4.1)
  "moon_phase": null,              //    "full" | "new" | null  (moon glyph)
  "is_auspicious_to_wear_rudraksha": true,  // ← tint the cell (green in the design)
  "in_range": true
}
```

### What renders where (matches the design box)
```
┌─────────────────────────────┐
│ 19            🔱 ← markers   │   top-left  small  = `date` / `day` (Gregorian)
│   04          ← nepali_day   │   center    big    = `nepali_day`
│ • Shravan Monday ← vratas/   │   sub-label (gold) = festival / "Shravan Monday" / vrat
│   Shashthi    ← tithi        │   bottom            = `tithi`
└─────────────────────────────┘
```
- **Big number** = `nepali_day`. **Corner number** = `day` (or parse `date`).
- **Bottom label** = `tithi`.
- **Gold sub-label** = first of: a `festivals[]` entry, else "Shravan Monday" when
  `markers` contains `shravan_somvar`, else a notable `vratas[]` entry (e.g. *Pradosh Vrat*).
- **Cell tint** (the green/cream highlight in the design) = `is_auspicious_to_wear_rudraksha`.

### 4.1 `markers` → icons (the trishul / snake / moon in the design)

| marker | meaning | suggested icon |
|---|---|---|
| `shravan_somvar` | Monday in Nepali Shravan | 🔱 trishul |
| `nag_panchami` | Nag Panchami | 🐍 snake |
| `shivaratri` | (Maha) Shivaratri | 🔱 / linga |
| `pradosh` | Trayodashi (Pradosh) | 🌙 crescent |
| `purnima` | Full-moon tithi | ● full moon (`moon_phase: "full"`) |
| `amavasya` | New-moon tithi | ○ new moon (`moon_phase: "new"`) |
| `ekadashi` | Ekadashi | (optional) |
| `chaturthi` | Chaturthi (Ganesh/Sankashti) | (optional) |
| `festival` | a named festival is present | (generic dot) |

`markers` is ordered; a day may have several (e.g. a Shravan Monday that is also Pradosh).
Use `moon_phase` for the literal moon glyph.

### 4.2 Muhurat (Subh / Asubh)
Each window is `{ "start": "07:02 AM", "end": "08:45 AM" }`.
- **Subh** (auspicious): `subh_muhurat.abhijit`, `subh_muhurat.brahma`.
- **Asubh** (avoid): `asubh_muhurat.rahu_kaal`, `asubh_muhurat.gulika_kaal`, `asubh_muhurat.yamaganda_kaal`.

---

## 5. `highlights[]` → the left "Auspicious Day To Wear Rudraksha" panel

Each card in the panel:
```jsonc
{
  "title": "First Shravan Somvar",   // ← card heading
  "type": "shravan_somvar",          //    machine type (icon/colour)
  "date": "2026-07-20",              //    Gregorian date
  "nepali_day": 4,                   // ← the badge number (Saun 4)
  "nepali_month": "Shrawan",
  "bs_year": 2083,
  "day": 20,                         //    Gregorian day (if you prefer the AUG badge)
  "weekday": "Monday",
  "tithi": "Saptami",
  "points": [                        // ← the bullet list under the heading
    "Most auspicious day to wear Rudraksha",
    "Start new spiritual practices",
    "Mantra chanting & meditation"
  ]
}
```
- **Badge** (the design's "AUG 04" chip) → `nepali_day` (Saun day). Use `day` instead if you
  want the Gregorian-date badge.
- **Heading** → `title`. **Bullets** → `points`.
- `highlights` is in **date order**. The first Shravan Monday is titled `"First Shravan Somvar"`;
  later ones are `"Shravan Somvar"`. `type` values: `shravan_somvar`, `nag_panchami`, `pradosh`,
  `purnima`, `amavasya`, `ekadashi`, `shivaratri`, `festival`.

---

## 6. Rendering recipe (pseudo-code)

```js
const res = await post("/panchanga-calendar", { latitude, longitude, start_date, end_date });

for (const block of res.calendar) {
  renderHeader(block.nepali_month_display, block.gregorian_span, block.subtitle);
  for (const week of block.weeks) {        // rows
    for (const cell of week) {             // 7 cols: Sun..Sat
      if (!cell) { renderEmptyBox(); continue; }
      renderBox({
        big:    cell.nepali_day,
        corner: cell.day,
        tithi:  cell.tithi,
        label:  cell.festivals[0]
                  ?? (cell.markers.includes("shravan_somvar") ? "Shravan Monday" : cell.vratas[0]),
        icons:  cell.markers,              // map via §4.1
        moon:   cell.moon_phase,
        tint:   cell.is_auspicious_to_wear_rudraksha,
      });
    }
  }
}

for (const h of res.highlights) {
  renderCard({ badge: h.nepali_day, title: h.title, bullets: h.points, type: h.type });
}
```

---

## 7. Caveat — Nepali day numbers vs. the official patro

`nepali_month`, `bs_year` and `nepali_day` are computed from the Sun's **sidereal sankranti at
local noon**. This matched the official **Saun 2083 = Jul 17 – Aug 16, 2026** in testing, but at a
month boundary the day count can differ by **±1 day** from the published patro (whose start-of-month
rule depends on the exact time of day of the sankranti). Tithis, festivals and vratas are lunar and
unaffected. If you need day numbers that are bit-exact to the official Nepali patro, ask the API team
to switch to a published BS conversion table.
