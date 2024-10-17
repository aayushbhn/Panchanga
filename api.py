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
    }
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
        rashi_names = ['Mesha', 'Vrishabha', 'Mithuna', 'Karka', 'Simha', 'Kanya', 'Tula', 
                       'Vrischika', 'Dhanu', 'Makara', 'Kumbha', 'Meena']
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
            'rahu_start': rahu_start.strftime('%I:%M:%S %p'),
            'rahu_end': rahu_end.strftime('%I:%M:%S %p'),
            'gulika_start': gulika_start.strftime('%I:%M:%S %p'),
            'gulika_end': gulika_end.strftime('%I:%M:%S %p'),
            'yamaganda_start': yamaganda_start.strftime('%I:%M:%S %p'),
            'yamaganda_end': yamaganda_end.strftime('%I:%M:%S %p'),
            'abhijit_start': abhijit_start.strftime('%I:%M:%S %p'),
             'abhijit_end': abhijit_end.strftime('%I:%M:%S %p'),
             'brahma_start': brahma_muhurat_start.strftime('%I:%M:%S %p'),
            'brahma_end': brahma_muhurat_end.strftime('%I:%M:%S %p'),
             'time_zone':timezone_str,
             'festival_today': festival_today if festival_today else 'None'
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