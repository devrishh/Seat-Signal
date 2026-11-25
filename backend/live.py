"""Live bus positions from the Delhi Transport Stack GTFS-Realtime feed (VehiclePositions).

The feed is a protobuf; this reads the few fields we need without extra packages.
The API key comes from the TS_API_KEY environment variable, or ts_key.txt next to the app
(kept out of git). Without a key, or if the feed can't be reached, live features stay hidden.
"""
from __future__ import annotations

import os
import struct
import threading
import time
import urllib.request
from pathlib import Path

FEED = ("https://dts-backend.transportstack.in/api/dataset/otd/get-file"
        "?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb")
CACHE_S = 20          # the feed updates every few seconds; one download serves everyone for 20 s
MAX_AGE_S = 300       # a bus not heard from for 5 minutes is left out


def _key(root: Path) -> str:
    k = os.environ.get("TS_API_KEY", "").strip()
    if not k and (root / "ts_key.txt").exists():
        k = (root / "ts_key.txt").read_text().strip()
    return k


def _fields(b: bytes, s: int = 0, e: int | None = None) -> dict[int, list]:
    """One protobuf message: field number -> list of values (ints, floats, or (start, end) spans)."""
    e = len(b) if e is None else e
    out: dict[int, list] = {}
    i = s
    while i < e:
        k = sh = 0
        while True:
            c = b[i]; i += 1; k |= (c & 127) << sh; sh += 7
            if c < 128:
                break
        f, t = k >> 3, k & 7
        if t == 0:
            v = sh = 0
            while True:
                c = b[i]; i += 1; v |= (c & 127) << sh; sh += 7
                if c < 128:
                    break
        elif t == 1:
            v = struct.unpack_from("<d", b, i)[0]; i += 8
        elif t == 5:
            v = struct.unpack_from("<f", b, i)[0]; i += 4
        elif t == 2:
            n = sh = 0
            while True:
                c = b[i]; i += 1; n |= (c & 127) << sh; sh += 7
                if c < 128:
                    break
            v = (i, i + n); i += n
        else:
            break
        out.setdefault(f, []).append(v)
    return out


def parse(b: bytes) -> tuple[int, list[dict]]:
    """FeedMessage -> (feed timestamp, [{route, lat, lon, ts, plate}])."""
    top = _fields(b)
    hdr = _fields(b, *top[1][0]) if 1 in top else {}
    txt = lambda span: b[span[0]:span[1]].decode("utf-8", "replace")
    buses = []
    for span in top.get(2, []):
        ent = _fields(b, *span)
        if 4 not in ent:
            continue
        v = _fields(b, *ent[4][0])
        trip = _fields(b, *v[1][0]) if 1 in v else {}
        pos = _fields(b, *v[2][0]) if 2 in v else {}
        veh = _fields(b, *v[8][0]) if 8 in v else {}
        if 5 not in trip or 1 not in pos or 2 not in pos:
            continue
        plate = txt(veh[3][0]) if 3 in veh else txt(veh[1][0]) if 1 in veh else ""
        buses.append(dict(route=txt(trip[5][0]), lat=float(pos[1][0]), lon=float(pos[2][0]),
                          ts=int(v[5][0]) if 5 in v else 0, plate=plate))
    return int(hdr[3][0]) if 3 in hdr else 0, buses


class Live:
    def __init__(self, root: Path, route_map: dict[str, str]):
        self.key = _key(root)
        self.route_map = route_map          # GTFS route_id -> our route id
        self.at, self.by_route, self.feed_ts = 0.0, {}, 0
        self.lock = threading.Lock()

    @property
    def on(self) -> bool:
        return bool(self.key and self.route_map)

    def buses(self) -> dict[str, list[dict]]:
        """Our route id -> buses on it now. Empty if the feed can't be reached."""
        if not self.on:
            return {}
        with self.lock:
            if time.time() - self.at < CACHE_S:
                return self.by_route
            self.at = time.time()           # also rate-limits retries when the feed is down
            try:
                req = urllib.request.Request(FEED, headers={"x-api-key": self.key})
                with urllib.request.urlopen(req, timeout=6) as r:
                    ts, buses = parse(r.read())
            except Exception:
                return self.by_route         # keep the last good copy for a while
            now = ts or int(time.time())
            out: dict[str, list[dict]] = {}
            for x in buses:
                rid = self.route_map.get(x["route"])
                if rid and now - x["ts"] <= MAX_AGE_S:
                    x["age"] = max(0, now - x["ts"])
                    out.setdefault(rid, []).append(x)
            self.by_route, self.feed_ts = out, now
            return out
