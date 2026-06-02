import time, api
c = api.app.test_client()
api.get_mantra_data()  # mantra pre-warmed (matches startup prewarm)
LAT, LON = 19.0760, 72.8777  # Mumbai - fresh location to avoid prior cache

def t1(path, body):
    s=time.perf_counter(); r=c.post(path, json=body); dt=time.perf_counter()-s
    assert r.status_code==200, (path, r.status_code, r.get_data()[:150])
    return dt*1000

# COLD (first time this location/date) then WARM (repeat identical)
dd = {"latitude":LAT,"longitude":LON,"day":7,"month":4,"year":2029}
print(f"any-date  COLD: {t1('/panchanga-date',dd):7.0f} ms | WARM: {t1('/panchanga-date',dd):6.0f} ms")
mm = {"latitude":LAT,"longitude":LON,"month":4,"year":2029}
print(f"monthly   COLD: {t1('/monthly-panchanga',mm):7.0f} ms | WARM: {t1('/monthly-panchanga',mm):6.0f} ms")
# daily (live time) - just one timing
da = {"latitude":LAT,"longitude":LON}
_=t1('/astrology',da)  # cold
print(f"daily     COLD: {t1('/astrology',da):7.0f} ms | WARM: {t1('/astrology',da):6.0f} ms")
