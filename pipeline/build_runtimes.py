"""Seat Signal: stop-to-stop running times from real bus trips (October 2026 GPS).

Input: the per-slice files from gps_runtimes.py (when each bus trip arrived at and left each
stop of its route) and route_stops.json (which route each file's route index is).
Output: data/runtimes.npz, for every route stretch k -> k+1, the median minutes it took
(from leaving stop k to reaching stop k+1, plus the stop at k+1) by hour, for weekdays and
Sundays. Gaps where a stop was missed are shared over the stretches by distance.

Usage: python build_runtimes.py <dir with dDD_HH.npz> <route_stops.json> <out.npz> [days...]
"""
import glob, json, math, sys
from collections import defaultdict
import numpy as np

SRC, STOPS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
DAYS = sys.argv[4].split(",") if len(sys.argv) > 4 else ["14", "15", "16", "18"]
SUNDAYS = {"18"}
MIN_N = 3                    # observations needed to trust an hour's median for one stretch

rs = json.load(open(STOPS))
gids = list(rs)


def km(a, b):
    if a is None or b is None:
        return float("nan")
    return math.hypot((a[0] - b[0]) * 111.0, (a[1] - b[1]) * 97.6)


# stretch lengths along the route's road path (GTFS) where known: a misplaced stop then has ~no length,
# so a bus "reaching" it far down the road can't be mistaken for a long stretch. Straight lines otherwise.
_path = json.load(open(STOPS.replace("route_stops.json", "route_segkm.json"))) if len(sys.argv) > 0 else {}
seg_km = [np.array(_path[g]) if g in _path and len(_path[g]) == len(rs[g][1]) - 1 else
          np.array([km(p[k], p[k + 1]) for k in range(len(p) - 1)]) for g, p in ((g, rs[g][1]) for g in gids)]


def observations(days):
    """Yields (route index, daytype, hour, stretch k, minutes) for each stretch a bus covered."""
    obs = defaultdict(list)                     # (g, dt, k) -> list of (hour, minutes)
    for day in days:
        dt = 1 if day in SUNDAYS else 0
        for f in sorted(glob.glob(f"{SRC}/d{day}_*.npz")):
            z = np.load(f)
            g, t, k, a, dep = z["route"], z["trip"], z["stop"], z["arr"], z["dep"]
            o = np.lexsort((k, t, g))
            g, t, k, a, dep = g[o], t[o], k[o], a[o], dep[o]
            same = (g[1:] == g[:-1]) & (t[1:] == t[:-1])
            for n in np.flatnonzero(same & (k[1:] > k[:-1]) & (k[1:] - k[:-1] <= 4)):
                gi, k1, k2 = int(g[n]), int(k[n]), int(k[n + 1])
                span = (a[n + 1] - dep[n]) / 60.0 + min((dep[n + 1] - a[n + 1]) / 60.0, 3.0)
                d = seg_km[gi][k1:k2]
                if np.isnan(d).any() or span <= 0:
                    continue
                dist = d.sum()
                if dist > 0.05 and not (3.0 <= dist / (span / 60) <= 65.0):     # GPS glitch, a long halt, or a misplaced stop
                    continue
                if dist <= 0.05 and span > 2.0:                                  # no road between them, yet minutes passed
                    continue
                hour = int(((dep[n] + 19800) % 86400) // 3600)
                w = d / dist if dist > 0 else np.full(len(d), 1 / len(d))
                for m, kk in enumerate(range(k1, k2)):
                    obs[(gi, dt, kk)].append((hour, span * w[m]))
    return obs


def build(days):
    obs = observations(days)
    out = {}
    for (gi, dt, k), lst in obs.items():
        h = np.array([x[0] for x in lst]); v = np.array([x[1] for x in lst])
        arr = out.setdefault(gi, np.full((2, 24, len(seg_km[gi])), np.nan, np.float32))
        allday = float(np.median(v))
        for hr in range(24):
            sel = v[np.abs(((h - hr + 12) % 24) - 12) <= 0]
            if len(sel) < MIN_N:
                sel = v[np.abs(((h - hr + 12) % 24) - 12) <= 1]           # borrow the neighbouring hours
            arr[dt, hr, k] = float(np.median(sel)) if len(sel) >= MIN_N else np.nan
        arr[dt, :, k] = np.where(np.isnan(arr[dt, :, k]), -allday, arr[dt, :, k])  # negative = all-day value, no hourly detail
    return out


if __name__ == "__main__":
    model = build(DAYS)
    rids = [rs[gids[gi]][0] for gi in model]
    np.savez_compressed(OUT, rids=np.array(rids), **{f"r{n}": model[gi].astype(np.float16) for n, gi in enumerate(model)})
    print(f"{OUT}: {len(model)} routes, days {DAYS}")
