"""In-bus travel time from real distances (Delhi bus GTFS) and real speeds (October 2026 GPS).

A ride from stop i to stop j on a route is timed stretch by stretch: each stretch's length
comes from the route's GTFS geometry, and its speed from the GPS speed of buses in that
~1 km grid cell during that half hour (data/speeds.npz), so a ride that starts at 8:50 and
crosses into the 9:00 rush slows down as it should.

Routes GTFS does not know: the distance is the straight line between the two end stops
times the detour factor measured on GTFS routes, at the speed along that line. Stops with
no known location fall back to a per-stop estimate, and the trip says so.
"""
from __future__ import annotations

import gzip
import math
import pickle
from pathlib import Path

import numpy as np


def _hav(la1, lo1, la2, lo2):
    la1, lo1, la2, lo2 = map(np.radians, (la1, lo1, la2, lo2))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def _fill(values: np.ndarray) -> np.ndarray | None:
    """Interpolate NaNs by index between known neighbours (ends hold the nearest value)."""
    ok = ~np.isnan(values)
    if ok.sum() < 2:
        return None
    idx = np.arange(len(values))
    return np.interp(idx, idx[ok], values[ok])


def fallback_minutes_per_stop(minute: float) -> float:
    """Used only for stops with no location at all."""
    h = int(minute // 60) % 24
    if 8 <= h < 11 or 17 <= h < 21:
        return 2.7
    if 7 <= h < 8 or 11 <= h < 12 or 16 <= h < 17 or 21 <= h < 22:
        return 2.3
    return 1.9


class RunTimes:
    """Stop-to-stop running times learned from real bus trips (data/runtimes.npz, built by
    pipeline/build_runtimes.py): minutes from leaving stop k to leaving stop k+1, by hour,
    for weekdays and Sundays. A negative value means "all-day median, too few trips that hour"."""

    def __init__(self, path):
        self.by: dict[str, np.ndarray] = {}
        p = Path(path)
        if p.exists():
            z = np.load(p)
            for n, rid in enumerate(z["rids"]):
                self.by[str(rid)] = np.abs(z[f"r{n}"].astype(np.float32))

    def stretch(self, rid: str, k: int, minute: float, d: int) -> float | None:
        a = self.by.get(rid)
        if a is None or k >= a.shape[2]:
            return None
        h = int(minute // 60) % 24
        if d == 1:                                            # Saturday: between a weekday and a Sunday
            v = np.nanmean([a[0, h, k], a[1, h, k]])
        else:
            v = a[1 if d == 2 else 0, h, k]
            if np.isnan(v):
                v = a[0 if d == 2 else 1, h, k]               # the other kind of day is better than nothing
        return None if np.isnan(v) else float(v)

    def minutes(self, rid: str, i: int, j: int, minute: float, d: int):
        t = float(minute)
        for k in range(i, j):
            v = self.stretch(rid, k, t, d)
            if v is None:
                return None
            t += v
        return t - minute


class Travel:
    # the grid-speed estimate ran about 9% slow against real trips (pipeline/check_runtimes.py), so it is scaled down
    GRID_CAL = 0.92

    def __init__(self, routes: dict, data_dir: Path):
        with gzip.open(data_dir / "geometry.pkl.gz", "rb") as f:
            G = pickle.load(f)
        z = np.load(data_dir / "speeds.npz")
        self.kmh = z["kmh"]                                   # [daytype, lat cell, lon cell, slot]
        self.lat0, self.lon0, self.cell = float(z["lat0"]), float(z["lon0"]), float(z["cell"])
        self.detour = float(G["detour"])
        self.stats = G["stats"]
        pts = G["stop_points"]
        self.pts = pts
        self.ambiguous = set(G.get("ambiguous", ()))
        self.rt = RunTimes(data_dir / "runtimes.npz")
        self.geo: dict[str, dict] = {}
        for rid, r in routes.items():
            stops = r["stops"]
            g = G["routes"].get(rid, {})
            own = {**pts, **g.get("pt", {})}      # the route's own GTFS stop beats the city-wide one
            lat = np.array([own[s][0] if s in own else np.nan for s in stops])
            lon = np.array([own[s][1] if s in own else np.nan for s in stops])
            entry = dict(source="none")
            if g.get("source") == "gtfs" and r.get("order_source") == "gtfs":
                km = np.array([g["km"].get(s, np.nan) for s in stops])
                km = _fill(km)
                la, lo = _fill(lat), _fill(lon)
                if km is not None and la is not None:
                    entry = dict(source="gtfs", km=np.maximum.accumulate(km), lat=la, lon=lo,
                                 own_lat=lat, own_lon=lon)
                    gp = np.array([g["pos"].get(s, np.nan) for s in stops], float) if "pos" in g else None
                    gp = _fill(gp) if gp is not None else None
                    if gp is not None:
                        entry["gpos"] = np.maximum.accumulate(gp)   # place of each stop on the GTFS path
                        entry["path"] = np.asarray(g["path"], float)
            if entry["source"] == "none" and (~np.isnan(lat)).sum() >= 2:
                entry = dict(source="stops", own_lat=lat, own_lon=lon)
            self.geo[rid] = entry

    # ------------------------------------------------------------------ speeds
    def speed(self, d: int, lat: float, lon: float, minute: float) -> float:
        i = int((lat - self.lat0) // self.cell)
        j = int((lon - self.lon0) // self.cell)
        s = int(minute // 30) % 48
        if 0 <= i < self.kmh.shape[1] and 0 <= j < self.kmh.shape[2]:
            return float(self.kmh[d, i, j, s])
        return float(np.median(self.kmh[d, :, :, s]))

    # ------------------------------------------------------------------ rides
    def ride(self, rid: str, stops: list[str], i: int, j: int, minute: float, d: int):
        """Returns (minutes at each stop i..j relative to boarding, km, source).
        Real trips first: each stretch the time buses actually took at that hour. A stretch no
        bus was seen on is filled from the grid estimate, scaled by how far off that runs."""
        times, km, source = self._grid_ride(rid, stops, i, j, minute, d)
        if self.rt.by.get(rid) is None:
            return [x * self.GRID_CAL for x in times], km, source
        t, out, filled = float(minute), [0.0], 0
        for k in range(i, j):
            v = self.rt.stretch(rid, k, t, d)
            if v is None:
                v = (times[k - i + 1] - times[k - i]) * self.GRID_CAL
                filled += 1
            t += v
            out.append(t - minute)
        return out, km, ("trips" if filled == 0 else "trips+estimate" if filled < (j - i) else source)

    def _grid_ride(self, rid: str, stops: list[str], i: int, j: int, minute: float, d: int):
        g = self.geo.get(rid, {"source": "none"})
        t, times = float(minute), [0.0]
        crow = None
        if g["source"] != "none" and not math.isnan(g["own_lat"][i]) and not math.isnan(g["own_lat"][j]):
            crow = float(_hav(g["own_lat"][i], g["own_lon"][i], g["own_lat"][j], g["own_lon"][j]))
        use_gtfs = g["source"] == "gtfs"
        if use_gtfs and crow is not None:
            along = float(g["km"][j] - g["km"][i])
            # a path shorter than the straight line, or wildly longer, means a stop was misplaced
            use_gtfs = 0.9 * crow <= along <= 3 * crow + 2
        if use_gtfs:
            km, la, lo = g["km"], g["lat"], g["lon"]
            for k in range(i, j):
                dist = float(km[k + 1] - km[k])
                if dist > 0:
                    v = self.speed(d, (la[k] + la[k + 1]) / 2, (lo[k] + lo[k + 1]) / 2, t)
                    t += dist / v * 60
                times.append(t - minute)
            return times, float(km[j] - km[i]), "gps"
        if crow is not None:
            la1, lo1, la2, lo2 = g["own_lat"][i], g["own_lon"][i], g["own_lat"][j], g["own_lon"][j]
            dist = crow * self.detour
            if dist >= 0.3:
                n = 6     # time the line in parts so the speed can follow the city and the clock
                for p in range(n):
                    f = (p + 0.5) / n
                    v = self.speed(d, la1 + f * (la2 - la1), lo1 + f * (lo2 - lo1), t)
                    t += dist / n / v * 60
                total = t - minute
                times = [total * (k - i) / (j - i) for k in range(i, j + 1)]
                return times, dist, "gps"
        for _ in range(i, j):
            t += fallback_minutes_per_stop(t)
            times.append(t - minute)
        return times, None, "estimate"

    def point(self, rid: str, i: int):
        """Where route rid's i-th stop is: its own GTFS stop, else its place along the GTFS path."""
        g = self.geo.get(rid)
        if not g or g["source"] == "none":
            return None
        if not math.isnan(g["own_lat"][i]):
            return float(g["own_lat"][i]), float(g["own_lon"][i])
        if g["source"] == "gtfs":
            return float(g["lat"][i]), float(g["lon"][i])
        return None

    def same_place(self, name: str, rid1: str, i: int, rid2: str, j: int, km: float = 0.8) -> bool:
        """Two routes share a stop name; is it really one place? Some names repeat across Delhi
        (there is more than one Ganesh Nagar), and a change of bus must not teleport."""
        a, b = self.point(rid1, i), self.point(rid2, j)
        if a is None or b is None:
            return name in self.pts and name not in self.ambiguous   # unverifiable: unique names only
        return float(_hav(a[0], a[1], b[0], b[1])) <= km

    # ------------------------------------------------------------------ maps
    def _on_path(self, g, x: float):
        """Point at fractional position x along the GTFS path."""
        P = g["path"]
        k = int(min(max(np.floor(x), 0), len(P) - 2)); f = x - k
        return P[k] * (1 - f) + P[k + 1] * f

    def shape(self, rid: str, i: int, j: int):
        """Map shape of a ride from stop i to j: one polyline per stretch between stops, the
        stops' positions, and whether the line is only approximate (straight between stops)."""
        g = self.geo.get(rid, {"source": "none"})
        pts = [self.point(rid, k) for k in range(i, j + 1)]
        r5 = lambda p: [round(float(p[0]), 5), round(float(p[1]), 5)]
        if g["source"] == "gtfs" and "gpos" in g:
            gp = g["gpos"]
            # do not draw a path that the time check rejected (a misplaced stop)
            a, b = self.point(rid, i), self.point(rid, j)
            along = float(g["km"][j] - g["km"][i])
            crow = float(_hav(a[0], a[1], b[0], b[1])) if a and b else None
            if crow is None or 0.9 * crow <= along <= 3 * crow + 2:
                segs = []
                for k in range(i, j):
                    x0, x1 = gp[k], gp[k + 1]
                    inner = [g["path"][m] for m in range(int(np.ceil(x0)), int(np.floor(x1)) + 1) if x0 < m < x1]
                    segs.append([r5(self._on_path(g, x0))] + [r5(p) for p in inner] + [r5(self._on_path(g, x1))])
                pts = [r5(self._on_path(g, gp[k])) for k in range(i, j + 1)]
                return dict(segments=segs, stops=pts, approx=False)
        known = [(k, p) for k, p in zip(range(i, j + 1), pts) if p]
        if len(known) < 2:
            return dict(segments=[], stops=[r5(p) if p else None for p in pts], approx=True)
        # straight lines between the stops we can place; unplaced stops sit evenly in between
        segs = []
        for k in range(i, j):
            prev = max((t for t in known if t[0] <= k), key=lambda t: t[0], default=None)
            nxt = min((t for t in known if t[0] >= k + 1), key=lambda t: t[0], default=None)
            if prev is None or nxt is None:
                segs.append([])
                continue
            a, b, span = np.array(prev[1]), np.array(nxt[1]), nxt[0] - prev[0]
            segs.append([r5(a + (b - a) * (k - prev[0]) / span), r5(a + (b - a) * (k + 1 - prev[0]) / span)])
        return dict(segments=segs, stops=[r5(p) if p else None for p in pts], approx=True)

    def walk_km(self, a: str, b: str):
        """Straight-line distance between two stop names, if both have one clear location."""
        if a in self.pts and b in self.pts:
            return float(_hav(*self.pts[a], *self.pts[b]))
        return None

    def coverage(self, routes: dict) -> dict:
        tot = sum(r["tickets"] for r in routes.values())
        by = {"gtfs": 0, "stops": 0, "none": 0}
        for rid, r in routes.items():
            by[self.geo[rid]["source"]] += r["tickets"]
        return {k: round(v / tot, 4) for k, v in by.items()}
