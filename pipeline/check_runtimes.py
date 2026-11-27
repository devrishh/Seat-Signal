"""Seat Signal: how close are predicted ride times to real bus trips on a day the model never saw?

Takes real trips from one held-out day of GPS (when each bus left stop i and reached stop j),
and compares the old model (grid-cell GPS speeds) and the new one (stop-to-stop running times
learned from the other days) with what actually happened.

Usage: python check_runtimes.py <runtimes dir> <route_stops.json> <model.npz built without the test day> <test day> [n]
"""
import glob, json, sys, random
import numpy as np

sys.path.insert(0, ".")
from backend import app as A

SRC, STOPS, MODEL, DAY = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
N = int(sys.argv[5]) if len(sys.argv) > 5 else 4000
random.seed(7)
rs = json.load(open(STOPS)); gids = list(rs)
from backend.travel import RunTimes
RT = RunTimes(MODEL)

pairs = []
for f in sorted(glob.glob(f"{SRC}/d{DAY}_*.npz")):
    z = np.load(f)
    g, t, k, a, dep = z["route"], z["trip"], z["stop"], z["arr"], z["dep"]
    o = np.lexsort((k, t, g)); g, t, k, a, dep = g[o], t[o], k[o], a[o], dep[o]
    cuts = np.flatnonzero((g[1:] != g[:-1]) | (t[1:] != t[:-1])) + 1
    for s, e in zip(np.r_[0, cuts], np.r_[cuts, len(g)]):
        if e - s < 6:
            continue
        for _ in range(2):
            i1 = random.randrange(s, e - 3); j1 = random.randrange(i1 + 3, min(e, i1 + 30))
            pairs.append((int(g[s]), int(k[i1]), int(k[j1]), int(dep[i1]), (a[j1] - dep[i1]) / 60.0))
random.shuffle(pairs)
pairs = [p for p in pairs if 2 <= p[4] <= 150][:N]

old, new, real, hours = [], [], [], []
for gi, i, j, t0, actual in pairs:
    rid = rs[gids[gi]][0]
    minute = ((t0 + 19800) % 86400) / 60.0
    old.append(A.TRAVEL._grid_ride(rid, A.ROUTES[rid]["stops"], i, j, minute, 0)[0][-1])
    v = RT.minutes(rid, i, j, minute, 0); new.append(np.nan if v is None else v)
    real.append(actual); hours.append(int(minute // 60))
old, new, real = map(np.array, (old, new, real))


def report(name, p):
    ok = ~np.isnan(p)
    e = p[ok] - real[ok]
    print(f"{name:>5}: {ok.sum()} trips | median error {np.median(np.abs(e)):.1f} min | within 5 min {np.mean(np.abs(e) <= 5) * 100:.0f}% "
          f"| within 20% {np.mean(np.abs(e) <= 0.2 * real[ok]) * 100:.0f}% | typical bias {np.median(e):+.1f} min ({np.median(p[ok] / real[ok]):.2f}x)")
    return dict(n=int(ok.sum()), median_abs_min=round(float(np.median(np.abs(e))), 1), within_5_min=round(float(np.mean(np.abs(e) <= 5)), 3),
                within_20pct=round(float(np.mean(np.abs(e) <= 0.2 * real[ok])), 3), bias_min=round(float(np.median(e)), 1),
                ratio=round(float(np.median(p[ok] / real[ok])), 2))


print(f"test day {DAY}: {len(real)} real rides, median {np.median(real):.0f} min")
res = dict(test_day=DAY, rides=len(real), real_median_min=round(float(np.median(real)), 1), old=report("old", old), new=report("new", new))
json.dump(res, open(f"{SRC}/check_{DAY}.json", "w"), indent=1)
