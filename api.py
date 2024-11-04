from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import pytz
from skyfield.api import load, Topos
from skyfield.almanac import find_discrete, sunrise_sunset, find_risings, find_settings, moon_phases
from skyfield.framelib import ecliptic_frame
from timezonefinder import TimezoneFinder

app = Flask(__name__)

# ---------------------------- Panchanga Utility Functions ---------------------------------
AYANAMSA = 24.2027778  # Lahiri Ayanamsa for 2024

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


festival_mapping = {
    'Makar Sankranti': {
        'fixed_date': 'January 14'  # Based on the solar calendar
    },
    'Pongal': {
        'fixed_date': 'January 15',  # Primarily celebrated in Tamil Nadu
    },
    'Vasant Panchami': {
        'tithi': 'पञ्चमी',
        'month': 'Magha',
        'paksha': 'Shukla Paksha'
    },
    'Ratha Saptami': {
        'tithi': 'सप्तमी',
        'month': 'Magha',
        'paksha': 'Shukla Paksha'
    },
    'Maha Shivaratri': {
        'tithi': 'चतुर्दशी',
        'month': 'Phalguna',
        'paksha': 'Krishna Paksha'
    },
    'Holi': {
        'tithi': 'पूर्णिमा',
        'month': 'Phalguna',
        'paksha': 'Shukla Paksha'
    },
    'Chaitra Navratri Begins': {
        'tithi': 'प्रतिपदा',
        'month': 'Chaitra',
        'paksha': 'Shukla Paksha'
    },
    'Gudi Padwa': {
        'tithi': 'प्रतिपदा',
        'month': 'Chaitra',
        'paksha': 'Shukla Paksha',
        'region': 'Maharashtra'
    },
    'Ugadi': {
        'tithi': 'प्रतिपदा',
        'month': 'Chaitra',
        'paksha': 'Shukla Paksha',
        'region': 'Andhra Pradesh, Karnataka'
    },
    'Ram Navami': {
        'tithi': 'नवमी',
        'month': 'Chaitra',
        'paksha': 'Shukla Paksha'
    },
    'Hanuman Jayanti': {
        'tithi': 'पूर्णिमा',
        'month': 'Chaitra',
        'paksha': 'Shukla Paksha'
    },
    'Akshaya Tritiya': {
        'tithi': 'तृतीया',
        'month': 'Vaishakha',
        'paksha': 'Shukla Paksha'
    },
    'Narasimha Jayanti': {
        'tithi': 'चतुर्दशी',
        'month': 'Vaishakha',
        'paksha': 'Shukla Paksha'
    },
    'Vat Savitri Vrat': {
        'tithi': 'अमावस्या',
        'month': 'Jyeshtha',
        'paksha': 'Krishna Paksha'
    },
    'Ganga Dussehra': {
        'tithi': 'दशमी',
        'month': 'Jyeshtha',
        'paksha': 'Shukla Paksha'
    },
    'Guru Purnima': {
        'tithi': 'पूर्णिमा',
        'month': 'Ashadha',
        'paksha': 'Shukla Paksha'
    },
    'Nag Panchami': {
        'tithi': 'पञ्चमी',
        'month': 'Shravana',
        'paksha': 'Shukla Paksha'
    },
    'Raksha Bandhan': {
        'tithi': 'पूर्णिमा',
        'month': 'Shravana',
        'paksha': 'Shukla Paksha'
    },
    'Krishna Janmashtami': {
        'tithi': 'अष्टमी',
        'month': 'Bhadrapada',
        'paksha': 'Krishna Paksha'
    },
    'Ganesh Chaturthi': {
        'tithi': 'चतुर्थी',
        'month': 'Bhadrapada',
        'paksha': 'Shukla Paksha'
    },
    'Radha Ashtami': {
        'tithi': 'अष्टमी',
        'month': 'Bhadrapada',
        'paksha': 'Shukla Paksha'
    },
    'Hartalika Teej': {
        'tithi': 'तृतीया',
        'month': 'Bhadrapada',
        'paksha': 'Shukla Paksha'
    },
    'Sharad Purnima (Kojagrat Brata)': {
        'tithi': 'पूर्णिमा',
        'month': 'Ashwin',
        'paksha': 'Shukla Paksha'
    },
    'Navratri Begins': {
        'tithi': 'प्रतिपदा',
        'month': 'Ashwin',
        'paksha': 'Shukla Paksha'
    },
    'Durga Ashtami': {
        'tithi': 'अष्टमी',
        'month': 'Ashwin',
        'paksha': 'Shukla Paksha'
    },
    'Dussehra (Vijayadashami)': {
        'tithi': 'दशमी',
        'month': 'Ashwin',
        'paksha': 'Shukla Paksha'
    },
    'Karva Chauth': {
        'tithi': 'चतुर्थी',
        'month': 'Kartik',
        'paksha': 'Krishna Paksha'
    },
    'Dhanteras': {
        'tithi': 'त्रयोदशी',
        'month': 'Kartik',
        'paksha': 'Krishna Paksha'
    },
    'Naraka Chaturdashi': {
        'tithi': 'चतुर्दशी',
        'month': 'Kartik',
        'paksha': 'Krishna Paksha'
    },
    'Diwali': {
        'tithi': 'अमावस्या',
        'month': 'Kartik',
        'paksha': 'Krishna Paksha'
    },
    'Bhai Dooj': {
        'tithi': 'द्वितीया',
        'month': 'Kartik',
        'paksha': 'Shukla Paksha'
    },
    'Mahalaya Amavasya': {
        'tithi': 'अमावस्या',
        'month': 'Ashwin',
        'paksha': 'Krishna Paksha'
    },
    'Kartika Purnima': {
        'tithi': 'पूर्णिमा',
        'month': 'Kartik',
        'paksha': 'Shukla Paksha'
    },
    'Tulsi Vivah': {
        'tithi': 'एकादशी',
        'month': 'Kartik',
        'paksha': 'Shukla Paksha'
    },
    
    
}


