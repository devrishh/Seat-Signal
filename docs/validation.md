# Seat Signal: validation report (Phase 1)

Every figure here is produced by the pipeline and can be regenerated:
`data/validation.json` (crowding and stop order, from `pipeline/build_model.py`) and
`data/speeds.json` (travel speeds, from `pipeline/build_speeds.py`). The app shows the same
numbers on its *How we know* page, read live from `/api/validation`. Week-to-week stability comes from
`pipeline/check_weeks.py` (`data/stability.json`) and fares from `pipeline/build_fares.py`
(`data/fares_check.json`).

## 1. Data used

| | |
|---|---:|
| E-tickets in the October 2026 file | 2,559,899 |
| Tickets used in the crowding model | **2,502,990 (97.8%)** |
| Dropped: origin and destination are the same stop | 107 |
| Dropped: travel against the route's stop order | 28,518 (1.1%) |
| Dropped: noise stops (fewer than 5 tickets on that route) | the rest |
| Route directions modelled | 1,792 |
| Stops indexed (after cleaning names, e.g. "Bdr" → "Border", "(T)" removed) | 6,088 |
| Bus GPS used for speeds | 14, 15, 16 October (weekdays) and 18 October (Sunday) |
| Buses seen in the GPS per day | 6,032 – 6,103 |
| GPS pings per day in the files / used (every 3rd ping) | about 29 million / about 7.5 million |
| Static schedule (GTFS) for stop positions | Delhi bus GTFS, 2022–23 edition (DIMTS/DTC), Transitland archive |

## 2. Is the stop order right?

The ticket file has stop names but no stop sequence. Each route is lined up with the same
route in the Delhi bus GTFS, matching our stop names against that route's own stops only.
Stops the GTFS can't place are put where their riders' tickets say they belong. Routes the
GTFS doesn't know keep an order inferred from ticket start and end pairs.

| | |
|---|---:|
| Routes ordered by the GTFS | 1,125 of 1,792 (**84.7% of tickets**) |
| **Independent check:** tickets between two GTFS-placed stops that ride forwards | **99.4%** of 1,890,032 |
| All tickets that ride forwards, every route | 98.9% |
| Routes where at least 95% of tickets ride forwards | 92.4% |
| Busiest routes: 717A UP / DOWN, 729 DOWN / UP | 99.1% / 99.96%, 99.99% / 99.8% |

The independent check matters: the GTFS was made years earlier by a different organisation,
yet riders in October 2026 travel along it 99.4% of the time. If the matching were wrong,
about half of those tickets would appear to travel backwards.

Before the GTFS was added, the order inferred from tickets alone had 95.4% of tickets
riding forwards, but it put some stops in the wrong place (for example a Janakpuri stop
between ITO and Mandi House on route 740). That broke travel times and put crowding on the
wrong stretch. The GTFS order fixes both.

## 3. Travel times

A ride is timed stretch by stretch. Each stretch's **length** comes from the GTFS stop
positions along the route. Each stretch's **speed** is how fast GPS-tracked buses actually
moved through that ~1 km grid cell in that half hour, including time stopped at signals and
bus stops. Buses standing still for 10 minutes or more (layovers at terminals) are left out.

| | |
|---|---:|
| Tickets on routes with a measured length (GTFS path, or end-to-end distance × 1.375 detour) | **99.9%** |
| Weekday bus movement in grid cells with their own measured speed | 99.6% |
| **Held-out check:** 16 Oct speeds predicted from 14–15 Oct, typical (median) error | **9.7%** |
| Same check: share of bus movement predicted within 20% | 74.0% |

Average weekday bus speed across Delhi (km/h):

| 3 am | 7 am | 9 am | 12 pm | 3 pm | 6 pm | 7 pm | 9 pm | 11 pm |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 21.1 | 17.5 | 14.5 | 13.4 | 13.8 | **11.2** | 11.2 | 14.8 | 18.7 |

Sunday is faster through the day (14.7 km/h at noon, 13.2 at 6 pm).

Spot checks (weekday, from the app):

| Trip | Route | Distance | Time |
|---|---|---:|---:|
| Dhaula Kuan → ITO, 10:43 am | 720 | 9.7 km | 36 min |
| Dhaula Kuan → ITO, 6:30 pm | 720 | 9.7 km | 51 min |
| Anand Vihar ISBT → Uttam Nagar Terminal, 10:43 am | 740 NS | 37.1 km | about 2.5 h |

