import json, api
c = api.app.test_client()
api.get_mantra_data()
out = {}
reqs = [
  ("/panchanga-date", {"latitude":28.61,"longitude":77.20,"day":15,"month":3,"year":2025}),
  ("/panchanga-date", {"latitude":13.08,"longitude":80.27,"day":2,"month":11,"year":2027,
                        "date_of_birth":"1990-05-15","time_of_birth":"14:30","birth_latitude":"27.7",
                        "birth_longitude":"85.3","rashi":"Mesh"}),
  ("/monthly-panchanga", {"latitude":27.7172,"longitude":85.324,"month":11,"year":2031}),
]
for path, body in reqs:
    r = c.post(path, json=body)
    d = r.get_json()
    # /astrology depends on today's date (server time) -> stable within a run; drop volatile kundali status
    out[path+json.dumps(body,sort_keys=True)] = d
print(json.dumps(out, default=str, sort_keys=True))
