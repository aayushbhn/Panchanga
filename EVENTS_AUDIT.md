# Panchanga Events Audit & Fix Plan

**Purpose:** Complete gap audit of festivals / vratas / Ekadashis / Sankrantis / eclipses,
plus the confirmed design decisions for the tithi correctness fixes.
Check off (`[x]`) the items you want implemented; strike out anything you want skipped.

**Confirmed decisions (from review):**
- **Tithi rule:** Udaya (sunrise) tithi is the day's label everywhere, **with per-festival
  night overrides** (Shivaratri = nisita/midnight, Diwali/Lakshmi = amavasya at night,
  Holika Dahan = pradosh, etc.).
- **Live `/astrology`:** split into `tithi` (Udaya tithi of the day) + `current_tithi`
  (running now, with `start`/`end`) + `next_tithi`.
- **Upcoming angas:** add next tithi/nakshatra/yoga/karana with start+end (reuse existing
  `find_discrete` arrays).

---

## PART A — Current inventory (what we already have)

- **Festivals:** 101 entries in `festival_mapping` (9 civil/fixed, ~89 lunar, 3 dead).
- **Vratas:** 25 entries in `vrata_mapping` (8 monthly-tithi, 7 weekday, 6 named Ekadashi, 4 month-specific).

### Known defects in existing data
- [ ] **Civil holidays treated as spiritual** — Republic Day, Independence Day, Gandhi Jayanti,
      Christmas, International Yoga Day, Lohri, Magh Bihu appear in the spiritual feed & pooja
      matching. `CALENDAR_SECULAR_FESTIVALS` filter is applied ONLY in the calendar highlights.
      → Add `"type": "civil"|"spiritual"` to every entry; filter upstream.
- [ ] **Dead entries that never fire** (require tithi+month+paksha, so skipped):
      `Shravana Somvar Vrat (Mondays)`, `Varalakshmi Vratam` (weekday_rule),
      `Onam (Thiruvonam – Nakshatra-based)`. → Implement weekday_rule + nakshatra matching, or remove.
- [ ] **Weekday vratas flood every day** — all 7 (Somvar…Ravivar) always match; raw list leaks
      into `/astrology` `vrata_today` and calendar. → gate behind flag / context.
- [ ] **Duplicate/near-duplicate**: `Makar Sankranti` and `Makar Sankranti (Solar) Reminder`;
      `Devuthani Ekadashi (Tulsi Vivah)` and `Tulsi Vivah`; `Gita Jayanti / Mokshada Ekadashi`
      overlaps vrata `Mokshada Ekadashi`. → dedupe.
- [ ] **No deity/region/nepali-alias fields** on festivals → needed for filtering & display.

---

## PART B — Missing NEPALI festivals (business-critical for nepalirudraksha.com)

Nepal-specific and Shaiva/rudraksha-relevant days currently absent:

- [ ] **Janai Purnima / Rishi Tarpani / Kwati Punhi** (Shravan Purnima) — major Shaiva day;
      currently only "Raksha Bandhan" occupies that tithi. HIGH priority.
- [ ] **Gai Jatra** (Bhadra Krishna Pratipada) — Newar, day after Janai Purnima.
- [ ] **Kushe Aunsi / Kuse Aunsi / Gokarna Aunsi** (Bhadrapada Amavasya) — Father's Day (Nepal).
- [ ] **Mata Tirtha Aunsi** (Baishakh Amavasya) — Mother's Day (Nepal).
- [ ] **Maghe Sankranti** (Makar Sankranti, Nepali name/framing) — add Nepali alias.
- [ ] **Sithi Nakha** (Jyeshtha Shukla Shashti) — Newar, Kumar Shashti.
- [ ] **Indra Jatra / Yenya** (Bhadra Shukla, ~Chaturdashi) — Kathmandu, 8 days.
- [ ] **Yomari Punhi** (Margashirsha/Mangsir Purnima) — Newar harvest.
- [ ] **Bala Chaturdashi** (Margashirsha Krishna Chaturdashi) — Pashupatinath/Shaiva. HIGH (Shiva).
- [ ] **Chaite Dashain / Chaitra Ashtami** (Chaitra Shukla Ashtami) — small Dashain.
- [ ] **Ghode Jatra** (Chaitra, Kathmandu).
- [ ] **Ropai / Asar 15 (Dahi-Chiura / Paddy Day)** — solar Asar, cultural.
- [ ] **Losar** (3): **Sonam Losar**, **Gyalpo Losar**, **Tamu Losar** — ethnic new years.
- [ ] **Buddha Jayanti** — present as "Buddha Purnima (Vesak)" ✓ (add Nepali alias).
- [ ] **Teej** — Hartalika & Hariyali present ✓ (confirm Nepali "Teej" naming/region tag).

