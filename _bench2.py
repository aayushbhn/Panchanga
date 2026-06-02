import time, api
from datetime import datetime, timedelta
LAT, LON = 27.7172, 85.3240
TZ = api.cached_timezone_str(api.round_coord(LAT), api.round_coord(LON))
api.get_mantra_data()  # pre-warm network cache (as a startup warm would)

# distinct dates => no sidereal-cache reuse across calls (realistic worst case)
base = datetime(2030,1,1)
dates = [base + timedelta(days=i*7) for i in range(20)]
for d in dates[:2]:
    api.calculate_panchanga_for_date(LAT, LON, d, TZ)  # warm lru per-date
t=time.perf_counter()
for d in dates:
    api.calculate_panchanga_for_date(LAT, LON, d, TZ)
print(f"single any-date, DISTINCT dates, mantra pre-warmed: {(time.perf_counter()-t)/len(dates)*1000:.1f} ms/call")
