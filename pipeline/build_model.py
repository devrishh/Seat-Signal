"""
Seat Signal: crowding model builder.

Reads the ONDC bus e-ticketing CSV (October 2026, Delhi) and builds:
  1. Stop order for every route direction: the Delhi bus GTFS order where
     pipeline/build_geometry.py could line the route up (data/route_order.json), otherwise
     inferred from ticket origin/destination pairs.
  2. On-board load for every route segment, per 30-minute slot and day type
     (weekday / saturday / sunday-holiday), by spreading each ticket across the
     segments it rides.
  3. A network-calibrated Crowd Index (0-100) for every segment and slot.

Usage:
    python pipeline/build_model.py "path/to/October-Delhi.csv"

Writes data/model.pkl.gz and data/validation.json.
"""
from __future__ import annotations

import gzip
import json
import os
import pickle
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"                 # what the app serves
WORK = ROOT / "work"                # pipeline working files (route_order.json)
SLOTS = 48                      # 30-minute slots in a day
DAYTYPES = ["weekday", "saturday", "sunday"]   # sunday also holds public holidays
MIN_STOP_TICKETS = 5            # stops seen fewer times on a route are treated as noise
MIN_ROUTE_TICKETS = 600         # routes below this are kept but flagged low-confidence
RIDE_MIN_PER_STOP = 2.5         # used only to spread a ticket over time while riding

ABBREV = [
    (r"\bbdr\b", "border"), (r"\bxing\b", "crossing"), (r"\bsec\b", "sector"),
    (r"\bsect\b", "sector"), (r"\bstn\b", "station"), (r"\brly\b", "railway"),
    (r"\bopp\b\.?", "opposite"), (r"\bext\b", "extension"), (r"\bmkt\b", "market"),
    (r"\bclny\b", "colony"), (r"\bhosp\b", "hospital"), (r"\btmnl\b", "terminal"),
]


