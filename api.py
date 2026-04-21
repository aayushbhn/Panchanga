from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import pytz
from functools import lru_cache
from bisect import bisect_right
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

AYANAMSA = 24.227570  # Lahiri Ayanamsa (your value)

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

def tropical_to_sidereal_arr(tropical_deg):
    return (_as_np(tropical_deg) - AYANAMSA) % 360.0

def tropical_to_sidereal(tropical_deg_scalar):
    return float((tropical_deg_scalar - AYANAMSA) % 360.0)

# --- Anga widths
TITHI_DEG = 12.0
NAK_DEG = 360.0 / 27.0
YOGA_DEG = 360.0 / 27.0
KARANA_DEG = 6.0

def get_sidereal_lons_geocentric(t):
    earth = geocentric_observer()
    sun = EPH["sun"]
    moon = EPH["moon"]

    sun_lon_trop = earth.at(t).observe(sun).apparent().frame_latlon(ecliptic_frame)[1].degrees
    moon_lon_trop = earth.at(t).observe(moon).apparent().frame_latlon(ecliptic_frame)[1].degrees

    sun_sid = tropical_to_sidereal_arr(sun_lon_trop)
    moon_sid = tropical_to_sidereal_arr(moon_lon_trop)
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
    return {"name": name, "id": pid, "variant_id": vid, "reason": reason}

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
    result = {}
    for name, body in planet_map:
        lon_trop = earth.at(t).observe(EPH[body]).apparent().frame_latlon(ecliptic_frame)[1].degrees
        lon_sid  = tropical_to_sidereal(float(np.atleast_1d(lon_trop)[0]))
        rashi    = rashi_names[int(lon_sid // 30) % 12]
        result[name] = {
            "longitude":   round(lon_sid, 4),
            "rashi":       rashi,
            "significance": (f"Transiting {rashi} ({RASHI_NATURE_BRIEF[rashi]}), "
                             f"influencing {PLANET_GOVERNS[name]}."),
        }

    d = float(np.atleast_1d(t.tt)[0]) - 2451545.0
    rahu_trop = (125.044522 - 0.052953922 * d) % 360.0
    rahu_sid  = tropical_to_sidereal(rahu_trop)
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
    """Generate a self-contained HTML summary of the day's panchanga."""
    def _esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _badge(text, color):
        return f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;background:{color};color:#fff;margin:2px">{_esc(text)}</span>'

    def _auspicious_quality(name):
        q = {"Amrit": "#1a7f4b", "Shubh": "#2e7d32", "Labh": "#388e3c",
             "Char": "#f57c00", "Udveg": "#c62828", "Kaal": "#b71c1c", "Rog": "#d32f2f"}
        return q.get(name, "#555")

    festivals = [f for f in (d.get("festival_today") or []) if f != "None"]
    vratas    = [v for v in (d.get("vrata_today") or [])    if v != "None"]
    poojas    = [p for p in (d.get("pooja_today") or [])    if p.get("name") != "None"]
    chog_day  = (d.get("choghadiya") or {}).get("day", [])
    chog_night= (d.get("choghadiya") or {}).get("night", [])
    durmuhurta= d.get("durmuhurta") or {}
    varjyam   = d.get("varjyam") or {}
    amrit     = d.get("amrit_kaal") or {}
    gochar    = d.get("graha_gochar") or {}
    subh      = d.get("subh_muhurat") or []
    asubh     = d.get("asubh_muhurat") or []

    h = []
    h.append('<style>'
        '.ps{font-family:system-ui,sans-serif;color:#222;line-height:1.5;max-width:900px;margin:0 auto}'
        '.ps h2{font-size:1.4em;font-weight:700;margin:0 0 4px}'
        '.ps h3{font-size:1em;font-weight:700;margin:0 0 10px;color:#5c3317;border-bottom:2px solid #f4a838;padding-bottom:4px;display:flex;align-items:center;gap:6px}'
        '.ps .sec{background:#fff;border:1px solid #e8d5b0;border-radius:10px;padding:16px;margin-bottom:14px}'
        '.ps .sec.good{border-color:#a5d6a7;background:#f1f8e9}'
        '.ps .sec.bad{border-color:#ef9a9a;background:#fff3f3}'
        '.ps .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}'
        '.ps .card{background:#fffbf2;border:1px solid #f4a838;border-radius:8px;padding:10px}'
        '.ps .card .label{font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.5px}'
        '.ps .card .value{font-size:15px;font-weight:700;color:#2c1810;margin-top:2px}'
        '.ps .card .sub{font-size:11px;color:#777;margin-top:2px}'
        '.ps .row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f0e8d8}'
        '.ps .row:last-child{border-bottom:none}'
        '.ps .row .k{font-weight:600;color:#555;font-size:13px}'
        '.ps .row .v{font-size:13px;color:#222;text-align:right}'
        '.ps .chog-slot{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px dotted #eee}'
        '.ps .chog-slot:last-child{border-bottom:none}'
        '.ps .pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700;color:#fff}'
        '.ps .sig{font-size:14px;color:#3d2c00;line-height:1.7;background:#fffbf0;border-left:4px solid #f4a838;padding:12px 14px;border-radius:0 8px 8px 0}'
        '.ps .hdr{background:linear-gradient(135deg,#c0392b 0%,#e67e22 50%,#f39c12 100%);color:#fff;border-radius:10px;padding:16px 20px;margin-bottom:14px}'
        '.ps .hdr h2{color:#fff}'
        '.ps .hdr .meta{font-size:12px;opacity:.85;margin-top:4px}'
        '.ps .planet-row{display:grid;grid-template-columns:90px 1fr;gap:4px;padding:4px 0;border-bottom:1px solid #f0e8d8;font-size:13px}'
        '.ps .planet-row:last-child{border-bottom:none}'
        '.ps table.chog{width:100%;border-collapse:collapse;font-size:13px}'
        '.ps table.chog th{background:#5c3317;color:#fff;padding:6px 10px;text-align:left}'
        '.ps table.chog td{padding:5px 10px;border-bottom:1px solid #f0e8d8}'
        '</style>')

    # ── Header ──────────────────────────────────────────────
    paksha_icon = "🌕" if "Shukla" in str(d.get("paksha", "")) else "🌑"
    h.append(f'''<div class="ps"><div class="ps hdr">
      <h2>{_esc(d.get("day_of_week",""))} · {_esc(d.get("date",""))}</h2>
      <div class="meta">
        {paksha_icon} {_esc(d.get("paksha",""))} &nbsp;|&nbsp;
        {_esc(d.get("amanta_month",""))} (Amanta) &nbsp;|&nbsp;
        Vikram Samvat {_esc(d.get("vikram_samvat",""))} &nbsp;|&nbsp;
        Shaka {_esc(d.get("shaka_samvat",""))}
        {" &nbsp;|&nbsp; <strong>Adhik Maas</strong>" if d.get("adhik_maas") else ""}
      </div>
    </div>''')

    # ── Five Angas ───────────────────────────────────────────
    h.append('<div class="ps sec"><h3>🕉 The Five Angas (Panchanga)</h3><div class="ps grid">')
    def _card(label, value, sub=""):
        s = f'<div class="ps card"><div class="label">{_esc(label)}</div><div class="value">{_esc(value)}</div>'
        if sub: s += f'<div class="sub">{_esc(sub)}</div>'
        s += '</div>'
        return s
    tithi_end_str  = f'Ends {d["tithi_end"]}' if d.get("tithi_end") else "Continues past midnight"
    nak_end_str    = f'Ends {d["nakshatra_end"]}' if d.get("nakshatra_end") else "Continues past midnight"
    yoga_end_str   = f'Ends {d["yoga_end"]}' if d.get("yoga_end") else "Continues past midnight"
    karana_end_str = f'Ends {d["karana_end"]}' if d.get("karana_end") else "Continues past midnight"

    h.append(_card("Tithi (Vara)",
                   f'{d.get("tithi","")} #{d.get("tithi_number","")}',
                   f'{d.get("tithi_nature","")} nature · {tithi_end_str}'))
    h.append(_card("Nakshatra",
                   d.get("nakshatra",""),
                   f'Pada {d.get("nakshatra_pada","")} · {nak_end_str}'))
    h.append(_card("Yoga", d.get("yoga",""), yoga_end_str))
    h.append(_card("Karana", d.get("karana",""), karana_end_str))
    h.append(_card("Vara (Day)", d.get("day_of_week",""),
                   f'{d.get("ritu","")} season'))
    h.append('</div>')
    # Tithi + Nakshatra nature blurbs
    tn_sig = d.get("tithi_nature_significance","")
    np_sig = d.get("nakshatra_pada_significance","")
    if tn_sig or np_sig:
        h.append('<div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px">')
        if tn_sig:
            h.append(f'<div style="font-size:12px;color:#5c3317;background:#fffbf0;padding:8px 10px;border-radius:6px;border-left:3px solid #f4a838">{_esc(tn_sig)}</div>')
        if np_sig:
            h.append(f'<div style="font-size:12px;color:#5c3317;background:#fffbf0;padding:8px 10px;border-radius:6px;border-left:3px solid #f4a838">{_esc(np_sig)}</div>')
        h.append('</div>')
    h.append('</div>')

    # ── Significance ─────────────────────────────────────────
    if d.get("significance"):
        h.append(f'<div class="ps sec"><h3>✨ Day\'s Significance</h3>'
                 f'<div class="ps sig">{_esc(d["significance"])}</div></div>')

    # ── Festivals / Vratas ───────────────────────────────────
    if festivals or vratas:
        h.append('<div class="ps sec"><h3>🎉 Festivals &amp; Vratas</h3>')
        if festivals:
            h.append('<div style="margin-bottom:6px"><strong>Festivals:</strong> ')
            h.append(" ".join(_badge(f, "#c0392b") for f in festivals))
            h.append('</div>')
        if vratas:
            h.append('<div><strong>Vratas:</strong> ')
            h.append(" ".join(_badge(v, "#1565c0") for v in vratas))
            h.append('</div>')
        h.append('</div>')

    # ── Best Times ───────────────────────────────────────────
    h.append('<div class="ps sec good"><h3>✅ Best Times Today — What To Do</h3>')
    # Brahma Muhurta
    for m in subh:
        if "brahma" in m:
            t = m["brahma"]
            h.append(f'<div class="ps row"><span class="k">🌄 Brahma Muhurta</span>'
                     f'<span class="v">{_esc(t[0])} – {_esc(t[1])}</span></div>')
            break
    # Abhijit
    for m in subh:
        if "abhijit" in m:
            t = m["abhijit"]
            h.append(f'<div class="ps row"><span class="k">☀️ Abhijit Muhurta</span>'
                     f'<span class="v">{_esc(t[0])} – {_esc(t[1])}</span></div>')
            break
    # Amrit Kaal
    windows = amrit.get("windows", [])
    if windows:
        for w in windows:
            h.append(f'<div class="ps row"><span class="k">🌙 Amrit Kaal</span>'
                     f'<span class="v">{_esc(w[0])} – {_esc(w[1])}</span></div>')
    else:
        h.append('<div class="ps row"><span class="k">🌙 Amrit Kaal</span>'
                 '<span class="v" style="color:#888">None today</span></div>')
    # Auspicious choghadiya
    good_slots = [s for s in chog_day + chog_night
                  if s.get("quality") in ("Auspicious", "Highly Auspicious")]
    if good_slots:
        h.append(f'<div class="ps row" style="padding-top:8px"><span class="k">Auspicious Choghadiya</span>'
                 f'<span class="v">' +
                 "".join(f'<span style="margin-left:4px;font-size:12px">{_badge(s["name"],"#2e7d32")} {_esc(s["start"])}–{_esc(s["end"])}</span>'
                         for s in good_slots) +
                 '</span></div>')
    if amrit.get("significance"):
        h.append(f'<div style="font-size:12px;color:#2e7d32;margin-top:8px;padding:6px;background:#f1f8e9;border-radius:4px">{_esc(amrit["significance"])}</div>')
    h.append('</div>')

    # ── Times to Avoid ────────────────────────────────────────
    h.append('<div class="ps sec bad"><h3>⛔ Times to Avoid</h3>')
    for m in asubh:
        for k, t in m.items():
            label = {"rahu": "🔴 Rahu Kaal", "gulika": "🟠 Gulika Kaal", "yamaganda": "⚫ Yamaganda"}.get(k, k.title())
            h.append(f'<div class="ps row"><span class="k">{label}</span>'
                     f'<span class="v">{_esc(t[0])} – {_esc(t[1])}</span></div>')
    # Durmuhurta
    dur_wins = durmuhurta.get("windows", [])
    if dur_wins:
        for w in dur_wins:
            h.append(f'<div class="ps row"><span class="k">🚫 Durmuhurta</span>'
                     f'<span class="v">{_esc(w[0])} – {_esc(w[1])}</span></div>')
    else:
        h.append(f'<div class="ps row"><span class="k">🚫 Durmuhurta</span>'
                 f'<span class="v" style="color:#2e7d32">None today (auspicious day)</span></div>')
    # Varjyam
    if varjyam.get("start"):
        h.append(f'<div class="ps row"><span class="k">⚠️ Varjyam</span>'
                 f'<span class="v">{_esc(varjyam["start"])} – {_esc(varjyam["end"])}</span></div>')
    if durmuhurta.get("significance"):
        h.append(f'<div style="font-size:12px;color:#c62828;margin-top:8px;padding:6px;background:#fff3f3;border-radius:4px">{_esc(durmuhurta["significance"])}</div>')
    h.append('</div>')

    # ── Choghadiya Table ─────────────────────────────────────
    if chog_day or chog_night:
        h.append('<div class="ps sec"><h3>🕐 Choghadiya</h3>'
                 '<table class="ps chog">'
                 '<thead><tr><th>Period</th><th>Name</th><th>Quality</th><th>Start</th><th>End</th><th>Guidance</th></tr></thead>'
                 '<tbody>')
        for i, slot in enumerate(chog_day):
            color = _auspicious_quality(slot["name"])
            h.append(f'<tr><td>Day {i+1}</td>'
                     f'<td>{_badge(slot["name"], color)}</td>'
                     f'<td style="color:{color};font-weight:600">{_esc(slot.get("quality",""))}</td>'
                     f'<td>{_esc(slot.get("start",""))}</td>'
                     f'<td>{_esc(slot.get("end",""))}</td>'
                     f'<td style="font-size:11px;color:#555">{_esc(slot.get("significance","")[:70])}…</td></tr>')
        for i, slot in enumerate(chog_night):
            color = _auspicious_quality(slot["name"])
            h.append(f'<tr style="background:#f0f0f8"><td>Night {i+1}</td>'
                     f'<td>{_badge(slot["name"], color)}</td>'
                     f'<td style="color:{color};font-weight:600">{_esc(slot.get("quality",""))}</td>'
                     f'<td>{_esc(slot.get("start",""))}</td>'
                     f'<td>{_esc(slot.get("end",""))}</td>'
                     f'<td style="font-size:11px;color:#555">{_esc(slot.get("significance","")[:70])}…</td></tr>')
        h.append('</tbody></table></div>')

    # ── Poojas ───────────────────────────────────────────────
    if poojas:
        h.append('<div class="ps sec"><h3>🪔 Poojas Today</h3>')
        for p in poojas:
            h.append(f'<div class="ps row"><span class="k">{_esc(p["name"])}</span>'
                     f'<span class="v" style="font-size:12px;color:#5c3317">{_esc(p.get("reason",""))}</span></div>')
        h.append('</div>')

    # ── Planetary Transits ───────────────────────────────────
    if gochar:
        h.append('<div class="ps sec"><h3>🪐 Planetary Transits (Graha Gochar)</h3>')
        for planet, info in gochar.items():
            h.append(f'<div class="ps planet-row">'
                     f'<span style="font-weight:700;color:#2c1810">{_esc(planet)}</span>'
                     f'<span style="color:#555">{_esc(info.get("rashi",""))} '
                     f'<span style="font-size:11px;color:#888">({round(info.get("longitude",0),1)}°)</span>'
                     f'</span></div>')
        h.append('</div>')

    # ── Moon & Sun info ──────────────────────────────────────
    h.append('<div class="ps sec"><h3>🌙 Solar &amp; Lunar</h3><div class="ps grid">')
    h.append(_card("Moon Sign", d.get("moon_sign",""), f'Nakshatra: {d.get("nakshatra","")} | Lord: {d.get("nakshatra_lord","")}'))
    h.append(_card("Sun Sign", d.get("sun_sign",""), f'Ritu: {d.get("ritu","")}'))
    h.append(_card("Sunrise", d.get("sunrise",""), ""))
    h.append(_card("Sunset", d.get("sunset",""), f'Day: {d.get("day_duration","")}'))
    if d.get("moonrise"): h.append(_card("Moonrise", d.get("moonrise",""), ""))
    if d.get("moonset"):  h.append(_card("Moonset",  d.get("moonset",""), ""))
    h.append('</div></div>')

    h.append('</div>')  # close .ps
    return "".join(h)


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
            result.append({
                "date":         target.strftime("%Y-%m-%d"),
                "day_of_week":  day_of_week,
                "tithi":        tithi_name,
                "tithi_number": tithi_number,
                "paksha":       paksha,
                "poojas":       poojas,
            })
    return result


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

        return jsonify({
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
        })

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

        monthly_data = []
        for day in range(1, num_days + 1):
            target_date = datetime(year, month, day)
            date_key = target_date.strftime("%Y-%m-%d")
            monthly_data.append(
                calculate_panchanga_for_date(
                    latitude,
                    longitude,
                    target_date,
                    timezone_str,
                    month_system=month_system,
                    precomputed_end_times=batch_end_times.get(date_key),
                )
            )

        return jsonify({
            "month": month,
            "year": year,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "total_days": num_days,
            "panchanga_data": monthly_data
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

        return jsonify({
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "panchanga_data": panchanga_data,
            "upcoming_poojas": upcoming_poojas,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ============================================================
# 15) RUN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)
