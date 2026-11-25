"""
Seat Signal API: crowding-aware bus journey planner for Delhi.

Run from the project root:
    python -m uvicorn backend.app:app --port 8000
Then open http://localhost:8000
"""
from __future__ import annotations

import gzip
import json
import os
import pickle
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .live import Live
from .travel import Travel

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data" / "model.pkl.gz"
FRONTEND = ROOT / "frontend"
IST = timezone(timedelta(hours=5, minutes=30))

with gzip.open(MODEL_PATH, "rb") as f:
    M = pickle.load(f)
ROUTES, STOPS, STOP_ROUTES, META = M["routes"], M["stops"], M["stop_routes"], M["meta"]
TRAVEL = Travel(ROUTES, ROOT / "data")
# e-ticket fare by route and number of stops ridden (pipeline/build_fares.py); optional
_fp = ROOT / "data" / "fares.json"
FARES = json.loads(_fp.read_text()) if _fp.exists() else {}
# timetable departures per route and minutes from the first stop to each stop (pipeline/build_schedule.py)
_sp = ROOT / "data" / "schedule.json"
SCHED = {k: (np.array(v["dep"], float), np.array(v["off"], float))
         for k, v in (json.loads(_sp.read_text()) if _sp.exists() else {}).items()}
_lp = ROOT / "data" / "live_routes.json"
LIVE = Live(ROOT, json.loads(_lp.read_text()) if _lp.exists() else {})
WALK_MIN = 3              # walking between buses at a change
DEFAULT_WAIT = 8          # routes with no timetable: a typical wait


def wait_at(rid: str, i: int, minute: float):
    """Average wait for a rider who reaches stop i of route rid around `minute` (any time in the
    surrounding half hour, since buses rarely keep to the minute), and the usual gap between buses.
    Returns (wait minutes, every N minutes or None, source)."""
    sc = SCHED.get(rid)
    if sc is None:
        return DEFAULT_WAIT, None, "estimate"
    dep, off = sc
    at = np.sort((dep + off[min(i, len(off) - 1)]) % 1440)
    at = np.r_[at, at + 1440]                        # tomorrow's first buses after midnight
    arrive = (minute + np.arange(-15, 15)) % 1440
    nxt = at[np.searchsorted(at, arrive)]
    wait = float(np.minimum(nxt - arrive, 90).mean())
    near = at[(at >= (minute - 45) % 1440) & (at <= (minute - 45) % 1440 + 90)]
    every = int(round(float(np.median(np.diff(near))))) if len(near) >= 3 else None
    return wait, every, "timetable"
DAY = {"weekday": 0, "saturday": 1, "sunday": 2}
TRANSFER_MIN = 7          # walking + waiting at an interchange
MAX_TRANSFER_SCAN = 45    # stops scanned along each leg when looking for interchanges
BIG_ROUTE = 2000          # tickets/month for a route to appear on the dashboard
MIN_ORDER_AGREE = 0.85    # below this share of tickets agreeing with the inferred stop order
                          # (rings such as the Mudrikas), stop counts are not trusted for trips

