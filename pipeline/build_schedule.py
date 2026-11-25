"""How often buses run, from the Delhi bus GTFS timetable, so trip times can include waiting.

For every ticket route matched to a GTFS route (same name, as in build_geometry.py) it writes
data/live_routes.json: GTFS route_id -> our route id, for the live bus feed, and
data/schedule.json:  {route id: {"dep": [departure minutes from the first stop, sorted],
                                 "off": [scheduled minutes from the first stop to each of our stops]}}
The app turns these into "a bus every N minutes" and the average wait at the stop you board.
Run after build_geometry.py:  python pipeline/build_schedule.py path/to/gtfs
"""
import gzip
import json
import pickle
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GTFS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "gtfs"
key = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
mins = lambda t: int(t[:2]) * 60 + int(t[3:5])


def main():
    M = pickle.load(gzip.open(ROOT / "data" / "model.pkl.gz", "rb"))
    order = json.loads((ROOT / "work" / "route_order.json").read_text(encoding="utf-8"))
    routes = pd.read_csv(GTFS / "routes.txt", dtype=str)
    trips = pd.read_csv(GTFS / "trips.txt", dtype=str, usecols=["route_id", "trip_id"])
    st = pd.read_csv(GTFS / "stop_times.txt", dtype={"trip_id": str, "stop_id": str},
                     usecols=["trip_id", "departure_time", "stop_sequence"])
    st = st.sort_values(["trip_id", "stop_sequence"])
    st["m"] = st.departure_time.map(mins)
    first = st.groupby("trip_id").m.first()
    n = st.groupby("trip_id").size()
    trips = trips.merge(routes[["route_id", "route_long_name"]])
    trips["k"] = trips.route_long_name.map(key)
    trips["dep"], trips["n"] = trips.trip_id.map(first), trips.trip_id.map(n)

    # the same representative trip build_geometry.py uses: the longest trip of the route_id with
    # the longest stop list for that name, so GTFS stop positions line up with route_order.json
    rep = trips.sort_values("n").groupby("route_id").tail(1)
    rep = rep.sort_values("n").groupby("k").tail(1).set_index("k")
    times = {t: g.m.to_numpy() - g.m.iloc[0] for t, g in st[st.trip_id.isin(rep.trip_id)].groupby("trip_id")}

    out, covered = {}, 0
    for rid, r in M["routes"].items():
        k = key(rid)
        if k not in rep.index or rid not in order:
            continue
        dep = np.sort(trips.loc[trips.k == k, "dep"].dropna().to_numpy() % 1440)
        tt = times[rep.loc[k, "trip_id"]]
        pos = order[rid]
        off = np.array([tt[pos[s]] if s in pos and pos[s] < len(tt) else np.nan for s in r["stops"]], float)
        if np.isnan(off).all() or len(dep) == 0:
            continue
        x = np.arange(len(off)); ok = ~np.isnan(off)
        off = np.maximum.accumulate(np.interp(x, x[ok], off[ok]))      # unplaced stops: in between
        out[rid] = dict(dep=[int(v) for v in dep], off=[int(round(v)) for v in off])
        covered += r["tickets"]
    # the live GTFS-RT feed names routes by GTFS route_id: map those ids to our route ids
    live = {str(gid): rid for gid, name in zip(routes.route_id, routes.route_long_name)
            for rid in [next((r for r in M["routes"] if key(r) == key(name)), None)] if rid}
    (ROOT / "data" / "live_routes.json").write_text(json.dumps(live, separators=(",", ":")))
    total = sum(r["tickets"] for r in M["routes"].values())
    (ROOT / "data" / "schedule.json").write_text(json.dumps(out, separators=(",", ":")))
    print(json.dumps(dict(routes=len(out), tickets_on_scheduled_routes=round(covered / total, 4),
                          departures=sum(len(v["dep"]) for v in out.values()))))


if __name__ == "__main__":
    main()
