"""Seat Signal: true stop order and real distances for every route, from Delhi bus GTFS.

The ticket data has stop names but no coordinates, and the stop order of a route had to
be inferred from which way tickets travel. That inference keeps most tickets moving
forward, but it can put a stop in the wrong place (a Janakpuri stop between ITO and
Mandi House), which breaks travel times and spreads crowding onto the wrong stretch.

This script lines each ticket route up with the same route in the Delhi bus GTFS
(static schedule with stop coordinates) and writes:
  data/route_order.json   route -> {stop: position in the GTFS sequence} for every stop
                          GTFS could place (read by build_model.py, which places the rest)
  data/geometry.pkl.gz    route -> km along the route at each stop, stop coordinates,
                          and the detour factor for routes GTFS does not know

Matching, most reliable first:
  1. Route by name (ticket '740UP' = GTFS route_long_name '740UP'); each of our stops is
     matched to a stop of that GTFS route by name (fuzzy, but only among that route's
     stops) or, failing that, by coordinates found for it on other routes.
  2. Routes with no GTFS twin keep the ticket-inferred order. A ride's distance is the
     straight line between its two end stops times a detour factor fitted on step 1.

Usage: python pipeline/build_geometry.py <gtfs folder> [model] [out folder]
"""
import gzip, json, pickle, re, sys
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent))
from text_norm import norm_stop  # noqa: E402

GTFS = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parents[1]
MODEL = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "model.pkl.gz"
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "data"     # geometry.pkl.gz: served by the app
WORK = ROOT / "work"                                                  # route_order.json: read by build_model.py
NAME_SCORE = 86         # fuzzy name score (0-100) for a stop to match a stop of the same route
NEAR_KM = 0.6           # or: a stop located elsewhere lies this close to a stop of the route
MIN_PLACED = 0.6        # share of a route's stops that must be placed to trust GTFS order
SNAP_KM = 0.3          # a stop must lie within this distance of the route's road path to use it
FILLER = r"\b(t|terminal|metro station|metro|station|stop|bus|depot|opposite|near|crossing|chowk|more|xing|nh8|nh 8)\b"


def squash(k: str) -> str:
    return re.sub(FILLER, "", k).replace(" ", "")


def score(a: str, b: str) -> float:
    qa, qb = squash(a) or a.replace(" ", ""), squash(b) or b.replace(" ", "")
    s = max(fuzz.ratio(qa, qb), fuzz.token_set_ratio(a, b) if min(len(a), len(b)) >= 6 else 0)
    if min(len(qa), len(qb)) >= 4 and (qa.startswith(qb) or qb.startswith(qa)):
        s = max(s, 90)       # 'anand vihar isbt' vs 'anand vihar'
    wa, wb = a.split(), b.split()
    if wa and wb and len(wa[0]) >= 3 and wa[0] == wb[0] and (len(wa) == 1 or len(wb) == 1):
        s = max(s, 88)       # 'ito agcr' vs 'ito': a one-word name that opens the other
    return s


def hav(la1, lo1, la2, lo2):
    la1, lo1, la2, lo2 = map(np.radians, (la1, lo1, la2, lo2))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def load_gtfs():
    routes = pd.read_csv(GTFS / "routes.txt", dtype={"route_id": str})
    stops = pd.read_csv(GTFS / "stops.txt", dtype={"stop_id": str})
    trips = pd.read_csv(GTFS / "trips.txt", dtype={"route_id": str, "trip_id": str, "shape_id": str})
    st = pd.read_csv(GTFS / "stop_times.txt", dtype={"trip_id": str, "stop_id": str},
                     usecols=["trip_id", "stop_id", "stop_sequence"])
    stops["k"] = stops.stop_name.map(norm_stop)
    tl = st.groupby("trip_id").size().rename("n").reset_index().merge(trips[["trip_id", "route_id"]])
    rep = tl.sort_values("n").groupby("route_id").tail(1).set_index("trip_id").route_id
    st = st[st.trip_id.isin(rep.index)].sort_values(["trip_id", "stop_sequence"])
    seq = {rep[t]: g.stop_id.tolist() for t, g in st.groupby("trip_id")}
    key = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
    # the road path each route's representative trip follows (shapes.txt; older feeds have none)
    shp_of_route, shp = {}, {}
    if "shape_id" in trips and (GTFS / "shapes.txt").exists():
        sid = trips.set_index("trip_id").shape_id
        shp_of_route = {r: sid.get(t) for t, r in rep.items()}
        want = {v for v in shp_of_route.values() if isinstance(v, str)}
        sh = pd.read_csv(GTFS / "shapes.txt", dtype={"shape_id": str},
                         usecols=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])
        sh = sh[sh.shape_id.isin(want)].sort_values(["shape_id", "shape_pt_sequence"])
        shp = {k: g[["shape_pt_lat", "shape_pt_lon"]].to_numpy(float) for k, g in sh.groupby("shape_id")}
    by_name: dict[str, list[str]] = {}
    road: dict[str, np.ndarray] = {}
    for rid, name in zip(routes.route_id, routes.route_long_name):
        if rid in seq and len(seq[rid]) > len(by_name.get(key(name), [])):
            by_name[key(name)] = seq[rid]
            road[key(name)] = shp.get(shp_of_route.get(rid))
    return stops, by_name, key, road


