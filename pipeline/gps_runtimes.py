"""Seat Signal: real stop-to-stop running times from bus GPS.

For each bus trip in the GPS log (one vehicle on one trip_id), find when it reached and left each
stop of its route: the first and last GPS ping within RADIUS metres of the stop, in route order.
Writes one small .npz per slice of the day with a row per (trip, stop) the bus was seen at:
route (index into route_stops.json order), trip, stop index, time arrived, time left (unix s).

Usage: python gps_runtimes.py <day.db> <route_stops.json> <out.npz> <ist_hour_from> <ist_hour_to>
Trips are kept by their first ping, so a trip that starts in [from, to) is read to its end
(up to LOOKAHEAD after `to`) and never counted twice across slices.
"""
import json, sqlite3, sys, time
import numpy as np

DB, STOPS, OUT, H0, H1 = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
RADIUS = 90            # metres: a bus is "at" a stop when a ping is this close
LOOKAHEAD = 3 * 3600   # longest trip we follow past the slice end
LOOKBACK = 3 * 3600    # read this far back too, so a trip already running isn't taken to start at the slice
t_start = time.time()

rs = json.load(open(STOPS))
gids = list(rs.keys())
gindex = {float(g): n for n, g in enumerate(gids)}
coords = [np.array([p if p else [np.nan, np.nan] for p in rs[g][1]], np.float64) for g in gids]

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
first = int(con.execute("select timestamp from vehicle_feed limit 1").fetchone()[0])
mid = first + 3600                                          # the first ping can be a few seconds before midnight
day0 = mid - (mid + 19800) % 86400                          # IST midnight of this file's day
a, b = day0 + int(H0 * 3600), day0 + int(H1 * 3600)
cur = con.execute(
    "select cast(route_id as integer), vehicle_id || '|' || trip_id, cast(timestamp as integer), cast(lat as real), cast(lng as real)"
    " from vehicle_feed where timestamp >= ? and timestamp < ? and route_id is not null and trip_id != ''",
    (str(a - LOOKBACK), str(b + LOOKAHEAD)))
key_code: dict = {}
G, C, TS, LA, LO = [], [], [], [], []
nrows = 0
while True:
    batch = cur.fetchmany(200000)
    if not batch:
        break
    nrows += len(batch)
    g = np.fromiter((gindex.get(float(x[0]), -1) if x[0] is not None else -1 for x in batch), np.int32, len(batch))
    c = np.fromiter((key_code.setdefault(x[1], len(key_code)) for x in batch), np.int32, len(batch))
    ts = np.fromiter((x[2] or 0 for x in batch), np.int64, len(batch))
    la = np.fromiter((x[3] or 0.0 for x in batch), np.float32, len(batch))
    lo = np.fromiter((x[4] or 0.0 for x in batch), np.float32, len(batch))
    m = (g >= 0) & (la > 28.2) & (la < 29.1) & (lo > 76.7) & (lo < 77.8)
    G.append(g[m]); C.append(c[m]); TS.append(ts[m]); LA.append(la[m]); LO.append(lo[m])
con.close()
G, C, TS, LA, LO = (np.concatenate(x) if x else np.zeros(0) for x in (G, C, TS, LA, LO))
t_read = time.time() - t_start
o = np.lexsort((TS, C))
G, C, TS, LA, LO = G[o], C[o], TS[o], LA[o], LO[o]
cuts = np.flatnonzero(np.diff(C)) + 1
starts, ends = np.r_[0, cuts], np.r_[cuts, len(C)]

R_, T_, K_, A_, D_ = [], [], [], [], []
kept = 0
for n, (s0, e0) in enumerate(zip(starts, ends)):
    if e0 - s0 < 5 or not (a <= TS[s0] < b):
        continue
    g = int(G[s0])
    kept += 1
    tsv, lav, lov = TS[s0:e0], LA[s0:e0].astype(np.float64), LO[s0:e0].astype(np.float64)
    S = coords[g]
    dy = (lav[:, None] - S[None, :, 0]) * 111000.0
    dx = (lov[:, None] - S[None, :, 1]) * 97600.0
    near = (dx * dx + dy * dy) < RADIUS * RADIUS                # pings x stops
    i = 0                                                       # walk the stops in order, never backwards in time
    npn = len(tsv)
    for k in range(S.shape[0]):
        col = near[i:, k]
        if not col.any():
            continue
        s = i + int(col.argmax())
        e = s
        while e + 1 < npn and near[e + 1, k]:
            e += 1
        R_.append(g); T_.append(n); K_.append(k); A_.append(int(tsv[s])); D_.append(int(tsv[e]))
        i = s
np.savez_compressed(OUT, route=np.array(R_, np.int16), trip=np.array(T_, np.int32), stop=np.array(K_, np.int16),
                    arr=np.array(A_, np.int64), dep=np.array(D_, np.int64))
print(f"{OUT}: {nrows} rows, {kept} trips, {len(K_)} stop visits; read {t_read:.0f}s, total {time.time() - t_start:.0f}s", flush=True)
