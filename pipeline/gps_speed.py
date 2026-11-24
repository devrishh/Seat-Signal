"""Seat Signal: GPS pings -> effective bus speed per ~1 km grid cell per half hour.

Reads one bus_movements_YYYY_MM_DD.db (read-only) and writes a small .npz of totals:
distance and time travelled between consecutive pings of the same bus, summed per
(grid cell, IST half-hour slot). Speed = distance / time, so stops at bus stops and
signals count (they are part of a real journey), while long layovers do not.

Usage: python gps_speed.py <day.db> <out.npz> [sample_mod]
"""
import sqlite3, sys, time
import numpy as np

DB, OUT = sys.argv[1], sys.argv[2]
MOD = int(sys.argv[3]) if len(sys.argv) > 3 else 1
LAT0, LON0, CELL = 28.20, 76.70, 0.01          # grid origin; 0.01 deg ~ 1.1 km x 1.0 km
NLAT, NLON = 90, 110                            # covers 28.20-29.10 N, 76.70-77.80 E
MIN_DT, MAX_DT = 5, 180                         # seconds between pings we trust
MAX_KMH = 80                                    # faster than this between pings = GPS jump
LAYOVER_S = 600                                 # standing still this long = layover, not a trip

t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
q = "select vehicle_id, timestamp, lat, lng from vehicle_feed"
if MOD > 1:
    q += f" where rowid % {MOD} = 0"
vid_code: dict[str, int] = {}
V, T, LA, LO = [], [], [], []
for v, ts, la, lo in con.execute(q):
    try:
        la = float(la); lo = float(lo); ts = int(ts)
    except (TypeError, ValueError):
        continue
    if not (28.2 < la < 29.1 and 76.7 < lo < 77.8):
        continue
    c = vid_code.get(v)
    if c is None:
        c = vid_code[v] = len(vid_code)
    V.append(c); T.append(ts); LA.append(la); LO.append(lo)
con.close()
V = np.array(V, np.int32); T = np.array(T, np.int64)
LA = np.array(LA, np.float64); LO = np.array(LO, np.float64)
print(f"read {len(V):,} pings, {len(vid_code):,} buses in {time.time() - t0:.0f}s", flush=True)

o = np.lexsort((T, V))
V, T, LA, LO = V[o], T[o], LA[o], LO[o]
keep = np.ones(len(V), bool)
keep[1:] = ~((V[1:] == V[:-1]) & (T[1:] == T[:-1]))   # drop duplicate pings
V, T, LA, LO = V[keep], T[keep], LA[keep], LO[keep]

same = V[1:] == V[:-1]
dt = (T[1:] - T[:-1]).astype(np.float64)
la1, lo1, la2, lo2 = map(np.radians, (LA[:-1], LO[:-1], LA[1:], LO[1:]))
h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
d = 2 * 6371000 * np.arcsin(np.sqrt(h))                 # metres

# layovers: runs of near-zero movement by the same bus lasting LAYOVER_S or more
still = same & (d < 15)
run_id = np.cumsum(np.r_[0, (still[1:] != still[:-1]).astype(np.int64)])
run_time = np.bincount(run_id, weights=np.where(still, dt, 0.0))
layover = still & (run_time[run_id] >= LAYOVER_S)

ok = same & (dt >= MIN_DT) & (dt <= MAX_DT) & ~layover & (d / np.maximum(dt, 1) * 3.6 <= MAX_KMH)
mid_la = (LA[:-1] + LA[1:]) / 2
mid_lo = (LO[:-1] + LO[1:]) / 2
ci = np.floor((mid_la - LAT0) / CELL).astype(np.int64)
cj = np.floor((mid_lo - LON0) / CELL).astype(np.int64)
ist = (T[:-1] + T[1:]) / 2 + 19800
slot = ((ist % 86400) // 1800).astype(np.int64)
ok &= (ci >= 0) & (ci < NLAT) & (cj >= 0) & (cj < NLON)

idx = (ci[ok] * NLON + cj[ok]) * 48 + slot[ok]
n = NLAT * NLON * 48
sum_d = np.bincount(idx, weights=d[ok], minlength=n).reshape(NLAT, NLON, 48)
sum_t = np.bincount(idx, weights=dt[ok], minlength=n).reshape(NLAT, NLON, 48)
cnt = np.bincount(idx, minlength=n).reshape(NLAT, NLON, 48)
np.savez_compressed(OUT, sum_d=sum_d.astype(np.float32), sum_t=sum_t.astype(np.float32),
                    cnt=cnt.astype(np.int32), lat0=LAT0, lon0=LON0, cell=CELL, mod=MOD,
                    pings=len(V), buses=len(vid_code))
net = sum_d.sum(axis=(0, 1)) / np.maximum(sum_t.sum(axis=(0, 1)), 1) * 3.6
print("network km/h by hour:", " ".join(f"{int(i // 2)}:{net[i]:.0f}" for i in range(0, 48, 2)))
print(f"pairs used {ok.sum():,} of {len(ok):,}; layover pairs {layover.sum():,}; done in {time.time() - t0:.0f}s", flush=True)