vrata_mapping = {
    # Tithi-based Vratas (Observed on specific lunar days)
    'Ekadashi': {
        'tithi': 'एकादशी',
        'paksha': 'Both',
        'deity': 'Lord Vishnu',
        'significance': 'Fasting for spiritual growth, Lord Vishnu worship',
    },
    'Pradosh Vrat': {
        'tithi': 'त्रयोदशी',
        'paksha': 'Both',
        'deity': 'Lord Shiva',
        'significance': 'Fasting for happiness, prosperity, and well-being',
    },
    'Sankashti Chaturthi': {
        'tithi': 'चतुर्थी',
        'paksha': 'Krishna Paksha',
        'deity': 'Lord Ganesha',
        'significance': 'Fasting for removing obstacles and gaining wisdom',
    },
    'Vinayaka Chaturthi': {
        'tithi': 'चतुर्थी',
        'paksha': 'Shukla Paksha',
        'deity': 'Lord Ganesha',
        'significance': 'Fasting for wisdom, prosperity, and success',
    },
    'Purnima Vrat': {
        'tithi': 'पूर्णिमा',
        'paksha': 'Shukla Paksha',
        'deity': 'Lord Vishnu, Goddess Lakshmi',
        'significance': 'Fasting for wealth, health, and prosperity',
    },
    'Amavasya Vrat': { 
        'tithi': 'अमावस्या',
        'paksha': 'Krishna Paksha',
        'deity': 'Pitru Devatas (Ancestors)',
        'significance': 'Fasting for the peace of ancestors\' souls',
    },
    'Masik Shivaratri': {
        'tithi': 'चतुर्दशी',
        'paksha': 'Krishna Paksha',
        'deity': 'Lord Shiva',
        'significance': 'Fasting for the blessings of Lord Shiva',
    },
    'Kalashtami': {
        'tithi': 'अष्टमी',
        'paksha': 'Krishna Paksha',
        'deity': 'Lord Bhairava',
        'significance': 'Fasting for protection and the blessings of Lord Bhairava',
    },
    'Ahoi Ashtami': {
        'tithi': 'अष्टमी',
        'month': 'Kartik',
        'paksha': 'Krishna Paksha',
        'deity': 'Goddess Ahoi',
        'significance': 'Fasting for the well-being of sons',
    },
    'Karva Chauth': {
        'tithi': 'चतुर्थी',
        'month': 'Kartik',
        'paksha': 'Krishna Paksha',
        'deity': 'Lord Shiva, Parvati',
        'significance': 'Fasting for the long life and well-being of husbands',
    },
    'Nirjala Ekadashi': {
        'tithi': 'एकादशी',
        'month': 'Jyeshtha',
        'paksha': 'Shukla Paksha',
        'deity': 'Lord Vishnu',
        'significance': 'Fasting without water for purification and blessings',
    },
    'Vaikunta Ekadashi': {
        'tithi': 'एकादशी',
        'month': 'Margashirsha',
        'paksha': 'Shukla Paksha',
        'deity': 'Lord Vishnu',
        'significance': 'Fasting to attain Vaikunta (abode of Vishnu)',
    },
    'Devshayani Ekadashi': {
        'tithi': 'एकादशी',
        'month': 'Ashadha',
        'paksha': 'Shukla Paksha',
        'deity': 'Lord Vishnu',
        'significance': 'Marks the beginning of Lord Vishnu\'s slumber (Chaturmas)',
    },
    'Rishi Panchami': {
        'tithi': 'पञ्चमी',
        'month': 'Bhadrapada',
        'paksha': 'Shukla Paksha',
        'deity': 'Saptarishi (Seven Sages)',
        'significance': 'Fasting for purification from sins and menstrual impurity',
    },
    'Savitri Vrat': {
        'tithi': 'अमावस्या',
        'month': 'Jyeshtha',
        'paksha': 'Krishna Paksha',
        'deity': 'Goddess Savitri',
        'significance': 'Fasting for the long life and well-being of the husband',
    },

    # Day-based Vratas (Observed on specific days of the week)
    'Somvar Vrat': {
        'day_of_week': 'Monday',
        'deity': 'Lord Shiva',
        'significance': 'For marital happiness, spiritual growth, and fulfillment of desires',
    },
    'Shani Vrat': {
        'day_of_week': 'Saturday',
        'deity': 'Lord Shani (Saturn)',
        'significance': 'For relief from obstacles and the negative effects of Shani',
    },
    'Mangala Gauri Vrat': {
        'day_of_week': 'Tuesday',
        'month': 'Shravana',
        'paksha': 'Shukla Paksha',
        'deity': 'Goddess Parvati',
        'significance': 'For the happiness and prosperity of the family',
    },
    'Guruvar Vrat': {
        'day_of_week': 'Thursday',
        'deity': 'Brihaspati (Jupiter)',
        'significance': 'For prosperity, education, and spiritual progress',
    },
    'Vaibhav Lakshmi Vrat': {
        'day_of_week': 'Friday',
        'deity': 'Goddess Lakshmi',
        'significance': 'For wealth, prosperity, and success in life',
    },
    'Rohini Vrat': {
        'nakshatra': 'Rohini',
        'month': 'Every Month',
        'paksha': 'All',
        'deity': 'Lord Krishna',
        'significance': 'Fasting for the prosperity and well-being of the family',
    },

    # Solar and Seasonal Festivals (Fixed Dates)
    'Makar Sankranti': {
        'fixed_date': 'January 14',
        'significance': 'Sun enters Capricorn, marks the harvest season',
    },
    'Pongal': {
        'fixed_date': 'January 15',
        'region': 'Tamil Nadu',
        'significance': 'Harvest festival celebrated in South India',
    },
}

