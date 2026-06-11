import json, sys
import api
from datetime import datetime
LAT, LON = 27.7172, 85.3240
TZ = api.cached_timezone_str(api.round_coord(LAT), api.round_coord(LON))
out = {}
for d in [1,5,15,28]:
    r = api.calculate_panchanga_for_date(LAT, LON, datetime(2026,6,d), TZ)
    out[str(d)] = r
# also a couple other months/locations
for (la,lo,y,m,dd) in [(28.61,77.20,2025,3,15),(13.08,80.27,2027,11,2)]:
    tz = api.cached_timezone_str(api.round_coord(la), api.round_coord(lo))
    out[f"{la}-{y}-{m}-{dd}"] = api.calculate_panchanga_for_date(la,lo,datetime(y,m,dd),tz)
print(json.dumps(out, default=str, sort_keys=True))
