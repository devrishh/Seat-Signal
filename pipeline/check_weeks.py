"""Week-to-week check: do October's weekday patterns repeat from one week to the next?

Compares full weeks of weekdays (holidays left out) on riders per route and half hour.
Writes data/stability.json, shown on the app's "How we know" page.
Run:  python pipeline\check_weeks.py
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TICKETS_CSV", str(ROOT.parent / "October 2026 bus e-ticketing" / "October-Delhi.csv"))
HOLIDAYS = {pd.Timestamp("2026-10-02"), pd.Timestamp("2026-10-20")}   # found by build_model.py

df = pd.read_csv(CSV, usecols=["passenger_count", "route", "created_at"], dtype={"route": "string"})
ts = pd.to_datetime(df.created_at.str.slice(0, 19))
df["d"], df["slot"] = ts.dt.normalize(), ts.dt.hour * 2 + ts.dt.minute // 30
wk = df[(df.d.dt.dayofweek < 5) & (~df.d.isin(HOLIDAYS))].copy()
wk["week"] = wk.d.dt.isocalendar().week
days = wk.groupby("week").d.nunique()
full = [w for w in sorted(days.index) if days[w] >= 4]            # weeks with at least 4 working weekdays
per = (wk.groupby(["week", "route", "slot"]).passenger_count.sum() / days).rename("v").reset_index()
P = per.pivot_table(index=["route", "slot"], columns="week", values="v", fill_value=0)[full]
big = P[P.mean(axis=1) >= 5]                                         # route-half-hours with 5+ riders a day
c = big.corr().values
off = c[~np.eye(len(full), dtype=bool)]
rel = [float((np.abs(big[a] - big[b]) / ((big[a] + big[b]) / 2)).median()) for a, b in zip(full, full[1:])]
net = wk.groupby(["week", "slot"]).passenger_count.sum().unstack(0)[full]
tops = [set(wk[wk.week == w].groupby("route").passenger_count.sum().nlargest(20).index) for w in full]
out = dict(full_weeks=[int(w) for w in full], route_halfhours=len(big),
           corr_min=round(float(off.min()), 3), corr_mean=round(float(off.mean()), 3),
           median_rel_change=[round(e, 3) for e in rel],
           busiest_slot_by_week={int(w): int(net[w].idxmax()) for w in full},
           am_peak_vs_midday_by_week={int(w): round(float(net[w].iloc[16:22].mean() / net[w].iloc[22:32].mean()), 2) for w in full},
           top20_route_overlap=[len(tops[i] & tops[i + 1]) / 20 for i in range(len(tops) - 1)])
(ROOT / "data" / "stability.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out))
