import time, json, api
c = api.app.test_client()
api.get_mantra_data()  # ensure warm (prewarm thread may still be running)
base = {"latitude":27.7172,"longitude":85.3240}

def post(path, body, n, label, warm=1):
    for _ in range(warm):
        c.post(path, json=body)
    t=time.perf_counter()
    for _ in range(n):
        r=c.post(path, json=body)
    dt=(time.perf_counter()-t)/n
    assert r.status_code==200, (path, r.status_code, r.get_data()[:200])
    print(f"{label}: {dt*1000:.0f} ms/req  (size={len(r.get_data())//1024}KB)")

# daily (/astrology) - no date => today
post("/astrology", dict(base), 3, "/astrology  (daily)")
# any-date
post("/panchanga-date", dict(base, day=15, month=9, year=2032), 3, "/panchanga-date (new date)")
# monthly (cold-ish: distinct month so caches differ)
post("/monthly-panchanga", dict(base, month=11, year=2031), 1, "/monthly-panchanga (cold month)", warm=0)
post("/monthly-panchanga", dict(base, month=11, year=2031), 2, "/monthly-panchanga (warm)", warm=0)
