# Panchanga — Fixes & Additions Report

All changes are **additive**: existing response field names, festival/vrata dict
schema, and keywords are unchanged. New fields and tables were added alongside.
Every route was smoke-tested (200 OK) and key behaviours validated against 2026.

---

## 1. Tithi correctness — Udaya Tithi (the main fix)

**Problem:** the day's tithi was sampled at the wrong instant — `/astrology` used
"right now", the dated/monthly routes used **local noon**. So an Ekadashi running
Mon 4 PM → Tue 3 PM could show on Monday.

**Fix:** the day's tithi/nakshatra/yoga/karana + lunar month are now sampled at
**sunrise (Udaya)** everywhere — the canonical Hindu rule, matching the Nepali patro.
- `_calculate_panchanga_for_date_uncached` and `_calendar_day_entry` sample at sunrise.
- `/astrology` headline `tithi` is the Udaya tithi of the day.
- Festival matching is Udaya by default, with **per-festival night overrides**
  (`NIGHT_TITHI_FESTIVALS`) so Shivaratri/Diwali/Holika Dahan/Naraka & Bala
  Chaturdashi still match on their night (Nisita) tithi.

## 2. `current_*` and `next_*` anga timelines (new fields)

Every day payload now carries, for tithi/nakshatra/yoga/karana:
- `current_tithi` / `current_nakshatra` / `current_yoga` / `current_karana` — the
  running anga **with `start` and `end`** (previously these were `null`).
- `next_tithi` / `next_nakshatra` / `next_yoga` / `next_karana` — what comes next,
  with `start` + `end`.

On `/astrology`, `tithi` = Udaya tithi of the day, while `current_tithi` = what is
running **right now** (sampled at the request time) + `next_tithi`. New helper
`compute_anga_windows()` (single date) and the reworked monthly batch supply these.

## 3. Event list quality

- **Krishna double-match fixed.** In the default `both` month system, every
  Krishna-paksha festival used to fire **twice** (its real purnimanta date + a
  spurious amanta date a fortnight later). Now Krishna festivals match purnimanta
  only → one correct date. (Removed ~10 spurious firings/year: Shattila, Varuthini,
  Nirjala, Aja, etc.)
- **"8 Ekadashi names" fixed.** `get_vratas_for_day` ignored each vrata's `month`,
  so every named Ekadashi (Vaikunta, Nirjala, Jaya, Mokshada…) matched on *every*
  Ekadashi. It is now **month-aware** — only the correct-month vrata appears. Same
  fix applies to Karwa Chauth, Ahoi Ashtami, etc.
- **Secular days removed from spiritual output.** Independence Day, Republic Day,
  Gandhi Jayanti, Christmas, Yoga Day, Lohri, Magh Bihu (`CALENDAR_SECULAR_FESTIVALS`)
  are now excluded from the spiritual-events feed and the day's headline event
  (previously only the calendar highlights filtered them).
- **Weekday vratas no longer hijack the headline.** Somvar…Ravivar vratas are never
  chosen as the day's primary spiritual event; a real festival, a tithi-based vrata,
  or the day's tithi is used instead (`_WEEKDAY_ONLY_VRATAS`).

## 4. Dynamic, day-specific guidance (`today_spiritual_guidance` + feed)

Previously `why_it_matters` / `who_should_use_it` / `recommended_practices` /
`avoid_practices` were **static paksha-only text**. Now:
- **`why_it_matters`** is a day-specific sentence woven from the actual tithi +
  paksha + nakshatra + yoga (`TITHI_NATURE_ESSENCE`) — it varies every day.
- **`recommended_practices`** name the **deity + concrete act per tithi**
  (`TITHI_PRACTICE`): e.g. Panchami → *chant the Saraswati mantra; favour study,
  music, and the arts*; Ekadashi → *chant Vishnu mantras; observe the fast*.
- Named events use their own significance (festival `FESTIVAL_CONTENT`, vrata
  significance, or keyword guidance) via the new `_spiritual_guidance_for()`.
- Same treatment applied to the **upcoming spiritual events** feed, and its
  `all_events` list is now de-duplicated.

## 5. New events added (data — same schema)

- **13 missing Ekadashis** (completes the 24): Kamada, Papmochani, Mohini, Apara,
  Yogini, Kamika, Papankusha, Indira, Rama, Utpanna, Saphala, Amalaki, Vijaya —
  each verified to fall on a single correct date in 2026.
