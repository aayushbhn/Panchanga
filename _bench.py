import cProfile, pstats, io, time, sys
import api
from datetime import datetime

LAT, LON = 27.7172, 85.3240  # Kathmandu
TZ = api.cached_timezone_str(api.round_coord(LAT), api.round_coord(LON))
print("tz:", TZ)

def warm():
    # mimic a cold-ish process but reusable TS/EPH already loaded
    pass

def single_any_date():
    return api.calculate_panchanga_for_date(LAT, LON, datetime(2026, 6, 15), TZ)

def monthly():
    lat_r, lon_r = api.round_coord(LAT), api.round_coord(LON)
    year, month = 2026, 6
    api.cached_moon_phases_for_month(year, month, TZ)
    py, pm = api._prev_month(year, month)
    api.cached_moon_phases_for_month(py, pm, TZ)
    first = datetime(year, month, 1)
    nxt = datetime(year, month+1, 1)
    num = (nxt-first).days
    for d in range(1, num+1):
        ds = datetime(year, month, d).strftime("%Y-%m-%d")
        api.cached_sunrise_sunset(lat_r, lon_r, ds, TZ)
        api.cached_moonrise_moonset(lat_r, lon_r, ds, TZ)
    bet = api.compute_month_anga_end_times_batch(year, month, TZ)
    out = []
    for d in range(1, num+1):
        td = datetime(year, month, d)
        out.append(api.calculate_panchanga_for_date(LAT, LON, td, TZ, precomputed_end_times=bet.get(td.strftime("%Y-%m-%d"))))
    return out

def timeit(fn, n, label):
    fn()  # warm caches
    t=time.perf_counter()
    for _ in range(n):
        fn()
    dt=(time.perf_counter()-t)/n
    print(f"{label}: {dt*1000:.1f} ms/call (n={n}, warm caches)")
    return dt

_CACHED = ["cached_timezone_str","cached_location","cached_observer","cached_sunrise_sunset",
           "cached_moonrise_moonset","cached_moon_phases_for_month","compute_month_anga_end_times_batch",
           "_fetch_mantra_data_cached"]
def _clear():
    for name in _CACHED:
        obj=getattr(api,name,None)
        if obj is not None and hasattr(obj,'cache_clear'):
            obj.cache_clear()

def cold_timeit(fn, label):
    _clear()
    t=time.perf_counter()
    fn()
    dt=time.perf_counter()-t
    print(f"{label} (COLD): {dt*1000:.1f} ms")
    return dt

mode = sys.argv[1] if len(sys.argv)>1 else "time"

if mode=="time":
    cold_timeit(single_any_date, "single any-date")
    timeit(single_any_date, 5, "single any-date")
    cold_timeit(monthly, "monthly(30d)")
    timeit(monthly, 2, "monthly(30d)")
elif mode=="prof_single":
    _clear()
    pr=cProfile.Profile(); pr.enable()
    single_any_date()
    pr.disable()
    s=io.StringIO(); ps=pstats.Stats(pr,stream=s).sort_stats('cumulative'); ps.print_stats(35)
    print(s.getvalue())
elif mode=="prof_monthly":
    _clear()
    pr=cProfile.Profile(); pr.enable()
    monthly()
    pr.disable()
    s=io.StringIO(); ps=pstats.Stats(pr,stream=s).sort_stats('tottime'); ps.print_stats(35)
    print(s.getvalue())
