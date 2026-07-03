# Pooja Guide — Which Pooja is Suggested, and When

This explains every pooja the app can suggest and the days or situations that trigger it,
in plain language.

There are **two ways** a pooja gets suggested:

- **By the calendar** — based on the day itself (the tithi, the fortnight, the month, the
  weekday, or a festival). This is the same for everyone on a given day.
- **By the person's birth chart** — based on the user's birthday, their doshas, and the planetary
  period (dasha) they are currently running. This is personal to each user.

---

## The 9 Poojas

| Pooja | Main deity |
|---|---|
| Maha Shivaratri Pooja at Pashupatinath | Lord Shiva |
| Masik Shivaratri Pooja at Pashupatinath | Lord Shiva |
| Karya Siddhi Ganesh Pooja | Lord Ganesha |
| Lakshmi Kuber Pooja | Goddess Lakshmi & Lord Kubera |
| Rudra Abishek Pooja | Lord Shiva |
| Laxmi Narayan Pooja | Lord Vishnu & Goddess Lakshmi |
| Shri Durga Saptshati Chandi Path | Goddess Durga |
| Kaal Bhairav and Shakti Maha Puja | Lord Kaal Bhairav & Shakti |
| Navagraha Shanti Pooja with Hawan | The Nine Planets (Navagraha) |

Every pooja also comes with its deity, a short description, and the step-by-step ritual.

---

## Part 1 — Poojas suggested by the calendar

On any given day, the app looks at the day and suggests these poojas. A single day can
suggest more than one.

**Maha Shivaratri Pooja**
- Suggested on **Maha Shivaratri** — the Krishna Chaturdashi (14th day of the dark fortnight)
  in the month of Phalguna.

**Masik Shivaratri Pooja**
- Suggested on the **monthly Shivaratri** — the Krishna Chaturdashi of every *other* month
  (every month except the Maha Shivaratri one).

**Karya Siddhi Ganesh Pooja**
- Suggested on **Chaturthi** (4th day) of the bright fortnight.
- Also suggested on any **Chaturthi that falls on a Tuesday** (called Mangal Chaturthi).

**Lakshmi Kuber Pooja** (for wealth & prosperity)
- Suggested on **Purnima** (full moon), **Amavasya** (new moon),
  **Trayodashi** (13th day) and **Panchami** (5th day) of either fortnight.
- Also suggested on the wealth festivals: **Dhanteras, Diwali (Lakshmi Puja),
  Tihar (Lakshmi Puja), and Akshaya Tritiya.**

**Rudra Abishek Pooja**
- Suggested on **Krishna Pradosh** — the Trayodashi (13th day) of the dark fortnight.

**Laxmi Narayan Pooja**
- Suggested on **Ekadashi (11th day), Trayodashi (13th day), and Purnima (full moon)** of the
  bright fortnight.

**Shri Durga Saptshati Chandi Path**
- Suggested during **Navaratri** — the first nine days of the bright fortnight in Chaitra and
  Ashwin months.
- Also suggested on any **Navami** (9th day) in either fortnight.

**Kaal Bhairav and Shakti Maha Puja**
- Suggested on **Kalashtami** — the Ashtami (8th day) of the dark fortnight.

> Some days suggest two poojas together. For example, a **bright-fortnight Trayodashi (13th day)**
> suggests both **Lakshmi Kuber** and **Laxmi Narayan**, and a **full moon (Purnima)** also
> suggests both.

---

## Part 2 — Poojas suggested by the person's birth chart

These are personal. They come from three things, in order of importance:

**1. The user's birthday (highest priority)**
- On the user's birthday, the app suggests the **Navagraha Shanti Pooja with Hawan** — to
  balance all nine planets and bless the year ahead.

**2. Doshas found in the birth chart**
- **Manglik (Mangal) dosha** → **Kaal Bhairav and Shakti Maha Puja**
- **Shani Sade Sati / Shani dosha** → **Rudra Abishek Pooja**
- **Kaal Sarp dosha** → **Navagraha Shanti Pooja with Hawan**

**3. The current planetary period (dasha)**
- The planet ruling the user's current main period (Mahadasha) and sub-period (Antardasha)
  suggests a pooja to strengthen and calm that planet:

| Ruling planet | Suggested pooja |
|---|---|
| Sun | Laxmi Narayan Pooja |
| Moon | Rudra Abishek Pooja |
| Mars | Kaal Bhairav and Shakti Maha Puja |
| Mercury | Laxmi Narayan Pooja |
| Jupiter | Laxmi Narayan Pooja |
| Venus | Lakshmi Kuber Pooja |
| Saturn | Rudra Abishek Pooja |
| Rahu | Kaal Bhairav and Shakti Maha Puja |
| Ketu | Karya Siddhi Ganesh Pooja |

If the same pooja is suggested for more than one reason, it is shown once with all its reasons
combined.

---

## Where these show up in the app

- **Today's suggested pooja** and the **daily panchanga** → from the calendar (Part 1).
- **Upcoming poojas (next few days)** → from the calendar (Part 1).
- **Personalised pooja recommendations** → from the birth chart (Part 2).
- **The calendar view** (`/panchanga-calendar`) shows the calendar poojas on each day.

---

## For the developer (IDs & code)

The exact Shopify IDs and the functions behind each rule:

| Pooja | product_id | variant_id |
|---|---|---|
| Maha Shivaratri Pooja at Pashupatinath | `7468622348530` | `42124272730354` |
| Masik Shivaratri Pooja at Pashupatinath | `9035889672434` | `49098993008882` |
| Karya Siddhi Ganesh Pooja | `7465529606386` | `42114181464306` |
| Lakshmi Kuber Pooja | `8820054950130` | `47901573153010` |
| Rudra Abishek Pooja | `7465532653810` | `42114187985138` |
| Laxmi Narayan Pooja | `7465524363506` | `42114162000114` |
| Shri Durga Saptshati Chandi Path | `8817900945650` | `47892681785586` |
| Kaal Bhairav and Shakti Maha Puja | `8955542700274` | `48729126895858` |
| Navagraha Shanti Pooja with Hawan | `7465527705842` | `42114175566066` ⚠️ placeholder |

- ⚠️ The **Navagraha variant id is a placeholder** — confirm the real Shopify variant before
  going live.
- Calendar rules: `get_poojas_for_day()` in `helpers.py`.
- Birth-chart rules: `get_kundali_pooja_recommendations()` (with `_detect_doshas()` and the
  `PLANET_TO_POOJA` map) in `helpers.py`.
- Catalog & details: `POOJA_DETAILS`, `_KUNDALI_POOJA_CATALOG`, `PLANET_TO_POOJA` in `constants.py`.
- Each pooja in a response carries: `name`, `id` (product id), `variant_id`, `reason`, `deity`,
  `about`, and `ritual_sequence`.