def norm_stop(name: str) -> str:
    s = re.sub(r"\((t|terminal)\)", " ", str(name).lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    for pat, rep in ABBREV:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


def split_route(r: str) -> tuple[str, str]:
    m = re.match(r"^(.*?)(UP|DOWN)$", r)
    return (m.group(1), m.group(2)) if m else (r, "")


def order_stops(pairs: pd.DataFrame) -> tuple[list[str], float]:
    """Order stops so that ticket origins come before destinations.

    pairs: columns a, b, w (weight = passengers travelling a -> b).
    Copeland ranking on net pairwise precedence, then adjacent-swap refinement
    to minimise the weight of tickets that would travel 'backwards'.
    Returns (ordered stops, share of ticket weight consistent with the order).
    """
    stops = sorted(set(pairs.a) | set(pairs.b))
    idx = {s: i for i, s in enumerate(stops)}
    n = len(stops)
    M = np.zeros((n, n))
    np.add.at(M, (pairs.a.map(idx).values, pairs.b.map(idx).values), pairs.w.values)
    net = M - M.T
    score = (net > 0).sum(1) - (net < 0).sum(1) + 1e-6 * net.sum(1)
    order = list(np.argsort(-score))
    # adjacent swap refinement
    improved, passes = True, 0
    while improved and passes < 50:
        improved, passes = False, passes + 1
        for k in range(n - 1):
            i, j = order[k], order[k + 1]
            if M[j, i] > M[i, j]:
                order[k], order[k + 1] = j, i
                improved = True
    pos = np.empty(n, int)
    pos[order] = np.arange(n)
    pa, pb = pos[pairs.a.map(idx).values], pos[pairs.b.map(idx).values]
    consistent = pairs.w.values[pa < pb].sum() / max(pairs.w.values.sum(), 1)
    return [stops[i] for i in order], float(consistent)


def order_from_anchors(pairs: pd.DataFrame, anchors: dict[str, int], stops: list[str]) -> list[str]:
    """Stops GTFS placed keep their GTFS order. Each other stop goes into the gap between
    anchors where the most of its tickets travel forward (riders from it go to later stops,
    riders to it come from earlier ones). Several stops in one gap keep their inferred order."""
    A = sorted(anchors, key=anchors.get)
    rank = {s: i for i, s in enumerate(A)}
    w = pairs.groupby(["a", "b"]).w.sum().to_dict()
    slot = {}
    for u in stops:
        if u in rank:
            continue
        out = np.zeros(len(A)); inn = np.zeros(len(A))
        for x, i in rank.items():
            out[i] += w.get((u, x), 0.0)        # u -> x: x should come after u
            inn[i] += w.get((x, u), 0.0)        # x -> u: x should come before u
        # score of inserting before anchor q = forward out-tickets to anchors >= q + in-tickets from < q
        after = np.r_[np.cumsum(out[::-1])[::-1], 0.0]
        before = np.r_[0.0, np.cumsum(inn)]
        sc = after + before
        best = np.flatnonzero(sc == sc.max())
        slot[u] = int(best[len(best) // 2])
    keyed = [((rank[s], 1, 0) if s in rank else (slot[s] - 0.5, 0, k)) for k, s in enumerate(stops)]
    return [s for _, s in sorted(zip(keyed, stops))]


def forward_share(pairs: pd.DataFrame, order: list[str]) -> float:
    """Share of ticket weight that travels forward along a given stop order."""
    pos = {s: i for i, s in enumerate(order)}
    fwd = pairs.a.map(pos).values < pairs.b.map(pos).values
    return float(pairs.w.values[fwd].sum() / max(pairs.w.values.sum(), 1))


def main(csv_path: str) -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(
        csv_path,
        usecols=["passenger_count", "amount", "vehicle_number", "end_stop_name",
                 "route", "start_stop_name", "created_at", "is_ac"],
        dtype={"amount": "string", "vehicle_number": "string", "route": "string",
               "start_stop_name": "string", "end_stop_name": "string"},
    )
    n_raw = len(df)
    df["ts"] = pd.to_datetime(df.created_at.str.slice(0, 19), format="%Y-%m-%d %H:%M:%S")
    df.drop(columns="created_at", inplace=True)
    df["amount"] = pd.to_numeric(df.amount, errors="coerce")

    # ---- stop names -------------------------------------------------------
    raw_names = pd.concat([df.start_stop_name, df.end_stop_name]).dropna()
    uniq = raw_names.unique()
    key_of = {n: norm_stop(n) for n in uniq}
    df["a"] = df.start_stop_name.map(key_of)
    df["b"] = df.end_stop_name.map(key_of)
    counts = raw_names.value_counts()
    display = {}
    for name, c in counts.items():          # most frequent spelling wins
        display.setdefault(key_of[name], name.strip())

    df = df.dropna(subset=["a", "b", "route"])
    same = (df.a == df.b)
    n_same = int(same.sum())
    df = df[~same].copy()

    # ---- day types (holidays detected from the data) ---------------------
    df["date"] = df.ts.dt.normalize()
    daily = df.groupby("date").passenger_count.sum()
    dow = daily.index.dayofweek
    wk_median = daily[dow < 5].median()
    holidays = [d for d, v in daily.items() if d.dayofweek < 5 and v < 0.7 * wk_median]
    def daytype(d):
        if d in holidays or d.dayofweek == 6:
            return 2
        return 1 if d.dayofweek == 5 else 0
    dt_of_date = {d: daytype(d) for d in daily.index}
    df["dt"] = df.date.map(dt_of_date).astype(np.int8)
    n_days = np.bincount(list(dt_of_date.values()), minlength=3)

    # ---- per route-direction stop ordering --------------------------------
    order_file = WORK / "route_order.json"
    gtfs_order = json.loads(order_file.read_text(encoding="utf-8")) if order_file.exists() else {}
    anchor_check = []      # tickets between two GTFS-placed stops: independent check of the order
    routes = {}
    keep_rows = []
    for route, g in df.groupby("route", sort=False):
        pairs = g.groupby(["a", "b"]).passenger_count.sum().reset_index(name="w")
        stop_w = pd.concat([pairs.groupby("a").w.sum(), pairs.groupby("b").w.sum()]).groupby(level=0).sum()
        good = set(stop_w[stop_w >= MIN_STOP_TICKETS].index)
        pairs = pairs[pairs.a.isin(good) & pairs.b.isin(good)]
        if len(good) < 2 or pairs.w.sum() < 10:
            continue
        order, consistency = order_stops(pairs)
        inferred_consistency, source = consistency, "tickets"
        anchors = {s: j for s, j in gtfs_order.get(route, {}).items() if s in good}
        if len(anchors) >= 2 and len(anchors) >= 0.6 * len(good):
            order = order_from_anchors(pairs, anchors, order)
            consistency, source = forward_share(pairs, order), "gtfs"
            both = pairs[pairs.a.isin(anchors) & pairs.b.isin(anchors)]
            anchor_check.append((forward_share(both, order) * both.w.sum(), both.w.sum()))
        base, direction = split_route(route)
        routes[route] = dict(
            id=route, base=base, dir=direction, stops=order,
            pos={s: i for i, s in enumerate(order)},
            tickets=int(g.passenger_count.sum()), consistency=consistency,
            order_source=source, inferred_consistency=inferred_consistency,
            ac_share=float(g.is_ac.mean()),
            median_fare=float(g.amount.median()) if g.amount.notna().any() else None,
        )
        keep_rows.append(g.index[g.a.isin(good) & g.b.isin(good)])

    df = df.loc[np.concatenate(keep_rows)]
    rid = {r: i for i, r in enumerate(routes)}
    df["ri"] = df.route.map(rid)
    df["pa"] = [routes[r]["pos"][s] for r, s in zip(df.route, df.a)]
    df["pb"] = [routes[r]["pos"][s] for r, s in zip(df.route, df.b)]
    backward = df.pa > df.pb
    n_backward = int(backward.sum())
    df = df[~backward]

    # ---- spread every ticket over the segments (and time) it rides ---------
    nseg = np.array([len(routes[r]["stops"]) - 1 for r in routes])
    block = 3 * SLOTS * nseg
    base_off = np.concatenate([[0], np.cumsum(block)[:-1]])
    ri, pa, pb = df.ri.values, df.pa.values, df.pb.values
    minute = (df.ts.dt.hour * 60 + df.ts.dt.minute).values
    L = pb - pa
    rep = np.repeat(np.arange(len(df)), L)
    k = np.arange(L.sum()) - np.repeat(np.cumsum(L) - L, L)
    seg = pa[rep] + k
    slot = ((minute[rep] + k * RIDE_MIN_PER_STOP) // 30).astype(int) % SLOTS
    flat = base_off[ri[rep]] + (df.dt.values[rep] * SLOTS + slot) * nseg[ri[rep]] + seg
    load = np.bincount(flat, weights=df.passenger_count.values[rep], minlength=int(block.sum()))

    # average riders on board per day of that type
    for i, r in enumerate(routes):
        arr = load[base_off[i]: base_off[i] + block[i]].reshape(3, SLOTS, nseg[i])
        routes[r]["load"] = (arr / n_days[:, None, None]).astype(np.float32)

    # ---- network calibration of the Crowd Index -----------------------------
    # E-tickets are a sample of riders, so absolute counts are not bus loads.
    # The Crowd Index is a log-scaled load calibrated on the whole network:
    #   index = 100 * log(1 + load) / log(1 + cap)
    # where cap is 1.3x the 99.9th percentile of daytime weekday segment loads.
    # This keeps differences between routes (at the same time) and between times
    # (on the same route) both visible, instead of saturating busy corridors.
    ref_vals = np.concatenate([routes[r]["load"][0, 12:44].ravel() for r in routes])
    ref = float(np.percentile(ref_vals, 99.9) * 1.3)
    for r in routes.values():
        r["crowd"] = np.clip(100 * np.log1p(r["load"]) / np.log1p(ref), 0, 100).astype(np.float32)
        r["low_data"] = r["tickets"] < MIN_ROUTE_TICKETS
        del r["pos"]

    # ---- stop index ---------------------------------------------------------
    stop_routes = defaultdict(list)
    for r in routes.values():
        for i, s in enumerate(r["stops"]):
            stop_routes[s].append((r["id"], i))
    stop_vol = pd.concat([df.groupby("a").passenger_count.sum(), df.groupby("b").passenger_count.sum()]).groupby(level=0).sum()
    stops = {s: dict(key=s, name=display.get(s, s), routes=len(v), volume=int(stop_vol.get(s, 0)))
             for s, v in stop_routes.items()}

    # ---- network profiles for the dashboard and validation -------------------
    hourly = np.zeros((3, SLOTS))
    for r in routes.values():
        hourly += r["load"].sum(2)
    board = df.groupby(["dt", (df.ts.dt.hour * 2 + df.ts.dt.minute // 30)]).passenger_count.sum()
    boardings = np.zeros((3, SLOTS))
    for (d, s), v in board.items():
        boardings[d, s] = v / n_days[d]

    meta = dict(
        source=Path(csv_path).name, rows_raw=n_raw, rows_used=int(len(df)),
        rows_same_stop=n_same, rows_backward=n_backward,
        date_min=str(df.ts.min()), date_max=str(df.ts.max()),
        n_routes=len(routes), n_stops=len(stops), n_days=n_days.tolist(),
        holidays=[d.strftime("%Y-%m-%d") for d in holidays],
        crowd_ref_load=ref, daytypes=DAYTYPES, slots=SLOTS,
        daily_totals={d.strftime("%Y-%m-%d"): int(v) for d, v in daily.items()},
        ac_share=float(df.is_ac.mean()),
        built_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    model = dict(meta=meta, routes=routes, stops=stops, stop_routes=dict(stop_routes),
                 network_onboard=hourly.astype(np.float32), network_boardings=boardings.astype(np.float32))
    with gzip.open(OUT / "model.pkl.gz", "wb", compresslevel=5) as f:
        pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)

    # ---- validation summary -------------------------------------------------
    def window(arr, h0, h1):
        return float(arr[h0 * 2: h1 * 2].mean())
    wk = boardings[0]
    cons = np.array([r["consistency"] for r in routes.values()])
    tix = np.array([r["tickets"] for r in routes.values()])
    val = dict(
        meta=meta,
        peak_offpeak=dict(
            am_peak_8_11=window(wk, 8, 11), midday_12_16=window(wk, 12, 16),
            pm_peak_17_21=window(wk, 17, 21), night_22_24=window(wk, 22, 24),
            am_peak_ratio=window(wk, 8, 11) / window(wk, 12, 16),
            pm_peak_ratio=window(wk, 17, 21) / window(wk, 12, 16),
            busiest_slot_weekday=int(np.argmax(wk)),
        ),
        daytype_avg_daily_boardings=[float(boardings[d].sum()) for d in range(3)],
        stop_order=dict(
            weighted_consistency=float((cons * tix).sum() / tix.sum()),
            median_consistency=float(np.median(cons)),
            share_routes_above_95=float((cons >= 0.95).mean()),
            routes_gtfs_order=int(sum(r["order_source"] == "gtfs" for r in routes.values())),
            tickets_gtfs_order=float(sum(r["tickets"] for r in routes.values() if r["order_source"] == "gtfs") / tix.sum()),
            gtfs_independent_forward_share=float(sum(a for a, _ in anchor_check) / max(1, sum(b for _, b in anchor_check))),
            gtfs_independent_tickets=float(sum(b for _, b in anchor_check)),
            gtfs_routes_forward_share=float(sum(r["consistency"] * r["tickets"] for r in routes.values() if r["order_source"] == "gtfs")
                                            / max(1, sum(r["tickets"] for r in routes.values() if r["order_source"] == "gtfs"))),
        ),
        top_routes=sorted(({"route": r["id"], "tickets": r["tickets"], "stops": len(r["stops"]),
                            "consistency": round(r["consistency"], 4), "order": r["order_source"]} for r in routes.values()),
                          key=lambda x: -x["tickets"])[:15],
        weekday_boardings_by_slot=wk.round(1).tolist(),
        weekend_boardings_by_slot=boardings[2].round(1).tolist(),
    )
    (OUT / "validation.json").write_text(json.dumps(val, indent=2))
    print(f"Built model: {len(routes)} routes, {len(stops)} stops, {len(df):,} tickets "
          f"in {time.time() - t0:.0f}s; holidays detected: {meta['holidays']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TICKETS_CSV", str(ROOT.parent / "October 2026 bus e-ticketing" / "October-Delhi.csv")))
