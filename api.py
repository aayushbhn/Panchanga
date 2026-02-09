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

def generate_significance(paksha, nakshatra_name, moon_sign, yoga_name):
    parts = []
    for k in (paksha, nakshatra_name, moon_sign, yoga_name):
        if k in messages:
            parts.append(messages[k])
    txt = " ".join(parts).strip()
    return txt if txt else "Today is a good day for reflection and alignment with your intentions."

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

# ============================================================
# 13) DAILY PANCHANGA (for monthly endpoint)
# ============================================================
def calculate_panchanga_for_date(latitude, longitude, target_date_naive, tz_name, month_system="both"):
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

    nakshatra_name = nakshatras[_to_int_scalar(nakshatra_index_at(t))]
    yoga_name = yoga_names[_to_int_scalar(yoga_index_at(t))]
    karana_name = karana_name_from_number(_to_int_scalar(karana_index_at(t)))

    moon_sign = rashi_names[int(moon_sid // 30) % 12]
    ritu = calculate_ritu(sun_sid)

    date_ymd = target_date_naive.strftime("%Y-%m-%d")

    sunrise_utc, sunset_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)
    sunrise = sunrise_utc.astimezone(tz)
    sunset = sunset_utc.astimezone(tz)

    mr_utc, ms_utc = cached_moonrise_moonset(lat_r, lon_r, date_ymd, tz_name)
    moonrise = mr_utc.astimezone(tz) if mr_utc else None
    moonset = ms_utc.astimezone(tz) if ms_utc else None

    rahu_start, rahu_end = calculate_rahu_kaal(sunrise, sunset, target_date_naive.weekday())
    gulika_start, gulika_end = calculate_gulika_kaal(sunrise, sunset, target_date_naive.weekday())
    yamaganda_start, yamaganda_end = calculate_yamaganda_kaal(sunrise, sunset, target_date_naive.weekday())
    abhijit_start, abhijit_end = calculate_abhijit_muhurat(sunrise, sunset)
    brahma_start, brahma_end = calculate_brahma_muhurat(sunrise, sunset)

    # Samvat (your rule)
    current_year = target_date_naive.year
    current_month = target_date_naive.month
    if current_month < 4:
        vikram_samvat = (current_year - 1) + 57
        shaka_samvat = (current_year - 1) - 78
    else:
        vikram_samvat = current_year + 57
        shaka_samvat = current_year - 78

    amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
        target_date_local, paksha, tz_name, lat_r, lon_r
    )

    def tithi_context_at(local_dt):
        t_local = TS.from_datetime(local_dt.astimezone(pytz.utc))
        sun_sid_local, moon_sid_local = get_sidereal_lons_geocentric(t_local)
        sun_sid_local = float(np.atleast_1d(sun_sid_local)[0])
        moon_sid_local = float(np.atleast_1d(moon_sid_local)[0])
        angle_local = (moon_sid_local - sun_sid_local) % 360.0
        tithi_number_local, paksha_local, tithi_name_local = calculate_tithi_and_paksha_from_angle(angle_local)
        amanta_local, purnimanta_local = calculate_amanta_purnimanta_month_fast(
            local_dt, paksha_local, tz_name, lat_r, lon_r
        )
        return tithi_name_local, paksha_local, amanta_local, purnimanta_local

    def festivals_for_instant(local_dt):
        tithi_name_local, paksha_local, amanta_local, purnimanta_local = tithi_context_at(local_dt)
        return get_festivals_for_day(
            tithi_name_local,
            paksha_local,
            amanta_local,
            purnimanta_local,
            month_system=month_system,
        )

    def nisita_time_for_date():
        date_ymd = target_date_naive.strftime("%Y-%m-%d")
        sunset_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)[1]
        next_date_ymd = (target_date_naive + timedelta(days=1)).strftime("%Y-%m-%d")
        next_sunrise_utc = cached_sunrise_sunset(lat_r, lon_r, next_date_ymd, tz_name)[0]
        sunset_local = sunset_utc.astimezone(tz)
        next_sunrise_local = next_sunrise_utc.astimezone(tz)
        return sunset_local + (next_sunrise_local - sunset_local) / 2

    fixed_list = check_fixed_festivals(target_date_naive)
    nisita_local = nisita_time_for_date()
    nisita_list = festivals_for_instant(nisita_local)
    if not nisita_list:
        sunrise_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, tz_name)[0]
        sunrise_list = festivals_for_instant(sunrise_utc.astimezone(tz))
        lunar_list = sunrise_list
    else:
        lunar_list = nisita_list

    all_festivals = fixed_list + lunar_list
    festival_today = all_festivals if all_festivals else ["None"]

    vrata_list = get_vratas_for_day(tithi_name, paksha, target_date_local.strftime("%A"), nakshatra_name)
    vrata_today = vrata_list if vrata_list else ["None"]

    significance_text = generate_significance(paksha, nakshatra_name, moon_sign, yoga_name)
    day_duration = (sunset - sunrise).total_seconds() / 3600

    return {
        "date": date_ymd,
        "day_of_week": target_date_local.strftime("%A"),
        "tithi": tithi_name,
        "tithi_number": tithi_number,
        "paksha": paksha,
        "nakshatra": nakshatra_name,
        "karana": karana_name,
        "yoga": yoga_name,
        "moon_sign": moon_sign,
        "ritu": ritu,
        "amanta_month": amanta_month,
        "purnimanta_month": purnimanta_month,
        "vikram_samvat": vikram_samvat,
        "shaka_samvat": shaka_samvat,
        "sun_moon_angle": angle,
        "sun_sidereal": sun_sid,
        "sunrise": sunrise.strftime("%I:%M:%S %p"),
        "sunset": sunset.strftime("%I:%M:%S %p"),
        "moonrise": format_time_with_date_if_needed(moonrise, date_ymd),
        "moonset": format_time_with_date_if_needed(moonset, date_ymd),
        "day_duration": f"{day_duration:.2f} hours",
        "festival_today": festival_today,
        "vrata_today": vrata_today,
        "significance": significance_text,
        "subh_muhurat": [
            {"abhijit": [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")]},
            {"brahma": [brahma_start.strftime("%I:%M:%S %p"), brahma_end.strftime("%I:%M:%S %p")]},
        ],
        "asubh_muhurat": [
            {"rahu": [rahu_start.strftime("%I:%M:%S %p"), rahu_end.strftime("%I:%M:%S %p")]},
            {"gulika": [gulika_start.strftime("%I:%M:%S %p"), gulika_end.strftime("%I:%M:%S %p")]},
            {"yamaganda": [yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")]},
        ],
    }

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
        sun_sid = float(np.atleast_1d(sun_sid)[0])
        moon_sid = float(np.atleast_1d(moon_sid)[0])

        angle = (moon_sid - sun_sid) % 360.0
        tithi_number, paksha, tithi_name = calculate_tithi_and_paksha_from_angle(angle)
        nakshatra_name = nakshatras[_to_int_scalar(nakshatra_index_at(t_now))]
        yoga_name = yoga_names[_to_int_scalar(yoga_index_at(t_now))]
        karana_name = karana_name_from_number(_to_int_scalar(karana_index_at(t_now)))

        # Sunrise/Sunset, Moonrise/Moonset
        sunrise_utc, sunset_utc = cached_sunrise_sunset(lat_r, lon_r, date_ymd, timezone_str)
        sunrise = sunrise_utc.astimezone(tz)
        sunset = sunset_utc.astimezone(tz)

        mr_utc, ms_utc = cached_moonrise_moonset(lat_r, lon_r, date_ymd, timezone_str)
        moonrise = mr_utc.astimezone(tz) if mr_utc else None
        moonset = ms_utc.astimezone(tz) if ms_utc else None

        # Muhurats
        rahu_start, rahu_end = calculate_rahu_kaal(sunrise, sunset, now_local.weekday())
        gulika_start, gulika_end = calculate_gulika_kaal(sunrise, sunset, now_local.weekday())
        yamaganda_start, yamaganda_end = calculate_yamaganda_kaal(sunrise, sunset, now_local.weekday())
        abhijit_start, abhijit_end = calculate_abhijit_muhurat(sunrise, sunset)
        brahma_start, brahma_end = calculate_brahma_muhurat(sunrise, sunset)

        moon_sign = rashi_names[int(moon_sid // 30) % 12]
        ritu = calculate_ritu(sun_sid)

        # Samvat (your rule)
        current_year = now_local.year
        current_month = now_local.month
        if current_month < 4:
            vikram_samvat = (current_year - 1) + 57
            shaka_samvat = (current_year - 1) - 78
        else:
            vikram_samvat = current_year + 57
            shaka_samvat = current_year - 78

        amanta_month, purnimanta_month = calculate_amanta_purnimanta_month_fast(
            now_local, paksha, timezone_str, lat_r, lon_r
        )

        fixed_list = check_fixed_festivals(now_local.replace(tzinfo=None))
        lunar_list = get_festivals_for_day(
            tithi_name,
            paksha,
            amanta_month,
            purnimanta_month,
            month_system=month_system,
        )
        all_festivals = fixed_list + lunar_list
        festival_today = all_festivals if all_festivals else ["None"]

        vrata_today = get_vratas_for_day(tithi_name, paksha, now_local.strftime("%A"), nakshatra_name)
        vrata_today = vrata_today if vrata_today else ["None"]

        day_duration = (sunset - sunrise).total_seconds() / 3600
        significance_text = generate_significance(paksha, nakshatra_name, moon_sign, yoga_name)

        subh_muhurat = [
            {"abhijit": [abhijit_start.strftime("%I:%M:%S %p"), abhijit_end.strftime("%I:%M:%S %p")]},
            {"brahma": [brahma_start.strftime("%I:%M:%S %p"), brahma_end.strftime("%I:%M:%S %p")]},
        ]
        asubh_muhurat = [
            {"rahu": [rahu_start.strftime("%I:%M:%S %p"), rahu_end.strftime("%I:%M:%S %p")]},
            {"gulika": [gulika_start.strftime("%I:%M:%S %p"), gulika_end.strftime("%I:%M:%S %p")]},
            {"yamaganda": [yamaganda_start.strftime("%I:%M:%S %p"), yamaganda_end.strftime("%I:%M:%S %p")]},
        ]

        return jsonify({
            "tithi": tithi_name,
            "tithi_end": format_dt_local(end_times["tithi_end"]),
            "nakshatra": nakshatra_name,
            "nakshatra_end": format_dt_local(end_times["nakshatra_end"]),
            "karana": karana_name,
            "karana_end": format_dt_local(end_times["karana_end"]),
            "yoga": yoga_name,
            "yoga_end": format_dt_local(end_times["yoga_end"]),

            "tithi_number": tithi_number,
            "paksha": paksha,
            "day_of_week": now_local.strftime("%A"),
            "date": date_ymd,
            "day_duration": f"{day_duration:.2f} hours",
            "moon_sign": moon_sign,
            "ritu": ritu,
            "amanta_month": amanta_month,
            "purnimanta_month": purnimanta_month,
            "vikram_samvat": vikram_samvat,
            "shaka_samvat": shaka_samvat,
            "sun_moon_angle": angle,
            "sun_sidereal": sun_sid,

            "sunrise": sunrise.strftime("%I:%M:%S %p"),
            "sunset": sunset.strftime("%I:%M:%S %p"),
            "moonrise": format_time_with_date_if_needed(moonrise, date_ymd),
            "moonset": format_time_with_date_if_needed(moonset, date_ymd),

            "significance": significance_text,
            "time_zone": timezone_str,
            "festival_today": festival_today,
            "vrata_today": vrata_today,
            "month_system": month_system,
            "subh_muhurat": subh_muhurat,
            "asubh_muhurat": asubh_muhurat,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/monthly-panchanga-page")
def monthly_panchanga_page():
    return render_template("monthly_panchanga.html")

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

        monthly_data = []
        for day in range(1, num_days + 1):
            target_date = datetime(year, month, day)
            monthly_data.append(
                calculate_panchanga_for_date(
                    latitude,
                    longitude,
                    target_date,
                    timezone_str,
                    month_system=month_system,
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

# ============================================================
# 15) RUN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)