---

## PART C — The 24 Ekadashis (half are missing)

Two Ekadashis per lunar month. ✓ = present, ☐ = missing. (Names by lunar month.)

- [x] Chaitra: **Kamada** (S) — ☐ MISSING / **Papmochani** (K) — ☐ MISSING
  - [ ] Add **Kamada Ekadashi** (Chaitra Shukla)
  - [ ] Add **Papmochani Ekadashi** (Chaitra Krishna)
- Vaishakha: [ ] **Mohini Ekadashi** (Shukla) MISSING / Varuthini (Krishna) ✓
- Jyeshtha: Nirjala (Shukla) ✓ / [ ] **Apara / Achala Ekadashi** (Krishna) MISSING
- Ashadha: Devshayani (Shukla) ✓ / [ ] **Yogini Ekadashi** (Krishna) MISSING
- Shravana: Putrada/Pavitra (Shukla) ✓ / [ ] **Kamika Ekadashi** (Krishna) MISSING
- Bhadrapada: Parsva/Parivartini (Shukla) ✓ / Aja (Krishna) ✓
- Ashwin: [ ] **Papankusha Ekadashi** (Shukla) MISSING / [ ] **Indira Ekadashi** (Krishna) MISSING
- Kartika: Devuthani/Prabodhini (Shukla) ✓ / [ ] **Rama Ekadashi** (Krishna) MISSING
- Margashirsha: Mokshada (Shukla) ✓ / [ ] **Utpanna Ekadashi** (Krishna) MISSING
- Pausha: Paush Putrada (Shukla) ✓ / [ ] **Saphala Ekadashi** (Krishna) MISSING
- Magha: Jaya (Shukla) ✓ / Shattila (Krishna) ✓
- Phalguna: [ ] **Amalaki Ekadashi** (Shukla) MISSING / [ ] **Vijaya Ekadashi** (Krishna) MISSING
- Adhik Maas: [ ] **Padmini** (Shukla) & **Parama** (Krishna) — only in leap month, MISSING

**Total missing Ekadashis: ~12 regular + 2 adhik.**

---

## PART D — The 12 Sankrantis (only 1 present)

Solar ingress into each rashi = punya-kaal. Only **Makar Sankranti** exists. Add the rest,
each as a solar/fixed-ish event (better: computed from exact sidereal ingress — see Part F).

- [x] Makar Sankranti (Capricorn) ✓
- [ ] Kumbha Sankranti (Aquarius)
- [ ] Meena Sankranti (Pisces)
- [ ] Mesha Sankranti (Aries) — **Nepali/Bengali New Year, Baisakh 1** HIGH
- [ ] Vrishabha Sankranti (Taurus)
- [ ] Mithuna Sankranti (Gemini)
- [ ] Karka Sankranti (Cancer) — **Shrawan 1 / start of Dakshinayana** HIGH
- [ ] Simha Sankranti (Leo)
- [ ] Kanya Sankranti (Virgo) — Vishwakarma Puja
- [ ] Tula Sankranti (Libra)
- [ ] Vrishchika Sankranti (Scorpio)
- [ ] Dhanu Sankranti (Sagittarius)

---

## PART E — Other pan-Hindu gaps