def snap_to_road(lat, lon, P, near_km=SNAP_KM):
    """Index of each GTFS stop along the road path P, always moving forward.
    Returns None if any stop is further than near_km from the path (then the straight stop line is kept)."""
    idx, start = [], 0
    for a, b in zip(lat, lon):
        d = hav(a, b, P[start:, 0], P[start:, 1])
        close = np.flatnonzero(d <= near_km)
        if not len(close):
            return None
        run_end = close[0]                              # first stretch of the path that passes the stop
        while run_end + 1 < len(d) and d[run_end + 1] <= near_km:
            run_end += 1
        k = close[0] + int(d[close[0]: run_end + 1].argmin())
        start += k
        idx.append(start)
    return idx


def main():
    with gzip.open(MODEL, "rb") as f:
        M = pickle.load(f)
    R = M["routes"]
    stops, by_name, key, road = load_gtfs()
    S = stops.set_index("stop_id")

    # pass 0: coordinates for stops whose name is unambiguous in GTFS (one place, < 1 km spread)
    pts: dict[str, tuple[float, float]] = {}
    for k, g in stops.groupby("k"):
        if hav(g.stop_lat.min(), g.stop_lon.min(), g.stop_lat.max(), g.stop_lon.max()) < 1.0:
            pts[k] = (float(g.stop_lat.mean()), float(g.stop_lon.mean()))
    exact_pts = {k: v for k, v in pts.items() if k in M["stops"]}

    def place(rid):
        g = by_name.get(key(rid))
        if not g:
            return None
        names = [S.k[s] for s in g]
        lat = S.stop_lat[g].values.astype(float); lon = S.stop_lon[g].values.astype(float)
        seg = hav(lat[:-1], lon[:-1], lat[1:], lon[1:])
        seg = np.where(seg > 5, 0, seg)                 # a 5 km jump between stops is a data error
        cum = np.r_[0, np.cumsum(seg)]
        pos = {}
        for s in R[rid]["stops"]:
            sc = np.array([score(s, b) for b in names])
            j = int(sc.argmax())
            best = np.flatnonzero(sc == sc[j])
            spread = float(hav(lat[best].min(), lon[best].min(), lat[best].max(), lon[best].max()))
            if sc[j] >= NAME_SCORE and spread <= 1.5:
                pos[s] = int(best[len(best) // 2])     # ties close together: 'ITO', 'ITO (DDU Marg)'
            elif s in pts:
                d = hav(pts[s][0], pts[s][1], lat, lon)
                if d.min() <= NEAR_KM:
                    pos[s] = int(d.argmin())
        return pos, lat, lon, cum

    order, geo, found, detour = {}, {}, {}, []
    on_road = 0
    for rid, r in R.items():
        res = place(rid)
        if not res:
            continue
        pos, lat, lon, cum = res
        if len(pos) < 2 or len(pos) < MIN_PLACED * len(r["stops"]):
            continue
        # stops GTFS cannot place are placed by build_model.py from where their tickets go
        order[rid] = {s: int(j) for s, j in pos.items()}
        km = {s: float(cum[pos[s]]) for s in pos}
        pt = {s: (float(lat[j]), float(lon[j])) for s, j in pos.items()}   # where THIS route stops
        geo[rid] = dict(source="gtfs", km=km, pt=pt, pos={s: int(j) for s, j in pos.items()},
                        path=np.c_[lat, lon].astype(np.float32))       # every GTFS stop, for maps
        P = road.get(key(rid))
        if P is not None and len(P) >= 2:
            ix = snap_to_road(lat, lon, P)
            if ix is not None:                        # draw the real road: positions along the road path
                geo[rid].update(path=P.astype(np.float32), pos={s: int(ix[j]) for s, j in pos.items()}, road=True)
                on_road += 1
        for s, j in pos.items():
            found.setdefault(s, []).append((lat[j], lon[j]))
        if len(pos) >= 2:
            js = sorted(pos.values())
            crow = float(hav(lat[js[0]], lon[js[0]], lat[js[-1]], lon[js[-1]]))
            if crow > 3:
                detour.append((cum[js[-1]] - cum[js[0]]) / crow)

    ambiguous = set()
    for s, v in found.items():
        la = np.array([p[0] for p in v]); lo = np.array([p[1] for p in v])
        if hav(la.min(), lo.min(), la.max(), lo.max()) > 2.0:
            ambiguous.add(s)              # one name, two places (there is more than one Ganesh Nagar)
            pts.pop(s, None)
            continue
        pts[s] = (float(np.median(la)), float(np.median(lo)))
    f = float(np.median(detour)) if detour else 1.35
    for rid in R:
        if rid not in geo:
            geo[rid] = dict(source="stops", km=None)

    stop_points = {k: pts[k] for k in M["stops"] if k in pts}
    tickets = sum(r["tickets"] for r in R.values())
    stats = dict(
        routes=len(R), routes_gtfs_order=len(order), routes_on_road_path=on_road,
        tickets_gtfs_order=round(sum(R[k]["tickets"] for k in order) / tickets, 4),
        stops_located=len(stop_points), stops_total=len(M["stops"]),
        volume_located=round(sum(M["stops"][k]["volume"] for k in stop_points)
                             / sum(s["volume"] for s in M["stops"].values()), 4),
        stops_exact_name=len(exact_pts), stops_ambiguous=len(ambiguous), detour_factor=round(f, 3),
        gtfs_source="Delhi bus GTFS static (DTC/DIMTS), feed v32, from Delhi Transport Stack (updated Nov 2026)",
    )
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(exist_ok=True)
    (WORK / "route_order.json").write_text(json.dumps(order), encoding="utf-8")
    with gzip.open(OUT / "geometry.pkl.gz", "wb") as fh:
        pickle.dump(dict(routes=geo, stop_points=stop_points, ambiguous=sorted(ambiguous),
                         detour=f, stats=stats), fh, protocol=4)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
