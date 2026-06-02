import cProfile, pstats, io, api
from datetime import datetime
LAT, LON = 27.7172, 85.3240
TZ = api.cached_timezone_str(api.round_coord(LAT), api.round_coord(LON))
api.get_mantra_data()
pr=cProfile.Profile(); pr.enable()
api.calculate_panchanga_for_date(LAT, LON, datetime(2032,9,3), TZ)
pr.disable()
s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats('cumulative').print_stats(28)
print(s.getvalue())