- **Nepal festivals** (approved subset): Janai Purnima / Rishi Tarpani, Kushe Aunsi
  (Father's Day), Mata Tirtha Aunsi (Mother's Day), Bala Chaturdashi, Chaite Dashain,
  Ghode Jatra. *(Excluded per instruction: Gai Jatra, Indra Jatra, Yomari Punhi,
  Sithi Nakha, the three Losars, Maghe Sankranti renaming.)*
- **Pan-Hindu:** Akshaya Navami, Skanda Shashti; **vratas** Masik Durga Ashtami,
  monthly Skanda Shashti, and **Mangala Gauri Vrat** (Shravan solar Tuesdays).
- **12 Sankrantis** (computed): the Sun's sidereal ingress into each rashi is
  detected at sunrise (`sankranti_for_date`) and surfaced as an event. Makar
  Sankranti keeps its existing fixed-date entry (no duplication).
- **Eclipses / Grahan** (computed & validated): `find_eclipses_in_range` detects
  solar (New Moon near node) and lunar (Full Moon near node) eclipses. Validated
  against all four 2026 eclipses (Feb 17, Mar 3, Aug 12, Aug 28). Surfaced as
  "Surya/Chandra Grahan" with Sutak-aware guidance (mantra/meditation; avoid new
  work, food, temple worship). Cached per year for speed.

## 6. Shravan

- Shravan Somvar highlights are numbered **First … Sixth Shravan Somvar**, reset per
  Nepali solar Shrawan month.
- **Mangala Gauri Vrat** added on Shravan (solar Shrawan) Tuesdays.

## 7. Performance

- **Monthly: ~11.5 s → ~2 s** cold. The month batch (`compute_month_anga_end_times_batch`)
  was reworked to be **sunrise-referenced** and to return the full current+next
  windows in its single 4-`find_discrete` pass, so per-day `find_discrete` is avoided
  again while staying Udaya-correct.
- **Single date ~0.4 s**, **calendar ~0.3 s**, **range (10 days) ~1 s** cold.
- Eclipses cached per (year, tz); Sankranti sun-rashi lookup memoised.
- **Note on the "20 s daily":** the compute is ~0.4 s. The remaining latency on
  personalized/first calls is the **external kundali (12 s) and mantra (10 s) HTTP
  timeouts** (`KUNDALI_TIMEOUT_SECONDS`, mantra `timeout=10`). Mantra is cached after
  the first call; kundali only runs when birth details are supplied. If you want a
  tighter ceiling, lower those two timeouts — that is a business/UX trade-off (slow
  chart API vs. degraded personalization), so I left the values as-is.

---

## Files touched
- `constants.py` — new festivals/vratas; `NIGHT_TITHI_FESTIVALS`, `SANKRANTI_NAMES`,
  `TITHI_PRACTICE`, `TITHI_NATURE_WHO/RECOMMEND/AVOID/ESSENCE`.
- `calculations.py` — `compute_anga_windows`, sunrise-referenced windowed batch,
  `sankranti_for_date`, `find_eclipses_in_range`.
- `helpers.py` — Udaya sampling, dynamic guidance (`_dynamic_tithi_guidance`,
  `_spiritual_guidance_for`), month-aware vratas, secular filter, `extra_solar_events`,
  eclipse cache, `current_*`/`next_*` in payload + `order_day_payload`, Shravan numbering.
- `routes.py` — `/astrology` Udaya headline + `current_*`/`next_*`; batch caller signature.
- `utils.py` — `_prev_day_ymd`.

## Follow-ups (not done, flagged honestly)
- Golden fixtures (`_verify.py`, `_verify_routes.py`) will now differ **by design**
  (Udaya vs noon, dedupe, new events) — regenerate them; don't treat the diffs as
  regressions.
- Grahan **Sutak pooja suppression**: eclipses are surfaced, but the tithi-based
  pooja recommender is not yet suppressed during Sutak — worth adding.
- The 3 pre-existing dead festival entries (Varalakshmi weekday-rule, Onam nakshatra,
  "Shravana Somvar Vrat (Mondays)") still never match; left as-is (niche, non-Nepal)
  rather than change matching signatures further.
- Eclipse detection uses ecliptic-latitude limits (good for date/type); it does not
  compute per-location visibility or exact magnitude.
