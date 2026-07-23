"""Static data tables, lookup maps, and configuration constants.

Pure data + the Lahiri ayanamsa helper. No project imports.
"""

__all__ = [
    'AYANAMSA',
    'CHOGHADIYA_DAY_START',
    'CHOGHADIYA_NAMES',
    'CHOGHADIYA_NIGHT_START',
    'CHOGHADIYA_QUALITY',
    'CHOGHADIYA_SIGNIFICANCE',
    'DASHA_GUIDANCE',
    'DASHA_SEQUENCE',
    'DURMUHURTA_INDEX',
    'EVENT_DEITY_MAP',
    'FESTIVAL_CONTENT',
    'HOUSE_NAME_TO_NUM',
    'HOUSE_THEMES',
    'KARANA_DEG',
    'KARANA_REPEATING',
    'KUNDALI_REPORT_URL',
    'KUNDALI_TIMEOUT_SECONDS',
    'MANTRA_API_URL',
    'NAKSHATRA_DEITIES',
    'NAKSHATRA_LORDS',
    'NAKSHATRA_PADA_DESC',
    'NAK_DEG',
    'PLANET_GOVERNS',
    'PLANET_HOUSE_INSIGHT',
    'PLANET_MUKHI',
    'PLANET_NATURE',
    'PLANET_PRIORITY',
    'PLANET_TO_DEITY_NAME',
    'PLANET_TO_POOJA',
    'PLANET_TRANSIT_EFFECT',
    'POOJA_DETAILS',
    'RASHI_NATURE_BRIEF',
    'RASHI_PROFILE',
    'RASHI_TONE',
    'SIGNIFICANT_VRATA_KEYWORDS',
    'SUN_RASHI_TO_LUNAR_MONTH',
    'TITHI_DEG',
    'TITHI_NATURE_NAMES',
    'TITHI_NATURE_SIGNIFICANCE',
    'TRANSIT_POOJA_PRACTICES',
    'VARJYAM_TABLE',
    'WEEKDAY_PLANET',
    'YOGA_AUSPICIOUS',
    'YOGA_DEG',
    '_CHANDRA_GOOD',
    '_DAILY_BODY_AUSPICIOUS',
    '_DAILY_BODY_RIKTA',
    '_DAILY_TITLE_AUSPICIOUS',
    '_DAILY_TITLE_FESTIVAL',
    '_DAILY_TITLE_RIKTA',
    '_DASHA_ORDER',
    '_DASHA_YEARS',
    '_DASHA_YEAR_DAYS',
    '_DURMUHURTA_SIG',
    '_FEST_BODY',
    '_KUNDALI_POOJA_CATALOG',
    '_MOON_SIGN_FLAVOR',
    '_NAVAGRAHA_VARIANT_ID',
    '_NO_DURMUHURTA',
    '_PLANET_ALIASES',
    '_RASHI_SANSKRIT',
    '_RITU_CLOSING',
    '_SIGNIFICANT_TRANSIT_PLANETS',
    '_TARA_GOOD',
    '_TARA_MEANING',
    '_TARA_NAMES',
    '_TITHI_NATURE_AUSPICIOUS',
    '_TITHI_NATURE_GUIDANCE',
    '_lahiri_ayanamsa',
    'festival_mapping',
    'messages',
    'months',
    'nakshatras',
    'rashi_names',
    'ritu_names',
    'tithi_names',
    'vrata_mapping',
    'yoga_names',
]



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

    # ============================================================
    # ADDED — remaining Ekadashis (lunar-month names follow the same
    # purnimanta convention as the entries above; matched identically
    # by get_festivals_for_day). Completes the 24-Ekadashi cycle.
    # ============================================================
    "Kamada Ekadashi": {"tithi": "एकादशी", "month": "Chaitra", "paksha": "Shukla Paksha"},
    "Papmochani Ekadashi": {"tithi": "एकादशी", "month": "Chaitra", "paksha": "Krishna Paksha"},
    "Mohini Ekadashi": {"tithi": "एकादशी", "month": "Vaishakha", "paksha": "Shukla Paksha"},
    "Apara Ekadashi": {"tithi": "एकादशी", "month": "Jyeshtha", "paksha": "Krishna Paksha"},
    "Yogini Ekadashi": {"tithi": "एकादशी", "month": "Ashadha", "paksha": "Krishna Paksha"},
    "Kamika Ekadashi": {"tithi": "एकादशी", "month": "Shravana", "paksha": "Krishna Paksha"},
    "Papankusha Ekadashi": {"tithi": "एकादशी", "month": "Ashwin", "paksha": "Shukla Paksha"},
    "Indira Ekadashi": {"tithi": "एकादशी", "month": "Ashwin", "paksha": "Krishna Paksha"},
    "Rama Ekadashi": {"tithi": "एकादशी", "month": "Kartika", "paksha": "Krishna Paksha"},
    "Utpanna Ekadashi": {"tithi": "एकादशी", "month": "Margashirsha", "paksha": "Krishna Paksha"},
    "Saphala Ekadashi": {"tithi": "एकादशी", "month": "Pausha", "paksha": "Krishna Paksha"},
    "Amalaki Ekadashi": {"tithi": "एकादशी", "month": "Phalguna", "paksha": "Shukla Paksha"},
    "Vijaya Ekadashi": {"tithi": "एकादशी", "month": "Phalguna", "paksha": "Krishna Paksha"},

    # ============================================================
    # ADDED — Nepal festivals (region-tagged; nepalirudraksha.com audience)
    # ============================================================
    "Janai Purnima / Rishi Tarpani": {"tithi": "पूर्णिमा", "month": "Shravana", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Kushe Aunsi (Father's Day)": {"tithi": "अमावस्या", "month": "Bhadrapada", "paksha": "Krishna Paksha", "region": "Nepal"},
    "Mata Tirtha Aunsi (Mother's Day)": {"tithi": "अमावस्या", "month": "Vaishakha", "paksha": "Krishna Paksha", "region": "Nepal"},
    "Bala Chaturdashi": {"tithi": "चतुर्दशी", "month": "Margashirsha", "paksha": "Krishna Paksha", "region": "Nepal"},
    "Chaite Dashain": {"tithi": "अष्टमी", "month": "Chaitra", "paksha": "Shukla Paksha", "region": "Nepal"},
    "Ghode Jatra": {"tithi": "अमावस्या", "month": "Chaitra", "paksha": "Krishna Paksha", "region": "Nepal"},

    # ============================================================
    # ADDED — other pan-Hindu observances
    # ============================================================
    "Akshaya Navami (Amla Navami)": {"tithi": "नवमी", "month": "Kartika", "paksha": "Shukla Paksha"},
    "Skanda Shashti (Kartika)": {"tithi": "षष्ठी", "month": "Kartika", "paksha": "Shukla Paksha"},
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
    "Masik Durga Ashtami (Monthly)": {
        "tithi": "अष्टमी", "paksha": "Shukla Paksha",
        "deity": "Goddess Durga", "significance": "Strength, protection, and Shakti worship"
    },
    "Skanda Shashti (Monthly)": {
        "tithi": "षष्ठी", "paksha": "Shukla Paksha",
        "deity": "Kartikeya (Skanda)", "significance": "Victory over obstacles, courage, and health"
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
    # Shravan-month Tuesday vrat: matched on the NEPALI SOLAR Shrawan month + Tuesday
    # (handled explicitly in get_vratas_for_day via the "solar_month"+"day_of_week" keys).
    "Mangala Gauri Vrat": {
        "solar_month": "Shrawan", "day_of_week": "Tuesday",
        "deity": "Goddess Gauri (Parvati)", "significance": "Marital happiness and family well-being (Shravan Tuesdays)"
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

# Dynamic day-guidance building blocks, keyed by tithi nature. Used to compose
# per-day why_it_matters / who_should_use_it / recommended & avoid practices when
# the day has no curated named event — so the guidance reflects the ACTUAL day
# (tithi nature + paksha + nakshatra + yoga) instead of static paksha-only text.
TITHI_NATURE_WHO = {
    "Nanda":  "Anyone starting something joyful — new ventures, celebrations, or auspicious beginnings.",
    "Bhadra": "Those pursuing study, ceremonies, travel, or steady constructive work.",
    "Jaya":   "Anyone facing competition or challenges, or needing decisive courage.",
    "Rikta":  "Those completing pending work, decluttering, healing, or turning inward.",
    "Poorna": "Anyone completing goals, giving thanks, performing puja, or celebrating.",
}
TITHI_NATURE_RECOMMEND = {
    "Nanda":  ["Begin auspicious new work, celebrations, or social gatherings.",
               "Offer morning prayer and set a clear, positive intention for the day."],
    "Bhadra": ["Take up study, ceremonies, or constructive, stabilising work.",
               "Attend to important tasks that need reliability and follow-through."],
    "Jaya":   ["Act decisively on competitive or long-pending matters.",
               "Resolve disputes and pursue goals that call for courage."],
    "Rikta":  ["Finish pending tasks, clean, declutter, and simplify.",
               "Do meditation, japa, and quiet introspection."],
    "Poorna": ["Complete and dedicate ongoing projects.",
               "Perform puja, give charity, and express gratitude."],
}
TITHI_NATURE_AVOID = {
    "Nanda":  ["Postponing good news or withdrawing from people who need you."],
    "Bhadra": ["Rushing, or making careless and hasty commitments."],
    "Jaya":   ["Timidity, indecision, and avoiding a necessary conversation."],
    "Rikta":  ["Starting important new ventures, signing deals, or ceremonies.",
               "Major purchases and hard-to-reverse decisions."],
    "Poorna": ["Leaving key work unfinished or scattering your focus."],
}
__all__ += ["TITHI_NATURE_WHO", "TITHI_NATURE_RECOMMEND", "TITHI_NATURE_AVOID"]

# Concise "essence" clause per tithi nature, used to compose a day-specific
# why_it_matters sentence (woven together with the actual tithi + paksha +
# nakshatra) rather than a bare category label.
TITHI_NATURE_ESSENCE = {
    "Nanda":  "a joyful (Nanda) tithi that favours auspicious beginnings, celebration, and new ventures",
    "Bhadra": "an auspicious (Bhadra) tithi that supports learning, ceremonies, and steady, constructive work",
    "Jaya":   "a victorious (Jaya) tithi that rewards bold, decisive action and overcoming obstacles",
    "Rikta":  "a hollow (Rikta) tithi — best for completing, clearing, and refining rather than launching",
    "Poorna": "a complete (Poorna) tithi, ideal for fulfilment, gratitude, charity, and finishing what you began",
}
__all__ += ["TITHI_NATURE_ESSENCE"]

# Sankranti (solar ingress) names, indexed to match rashi_names
# (0=Aries … 11=Pisces). A Sankranti falls on the day the Sun enters the rashi.
SANKRANTI_NAMES = [
    "Mesha Sankranti", "Vrishabha Sankranti", "Mithuna Sankranti", "Karka Sankranti",
    "Simha Sankranti", "Kanya Sankranti", "Tula Sankranti", "Vrishchika Sankranti",
    "Dhanu Sankranti", "Makar Sankranti", "Kumbha Sankranti", "Meena Sankranti",
]
__all__ += ["SANKRANTI_NAMES"]

# Per-tithi presiding deity + concrete devotional practice. Used so that a day's
# recommended_practices name the deity and the specific act (e.g. Panchami →
# Saraswati mantra + creative pursuits; Ekadashi → Vishnu mantra + fast).
# Keyed by the Devanagari tithi name (both Pratipada spellings included).
TITHI_PRACTICE = {
    "प्रथमा":   ["Light a lamp to Agni/Brahma and set fresh, positive intentions.",
                "Begin a new routine, study, or creative undertaking."],
    "प्रतिपदा": ["Light a lamp to Agni/Brahma and set fresh, positive intentions.",
                "Begin a new routine, study, or creative undertaking."],
    "द्वितीया":  ["Invoke Brahma/Vidhata for steady growth and good planning.",
                "Nurture new relationships, partnerships, and plans."],
    "तृतीया":   ["Worship Gauri (Parvati) for harmony and marital well-being.",
                "Favour beauty, art, and auspicious purchases."],
    "चतुर्थी":  ["Chant the Ganesha mantra (Om Gan Ganapataye Namah) to clear obstacles.",
                "Offer durva grass and modak before starting new work."],
    "पञ्चमी":   ["Chant the Saraswati mantra; favour study, music, and the arts.",
                "Support clarity of thought and creative, artistic pursuits.",
                "Offer worship to the Nagas where that tradition is observed."],
    "षष्ठी":    ["Worship Kartikeya (Skanda) for courage, discipline, and health.",
                "Good for acts of valour and the well-being of children."],
    "सप्तमी":   ["Offer arghya (water) to Surya at sunrise and chant Surya mantras.",
                "Favour vitality, confidence, and health."],
    "अष्टमी":   ["Worship Durga (or Shiva) for strength and protection.",
                "Observe a light fast and recite a Devi or Shiva stotram."],
    "नवमी":     ["Worship Goddess Durga (Ambika) for protection and victory.",
                "Recite Durga Saptashati, Devi Kavach, or the Durga Chalisa."],
    "दशमी":     ["Honour Dharma/Yama; act with righteousness and integrity.",
                "Favourable for consolidating and completing important work."],
    "एकादशी":   ["Chant Vishnu mantras (Om Namo Narayanaya).",
                "Observe a grain-free/sattvic Ekadashi fast as health permits.",
                "Read the Gita and offer tulsi to Lord Vishnu."],
    "द्वादशी":   ["Continue Vishnu worship; break the Ekadashi fast at parana time.",
                "Offer tulsi and chant the Vishnu Sahasranama."],
    "त्रयोदशी":  ["Worship Shiva at Pradosh (twilight) with bilva leaves and a deepam.",
                "Chant Om Namah Shivaya for health, peace, and prosperity."],
    "चतुर्दशी":  ["Worship Shiva/Kali; chant Om Namah Shivaya.",
                "Favour cleansing, protection, and removal of negativity."],
    "पूर्णिमा":  ["Perform Satyanarayan puja; worship Vishnu and the Moon (Chandra).",
                "Offer white flowers or milk to the Moon and give charity."],
    "अमावस्या": ["Perform Pitru Tarpan and prayers for the ancestors.",
                "Donate food and light a lamp in memory of departed family."],
}
__all__ += ["TITHI_PRACTICE"]

# Per-tithi significance sentence (keyed by Devanagari name). Gives each of the 16
# tithis its OWN why_it_matters base — so days don't share one of only 5 nature
# clauses. Woven with the day's nakshatra + yoga for daily variation.
TITHI_SIGNIFICANCE = {
    "प्रथमा":   "Pratipada, the first tithi (ruled by Agni/Brahma), is for kindling new beginnings and fresh resolves.",
    "प्रतिपदा": "Pratipada, the first tithi (ruled by Agni/Brahma), is for kindling new beginnings and fresh resolves.",
    "द्वितीया":  "Dwitiya, presided by Brahma, favours nurturing new plans, partnerships, and steady growth.",
    "तृतीया":   "Tritiya, sacred to Gauri (Parvati), supports harmony, beauty, marital well-being, and auspicious purchases.",
    "चतुर्थी":  "Chaturthi belongs to Lord Ganesha — ideal for removing obstacles before any new undertaking.",
    "पञ्चमी":   "Panchami, associated with Saraswati and the Nagas, favours learning, music, the arts, and clarity of thought.",
    "षष्ठी":    "Shashti, sacred to Kartikeya (Skanda), lends courage, discipline, health, and protection for children.",
    "सप्तमी":   "Saptami is the Sun's tithi — a day for vitality, confidence, health, and honouring Surya.",
    "अष्टमी":   "Ashtami carries the fierce Shakti of Durga and Shiva — for strength, protection, and inner resolve.",
    "नवमी":     "Navami, sacred to Goddess Durga (Ambika), is for protection, valour, and victory over obstacles.",
    "दशमी":     "Dashami, linked with Dharma and Yama, favours righteous action, consolidation, and completion.",
    "एकादशी":   "Ekadashi is Vishnu's most sacred tithi — fasting, japa, and devotion for purity and liberation.",
    "द्वादशी":   "Dwadashi continues Vishnu's grace — for the fast-breaking (parana), charity, and gratitude.",
    "त्रयोदशी":  "Trayodashi, sacred to Shiva at Pradosh twilight, is for purification, health, and removing obstacles.",
    "चतुर्दशी":  "Chaturdashi belongs to Shiva and Kali — a time for cleansing, protection, and dissolving negativity.",
    "पूर्णिमा":  "Purnima, the full moon, peaks lunar energy — ideal for Satyanarayan puja, gratitude, charity, and abundance.",
    "अमावस्या": "Amavasya, the new moon, is the most potent day for ancestor offerings (Pitru Tarpan) and inner reset.",
}
__all__ += ["TITHI_SIGNIFICANCE"]

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

# --- Anga widths
TITHI_DEG = 12.0
NAK_DEG = 360.0 / 27.0
YOGA_DEG = 360.0 / 27.0
KARANA_DEG = 6.0

# ============================================================
# 6) KARANA NAME MAP
# ============================================================
KARANA_REPEATING = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]


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

# When several poojas share a tithi (e.g. Trayodashi triggers both the wealth
# poojas AND Rudra Abhishek), the SUGGESTED pooja should match the day's headline
# event rather than list order. Maps a lowercase keyword found in the event name
# to the pooja id that fits it. Checked in order; first keyword match wins.
# Extend this list to steer more events to their proper pooja.
EVENT_PREFERRED_POOJA_ID = [
    ("pradosh", "7465532653810"),   # Pradosh Vrat (Shiva) -> Rudra Abishek Pooja
]
__all__ += ["EVENT_PREFERRED_POOJA_ID"]


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


# ============================================================
# DURMUHURTA
# ============================================================
_DURMUHURTA_SIG = ("Avoid starting new ventures, ceremonies, travel, or signing agreements. "
                   "Routine work and spiritual practice are acceptable during this period.")
_NO_DURMUHURTA  = "No Durmuhurta today — Thursday (Guruvar) is auspicious and free of this inauspicious period."

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


# Tithis significant enough to surface in Upcoming Spiritual Events even without a
# named festival on that day. Matched as case-insensitive substrings against vrata names
# (e.g. "Kalashtami (Monthly)" -> ashtami, "Sankashti Chaturthi (Monthly)" -> chaturthi,
# "Purnima Vrat (Monthly)" -> purnima, "Amavasya Vrat (Monthly)" -> amavasya).
SIGNIFICANT_VRATA_KEYWORDS = ("ekadashi", "pradosh", "ashtami", "chaturthi", "purnima", "amavasya")


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
    "Lohri": {"description": "Lohri is a Punjabi winter harvest festival celebrated around a bonfire with songs, dance, and offerings of til, gud, and popcorn to the fire.", "why_it_matters": "A bonfire festival marking the end of peak winter and the coming harvest.", "recommended_mukhi": None},
    "Pongal": {"description": "Pongal is the four-day Tamil harvest festival thanking the Sun god for a bountiful crop, celebrated by boiling the season's first rice.", "why_it_matters": "A Tamil thanksgiving to Surya for the harvest's abundance.", "recommended_mukhi": "12"},
    "Magh Bihu": {"description": "Magh Bihu (Bhogali Bihu) is Assam's harvest festival of feasting and community bonfires (Meji), marking the end of the harvesting season.", "why_it_matters": "Assam's harvest feast — gratitude, fire, and community.", "recommended_mukhi": None},

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

# Specific significance for each named Ekadashi that lacked curated copy, so
# why_it_matters/description are unique per event instead of the generic
# "Ekadashi supports discipline…" line. (Vishnu-linked → 5 Mukhi rudraksha.)
FESTIVAL_CONTENT.update({
    "Jaya Ekadashi": {"description": "Jaya Ekadashi (Magha Shukla) is believed to free beings from a ghostly (pishacha) existence and to grant liberation.", "why_it_matters": "Jaya Ekadashi frees one from lower births and negative karma, granting victory and Vishnu's grace.", "recommended_mukhi": "5"},
    "Shattila Ekadashi": {"description": "Shattila Ekadashi (Magha Krishna) is observed with six uses of sesame (til) — in bath, food, offering, and charity — to burn away sins and poverty.", "why_it_matters": "Shattila Ekadashi's sesame charity destroys sins and removes want and poverty.", "recommended_mukhi": "5"},
    "Varuthini Ekadashi": {"description": "Varuthini Ekadashi (Vaishakha Krishna) grants divine protection (varutha = armour) and turns misfortune into fortune.", "why_it_matters": "Varuthini Ekadashi shields the devotee like armour and brings good fortune and merit.", "recommended_mukhi": "5"},
    "Parsva Ekadashi": {"description": "Parivartini (Parsva) Ekadashi (Bhadrapada Shukla) marks Lord Vishnu turning to His other side during His Chaturmas sleep.", "why_it_matters": "On Parivartini Ekadashi the sleeping Vishnu turns over — a potent mid-Chaturmas day for devotion.", "recommended_mukhi": "5"},
    "Aja Ekadashi": {"description": "Aja Ekadashi (Bhadrapada Krishna) restored the fortune and family of King Harishchandra; its observance washes away grave sins.", "why_it_matters": "Aja Ekadashi removes the heaviest sins and restores lost fortune and dignity.", "recommended_mukhi": "5"},
    "Paush Putrada Ekadashi": {"description": "Pausha Putrada Ekadashi (Pausha Shukla) is observed by couples praying for virtuous children (putra).", "why_it_matters": "Pausha Putrada Ekadashi is kept for the blessing of children and family well-being.", "recommended_mukhi": "5"},
    "Kamada Ekadashi": {"description": "Kamada Ekadashi (Chaitra Shukla), the first Ekadashi of the lunar year, fulfils sincere desires (kama) and frees from curses.", "why_it_matters": "Kamada Ekadashi fulfils heartfelt wishes and releases one from curses and sins.", "recommended_mukhi": "5"},
    "Papmochani Ekadashi": {"description": "Papmochani Ekadashi (Chaitra Krishna) is the 'remover of sins' — its observance dissolves even grave wrongdoing.", "why_it_matters": "Papmochani Ekadashi erases accumulated sins and purifies the mind.", "recommended_mukhi": "5"},
    "Mohini Ekadashi": {"description": "Mohini Ekadashi (Vaishakha Shukla) frees the devotee from the web of worldly delusion (moha) and from sins.", "why_it_matters": "Mohini Ekadashi cuts through delusion and attachment, granting clarity and merit.", "recommended_mukhi": "5"},
    "Apara Ekadashi": {"description": "Apara (Achala) Ekadashi (Jyeshtha Krishna) grants limitless (apara) merit and wealth and removes sins.", "why_it_matters": "Apara Ekadashi bestows boundless merit, reputation, and removal of sins.", "recommended_mukhi": "5"},
    "Yogini Ekadashi": {"description": "Yogini Ekadashi (Ashadha Krishna) is said to equal feeding thousands of brahmins in merit and to cure ailments and free from sins.", "why_it_matters": "Yogini Ekadashi grants great healing merit and release from sins.", "recommended_mukhi": "5"},
    "Kamika Ekadashi": {"description": "Kamika Ekadashi (Shravana Krishna) grants the merit of pilgrimages and washes away sins through Vishnu worship with tulsi.", "why_it_matters": "Kamika Ekadashi confers pilgrimage-level merit and cleanses sins.", "recommended_mukhi": "5"},
    "Papankusha Ekadashi": {"description": "Papankusha Ekadashi (Ashwin Shukla) is a goad (ankusha) against sins (papa) and grants heavenly merit and liberation.", "why_it_matters": "Papankusha Ekadashi restrains sin and grants punya and liberation.", "recommended_mukhi": "5"},
    "Indira Ekadashi": {"description": "Indira Ekadashi (Ashwin Krishna, in Pitru Paksha) is observed to liberate departed ancestors from lower realms.", "why_it_matters": "Indira Ekadashi helps free ancestors from suffering and raises them to higher realms.", "recommended_mukhi": "5"},
    "Rama Ekadashi": {"description": "Rama Ekadashi (Kartika Krishna), just before Diwali, destroys great sins and leads the devotee toward Vaikuntha.", "why_it_matters": "Rama Ekadashi burns away grave sins and draws one to Vishnu's abode.", "recommended_mukhi": "5"},
    "Utpanna Ekadashi": {"description": "Utpanna Ekadashi (Margashirsha Krishna) marks the appearance (utpanna) of Ekadashi Devi, who slew the demon Mura; it begins the Ekadashi vow.", "why_it_matters": "Utpanna Ekadashi celebrates the origin of Ekadashi and is ideal to begin the vrat.", "recommended_mukhi": "5"},
    "Saphala Ekadashi": {"description": "Saphala Ekadashi (Pausha Krishna) makes one's efforts fruitful (saphala) and turns failures into success.", "why_it_matters": "Saphala Ekadashi makes endeavours bear fruit and removes obstacles to success.", "recommended_mukhi": "5"},
    "Amalaki Ekadashi": {"description": "Amalaki Ekadashi (Phalguna Shukla) worships Lord Vishnu with the sacred amla tree for health, longevity, and liberation.", "why_it_matters": "Amalaki Ekadashi, worshipping Vishnu at the amla tree, grants health, longevity, and moksha.", "recommended_mukhi": "5"},
    "Vijaya Ekadashi": {"description": "Vijaya Ekadashi (Phalguna Krishna) grants victory (vijaya) over enemies and obstacles — Lord Rama observed it before crossing to Lanka.", "why_it_matters": "Vijaya Ekadashi grants victory over adversaries and hard obstacles.", "recommended_mukhi": "5"},
})


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


# ============================================================
# CALENDAR ENDPOINT DATA (/panchanga-calendar)
# ============================================================
# English/transliterated tithi names (parallel to the Devanagari `tithi_names`).
# Index 0..29: Shukla Pratipada..Purnima (0..14), Krishna Pratipada..Amavasya (15..29).
tithi_names_en = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Purnima",
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Amavasya",
]

# ------------------------------------------------------------------
# Tithi display formatting.
# The API historically emitted the tithi as raw Devanagari (e.g. "पञ्चमी")
# while every other anga was English — an inconsistency. Emitted tithi values
# now use a combined "English (Devanagari)" form (e.g. "Panchami (पञ्चमी)").
# The raw Devanagari string is still used internally as a lookup key for
# festival/vrata/practice selection, so these helpers convert ONLY at the
# emission boundary; `tithi_to_dev` strips the combined form back to raw
# Devanagari for any keyed lookup.
# ------------------------------------------------------------------
# Devanagari -> English (parallel lists, same index). `tithi_names` uses प्रथमा
# for the first tithi; प्रतिपदा is an accepted variant (see normalize_tithi_names),
# so it maps to the same English name.
TITHI_DEV_TO_EN = dict(zip(tithi_names, tithi_names_en))
TITHI_DEV_TO_EN.setdefault("प्रतिपदा", "Pratipada")


def tithi_to_dev(value):
    """Return the raw Devanagari tithi from a raw OR combined value.

    "पञ्चमी" -> "पञ्चमी"; "Panchami (पञ्चमी)" -> "पञ्चमी". Used to key the
    Devanagari-indexed lookups (TITHI_PRACTICE/TITHI_SIGNIFICANCE) regardless of
    whether the caller passes the raw or the display form. Unknown values are
    returned unchanged.
    """
    if not value:
        return value
    if value in TITHI_DEV_TO_EN:
        return value
    l = value.rfind("(")
    r = value.rfind(")")
    if l != -1 and r > l:
        inner = value[l + 1:r].strip()
        if inner:
            return inner
    return value


def format_tithi_display(value):
    """Return the combined "English (Devanagari)" tithi form (idempotent).

    Accepts a raw Devanagari name or an already-combined string. Values that are
    not recognised tithi names are returned unchanged, so non-tithi placeholders
    (e.g. "None", "Spiritual Day") are never corrupted.
    """
    if not value:
        return value
    dev = tithi_to_dev(value)
    en = TITHI_DEV_TO_EN.get(dev)
    return f"{en} ({dev})" if en else value


def tithi_to_en(value):
    """Return just the English tithi name from a raw, combined, or English value.

    "त्रयोदशी" / "Trayodashi (त्रयोदशी)" -> "Trayodashi". Unknown values are
    returned unchanged. Used e.g. to build an event_context like
    "Trayodashi (Pradosh Vrat)".
    """
    if not value:
        return value
    return TITHI_DEV_TO_EN.get(tithi_to_dev(value), value)


__all__ += ["TITHI_DEV_TO_EN", "tithi_to_dev", "format_tithi_display", "tithi_to_en"]

# Devotional theme/subtitle for each lunar (amanta) month — used as the calendar
# header subtitle (e.g. Shravana -> "Sacred Month of Lord Shiva").
LUNAR_MONTH_THEME = {
    "Shravana":     "Sacred Month of Lord Shiva",
    "Kartika":      "Sacred Month of Lord Vishnu & Damodar",
    "Magha":        "Holy Month of Sacred Bathing & Charity",
    "Vaishakha":    "Month of Charity & Akshaya Merit",
    "Chaitra":      "Month of New Beginnings & Chaitra Navratri",
    "Ashwin":       "Month of Navratri & Dussehra",
    "Bhadrapada":   "Month of Ganesh Chaturthi & Krishna Janmashtami",
    "Margashirsha": "Month of Gita Jayanti & Vivah Panchami",
    "Phalguna":     "Month of Maha Shivaratri & Holi",
    "Jyeshtha":     "Month of Ganga Dussehra & Nirjala Ekadashi",
    "Ashadha":      "Month of Guru Purnima & Rath Yatra",
    "Pausha":       "Month of Devotion & Vaikuntha Ekadashi",
}

# Display spelling for the calendar title (the amanta `months` naming -> common form).
LUNAR_MONTH_DISPLAY = {
    "Shravana": "Shravan",
    "Ashwin":   "Ashwin",
}

# Curated bullet-point content for the "auspicious days" highlight panel, keyed by
# the marker/highlight type produced for each day.
CALENDAR_HIGHLIGHT_CONTENT = {
    "shravan_somvar": {
        "title": "Shravan Somvar",
        "points": [
            "Most auspicious day to wear Rudraksha",
            "Start new spiritual practices",
            "Mantra chanting & meditation",
        ],
    },
    "nag_panchami": {
        "title": "Nag Panchami",
        "points": [
            "Worship of Nag Devta",
            "Protection & blessings",
            "Special prayers for well-being",
        ],
    },
    "pradosh": {
        "title": "Pradosh Vrat",
        "points": [
            "Evening worship of Lord Shiva",
            "Fasting till Pradosh time",
            "Chant \"Om Namah Shivaya\"",
        ],
    },
    "purnima": {
        "title": "Purnima",
        "points": [
            "Full Moon day — highly auspicious",
            "Wear Rudraksha",
            "Guru worship & gratitude",
        ],
    },
    "amavasya": {
        "title": "Amavasya",
        "points": [
            "Ancestor remembrance (Tarpan)",
            "Charity & introspection",
            "Pitru blessings",
        ],
    },
    "ekadashi": {
        "title": "Ekadashi",
        "points": [
            "Fasting for Lord Vishnu",
            "Spiritual purification",
            "Japa & scripture reading",
        ],
    },
    "shivaratri": {
        "title": "Shivaratri",
        "points": [
            "Night-long worship of Lord Shiva",
            "Most powerful night to wear Rudraksha",
            "Rudrabhishek & Om Namah Shivaya",
        ],
    },
    "festival": {
        "title": "Festival",
        "points": [
            "Auspicious festival day",
            "Worship & gratitude",
            "Favourable to wear Rudraksha",
        ],
    },
}

__all__ += [
    "tithi_names_en", "LUNAR_MONTH_THEME", "LUNAR_MONTH_DISPLAY",
    "CALENDAR_HIGHLIGHT_CONTENT",
]


# Secular/national fixed-date festivals excluded from the spiritual "auspicious
# days" highlight panel of /panchanga-calendar (they still appear on the grid).
# Cultural/harvest festivals kept in festival_mapping but excluded from the
# "spiritual headline" selection (they still appear in festival_today).
# Civic/national and non-Vedic days (Republic Day, Independence Day, Gandhi
# Jayanti, International Yoga Day, Christmas) were removed from festival_mapping
# entirely, so they no longer need to be listed here.
CALENDAR_SECULAR_FESTIVALS = {
    "Lohri", "Magh Bihu",
}
__all__ += ["CALENDAR_SECULAR_FESTIVALS"]

# Night-based festivals: observed when the required tithi prevails at NIGHT
# (nisita/midnight or pradosh), not at sunrise. These are matched at nisita while
# every other festival follows the Udaya (sunrise) tithi. Keep this list tight —
# only genuinely night-anchored observances belong here.
NIGHT_TITHI_FESTIVALS = {
    "Maha Shivaratri",
    "Holika Dahan",
    "Naraka Chaturdashi",
    "Diwali (Lakshmi Puja)",
    "Tihar (Lakshmi Puja)",
    "Bala Chaturdashi",
}
__all__ += ["NIGHT_TITHI_FESTIVALS"]


# ============================================================
# NEPALI SOLAR (Bikram Sambat) MONTHS — for /panchanga-calendar
# ============================================================
# The Nepali civil month is solar: it is the rashi the SUN currently occupies
# (sidereal). The month begins at sankranti (the Sun's ingress into the rashi).
# "Shravan" (Saun) = Sun in Cancer/Karka — this is what Nepali patros and the
# Shravan Somvar vrat follow, NOT the lunar Shravana.
SUN_RASHI_TO_NEPALI_SOLAR_MONTH = {
    "Aries": "Baishakh", "Taurus": "Jestha", "Gemini": "Ashar", "Cancer": "Shrawan",
    "Leo": "Bhadra", "Virgo": "Ashwin", "Libra": "Kartik", "Scorpio": "Mangsir",
    "Sagittarius": "Poush", "Capricorn": "Magh", "Aquarius": "Falgun", "Pisces": "Chaitra",
}

NEPALI_MONTH_DISPLAY = {
    "Shrawan": "Shravan",
    "Ashar": "Ashadh",
}

NEPALI_MONTH_THEME = {
    "Baishakh":  "Nepali New Year Month",
    "Jestha":    "Month of Summer & Vat Savitri",
    "Ashar":     "Month of Ropai & Guru Purnima",
    "Shrawan":   "Sacred Month of Lord Shiva",
    "Bhadra":    "Month of Teej & Krishna Janmashtami",
    "Ashwin":    "Month of Dashain (Navaratri)",
    "Kartik":    "Month of Tihar (Deepawali)",
    "Mangsir":   "Month of Vivah & Harvest",
    "Poush":     "Month of Devotion & Winter",
    "Magh":      "Month of Maghe Sankranti & Sacred Bathing",
    "Falgun":    "Month of Maha Shivaratri & Holi",
    "Chaitra":   "Month of Chaitra Dashain & Ram Navami",
}

__all__ += [
    "SUN_RASHI_TO_NEPALI_SOLAR_MONTH", "NEPALI_MONTH_DISPLAY", "NEPALI_MONTH_THEME",
]


# ============================================================
# DYNAMIC NOTIFICATION COPY — /notifications auspicious days & eclipses
# ============================================================
# Rotated deterministically via _stable_pick(seed) so each day reads differently
# (seed = date + tara + nakshatra) and weaves in the day's real data — catchy and
# click-worthy, not boilerplate. Placeholders: {date} {tara} {tara_meaning}
# {nak} {house} {sign} {type}.
AUSPICIOUS_TITLES = [
    "🌟 A golden window opens on {date}",
    "✨ {date} is working in your favour",
    "🪔 The stars align for you on {date}",
    "🙏 {tara} Tara blesses you on {date}",
    "🌸 Make {date} count — it's your day",
    "⭐ {date}: a rare lucky day for you",
    "🔆 Strong supportive energy on {date}",
    "🌼 {date} favours bold, positive moves",
]
AUSPICIOUS_BODIES = [
    "With the Moon in {nak} and {tara} Tara bringing {tara_meaning}, {date} is a great day to wear your Rudraksha and begin something meaningful. Tap to see why →",
    "{tara} Tara favours {tara_meaning} today — ideal for new starts, travel, or puja, with your {house} house lit up. Don't let this window pass; tap for guidance →",
    "The stars back you on {date}: {tara_meaning} is supported. Set an intention, wear your Rudraksha, and act. Tap to plan your day →",
    "A rare supportive day — the Moon in {nak} lifts your {house} house. Perfect for decisions and devotion. Tap to make the most of it →",
    "{date} carries {tara} Tara's blessing of {tara_meaning}. Begin that pending task or puja now — tap for the details →",
    "Momentum is with you: {nak} nakshatra and {tara} Tara favour fresh starts and worship today. Tap to seize {date} →",
]
AUSPICIOUS_DESC_CLOSE = [
    "A favourable day for important decisions, new beginnings, travel, or spiritual practice.",
    "A supportive day to start ventures, travel, or deepen your sadhana.",
    "An auspicious window for new beginnings, key decisions, and worship.",
    "Energies favour you today — good for fresh starts, journeys, and devotion.",
    "A strong day to act on plans, begin a puja, or wear your Rudraksha.",
]
ROUTINE_TITLES = [
    "📿 {date}: a calm, steady day",
    "🍃 Keep {date} simple",
    "🧘 {date} favours routine over big moves",
    "🌙 A quiet day on {date}",
    "🪷 {date}: steady effort beats big starts",
]
ROUTINE_BODIES = [
    "The Moon in {nak} keeps {date} low-key — better for routine than big launches. Tap to find your next auspicious day →",
    "Nothing is pushing you forward today; steady work and gentle sadhana suit {date}. Tap to see your upcoming lucky days →",
    "{date} is a quiet day — hold major starts for a stronger window. Tap to plan ahead →",
    "A day for consistency, not bold moves. Keep your routine and tap to see when your luck turns →",
]
ROUTINE_DESC_CLOSE = [
    "A routine day — not specially marked for new beginnings.",
    "An ordinary day; better suited to steady work than big starts.",
    "A quiet day — hold major new beginnings for a stronger window.",
    "A low-key day; focus on routine and gentle practice.",
]
ECLIPSE_TITLES = [
    "🌑 A {type} eclipse touches your {house} house",
    "🌘 {type} eclipse in {sign} — your {house} house in focus",
    "🌒 Eclipse alert: your {house} house comes into focus",
    "🌑 {type} eclipse in {sign} affects your {house} house",
]
ECLIPSE_CTAS = [
    "Tap for what to do →",
    "Tap to prepare →",
    "See how to navigate it →",
    "Tap for remedies and timing →",
]

__all__ += [
    "AUSPICIOUS_TITLES", "AUSPICIOUS_BODIES", "AUSPICIOUS_DESC_CLOSE",
    "ROUTINE_TITLES", "ROUTINE_BODIES", "ROUTINE_DESC_CLOSE",
    "ECLIPSE_TITLES", "ECLIPSE_CTAS",
]


# ============================================================
# POOJA "WHY IT'S RECOMMENDED" COPY (dynamic, human text)
# ============================================================
# A short, deity-neutral benefit clause per pooja (reads after "...helps {benefit}").
POOJA_BENEFIT = {
    "Maha Shivaratri Pooja at Pashupatinath": "to seek liberation, inner transformation, and release from past karma",
    "Masik Shivaratri Pooja at Pashupatinath": "for health, peace, and the steady removal of obstacles",
    "Karya Siddhi Ganesh Pooja": "to clear obstacles and smooth the path before any important new beginning",
    "Lakshmi Kuber Pooja": "to attract wealth and financial stability and clear blockages to prosperity",
    "Rudra Abishek Pooja": "to pacify planetary afflictions and restore peace, health, and protection",
    "Laxmi Narayan Pooja": "to invite prosperity, harmony at home, and divine grace",
    "Shri Durga Saptshati Chandi Path": "to invoke protection, strength, and victory over difficulties",
    "Kaal Bhairav and Shakti Maha Puja": "to seek protection from fear, hidden enemies, and negative energy",
    "Navagraha Shanti Pooja with Hawan": "to balance and pacify all nine planets for overall well-being",
}

# Rotated per (pooja + occasion) so the explanation reads differently across poojas
# and days. Placeholders: {occasion} {pooja} {deity} {benefit}.
POOJA_WHY_CALENDAR = [
    "{occasion} is an especially auspicious time to honour {deity}. The {pooja} is performed {benefit}.",
    "Because today is {occasion}, it's a powerful window for this worship — the {pooja} is offered {benefit}.",
    "{occasion} carries special devotional energy, which is why the {pooja} is suggested today, {benefit}.",
    "On {occasion}, {deity} is worshipped with extra devotion, so the {pooja} is a fitting choice — performed {benefit}.",
    "Today being {occasion} makes it ideal for the {pooja}, dedicated to {deity} {benefit}.",
    "{occasion} is when this worship bears the most fruit. Devotees perform the {pooja} {benefit}.",
]

# Personalised (birth-chart) version. Placeholders: {causes} {pooja} {deity} {benefit}.
POOJA_WHY_KUNDALI = [
    "This one comes from your birth chart. {causes} Performing the {pooja} helps {benefit}.",
    "Recommended for you personally — {causes} The {pooja} invokes {deity} {benefit}.",
    "Your kundali points to this: {causes} That's why the {pooja} is suggested, {benefit}.",
    "Based on your chart, {causes} The {pooja} is a meaningful choice {benefit}.",
    "This is tailored to you — {causes} The {pooja} is offered {benefit}.",
]

__all__ += ["POOJA_BENEFIT", "POOJA_WHY_CALENDAR", "POOJA_WHY_KUNDALI"]
