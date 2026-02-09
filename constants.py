tithi_names = [
    'प्रथमा', 'द्वितीया', 'तृतीया', 'चतुर्थी', 'पञ्चमी', 'षष्ठी',
    'सप्तमी', 'अष्टमी', 'नवमी', 'दशमी', 'एकादशी', 'द्वादशी',
    'त्रयोदशी', 'चतुर्दशी', 'पूर्णिमा',  # Shukla Paksha Tithis (1-15)
    'प्रथमा', 'द्वितीया', 'तृतीया', 'चतुर्थी', 'पञ्चमी', 'षष्ठी',
    'सप्तमी', 'अष्टमी', 'नवमी', 'दशमी', 'एकादशी', 'द्वादशी',
    'त्रयोदशी', 'चतुर्दशी', 'अमावस्या'  # Krishna Paksha Tithis (16-30)
]

nakshatras = [
    'Ashwini', 'Bharani', 'Krittika', 'Rohini', 'Mrigashira', 'Ardra', 'Punarvasu', 
    'Pushya', 'Ashlesha', 'Magha', 'Purva Phalguni', 'Uttara Phalguni', 'Hasta', 'Chitra', 
    'Swati', 'Vishakha', 'Anuradha', 'Jyeshtha', 'Mula', 'Purva Ashadha', 'Uttara Ashadha', 
    'Shravana', 'Dhanishta', 'Shatabhisha', 'Purva Bhadrapada', 'Uttara Bhadrapada', 'Revati'
]

yoga_names = [
    'Vishkambha', 'Priti', 'Ayushman', 'Saubhagya', 'Shobhana', 'Atiganda', 
    'Sukarma', 'Dhriti', 'Shoola', 'Ganda', 'Vriddhi', 'Dhruva', 'Vyaghata', 
    'Harshana', 'Vajra', 'Siddhi', 'Vyatipata', 'Variyana', 'Parigha', 
    'Shiva', 'Siddha', 'Sadhya', 'Shubha', 'Shukla', 'Brahma', 'Indra', 'Vaidhriti'
]

karana_table = {
    'Shukla': [('Kimstughna', 'Bava'), ('Balava', 'Kaulava'), ('Taitila', 'Gara'), 
               ('Vanija', 'Vishti'), ('Bava', 'Balava'), ('Kaulava', 'Taitila'), 
               ('Gara', 'Vanija'), ('Vishti', 'Bava'), ('Balava', 'Kaulava'), 
               ('Taitila', 'Gara'), ('Vanija', 'Vishti'), ('Bava', 'Balava'), 
               ('Kaulava', 'Taitila'), ('Gara', 'Vanija'), ('Vishti', 'Bava')],
    'Krishna': [('Bava', 'Balava'), ('Kaulava', 'Taitila'), ('Gara', 'Vanija'), 
                ('Vishti', 'Bava'), ('Balava', 'Kaulava'), ('Taitila', 'Gara'), 
                ('Vanija', 'Vishti'), ('Bava', 'Balava'), ('Kaulava', 'Taitila'), 
                ('Gara', 'Vanija'), ('Vishti', 'Bava'), ('Balava', 'Kaulava'), 
                ('Taitila', 'Gara'), ('Vanija', 'Vishti'), ('Shakuni', 'Chatushpada')]
}

ritu_names = [
    'Vasanta (Spring)', 'Grishma (Summer)', 'Varsha (Monsoon)', 
    'Sharad (Autumn)', 'Hemanta (Pre-Winter)', 'Shishira (Winter)'
]

months = ['Ashwin', 'Kartika', 'Margashirsha', 'Pausha', 'Magha', 'Phalguna', 
          'Chaitra', 'Vaishakha', 'Jyeshtha', 'Ashadha', 'Shravana', 'Bhadrapada']


# ----------------------------
# FESTIVALS (Feasible for your code)
# - Supports: fixed_date OR (tithi + month + paksha) OR (weekday + month) OR (nakshatra + month)
# - Uses your month names: Ashwin..Bhadrapada
# - Tithi in Hindi to match your tithi_names list
# ----------------------------

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
    "Maha Shivaratri": {"tithi": "त्रयोदशी", "month": "Phalguna", "paksha": "Krishna Paksha"},
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

    # Nepal Dashain (same tithis; kept separate via region)
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

    # Nepal: Tihar cluster (same tithis; region separated)
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


# ----------------------------
# VRATA / FASTING (Feasible for your code)
# - Supports: tithi + paksha, day_of_week, month-limited variants
# - Paksha allowed values: 'Shukla Paksha', 'Krishna Paksha', 'Both'
# ----------------------------

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

    # ---- Special named ekadashis (month-specific; still feasible) ----
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

    # ---- Month-specific vrats (already in your style) ----
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