app = FastAPI(title="Seat Signal API", version="1.0",
              description="Crowding-aware journey planning for Delhi buses, "
                          "built on October 2026 ONDC e-ticketing data.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2000)


# ---------------------------------------------------------------- helpers
def level(ci: float) -> str:
    if ci < 35:
        return "Comfortable"
    if ci < 60:
        return "Moderate"
    if ci < 80:
        return "Busy"
    return "Packed"


def seat_chance(ci: float) -> int:
    return int(np.clip(round(100 - ci * 1.05), 3, 96))


def parse_time(t: str | None) -> int:
    if not t:
        now = datetime.now(IST)
        return now.hour * 60 + now.minute
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if not m:
        raise HTTPException(400, "time must be HH:MM")
    return (int(m.group(1)) % 24) * 60 + int(m.group(2))


def default_day() -> str:
    d = datetime.now(IST).weekday()
    return "sunday" if d == 6 else "saturday" if d == 5 else "weekday"


def is_now(minute: int, d: int) -> bool:
    """True when the asked-for time is the present, so live buses apply."""
    now = datetime.now(IST)
    today = 2 if now.weekday() == 6 else 1 if now.weekday() == 5 else 0
    m = now.hour * 60 + now.minute
    delta = abs(((minute - m) + 720) % 1440 - 720)
    # The app's clock steps on the half hour, so the current half hour counts as now too.
    return d == today and (delta <= 10 or minute % 1440 == (m // 30) * 30)


def live_buses_on(rid: str):
    """Buses on route rid now, each with the index of the route stop it is at or nearest to."""
    out = []
    for b in LIVE.buses().get(rid, []):
        best, k_best = 0.6, None                     # within 600 m of one of the route's stops
        for k in range(len(ROUTES[rid]["stops"])):
            p = TRAVEL.point(rid, k)
            if p is None:
                continue
            dkm = (((p[0] - b["lat"]) * 111.0) ** 2 + ((p[1] - b["lon"]) * 97.6) ** 2) ** 0.5
            if dkm < best:
                best, k_best = dkm, k
        if k_best is not None:
            out.append(dict(lat=round(b["lat"], 5), lon=round(b["lon"], 5), plate=b["plate"], age=b["age"], at=k_best))
    return out


def live_next(rid: str, i: int, minute: int, d: int):
    """The nearest bus coming towards stop i of route rid, and about when it gets there."""
    near = [b for b in live_buses_on(rid) if b["at"] <= i]
    if not near:
        return None
    b = max(near, key=lambda x: x["at"])
    eta = 0 if b["at"] == i else ride(rid, b["at"], i, minute, d)["minutes"]
    return dict(eta=round(eta), stops_away=i - b["at"], plate=b["plate"], age=b["age"])


def m2s(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def ampm(minute: int) -> str:
    h, m = (minute // 60) % 24, minute % 60
    return f"{(h % 12) or 12}:{m:02d} {'am' if h < 12 else 'pm'}"


def fmt(minute: float) -> str:
    m = int(round(minute)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def display_number(base: str) -> str:
    """Route code as riders know it: '0740(NS)' -> '740 NS', '724BDOWN3' -> '724B'."""
    b = re.sub(r"(UP|DOWN)\d*$", "", base) or base
    b = re.sub(r"^0+(?=\d)", "", b)
    b = re.sub(r"\(([A-Z]+)\)", r" \1", b)
    return b.strip() or base


def plannable(rid: str) -> bool:
    """Trusted for journey planning: enough tickets, and a stop order we believe (from GTFS,
    or inferred with most tickets agreeing). Rings such as the Mudrikas often fail this."""
    r = ROUTES[rid]
    if r["low_data"]:
        return False
    return r.get("order_source") == "gtfs" or r["consistency"] >= MIN_ORDER_AGREE


def is_reliable(option: tuple) -> bool:
    return all(plannable(rid) for rid, _, _ in option)


def route_label(rid: str) -> dict:
    r = ROUTES[rid]
    return dict(id=rid, number=display_number(r["base"]), direction=r["dir"], ac=r["ac_share"] >= 0.5,
                towards=STOPS[r["stops"][-1]]["name"], low_data=r["low_data"])


def ride(rid: str, i: int, j: int, minute: float, d: int) -> dict:
    """Crowding and time for riding route rid from stop index i to j, boarding at minute."""
    r = ROUTES[rid]
    c = r["crowd"][d]
    times, km, source = TRAVEL.ride(rid, r["stops"], i, j, minute, d)
    crowds = [float(c[int((minute + times[k - i]) // 30) % 48, k]) for k in range(i, j)]
    arr = np.array(crowds)
    return dict(minutes=times[-1], crowd=float(arr.mean()), peak=float(arr.max()),
                board_crowd=float(arr[0]), profile=[round(x) for x in crowds],
                km=km, time_source=source)


def fare_of(rid: str, i: int, j: int) -> float | None:
    """Rupees per passenger for an e-ticket from stop i to stop j, from the October tickets."""
    f = FARES.get(rid)
    if f and 0 < j - i <= len(f):
        return f[j - i - 1]
    mf = ROUTES[rid].get("median_fare")
    return None if mf is None else round(mf * 2) / 2


def leg_out(rid, i, j, minute, d) -> dict:
    r = ROUTES[rid]
    x = ride(rid, i, j, minute, d)
    return dict(route=route_label(rid), board=STOPS[r["stops"][i]]["name"],
                alight=STOPS[r["stops"][j]]["name"], stops=j - i,
                depart=fmt(minute), arrive=fmt(minute + x["minutes"]),
                minutes=round(x["minutes"]), crowd=round(x["crowd"]), peak=round(x["peak"]),
                level=level(x["crowd"]), seat_chance=seat_chance(x["board_crowd"]),
                profile=x["profile"], km=None if x["km"] is None else round(x["km"], 1),
                time_source=x["time_source"], fare=fare_of(rid, i, j),
                stop_names=[STOPS[s]["name"] for s in r["stops"][i:j + 1]])


def evaluate(option: tuple, minute: float, d: int) -> dict:
    """option = ((rid, i, j), ...) legs."""
    legs, t = [], minute
    for n, (rid, i, j) in enumerate(option):
        if n:
            t += WALK_MIN
        w, every, src = wait_at(rid, i, t)
        t += w
        leg = leg_out(rid, i, j, t, d)
        leg.update(wait=round(w), every=every, wait_source=src)
        legs.append(leg)
        t += leg["minutes"]
    total = t - minute
    w = np.array([l["stops"] for l in legs], float)
    crowd = float((np.array([l["crowd"] for l in legs]) * w).sum() / w.sum())
    return dict(legs=legs, transfers=len(legs) - 1, minutes=round(total),
                depart=fmt(minute), arrive=fmt(minute + total),
                crowd=round(crowd), peak=max(l["peak"] for l in legs), level=level(crowd),
                seat_chance=legs[0]["seat_chance"], stops=int(w.sum()),
                km=None if any(l["km"] is None for l in legs) else round(sum(l["km"] for l in legs), 1),
                time_source="gps" if all(l["time_source"] == "gps" for l in legs) else "estimate",
                fare=None if any(l["fare"] is None for l in legs) else sum(l["fare"] for l in legs),
                wait=sum(l["wait"] for l in legs), ride=sum(l["minutes"] for l in legs),
                confidence="low" if any(l["route"]["low_data"] for l in legs) else "high")


def find_stop(key: str) -> str:
    if key in STOPS:
        return key
    k = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", key.lower())).strip()
    if k in STOPS:
        return k
    raise HTTPException(404, f"Unknown stop: {key}")


@lru_cache(maxsize=4096)
def candidate_options(a: str, b: str) -> list[tuple]:
    direct, seen = [], set()
    for rid, i in STOP_ROUTES[a]:
        for rid2, j in STOP_ROUTES[b]:
            if rid2 == rid and j > i:
                direct.append(((rid, i, j),))
                seen.add(rid)
    # one-transfer journeys
    after: dict[str, list] = {}
    for rid, i in STOP_ROUTES[a]:
        stops = ROUTES[rid]["stops"]
        for k in range(i + 1, min(len(stops), i + MAX_TRANSFER_SCAN)):
            after.setdefault(stops[k], []).append((rid, i, k))
    best: dict[tuple, tuple] = {}
    for rid2, j in STOP_ROUTES[b]:
        stops = ROUTES[rid2]["stops"]
        for k in range(max(0, j - MAX_TRANSFER_SCAN), j):
            for rid1, i, k1 in after.get(stops[k], []):
                if ROUTES[rid1]["base"] == ROUTES[rid2]["base"] or rid1 in seen or rid2 in seen:
                    continue
                if not TRAVEL.same_place(stops[k], rid1, k1, rid2, k):
                    continue
                n = (k1 - i) + (j - k)
                key = (rid1, rid2)
                if key not in best or n < best[key][0]:
                    best[key] = (n, ((rid1, i, k1), (rid2, k, j)))
    transfers = [v[1] for v in sorted(best.values(), key=lambda x: x[0])[:40]]
    direct.sort(key=lambda o: o[0][2] - o[0][1])
    return direct[:12] + transfers


# ---------------------------------------------------------------- endpoints
def _carto_key() -> str:
    """CARTO basemaps key: the CARTO_KEY environment variable (for hosting), else the first line
    of carto_key.txt in the project folder (kept out of git). Empty means maps work without it."""
    key = os.environ.get("CARTO_KEY", "").strip()
    f = ROOT / "carto_key.txt"
    if not key and f.exists():
        lines = f.read_text(encoding="utf-8").split()
        key = lines[0] if lines else ""
    return "" if key.startswith("<") else key        # "<insert your carto key>" is a placeholder


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def chrome_devtools_probe():
    """Chrome DevTools asks every local site for workspace settings. There are none: say so
    without a 404 in the log."""
    return Response(status_code=204)


@app.get("/api/config")
def config():
    """Settings the browser needs. The basemap key travels in tile URLs, so it is public by design;
    restrict it to your site's address in the CARTO dashboard."""
    return dict(carto_key=_carto_key(), live=LIVE.on)


@app.get("/api/meta")
def meta():
    m = META
    return dict(routes=m["n_routes"], stops=m["n_stops"], tickets=m["rows_used"],
                period=f"{m['date_min'][:10]} to {m['date_max'][:10]}", holidays=m["holidays"],
                ac_share=round(m["ac_share"], 3), source="ONDC bus e-ticketing, Transport Stack / IIIT Delhi",
                default_day=default_day(), now=fmt(parse_time(None)))


@app.get("/api/stops")
def stops(q: str = Query("", max_length=80), limit: int = 8):
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", q.lower()).split() if w]
    out = []
    for s in STOPS.values():
        key = s["key"]
        if all(w in key for w in words):
            starts = key.startswith(words[0]) if words else False
            out.append((not starts, -s["volume"], s))
    out.sort(key=lambda x: (x[0], x[1]))
    return [dict(key=s["key"], name=s["name"], routes=s["routes"], volume=s["volume"])
            for _, _, s in out[:limit]]


@lru_cache(maxsize=1)
def _stops_map():
    out = []
    for k, s in STOPS.items():
        p = TRAVEL.pts.get(k)
        if p:
            out.append([k, s["name"], round(p[0], 5), round(p[1], 5), s["volume"], s["routes"]])
    out.sort(key=lambda x: -x[4])
    return out


@app.get("/api/stops/map")
def stops_map():
    """Every stop with one clear location: [key, name, lat, lon, October trips, routes]."""
    return _stops_map()


@app.get("/api/plan")
def plan(origin: str = Query(..., alias="from"), dest: str = Query(..., alias="to"),
         time: str | None = None, day: str | None = None, prefer: str = "balanced"):
    a, b = find_stop(origin), find_stop(dest)
    if a == b:
        raise HTTPException(400, "Origin and destination are the same stop")
    day = day or default_day()
    d = DAY.get(day)
    if d is None:
        raise HTTPException(400, "day must be weekday, saturday or sunday")
    minute = parse_time(time)
    near = TRAVEL.walk_km(a, b)
    if near is not None and near <= 0.4:
        return dict(origin=STOPS[a]["name"], destination=STOPS[b]["name"], options=[], day=day,
                    depart=fmt(minute), walk_m=round(near * 1000, -1),
                    message=f"These stops are about {round(near * 1000, -1):.0f} m apart. It's quicker to walk.")
    cands = candidate_options(a, b)
    if not cands:
        return dict(origin=STOPS[a]["name"], destination=STOPS[b]["name"], options=[], day=day,
                    depart=fmt(minute),
                    message="No direct or one-change bus journey found in the ticket data.")
    # Routes with under 600 e-tickets, and rings whose stop order is unclear, can give absurd
    # times (a 10 km ride shown as 1 stop). Use them only when nothing better exists.
    solid = [o for o in cands if is_reliable(o)]
    hidden_low_data = len({r for o in cands if not is_reliable(o) for r, _, _ in o}) if solid else 0
    only_low_data = not solid
    cands = solid or cands
    opts = [evaluate(o, minute, d) | {"_key": o} for o in cands]
    # a 'ride' of no distance (two names for one terminal) is not a real option
    opts = [o for o in opts if all(l["km"] is None or l["km"] >= 0.1 for l in o["legs"])] or opts
    direct = sorted([o for o in opts if o["transfers"] == 0], key=lambda o: o["minutes"])[:4]
    changes = sorted([o for o in opts if o["transfers"] > 0], key=lambda o: o["minutes"])
    opts = direct + changes[: max(0, 8 - len(direct))]
    for o in opts:
        # routes with few e-tickets look emptier than they are: never let them win on comfort
        o["score"] = (o["minutes"] * (1 + 0.6 * o["crowd"] / 100) + 15 * o["transfers"]
                      + (25 if o["confidence"] == "low" else 0))
    reliable = [o for o in opts if o["confidence"] == "high"] or opts
    fastest = min(opts, key=lambda o: o["minutes"])
    calmest = min(reliable, key=lambda o: (o["crowd"], o["minutes"]))
    best = min(opts, key=lambda o: o["score"])
    cost = lambda o: (o["fare"] if o["fare"] is not None else 1e9, o["minutes"])
    cheapest = min(reliable, key=cost)
    if cheapest["fare"] is None or (best["fare"] is not None and cheapest["fare"] >= best["fare"]):
        cheapest = None                      # only worth a tag when it saves money over the recommended trip
    for o in opts:
        o["tags"] = [t for t, x in (("Best overall", best), ("Fastest", fastest), ("Least crowded", calmest),
                                    ("Cheapest", cheapest)) if x is o]
    key = {"fastest": lambda o: o["minutes"], "comfort": lambda o: (o["crowd"], o["minutes"]),
           "cheapest": cost}.get(prefer, lambda o: o["score"])
    opts.sort(key=key)
    # When should you leave? Re-evaluate the recommended option across nearby departures.
    times = []
    for off in range(-60, 121, 30):
        m2 = minute + off
        if 300 <= m2 % 1440 <= 1380:
            e = evaluate(best["_key"], m2, d)
            times.append(dict(depart=fmt(m2), offset=off, crowd=e["crowd"], minutes=e["minutes"], level=e["level"]))
    better = min(times, key=lambda x: (x["crowd"], abs(x["offset"]))) if times else None
    tip = None
    if better and better["offset"] != 0 and best["crowd"] >= 30 and best["crowd"] - better["crowd"] >= 12:
        drop = round(100 * (best["crowd"] - better["crowd"]) / max(best["crowd"], 1))
        when = "earlier" if better["offset"] < 0 else "later"
        tip = dict(depart=better["depart"], crowd=better["crowd"], drop_pct=drop,
                   offset=better["offset"],
                   text=f"Leave {abs(better['offset'])} minutes {when}, at {ampm(m2s(better['depart']))}, and the bus is about {drop}% less crowded.")
    live_now = LIVE.on and is_now(minute, d)
    for o in opts:
        for leg, (rid, i, j) in zip(o["legs"], o["_key"]):
            leg["shape"] = TRAVEL.shape(rid, i, j)        # for the map
        if live_now:
            rid, i, _ = o["_key"][0]
            o["live"] = live_next(rid, i, minute, d)    # None: no bus seen coming yet
        o.pop("_key", None)
        o.pop("score", None)
    return dict(origin=STOPS[a]["name"], destination=STOPS[b]["name"], depart=fmt(minute), day=day,
                options=opts, departure_curve=times, tip=tip,
                hidden_low_data=hidden_low_data, only_low_data=only_low_data,
                note="Crowding from October 2026 e-tickets. Travel times from route distances (Delhi bus GTFS) "
                     "and bus speeds measured by GPS in October 2026.")


@app.get("/api/route/{rid}")
def route(rid: str, time: str | None = None, day: str | None = None):
    if rid not in ROUTES:
        raise HTTPException(404, "Unknown route")
    r = ROUTES[rid]
    d = DAY.get(day or default_day(), 0)
    minute = parse_time(time)
    slot = (minute // 30) % 48
    c = r["crowd"][d]
    prof = c.mean(1)
    day_slots = range(12, 44)
    active = [s for s in day_slots if r["load"][d, s].sum() > 0] or list(day_slots)
    best_s = min(active, key=lambda s: prof[s])
    worst_s = max(active, key=lambda s: prof[s])
    return dict(route=route_label(rid), tickets=r["tickets"], median_fare=r["median_fare"],
                order_confidence=round(r["consistency"], 3), slot=fmt(slot * 30),
                stops=[dict(name=STOPS[s]["name"], key=s) for s in r["stops"]],
                segments=[round(float(x)) for x in c[slot]],
                segments_by_slot=[[round(float(x)) for x in c[s]] for s in range(10, 46)],   # 5 am to 11 pm, for the map
                hourly=[round(float(x)) for x in prof], peak_by_slot=[round(float(x)) for x in c.max(1)],
                best_time=fmt(best_s * 30), worst_time=fmt(worst_s * 30),
                best_crowd=round(float(prof[best_s])), worst_crowd=round(float(prof[worst_s])),
                now_crowd=round(float(prof[slot])), level=level(float(prof[slot])),
                shape=TRAVEL.shape(rid, 0, len(r["stops"]) - 1),
                live=live_buses_on(rid) if LIVE.on and is_now(minute, d) else None)


@lru_cache(maxsize=256)
def _pulse(slot: int, d: int):
    big = [r for r in ROUTES.values() if r["tickets"] >= BIG_ROUTE]
    rows = []
    for r in big:
        now = float(r["crowd"][d, slot].mean())
        prev = float(r["crowd"][d, (slot - 1) % 48].mean())
        rows.append(dict(route_label(r["id"]), crowd=round(now), change=round(now - prev, 1), level=level(now),
                         spark=[round(float(x)) for x in r["crowd"][d].mean(1)[10:46]]))
    net = M["network_onboard"]
    ref = float(net[0].max())
    curve = [round(float(100 * x / ref)) for x in net[d]]
    return rows, curve


@app.get("/api/pulse")
def pulse(time: str | None = None, day: str | None = None):
    d = DAY.get(day or default_day(), 0)
    minute = parse_time(time)
    slot = (minute // 30) % 48
    rows, curve = _pulse(slot, d)
    busiest = sorted(rows, key=lambda x: -x["crowd"])[:6]
    calmest = sorted([x for x in rows if x["crowd"] >= 12], key=lambda x: x["crowd"])[:6]
    movers = sorted(rows, key=lambda x: -abs(x["change"]))[:12]
    now = curve[slot]
    return dict(slot=fmt(slot * 30), day=day or default_day(), network_index=now,
                change=round(now - curve[(slot - 1) % 48], 1), level=level(now), curve=curve,
                peak_time=fmt(int(np.argmax(curve)) * 30), busiest=busiest, calmest=calmest, movers=movers)


@app.get("/api/routes")
def routes(q: str = Query("", max_length=40), time: str | None = None, day: str | None = None, limit: int = 30):
    d = DAY.get(day or default_day(), 0)
    slot = (parse_time(time) // 30) % 48
    ql = q.strip().lower().replace(" ", "")
    hits = [r for r in ROUTES.values()
            if not ql or r["base"].lower().startswith(ql) or r["id"].lower().startswith(ql)]
    hits.sort(key=lambda r: (r["base"].lower() != ql, -r["tickets"]))
    out = []
    for r in hits[:limit]:
        now = float(r["crowd"][d, slot].mean())
        out.append(dict(route_label(r["id"]), origin=STOPS[r["stops"][0]]["name"], stops=len(r["stops"]),
                        tickets=r["tickets"], crowd=round(now), level=level(now),
                        spark=[round(float(x)) for x in r["crowd"][d].mean(1)[10:46]]))
    return out


@app.get("/api/stop/{key}")
def stop(key: str, time: str | None = None, day: str | None = None):
    k = find_stop(key)
    d = DAY.get(day or default_day(), 0)
    slot = (parse_time(time) // 30) % 48
    rows, prof = [], np.zeros(48)
    n = 0
    for rid, i in STOP_ROUTES[k]:
        r = ROUTES[rid]
        seg = min(i, len(r["stops"]) - 2)          # stretch leaving this stop (or arriving, at the last stop)
        col = r["crowd"][d, :, seg]
        now = float(col[slot])
        rows.append(dict(route_label(rid), crowd=round(now), level=level(now), tickets=r["tickets"],
                         stops_left=len(r["stops"]) - 1 - i, terminus=i == len(r["stops"]) - 1))
        if not r["low_data"]:
            prof += col
            n += 1
    rows.sort(key=lambda x: (x["terminus"], -x["tickets"]))
    prof = prof / max(n, 1)
    day_slots = range(12, 44)
    best = min(day_slots, key=lambda s: prof[s])
    worst = max(day_slots, key=lambda s: prof[s])
    s = STOPS[k]
    pt = TRAVEL.pts.get(k)
    if pt is None:      # a name used in more than one place: take this stop on its busiest route
        rid, i = max(STOP_ROUTES[k], key=lambda t: ROUTES[t[0]]["tickets"])
        pt = TRAVEL.point(rid, i)
    return dict(key=k, name=s["name"], volume=s["volume"], routes=rows[:40], route_count=len(rows),
                lat=round(pt[0], 5) if pt else None, lon=round(pt[1], 5) if pt else None,
                slot=fmt(slot * 30), hourly=[round(float(x)) for x in prof],
                best_time=fmt(best * 30), worst_time=fmt(worst * 30))


@app.get("/api/besttime")
def besttime(origin: str = Query(..., alias="from"), dest: str = Query(..., alias="to"), day: str | None = None):
    a, b = find_stop(origin), find_stop(dest)
    if a == b:
        raise HTTPException(400, "Origin and destination are the same stop")
    day = day or default_day()
    d = DAY.get(day, 0)
    cands = candidate_options(a, b)
    cands = ([o for o in cands if is_reliable(o)] or cands)[:16]
    if not cands:
        return dict(origin=STOPS[a]["name"], destination=STOPS[b]["name"], day=day, slots=[])
    slots = []
    for m in range(330, 1381, 30):           # 5:30 am to 11:00 pm
        opts = [evaluate(o, m, d) for o in cands]
        for o in opts:
            o["score"] = (o["minutes"] * (1 + 0.6 * o["crowd"] / 100) + 15 * o["transfers"]
                          + (25 if o["confidence"] == "low" else 0))
        o = min(opts, key=lambda x: x["score"])
        slots.append(dict(depart=fmt(m), crowd=o["crowd"], minutes=o["minutes"], level=o["level"],
                          routes=[l["route"]["number"] for l in o["legs"]], seat_chance=o["seat_chance"],
                          fare=o["fare"]))
    day_part = [s for s in slots if 360 <= m2s(s["depart"]) <= 1320]
    best = min(day_part, key=lambda s: (s["crowd"], s["minutes"]))
    worst = max(day_part, key=lambda s: s["crowd"])
    return dict(origin=STOPS[a]["name"], destination=STOPS[b]["name"], day=day, slots=slots,
                best=best, worst=worst)


@app.get("/api/validation")
def validation():
    v = json.loads((ROOT / "data" / "validation.json").read_text())
    sp = ROOT / "data" / "speeds.json"
    v["travel"] = dict(
        speeds=json.loads(sp.read_text()) if sp.exists() else None,
        geometry=TRAVEL.stats,
        tickets_timed_by_route_geometry=TRAVEL.coverage(ROUTES),
    )
    fc = ROOT / "data" / "fares_check.json"
    v["fares"] = json.loads(fc.read_text()) if fc.exists() else None
    tot = sum(r["tickets"] for r in ROUTES.values())
    v["schedule"] = dict(routes=len(SCHED), departures=int(sum(len(x[0]) for x in SCHED.values())),
                         tickets_share=round(sum(ROUTES[k]["tickets"] for k in SCHED if k in ROUTES) / tot, 4))
    st = ROOT / "data" / "stability.json"
    v["stability"] = json.loads(st.read_text()) if st.exists() else None
    return v


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="static")
