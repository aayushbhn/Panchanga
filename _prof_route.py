import cProfile, pstats, io, api
c = api.app.test_client()
api.get_mantra_data()
body = {"latitude":27.7172,"longitude":85.3240,"month":11,"year":2031}
c.post("/monthly-panchanga", json=body)  # warm
pr=cProfile.Profile(); pr.enable()
c.post("/monthly-panchanga", json=body)
pr.disable()
s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats('tottime').print_stats(22)
print(s.getvalue())