rashi_names = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 'Libra', 
                       'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']

# Sun's sidereal Rashi at lunation -> Lunar month name
SUN_RASHI_TO_LUNAR_MONTH = {
    'Pisces': 'Chaitra',
    'Aries': 'Vaishakha',
    'Taurus': 'Jyeshtha',
    'Gemini': 'Ashadha',
    'Cancer': 'Shravana',
    'Leo': 'Bhadrapada',
    'Virgo': 'Ashwin',
    'Libra': 'Kartika',
    'Scorpio': 'Margashirsha',
    'Sagittarius': 'Pausha',
    'Capricorn': 'Magha',
    'Aquarius': 'Phalguna',
}


messages = {
    # Paksha messages
    'Shukla Paksha': "Today is a time for growth and new beginnings. You may find opportunities to start new projects, cultivate positive habits, and embrace new possibilities.",
    'Krishna Paksha': "This is a period for reflection, introspection, and release. Let go of what no longer serves you, slow down, and focus inward to renew your energy.",
    
    # Nakshatra messages
    'Ashwini': "Ashwini Nakshatra brings vitality and healing. This is a great day to focus on your health, engage in physical activities, and embrace new ideas with enthusiasm.",
    'Bharani': "Bharani Nakshatra encourages resilience and patience. Use this energy to manage responsibilities and approach challenges with determination.",
    'Krittika': "Krittika Nakshatra fosters transformation. Let go of the old and embrace positive changes; it's a day to sharpen your skills and stay focused.",
    'Rohini': "Rohini brings abundance and beauty. It's a great day for creative pursuits and nurturing meaningful connections with loved ones.",
    'Mrigashira': "The inquisitive nature of Mrigashira encourages exploration. Seek out new knowledge and keep an open mind to fresh perspectives.",
    'Ardra': "Ardra Nakshatra invites inner clarity and introspection. Embrace emotional healing and find strength through self-awareness.",
    'Punarvasu': "With Punarvasu’s energy, today is about renewal and optimism. Revisit old ideas with fresh enthusiasm and look for growth opportunities.",
    'Pushya': "Pushya Nakshatra fosters kindness and nurturing. Consider reaching out to loved ones, practicing compassion, and engaging in self-care.",
    'Ashlesha': "Ashlesha brings depth and insight. Use this energy for introspection, unraveling hidden thoughts, and understanding complex emotions.",
    'Magha': "Magha Nakshatra encourages honoring traditions. It’s a day for respecting your roots, reflecting on heritage, and embracing wisdom from the past.",
    'Purva Phalguni': "Purva Phalguni inspires creativity and joy. Enjoy leisure, spend time with friends, and let your playful side come forward.",
    'Uttara Phalguni': "Uttara Phalguni supports dedication and responsibility. Focus on organizing your life and building stable foundations.",
    'Hasta': "Hasta Nakshatra brings dexterity and precision. Pay attention to details today, and work on improving your skills.",
    'Chitra': "Chitra Nakshatra is associated with creativity. Let your artistic and innovative side shine today.",
    'Swati': "Swati encourages independence and flexibility. Take the time to pursue personal growth and adapt to changing situations.",
    'Vishakha': "Vishakha Nakshatra fosters determination and focus. Channel this energy into achieving long-term goals.",
    'Anuradha': "Anuradha encourages devotion and loyalty. Use this day to strengthen bonds and show appreciation to those around you.",
    'Jyeshtha': "Jyeshtha Nakshatra emphasizes strength and leadership. Stand confidently in your decisions and be a source of support for others.",
    'Mula': "Mula Nakshatra encourages you to explore deep truths. Seek knowledge and wisdom to understand complex situations.",
    'Purva Ashadha': "Purva Ashadha inspires confidence and ambition. Pursue your goals with vigor and believe in your potential.",
    'Uttara Ashadha': "Uttara Ashadha fosters determination. Today is ideal for taking responsibility and making steady progress.",
    'Shravana': "Shravana Nakshatra emphasizes learning and listening. Take time to gather information and practice humility.",
    'Dhanishta': "Dhanishta Nakshatra brings social energy. Engage in teamwork and share your talents with others.",
    'Shatabhisha': "Shatabhisha Nakshatra encourages introspection and healing. It’s a good day to focus on inner peace and well-being.",
    'Purva Bhadrapada': "Purva Bhadrapada fosters spiritual growth. Reflect on life’s deeper meaning and seek transformative insights.",
    'Uttara Bhadrapada': "Uttara Bhadrapada emphasizes patience and endurance. Work steadily and keep a calm mind.",
    'Revati': "Revati Nakshatra brings compassion and generosity. Engage in acts of kindness and support those in need.",
    
    # Moon sign messages
    'Aries': "With the Moon in Aries, it's a day for bold actions and new beginnings. Embrace your inner courage and take initiative.",
    'Taurus': "The Taurus Moon encourages stability and comfort. Focus on creating a peaceful environment and nurturing close relationships.",
    'Gemini': "With the Moon in Gemini, communication flows easily. It's a great time for socializing, learning, and sharing ideas.",
    'Cancer': "The Cancer Moon supports emotional depth and connection. Focus on family, home, and nurturing your inner self.",
    'Leo': "With the Moon in Leo, express your confidence and passion. This is a day to stand out and pursue what excites you.",
    'Virgo': "The Virgo Moon supports organizing and planning. Use this energy to create order in your life and focus on details.",
    'Libra': "With the Moon in Libra, harmony and balance take center stage. Spend time cultivating peaceful and fair relationships.",
    'Scorpio': "The Scorpio Moon brings intensity and transformation. Focus on understanding deeper emotions and renewing your inner strength.",
    'Sagittarius': "The Sagittarius Moon brings optimism and adventure. Explore new ideas, travel, or engage in learning experiences.",
    'Capricorn': "With the Moon in Capricorn, focus on your ambitions and responsibilities. Work steadily toward your long-term goals.",
    'Aquarius': "The Aquarius Moon encourages innovation and independence. Embrace unique ideas and connect with like-minded people.",
    'Pisces': "The Pisces Moon enhances intuition and compassion. Take time for self-reflection and explore your creative side.",
    
    # Yoga messages
    'Vishkambha': "Today brings strength and resilience. Overcome obstacles with courage and perseverance.",
    'Priti': "Priti Yoga promotes harmony and joy. Focus on building positive relationships and sharing happiness.",
    'Ayushman': "Ayushman Yoga brings health and vitality. Dedicate time to physical well-being and mental peace.",
    'Saubhagya': "Saubhagya Yoga brings luck and success. Trust your abilities and pursue your goals with confidence.",
    'Shobhana': "Shobhana Yoga enhances beauty and creativity. Engage in artistic activities and express your uniqueness.",
    'Atiganda': "Atiganda suggests caution. Avoid conflict and focus on maintaining inner peace.",
    'Sukarma': "Sukarma Yoga supports good deeds. Take time to help others and make positive contributions.",
    'Dhriti': "Dhriti brings patience and endurance. Take a calm approach to challenges and stay focused.",
    'Shoola': "Shoola suggests a day for introspection. Reflect on personal goals and identify areas for growth.",
    'Ganda': "Ganda promotes inner strength. Tackle difficult tasks with a resilient spirit.",
    'Vriddhi': "Vriddhi Yoga supports growth and prosperity. Focus on expanding your knowledge and skills.",
    'Dhruva': "Dhruva Yoga fosters stability. Use this time to establish a strong foundation for future goals.",
    'Vyaghata': "Vyaghata warns of potential obstacles. Move carefully and avoid unnecessary risks.",
    'Harshana': "Harshana brings joy and positivity. Surround yourself with uplifting people and experiences.",
    'Vajra': "Vajra suggests a day for spiritual insight. Engage in meditation or reflect on your deeper purpose.",
    'Siddhi': "Siddhi Yoga brings success and accomplishment. Trust your skills and work toward your goals.",
    'Vyatipata': "Vyatipata suggests caution. Avoid major decisions and be mindful of your surroundings.",
    'Variyana': "Variyana Yoga fosters clarity. It's a good day for introspection and setting clear intentions.",
    'Parigha': "Parigha indicates caution. Avoid conflicts and focus on peaceful activities.",
    'Shiva': "Shiva Yoga fosters transformation. Embrace change and seek personal growth.",
    'Siddha': "Siddha Yoga supports achievement. Work hard and trust that your efforts will yield results.",
    'Sadhya': "Sadhya encourages progress. Take steady steps toward your goals with determination.",
    'Shubha': "Shubha brings auspiciousness. It’s a favorable time for new endeavors and positive actions.",
    'Shukla': "Shukla enhances clarity. Use this time to make thoughtful decisions and express gratitude.",
    'Brahma': "Brahma Yoga supports wisdom and creativity. Engage in intellectual or artistic pursuits.",
    'Indra': "Indra brings authority. Step into a leadership role and pursue your goals boldly.",
    'Vaidhriti': "Vaidhriti suggests patience. Avoid impulsive actions and remain calm."
}

