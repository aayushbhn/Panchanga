from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import pytz
from functools import lru_cache
from bisect import bisect_right
import hashlib
import json
from urllib import request as urlrequest
import numpy as np

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
        "about": details.get("about", ""),
        "ritual_sequence": details.get("ritual_sequence", []),
    }


POOJA_DETAILS = {
    "7468622348530": {  # Maha Shivaratri Pooja at Pashupatinath
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

def calculate_durmuhurta(sunrise, sunset, weekday):
    muhurta = (sunset - sunrise).total_seconds() / 15
    indices = DURMUHURTA_INDEX[weekday]
    if not indices:
        return {"windows": [], "significance": _NO_DURMUHURTA}
    windows = []
    for idx in indices:
        s = sunrise + timedelta(seconds=muhurta * idx)
        e = s + timedelta(seconds=muhurta)
        windows.append([s.strftime("%I:%M %p"), e.strftime("%I:%M %p")])
    return {"windows": windows, "significance": _DURMUHURTA_SIG}


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
def calculate_varjyam(nak_idx, nak_start_utc, nak_end_utc, tz):
    offset_g, dur_g = VARJYAM_TABLE[nak_idx]
    end = nak_end_utc if nak_end_utc else (nak_start_utc + timedelta(hours=25))
    ghati   = (end - nak_start_utc).total_seconds() / 60.0
    v_start = nak_start_utc + timedelta(seconds=ghati * offset_g)
    v_end   = v_start       + timedelta(seconds=ghati * dur_g)
    return {
        "start": v_start.astimezone(tz).strftime("%I:%M %p"),
        "end":   v_end.astimezone(tz).strftime("%I:%M %p"),
        "significance": ("Inauspicious window based on the current nakshatra. "
                         "Avoid starting new work, ceremonies, or important decisions during this time."),
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
    """Returns poojas for next days_ahead days after from_date."""
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
                    {"abhijit": [abh_s.strftime("%I:%M:%S %p"), abh_e.strftime("%I:%M:%S %p")]},
                    {"brahma":  [brh_s.strftime("%I:%M:%S %p"), brh_e.strftime("%I:%M:%S %p")]},
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
                {"abhijit": [abh_s.strftime("%I:%M:%S %p"), abh_e.strftime("%I:%M:%S %p")]},
                {"brahma":  [brh_s.strftime("%I:%M:%S %p"), brh_e.strftime("%I:%M:%S %p")]},
            ]
        except Exception:
            day_muhurat = []

        # --- spiritual events entry ---
        festivals    = (fixed + lunar) or ["None"]
        vratas_list  = vratas or ["None"]
        clean_f  = _clean_event_list(festivals)
        clean_v  = [v for v in _clean_event_list(vratas_list)
                    if "ekadashi" in v.lower() or "pradosh" in v.lower()]
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
    if row.get("all_events"):
        return 2
    if "festival" in text or "jayanti" in text or "purnima" in text:
        return 3
    return 4


def get_upcoming_spiritual_events(lat_r, lon_r, tz_name, from_date, days_ahead=7, month_system="both"):
    """Return festival/vrata-rich upcoming spiritual events for app use."""
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
        clean_vratas = [v for v in _clean_event_list(vratas) if ("ekadashi" in v.lower() or "pradosh" in v.lower())]
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
    """For each planet in graha_gochar, estimate days until sign change using JD+1 daily motion.

    Returns {planet_name: {"days": int, "next_sign": str}} or {} per planet if unavailable.
    Single extra call to get_all_planet_positions at JD+1 for efficiency.
    """
    try:
        tomorrow_pos = get_all_planet_positions(TS.tt_jd(base_jd + 1.0))
    except Exception:
        return {}

    result = {}
    for planet, info in graha_gochar.items():
        try:
            cur_lon = float(info.get("longitude", 0))
            tmr_lon = float(tomorrow_pos[planet]["longitude"])
            daily_motion = tmr_lon - cur_lon
            if daily_motion > 180:
                daily_motion -= 360
            elif daily_motion < -180:
                daily_motion += 360

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
    base_rashi = (
        _extract_rashi_name((kundali_result or {}).get("lagna"))
        or _extract_rashi_name((kundali_result or {}).get("rashi"))
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


def _fetch_kundali_report(birth_details, fallback_tz_name, person_name=None):
    required = ["date_of_birth", "time_of_birth", "birth_latitude", "birth_longitude"]
    if not birth_details or any(birth_details.get(k) in (None, "") for k in required):
        return {"ok": False, "status": "birth_details_not_provided", "result": None}

    time_str = str(birth_details.get("time_of_birth", "")).strip()
    if len(time_str) == 5:
        time_str = f"{time_str}:00"

    payload = {
        "name": person_name or "Panchanga User",
        "date": str(birth_details.get("date_of_birth")).strip(),
        "time": time_str,
        "latitude": str(birth_details.get("birth_latitude")).strip(),
        "longitude": str(birth_details.get("birth_longitude")).strip(),
        "timezone": (birth_details.get("birth_timezone") or fallback_tz_name or "Asia/Kathmandu"),
        "user_currency": str(birth_details.get("user_currency") or "INR"),
    }

    try:
        req = urlrequest.Request(
            KUNDALI_REPORT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=KUNDALI_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw or "{}")
        if not parsed.get("ok") or not isinstance(parsed.get("result"), dict):
            return {"ok": False, "status": "kundali_api_failed", "result": None}
        return {"ok": True, "status": "ok", "result": parsed.get("result")}
    except Exception:
        return {"ok": False, "status": "kundali_api_error", "result": None}


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
    transit_base_rashi = (
        _extract_rashi_name((kundali_result or {}).get("lagna"))
        or _extract_rashi_name((kundali_result or {}).get("rashi"))
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
        "personalized_planetary_transits": personalized_transits,
        "today_horoscope": real_today_horoscope,
        "general_horoscope_all_rashi": general_all,
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


# ============================================================
# 13) DAILY PANCHANGA (for monthly endpoint)
# ============================================================
def calculate_panchanga_for_date(latitude, longitude, target_date_naive, tz_name, month_system="both", precomputed_end_times=None):
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
    durmuhurta  = calculate_durmuhurta(sunrise, sunset, weekday)

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
    varjyam       = calculate_varjyam(nak_idx, nak_start_utc, nak_end_utc, tz)

    amrit_windows = [[s["start"], s["end"]] for s in choghadiya["day"] + choghadiya["night"]
                     if s["name"] == "Amrit"]
    amrit_kaal = {
        "windows": amrit_windows,
        "significance": ("Most auspicious window of the day based on lunar nakshatra. "
                         "Begin important work, perform puja, start journeys, or take medicine "
                         "during Amrit Kaal for the best results."),
    }

    significance_text = generate_significance(
        tithi_name, tithi_nature, paksha, nakshatra_name, nakshatra_lord,
        yoga_name, moon_sign, sun_sign, ritu,
        target_date_local.strftime("%A"), festival_today, vrata_today, is_adhik
    )
    day_duration = (sunset - sunrise).total_seconds() / 3600

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
            {"abhijit":      [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")]},
            {"brahma":       [brahma_start.strftime("%I:%M:%S %p"),  brahma_end.strftime("%I:%M:%S %p")]},
        ],
        "asubh_muhurat": [
            {"rahu":     [rahu_start.strftime("%I:%M:%S %p"),      rahu_end.strftime("%I:%M:%S %p")]},
            {"gulika":   [gulika_start.strftime("%I:%M:%S %p"),    gulika_end.strftime("%I:%M:%S %p")]},
            {"yamaganda":[yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")]},
        ],
        "choghadiya":  choghadiya,
        "durmuhurta":  durmuhurta,
        "amrit_kaal":  amrit_kaal,
        "varjyam":     varjyam,
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
        durmuhurta = calculate_durmuhurta(sunrise, sunset, weekday)
        amrit_windows = [[s["start"], s["end"]] for s in choghadiya["day"] + choghadiya["night"]
                         if s["name"] == "Amrit"]
        amrit_kaal = {
            "windows": amrit_windows,
            "significance": ("Most auspicious window of the day based on lunar nakshatra. "
                             "Begin important work, perform puja, start journeys, or take medicine "
                             "during Amrit Kaal for the best results."),
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
        upcoming_poojas = get_upcoming_poojas(
            lat_r, lon_r, timezone_str, now_local.date(), days_ahead=7,
            month_system=month_system
        )

        nak_end_local = end_times["nakshatra_end"]
        nak_end_utc   = nak_end_local.astimezone(pytz.utc) if nak_end_local else None
        now_utc_dt    = now_local.astimezone(pytz.utc)
        nak_start_utc = estimate_nakshatra_start_utc(moon_sid, now_utc_dt, nak_end_utc)
        varjyam       = calculate_varjyam(nak_idx, nak_start_utc, nak_end_utc, tz)

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
            # --- Significance ---
            "significance": significance_text,
            # --- Muhurats ---
            "subh_muhurat": [
                {"abhijit": [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")]},
                {"brahma":  [brahma_start.strftime("%I:%M:%S %p"),  brahma_end.strftime("%I:%M:%S %p")]},
            ],
            "asubh_muhurat": [
                {"rahu":     [rahu_start.strftime("%I:%M:%S %p"),      rahu_end.strftime("%I:%M:%S %p")]},
                {"gulika":   [gulika_start.strftime("%I:%M:%S %p"),    gulika_end.strftime("%I:%M:%S %p")]},
                {"yamaganda":[yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")]},
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
            response_payload, upcoming_spiritual_events, requested_rashi, person_name, birth_details, timezone_str, upcoming_poojas
        )
        response_payload = order_day_payload(response_payload)
        response_payload["app_response"] = app_response
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

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)

        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

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

        # Fetch kundali once — birth data is static across all days
        precomputed_kundali = _fetch_kundali_report(birth_details, timezone_str, person_name)

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

        return jsonify({
            "month": month,
            "year": year,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "total_days": num_days,
            "panchanga_data": monthly_data,
            "app_response": monthly_app_response,
        })

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

        lat_r = round_coord(latitude)
        lon_r = round_coord(longitude)

        timezone_str = cached_timezone_str(lat_r, lon_r)
        if timezone_str is None:
            return jsonify({"error": "Timezone could not be determined from the provided coordinates."}), 400

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
            panchanga_data, upcoming_spiritual_events, requested_rashi, person_name, birth_details, timezone_str, upcoming_poojas
        )
        panchanga_data = order_day_payload(panchanga_data)

        return jsonify({
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "panchanga_data": panchanga_data,
            "upcoming_poojas": upcoming_poojas,
            "app_response": app_response,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ============================================================
# 15) RUN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)
