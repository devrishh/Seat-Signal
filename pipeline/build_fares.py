"""Fares from the e-tickets: what a ride on each route costs, by how many stops you ride.

Reads the ticket CSV and the built model's stop order, and writes data/fares.json:
{route id: [fare for riding 1 stop, 2 stops, ...]} in rupees per passenger.
E-ticket fares are the DTC fare less 10% (AC 9 / 13.5 / 18 / 22.5, non-AC 4.5 / 9 / 13.5).
Run after build_model.py:  python pipeline\\build_fares.py
"""
from __future__ import annotations

import gzip
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build_model import norm_stop  # noqa: E402  (same stop keys as the model)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MIN_TICKETS = 5        # a stop count needs this many tickets before its fare is trusted


def main(csv_path: str) -> None:
    M = pickle.load(gzip.open(DATA / "model.pkl.gz", "rb"))
    df = pd.read_csv(csv_path, usecols=["passenger_count", "amount", "route", "start_stop_name", "end_stop_name"],
                     dtype={"amount": "string", "route": "string"})
    df["fare"] = pd.to_numeric(df.amount, errors="coerce") / df.passenger_count
    df = df[(df.fare > 0) & df.route.isin(M["routes"].keys())].copy()
    names = pd.concat([df.start_stop_name, df.end_stop_name]).dropna().unique()
    key = {n: norm_stop(n) for n in names}
    df["a"], df["b"] = df.start_stop_name.map(key), df.end_stop_name.map(key)

    out, stats = {}, dict(routes=0, from_tickets=0, filled=0, tickets_used=0)
    for rid, g in df.groupby("route"):
        r = M["routes"][rid]
        pos = {s: i for i, s in enumerate(r["stops"])}
        n = g.b.map(pos) - g.a.map(pos)
        g = g.assign(n=n).dropna(subset=["n"])
        g = g[g.n > 0]
        size = len(r["stops"]) - 1
        if size < 1:
            continue
        fares = np.full(size, np.nan)
        for k, h in g.groupby("n"):
            if len(h) >= MIN_TICKETS and 1 <= k <= size:
                fares[int(k) - 1] = h.fare.round(1).mode().iloc[0]     # fares are fixed slabs: the commonest one
        seen = ~np.isnan(fares)
        stats["tickets_used"] += len(g)
        if not seen.any():
            if r.get("median_fare"):
                fares[:] = r["median_fare"]
            else:
                continue
        else:
            stats["from_tickets"] += int(seen.sum()); stats["filled"] += int((~seen).sum())
            s = pd.Series(fares).ffill().bfill().to_numpy()      # gaps take the nearest known slab
            fares = np.maximum.accumulate(s)                      # a longer ride never costs less
        out[rid] = [round(float(x) * 2) / 2 for x in fares]
        stats["routes"] += 1
    (DATA / "fares.json").write_text(json.dumps(out, separators=(",", ":")))

    # check: how often the table gives the price actually paid on each October e-ticket
    errs = []
    for rid, g in df.groupby("route"):
        if rid not in out:
            continue
        pos = {s: i for i, s in enumerate(M["routes"][rid]["stops"])}
        n = (g.b.map(pos) - g.a.map(pos)).dropna()
        n = n[n > 0].astype(int)
        errs.append(np.abs(np.array(out[rid])[n.values - 1] - g.fare.loc[n.index].values))
    e = np.concatenate(errs)
    stats.update(tickets_checked=int(len(e)), exact_share=round(float((e < 0.51).mean()), 4),
                 mean_abs_error_rs=round(float(e.mean()), 2), within_5_rs=round(float((e <= 5).mean()), 4))
    (DATA / "fares_check.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TICKETS_CSV", str(ROOT.parent / "October 2026 bus e-ticketing" / "October-Delhi.csv")))