rashi_names = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 'Libra', 
                       'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']


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




def tropical_to_sidereal(tropical_position):
    return (tropical_position - AYANAMSA) % 360

def calculate_tithi_and_paksha(moon_sidereal, sun_sidereal):
    sun_moon_angle = (moon_sidereal - sun_sidereal) % 360
    tithi_number = int(sun_moon_angle // 12) + 1
    paksha = 'Krishna Paksha' if tithi_number > 15 else 'Shukla Paksha'
    tithi_name = tithi_names[tithi_number - 1]
    return tithi_number, paksha, tithi_name

def calculate_nakshatra(moon_sidereal):
    nakshatra_index = int(moon_sidereal // 13.3333)
    return nakshatras[nakshatra_index % 27]

def calculate_yoga(sun_sidereal, moon_sidereal):
    yoga_value = (sun_sidereal + moon_sidereal) % 360
    yoga_number = int(yoga_value // 13.3333)
    return yoga_names[yoga_number % 27]

def calculate_karana(sun_moon_angle):
    tithi_number = int(sun_moon_angle // 12) + 1
    tithi_half = (sun_moon_angle % 12) // 6
    paksha = 'Shukla' if tithi_number <= 15 else 'Krishna'
    first_karana, second_karana = karana_table[paksha][(tithi_number - 1) % 15]
    return first_karana if tithi_half == 0 else second_karana

def get_sunrise_sunset(ts, eph, location, tz, now):
    f = sunrise_sunset(eph, location)
    t0 = ts.utc(now.year, now.month, now.day, 0, 0, 0)
    t1 = ts.utc(now.year, now.month, now.day, 23, 59, 59)
    times, events = find_discrete(t0, t1, f)
    sunrise_time, sunset_time = None, None
    for t, event in zip(times, events):
        local_time = t.utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz)
        if event == 1:
            sunrise_time = local_time
        elif event == 0:
            sunset_time = local_time
    return sunrise_time, sunset_time

def get_moonrise_moonset(observer, moon, ts, tz, date):
    t0 = ts.utc(date.year, date.month, date.day, 0, 0, 0)
    t1 = ts.utc(date.year, date.month, date.day, 23, 59, 59)
    moonrise_times, moonrise_events = find_risings(observer, moon, t0, t1)
    moonset_times, moonset_events = find_settings(observer, moon, t0, t1)
    moonrise_time = moonrise_times[0].utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz) if moonrise_times else None
    moonset_time = moonset_times[0].utc_datetime().replace(tzinfo=pytz.utc).astimezone(tz) if moonset_times else None
    return moonrise_time, moonset_time

def calculate_amanta_purnimanta_month(tithi_number, paksha, days_since_new_moon, days_since_full_moon):
    amanta_month_index = (days_since_new_moon // 30) % 12

    amanta_month = months[(amanta_month_index + 1) % 12] if paksha == 'Krishna Paksha' and tithi_number > 15 else months[amanta_month_index]

    purnimanta_month_index = (days_since_full_moon // 30) % 12

    purnimanta_month = months[(purnimanta_month_index + 1) % 12] if paksha == 'Shukla Paksha' and tithi_number <= 15 else months[purnimanta_month_index]
    
    return amanta_month, purnimanta_month

def calculate_rahu_kaal(sunrise, sunset, day_of_week):
    day_duration = (sunset - sunrise).total_seconds()
    part_duration = day_duration / 8
    rahu_period_index = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2,6: 7}
    rahu_index = rahu_period_index[day_of_week]
    rahu_start = sunrise + timedelta(seconds=part_duration * rahu_index)
    rahu_end = rahu_start + timedelta(seconds=part_duration)
    return rahu_start, rahu_end


def calculate_gulika_kaal(sunrise, sunset, day_of_week):
    day_duration = (sunset - sunrise).total_seconds()
    part_duration = day_duration / 8
    gulika_period_index = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0, 6: 6}
    gulika_index = gulika_period_index[day_of_week]
    gulika_start = sunrise + timedelta(seconds=part_duration * gulika_index)
    gulika_end = gulika_start + timedelta(seconds=part_duration)
    return gulika_start, gulika_end

def calculate_yamaganda_kaal(sunrise, sunset, day_of_week):
    day_duration = (sunset - sunrise).total_seconds()
    part_duration = day_duration / 8
    yamaganda_period_index = {0: 3, 1: 2, 2: 1, 3: 0, 4: 6, 5: 5, 6: 4}
    yamaganda_index = yamaganda_period_index[day_of_week]
    yamaganda_start = sunrise + timedelta(seconds=part_duration * yamaganda_index)
    yamaganda_end = yamaganda_start + timedelta(seconds=part_duration)
    return yamaganda_start, yamaganda_end

def calculate_abhijit_muhurat(sunrise, sunset):
    day_duration = (sunset - sunrise).total_seconds()
    muhurta_duration = day_duration / 15
    abhijit_start = sunrise + timedelta(seconds=6 * muhurta_duration)
    abhijit_end = sunrise + timedelta(seconds=8 * muhurta_duration)
    return abhijit_start, abhijit_end

def find_last_moon_phase(ts, eph, moon_phase_type='new'):
    moon_phase_map = {'new': 0, 'full': 2}
    t_now = ts.now()
    t0 = ts.utc(t_now.utc_datetime().year - 1, 1, 1)
    t1 = ts.utc(t_now.utc_datetime().year + 1, 1, 1)
    phase_times, phases = find_discrete(t0, t1, moon_phases(eph))
    for i in reversed(range(len(phases))):
        if phases[i] == moon_phase_map[moon_phase_type] and phase_times[i] < t_now:
            return phase_times[i].utc_datetime()
    return None

def calculate_ritu(sun_sidereal_longitude):
    ritu_index = int(sun_sidereal_longitude // 60)
    return ritu_names[ritu_index % 6]

def calculate_brahma_muhurat(sunrise):
    """
    Calculate the Brahma Muhurat based on the sunrise time.
    Brahma Muhurat starts 1 hour and 36 minutes (96 minutes) before sunrise and lasts for 48 minutes.
    
    :param sunrise: The local sunrise time as a datetime object.
    :return: Start and end time of Brahma Muhurat.
    """
    # Brahma Muhurat starts 96 minutes before sunrise
    brahma_muhurat_start = sunrise - timedelta(minutes=96)
    
    # Brahma Muhurat lasts for 48 minutes
    brahma_muhurat_end = brahma_muhurat_start + timedelta(minutes=48)
    
    return brahma_muhurat_start, brahma_muhurat_end


def get_festival_for_day(tithi_name, paksha, lunar_month):
    """
    Given the Tithi, Paksha, and Lunar Month, return the festival for that day if it exists.
    
    :param tithi_name: Name of the current Tithi (e.g., 'पूर्णिमा')
    :param paksha: Current Paksha (e.g., 'Shukla Paksha')
    :param lunar_month: Current lunar month (e.g., 'Ashwin')
    :return: Name of the festival if one is found, otherwise None.
    """
    # Check for a festival based on the tithi, paksha, and month
    for festival, details in festival_mapping.items():
        if 'fixed_date' in details:
            continue  # Skip solar date festivals (e.g., Makar Sankranti)
        if (details['tithi'] == tithi_name and details['paksha'] == paksha and details['month'] == lunar_month):
            return festival
    return None

def check_fixed_festivals(current_date):
    """
    Check if the current date matches any fixed-date festivals like Makar Sankranti.
    
    :param current_date: Today's date as a datetime object
    :return: Festival name if found, otherwise None.
    """
    for festival, details in festival_mapping.items():
        if 'fixed_date' in details:
            festival_date = datetime.strptime(details['fixed_date'], '%B %d')
            if current_date.month == festival_date.month and current_date.day == festival_date.day:
                return festival
    return None

def get_vrata_for_day(tithi_name, paksha, day_of_week):
    """
    Given the Tithi, Paksha, and Day of Week, return the Vrata for that day if it exists.
    
    :param tithi_name: Name of the current Tithi (e.g., 'एकादशी')
    :param paksha: Current Paksha (e.g., 'Shukla Paksha')
    :param day_of_week: Day of the week (e.g., 'Monday')
    :return: Name of the Vrata if one is found, otherwise None.
    """
    # Check for tithi-based Vratas
    for vrata, details in vrata_mapping.items():
        if 'tithi' in details:
            # Match the tithi and paksha for tithi-based Vratas like Ekadashi, Pradosh, etc.
            if details['tithi'] == tithi_name and (details['paksha'] == paksha or details['paksha'] == 'Both'):
                return vrata

        # Check for day-based Vratas like Somvar Vrat, Shani Vrat, etc.
        if 'day_of_week' in details and details['day_of_week'] == day_of_week:
            return vrata

    return None


def generate_significance(tithi_name, nakshatra_name, moon_sign, yoga_name):
    """
    Generate a significance message based on the astrological elements of the day.
    """
   

    significance = []

    # Add messages based on Paksha in the Tithi
    if "Shukla" in tithi_name:
        significance.append(messages.get('Shukla Paksha', ""))
    elif "Krishna" in tithi_name:
        significance.append(messages.get('Krishna Paksha', ""))

    # Append messages based on Nakshatra
    if nakshatra_name in messages:
        significance.append(messages.get(nakshatra_name, ""))

    # Append messages based on Moon Sign
    if moon_sign in messages:
        significance.append(messages.get(moon_sign, ""))

    # Append messages based on Yoga
    if yoga_name in messages:
        significance.append(messages.get(yoga_name, ""))

    # Join all messages into a single guidance text with a single space between words
    significance_text = " ".join(" ".join(significance).split())
    
    # Default message if no specific messages found
    return significance_text if significance_text else "Today is a good day for reflection and alignment with your intentions."





@app.route('/astrology', methods=['POST'])
def astrology_api_view():
    try:
        # Parse JSON data from the request body
        data = request.get_json()

        # Extract latitude, longitude, and timezone from the request
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))

        # Validate latitude and longitude
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({'error': 'Invalid latitude or longitude.'}), 400

        # Use TimezoneFinder to get the timezone from latitude and longitude
        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lng=longitude, lat=latitude)

        # Handle cases where timezone might not be found
        if timezone_str is None:
            return jsonify({'error': 'Timezone could not be determined from the provided coordinates.'}), 400

        # Load ephemeris data
        ts = load.timescale()
        eph = load('de421.bsp')
        location = Topos(latitude_degrees=latitude, longitude_degrees=longitude)
        sun, moon = eph['sun'], eph['moon']

        # Get current time in the provided timezone
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        t = ts.from_datetime(now)
        observer = eph['earth'] + location

        # Calculate positions
        sun_position = observer.at(t).observe(sun).apparent().frame_latlon(ecliptic_frame)[1].degrees
        moon_position = observer.at(t).observe(moon).apparent().frame_latlon(ecliptic_frame)[1].degrees

        # Convert to sidereal
        sun_sidereal = tropical_to_sidereal(sun_position)
        moon_sidereal = tropical_to_sidereal(moon_position)

        # Calculate astrological elements
        tithi_number, paksha, tithi_name = calculate_tithi_and_paksha(moon_sidereal, sun_sidereal)
        nakshatra_name = calculate_nakshatra(moon_sidereal)
        yoga_name = calculate_yoga(sun_sidereal, moon_sidereal)
        karana_name = calculate_karana((moon_sidereal - sun_sidereal) % 360)

        # Get sunrise and sunset times
        sunrise, sunset = get_sunrise_sunset(ts, eph, location, tz, now)

        # Calculate Rahu Kaal, Gulika Kalam, Yamaganda Kalam, and Abhijit Muhurat
        rahu_start, rahu_end = calculate_rahu_kaal(sunrise, sunset, now.weekday())
        gulika_start, gulika_end = calculate_gulika_kaal(sunrise, sunset, now.weekday())
        yamaganda_start, yamaganda_end = calculate_yamaganda_kaal(sunrise, sunset, now.weekday())
        abhijit_start, abhijit_end = calculate_abhijit_muhurat(sunrise, sunset)

        # Get moonrise and moonset times
        moonrise, moonset = get_moonrise_moonset(observer, moon, ts, tz, now)

        # Calculate Ritu (season) based on the Sun's sidereal position
        ritu = calculate_ritu(sun_sidereal)

        # Moon Sign (Rashi) calculation based on sidereal moon position
       
        moon_sign_index = int(moon_sidereal // 30)  # Each Rashi spans 30°
        moon_sign = rashi_names[moon_sign_index % 12]

        # Shaka Samvat and Vikram Samvat years
        current_year = datetime.now().year
        shaka_samvat = current_year - 78
        vikram_samvat = current_year + 57

        # Find the most recent New Moon (for Amanta) and Full Moon (for Purnimanta)
        last_new_moon = find_last_moon_phase(ts, eph, moon_phase_type='new')
        last_full_moon = find_last_moon_phase(ts, eph, moon_phase_type='full')

        # Calculate days since the last New Moon and Full Moon
        days_since_new_moon = (now - last_new_moon).days if last_new_moon else 0
        days_since_full_moon = (now - last_full_moon).days if last_full_moon else 0

        # Use the days since the moon phases for the month calculation
        moon_phase_day = days_since_new_moon

        # Calculate the Amanta and Purnimanta months
        amanta_month, purnimanta_month = calculate_amanta_purnimanta_month(tithi_number, paksha, days_since_new_moon, days_since_full_moon)

        # Day duration
        day_duration = (sunset - sunrise).seconds / 3600  # Duration in hours

        # Calculate Brahma Muhurat using the sunrise time
        brahma_muhurat_start, brahma_muhurat_end = calculate_brahma_muhurat(sunrise)

        # Check for fixed-date festivals (e.g., Makar Sankranti)
        today_date = datetime.now()
        fixed_festival_today = check_fixed_festivals(today_date)

        # Calculate the lunar month and check for lunar-based festivals
        lunar_month, _ = calculate_amanta_purnimanta_month(tithi_number, paksha, days_since_new_moon, days_since_full_moon)

        # Get the festival for the day based on lunar calculations
        festival_today = get_festival_for_day(tithi_name, paksha, lunar_month)

        # Final festival result (if a fixed festival is found, it takes precedence)
        if fixed_festival_today:
            festival_today = fixed_festival_today

            # Call get_vrata_for_day to check for any Vrata today
        vrata_today = get_vrata_for_day(tithi_name, paksha, now.strftime('%A'))

        
        # Subh (auspicious) Muhurats
        subh_muhurat = [
            {'abhijit': [abhijit_start.strftime('%I:%M:%S %p'), abhijit_end.strftime('%I:%M:%S %p')]},
            {'brahma': [brahma_muhurat_start.strftime('%I:%M:%S %p'), brahma_muhurat_end.strftime('%I:%M:%S %p')]}
        ]
        
        # Asubh (inauspicious) Muhurats
        asubh_muhurat = [
            {'rahu': [rahu_start.strftime('%I:%M:%S %p'), rahu_end.strftime('%I:%M:%S %p')]},
            {'gulika': [gulika_start.strftime('%I:%M:%S %p'), gulika_end.strftime('%I:%M:%S %p')]},
            {'yamaganda': [yamaganda_start.strftime('%I:%M:%S %p'), yamaganda_end.strftime('%I:%M:%S %p')]}
        ]

        # Generate daily significance based on astrological elements
        significance_text = generate_significance(tithi_name, nakshatra_name, moon_sign, yoga_name)

        # Prepare response data
        response_data = {
            'tithi': tithi_name,
            'tithi_number': tithi_number,
            'paksha': paksha,
            'nakshatra': nakshatra_name,
            'karana': karana_name,
            'yoga': yoga_name,
            'day_of_week': now.strftime('%A'),
            'date': now.strftime('%Y-%m-%d'),
            'day_duration': f"{day_duration:.2f} hours",
            'moon_sign': moon_sign,
            'ritu': ritu,
            'amanta_month': amanta_month,
            'purnimanta_month': purnimanta_month,
            'vikram_samvat': vikram_samvat,
            'shaka_samvat': shaka_samvat,
            'sun_moon_angle': (moon_sidereal - sun_sidereal) % 360,
            'sun_sidereal': sun_sidereal,
            'sunrise': sunrise.strftime('%I:%M:%S %p'),
            'sunset': sunset.strftime('%I:%M:%S %p'),
            'moonrise': moonrise.strftime('%I:%M:%S %p') if moonrise else 'N/A',
            'moonset': moonset.strftime('%I:%M:%S %p') if moonset else 'N/A',
            'significance': significance_text,
            # 'rahu_start': rahu_start.strftime('%I:%M:%S %p'),
            # 'rahu_end': rahu_end.strftime('%I:%M:%S %p'),
            # 'gulika_start': gulika_start.strftime('%I:%M:%S %p'),
            # 'gulika_end': gulika_end.strftime('%I:%M:%S %p'),
            # 'yamaganda_start': yamaganda_start.strftime('%I:%M:%S %p'),
            # 'yamaganda_end': yamaganda_end.strftime('%I:%M:%S %p'),
            # 'abhijit_start': abhijit_start.strftime('%I:%M:%S %p'),
            #  'abhijit_end': abhijit_end.strftime('%I:%M:%S %p'),
            #  'brahma_start': brahma_muhurat_start.strftime('%I:%M:%S %p'),
            # 'brahma_end': brahma_muhurat_end.strftime('%I:%M:%S %p'),
             'time_zone':timezone_str,
             'festival_today': festival_today if festival_today else 'None',
             'vrata_today': vrata_today if vrata_today else 'None',  # Add the vrata_today field 
             'subh_muhurat': subh_muhurat,
            'asubh_muhurat': asubh_muhurat
        }

        return jsonify(response_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 400

# # Run the Flask app live
# if __name__ == '__main__':
#     app.run(debug=True)

    # Run the Flask app local
if __name__ == '__main__':
    app.run(port=8001 ,debug=True)