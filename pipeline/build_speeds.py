"""Seat Signal: combine per-day GPS totals into one bus speed table.

Input:  work/gps/speed_YYYY_MM_DD.npz from pipeline/gps_speed.py
Output: data/speeds.npz  kmh[daytype, lat cell, lon cell, slot]  (daytype 0 weekday,
        1 saturday, 2 sunday/holiday), plus how much GPS evidence backs each value.

Weekday speeds come from the weekday files, Sunday from the Sunday files. No Saturday was
processed, so Saturday is the average of weekday and Sunday speeds (stated in the app).
A cell needs MIN_SECONDS of bus movement in a half hour to use its own speed; otherwise
its 3 x 3 neighbourhood is pooled, and failing that the city-wide speed for that half hour.

Usage: python pipeline/build_speeds.py
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GPS = ROOT / "work" / "gps"
MIN_SECONDS = 600        # 10 bus-minutes in a cell and half hour before trusting its speed
LO_KMH, HI_KMH = 4, 45   # keep speeds physically sensible for city buses


def daytype(name: str) -> int:
    d = dt.date(*map(int, name.split("_")[1:4]))
    return 2 if d.weekday() == 6 else 1 if d.weekday() == 5 else 0


def pool(a):
    """Sum each cell with its 8 neighbours (same slot)."""
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)))
    return sum(p[1 + i: p.shape[0] - 1 + i, 1 + j: p.shape[1] - 1 + j] for i in (-1, 0, 1) for j in (-1, 0, 1))


def main():
    files = sorted(GPS.glob("speed_*.npz"))
    sums: dict[int, list] = {}
    meta = None
    days = {0: [], 1: [], 2: []}
    per_day = {}
    for f in files:
        z = np.load(f)
        per_day[f.stem.replace("speed_", "")] = dict(
            pings_sampled=int(z["pings"]), sample_every=int(z["mod"]), buses=int(z["buses"]),
            sum_d=z["sum_d"].astype(np.float64), sum_t=z["sum_t"].astype(np.float64))
        meta = meta or {k: float(z[k]) for k in ("lat0", "lon0", "cell")}
        t = daytype(f.stem)
        days[t].append(f.stem.replace("speed_", ""))
        d, s = sums.get(t, (0, 0))
        sums[t] = (d + z["sum_d"].astype(np.float64), s + z["sum_t"].astype(np.float64))
    kmh, evidence = [], []
    for t in (0, 2):
        d, s = sums[t]
        own = np.where(s >= MIN_SECONDS, d / np.maximum(s, 1) * 3.6, np.nan)
        pd_, ps = pool(d), pool(s)
        near = np.where(ps >= MIN_SECONDS, pd_ / np.maximum(ps, 1) * 3.6, np.nan)
        city = d.sum((0, 1)) / np.maximum(s.sum((0, 1)), 1) * 3.6
        v = np.where(np.isnan(own), near, own)
        v = np.where(np.isnan(v), city[None, None, :], v)
        kmh.append(np.clip(v, LO_KMH, HI_KMH).astype(np.float32))
        evidence.append(np.where(~np.isnan(own), 2, np.where(~np.isnan(near), 1, 0)).astype(np.int8))
    sat = (kmh[0] + kmh[1]) / 2
    K = np.stack([kmh[0], sat, kmh[1]])
    E = np.stack([evidence[0], np.minimum(evidence[0], evidence[1]), evidence[1]])
    np.savez_compressed(ROOT / "data" / "speeds.npz", kmh=K, evidence=E, **meta)
    summary = dict(
        days=days, saturday="average of weekday and Sunday speeds (no Saturday GPS processed)",
        min_seconds_per_cell=MIN_SECONDS,
        weekday_city_kmh_by_hour=[round(float(np.average(
            sums[0][0].sum((0, 1))[h * 2:h * 2 + 2]) / max(1, np.average(sums[0][1].sum((0, 1))[h * 2:h * 2 + 2])) * 3.6), 1)
            for h in range(24)],
        sunday_city_kmh_by_hour=[round(float(np.average(
            sums[2][0].sum((0, 1))[h * 2:h * 2 + 2]) / max(1, np.average(sums[2][1].sum((0, 1))[h * 2:h * 2 + 2])) * 3.6), 1)
            for h in range(24)],
        bus_time_in_cells_with_own_speed_weekday=float(sums[0][1][E[0] == 2].sum() / sums[0][1].sum()),
    )
    # held-out check: predict the last weekday's speeds from the other weekdays
    wk = [k for k in sorted(per_day) if daytype("x_" + k) == 0]
    if len(wk) >= 2:
        test, train = wk[-1], wk[:-1]
        td, tt = sum(per_day[k]["sum_d"] for k in train), sum(per_day[k]["sum_t"] for k in train)
        hd, ht = per_day[test]["sum_d"], per_day[test]["sum_t"]
        ok = (tt >= MIN_SECONDS) & (ht >= MIN_SECONDS)
        pred, obs = td[ok] / tt[ok], hd[ok] / ht[ok]
        err = np.abs(pred - obs) / obs
        w = ht[ok]
        o = np.argsort(err)
        cw = np.cumsum(w[o]) / w.sum()
        summary["holdout"] = dict(test_day=test, train_days=train, cells=int(ok.sum()),
                                  median_abs_pct_error=round(float(err[o][np.searchsorted(cw, 0.5)]) * 100, 1),
                                  within_20pct=round(float(w[err <= 0.2].sum() / w.sum()) * 100, 1))
    summary["per_day"] = {k: {x: v[x] for x in ("pings_sampled", "sample_every", "buses")} for k, v in per_day.items()}
    (ROOT / "data" / "speeds.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary)[:900])


if __name__ == "__main__":
    main()