**Safeguards.** A change of bus is only offered where both routes really stop at the same
place: 140 stop names refer to more than one place in Delhi (there is more than one Ganesh
Nagar). A ride whose GTFS distance is shorter than the straight line between its end stops
is timed from the straight line instead. In a sweep of 900 random trips between the 400
busiest stops (5,790 options), none implied a speed below 5 or above 35 km/h, and only 5
came out shorter than 80% of the straight-line distance, all of them trips under 2 km where
stop positions differ by a few hundred metres. 99.8% of options were timed from GPS speeds.

## 4. Do the crowding peaks match known patterns?

Average weekday boardings per half hour:

| Window | Boardings per half hour | vs midday |
|---|---:|---:|
| Morning peak, 8–11 am | 5,767 | **4.2×** |
| Midday, 12–4 pm | 1,366 | 1.0× |
| Evening peak, 5–9 pm | 3,979 | **2.9×** |
| Late night, 10 pm–midnight | 456 | 0.3× |

The busiest weekday half hour is 9:00–9:30 am, and the slowest buses are at 6–8 pm, the
evening rush. Both line up with commute hours.

## 5. Weekday, weekend and holiday

| Day type | Days | Average e-tickets per day |
|---|---:|---:|
| Weekday | 20 | 100,028 |
| Saturday | 5 | 79,496 |
| Sunday or holiday | 6 | 49,155 |

Holidays were found from the data alone, as weekdays with under 70% of normal demand:
**2 October** (Gandhi Jayanti, 45,705 riders) and **20 October** (56,101 riders). Both are
modelled as Sunday-type days.

## 6. Week to week

The brief asks how estimates hold up from one week to the next. October has four full weeks of
weekdays (5–9, 12–16, 19–23 without the 20 October holiday, 26–30 October). For each week we
count average daily riders per route and half hour, and compare the weeks with each other
(5,322 route-half-hours with at least 5 riders a day).

| | |
|---|---:|
| Correlation between any two weeks, riders by route and half hour | **0.875 or higher** (average 0.892) |
| Typical (median) change in one route's half hour, week to next | 22–24% |
| Busiest weekday half hour, each week | 8:30 am (week 1), 9:00 am (weeks 2–4) |
| Morning rush (8–11 am) vs midday, each week | 3.5×, 4.0×, 3.9×, 4.0× |
| Of the 20 busiest routes, still in the top 20 the next week | 17, 17, 18 |

The shape of the day and the ranking of routes repeat every week. A single route's half hour
moves by about a fifth from week to week, mostly on small counts, which is why the app averages
all October days of the same type and labels thin routes.

## 7. Fares

For each route, the fare for riding a given number of stops is the most common price paid on
October e-tickets for that ride (needs 5 or more tickets; gaps take the nearest known step, and a
longer ride never costs less). E-ticket prices are the DTC fare less 10%: AC ₹9 / 13.50 / 18 /
22.50, non-AC ₹4.50 / 9 / 13.50, with higher fares on routes into Noida, Gurugram and other
neighbouring towns. A trip with a change of bus needs one ticket per bus.

| | |
|---|---:|
| E-tickets checked | 2,502,990 |
| Fare table gives the exact price paid | **75.1%** |
| Within ₹5 of the price paid | 96.4% |
| Typical (mean) error | ₹1.30 |

## 8. Known limits

- **E-tickets are a sample.** ONDC tickets are some of the riders, so the Crowd Index is
  relative, not a passenger count. Routes with fewer than 600 tickets are labelled "limited
  data" and are left out of trip results whenever better routes exist.
- **Saturday speeds** are the average of weekday and Sunday speeds; no Saturday GPS was
  processed (adding one more day file fixes this).
- **The GTFS is the 2022–23 edition.** About 15% of tickets are on newer routes it doesn't
  list (D-series, ML, 801 airport services). They are timed from the distance between their
  two end stops.
- **Times are in-bus times.** Waiting for the bus isn't included.
- **GPS route IDs aren't linked to ticket routes**, so speeds are measured per area of the
  city, not per route.