- [ ] **Skanda Shashti / Kumara Shashti** (Kartikeya, Shashti)
- [ ] **Masik Durga Ashtami** (Shukla Ashtami monthly) — currently only Kalashtami (Krishna) as vrata
- [ ] **Mangala Gauri Vrat** (Shravan Tuesdays) — women's Shravan vrat, MISSING
- [ ] **Shani Trayodashi / Shani Pradosh** (Saturday + Trayodashi) — special Shani day
- [ ] **Soma Pradosh / Bhaum Pradosh** (Mon/Tue + Trayodashi) — weekday-modified Pradosh
- [ ] **Purnima special names** beyond those present (e.g., Vaishakhi/Buddha ✓, Guru ✓,
      but **Sharad**, **Kartik** ✓; confirm all 12 named)
- [ ] **Amavasya special names** (Somvati Amavasya = Monday amavasya; Shani/Bhaumvati) — MISSING
- [ ] **Pitru Paksha (Shraddha) 16-day window** (Bhadrapada Krishna) — only Mahalaya Amavasya present
- [ ] **Navratri all 9 days named** (only "Begins", Saptami, Ashtami, Navami present) — add Ghatasthapana + daily Devi forms
- [ ] **Dhanwantari / Dhanteras** ✓ present
- [ ] **Tulsi/Amla Navami, Akshaya Navami** (Kartika Shukla Navami) — MISSING

---

## PART F — Eclipses (Grahan) — completely absent

Spiritually major (sutak period, temples closed, no pooja/food). Not tithi-matchable —
needs a dedicated astronomy module.

- [ ] **Surya Grahan (Solar eclipse)** — Sun/Moon conjunction near node (Amavasya)
- [ ] **Chandra Grahan (Lunar eclipse)** — Sun/Moon opposition near node (Purnima)
- [ ] Compute via Skyfield (node proximity + phase); expose date, type, start/peak/end, sutak window
- [ ] Suppress pooja recommendations during sutak; add a grahan notification/marker

---

## PART G — Correctness fixes (code, not data)

### G1. Udaya Tithi refactor (highest priority)
- [ ] New shared helper `angas_at(t)` returning tithi/paksha/nakshatra/yoga/karana + month.
- [ ] Sample the **day's sunrise** (not noon, not `now`) for the day's labels in
      `_calculate_panchanga_for_date_uncached` and `_calendar_day_entry`.
- [ ] Match **vratas + festivals off the same Udaya tithi** (internally consistent day).
- [ ] Per-festival **night overrides** table (Shivaratri→nisita, Diwali→amavasya-at-night,
      Holika Dahan→pradosh, Kartik/other night events).
- [ ] Handle **Kshaya** (skipped) and **Adhika** (repeated) tithis via the sunrise rule.

### G2. Live `/astrology` split
- [ ] `tithi` = Udaya tithi of the day.
- [ ] `current_tithi` = { name, number, start, end } running at `now`.
- [ ] `next_tithi` = { name, number, start, end }.

### G3. Upcoming-anga timelines (Issue 3)
- [ ] Return `next_tithi/next_nakshatra/next_yoga/next_karana` with start+end.
- [ ] Add `*_start` for each current anga (render "from → to" bars).
- [ ] Reuse the transition arrays already built in `compute_month_anga_end_times_batch`.

### G4. Shravan consolidation (Issue 2)
- [ ] One canonical **Nepali solar Shrawan** definition used in calendar + notifications + feed
      (currently notifications use LUNAR month — inconsistent).
- [ ] Compute exact **Karka sankranti instant** via `find_discrete` (removes ±1-day boundary error).
- [ ] Add **Shravan Mangalvar (Mangala Gauri)**.
- [ ] Number the Shravan Mondays ("1st Somvar" …).

### G5. Test/fixtures
- [ ] Regenerate golden fixtures (`_verify.py`, `_verify_routes.py`) — these are INTENTIONAL
      output changes, not regressions (breaks the prior byte-identical assumption).

---

## Suggested implementation order
1. **G1 + G2 + G3** (tithi correctness core) — everything depends on it.
2. **A defects** (type tagging, secular filter upstream, dedupe, dead entries, weekday-vrata noise).
3. **B** (Nepali festivals) + **C** (missing Ekadashis) + **D** (Sankrantis).
4. **F** (eclipses) — new module.
5. **G4** (Shravan) + **E** (remaining pan-Hindu) + **G5** (fixtures).
