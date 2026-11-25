# Seat Signal: technical note

Transport Stack Hackathon 2026, Delhi. Problem 2, Phase 1.

This note covers how we turn tickets into crowding, what we assume, and where the numbers are weakest. The full set of checks is in `docs/validation.md` in the repo, and the app shows them on its "How we know" page.

## Method

**Cleaning.** The October file has 2,559,899 e-tickets. We clean stop names ("Bdr" becomes "Border", "(T)" is dropped) and keep 2,523,265 tickets (98.6%). The rest start and end at the same stop, travel against the route's stop order, or use a stop seen fewer than 5 times on that route.

**Stop order.** Tickets carry stop names but no sequence. We match each route to the same route in the Delhi bus GTFS (the current feed, version 32, from Delhi Transport Stack), comparing names only against that route's own stops. Stops the GTFS can't place go where their riders' tickets put them. Routes the GTFS doesn't have get an order from ticket start and end pairs. 98.4% of tickets are on GTFS-ordered routes.

**Riders on board.** Each ticket adds its `passenger_count` to every stretch from its start stop to its end stop, moving forward about 2.5 minutes per stop. We sum this over October and divide by the number of days of each type (weekday, Saturday, Sunday or holiday). That gives the average riders on board for every route, direction, stretch and half hour.

The brief suggests grouping tickets by bus trip and keeping a running count. About half the tickets have no vehicle number, so we can't rebuild individual trips reliably. We keep the running count per route and half hour instead, which gives the same answer averaged over all the buses on that route.

**Crowd index.** E-tickets are only part of the ridership, so raw counts aren't bus loads. We use a 0 to 100 index: `100 × log(1 + load) / log(1 + cap)`, where `cap` is 1.3 times the 99.9th percentile of daytime weekday stretch loads across the network. Under 35 is Comfortable, under 60 Moderate, under 80 Busy, and the rest Packed. The seat chance shown in the app comes from the index where you board.

**Travel time.** Each stretch's length comes from GTFS stop positions. Its speed is how fast GPS-tracked buses moved through that 1 km grid cell in that half hour, stops at signals included and layovers at terminals left out (GPS from 14, 15, 16 and 18 October). The map draws each ride along the route's road path from the GTFS `shapes.txt`.

**Waiting.** From the GTFS timetable (65,116 departures, 98.4% of tickets), shifted to each stop by its scheduled running time, we take how often a bus comes and the average wait for someone arriving around their chosen time. It is part of every trip time. A change of bus adds a 3-minute walk plus the wait for the next bus, and is only offered where both routes stop at the same place, because 140 stop names exist in more than one part of Delhi.

**Fare.** For each route, the fare for riding a given number of stops is the price most October e-tickets paid for that ride. It matches the exact price paid on 78.6% of tickets, with a typical error of ₹1.08.

**Live buses.** When planning for now, the app reads the Transport Stack GTFS-Realtime feed (about 6,100 buses), places each bus at its nearest stop and times the nearest one coming towards the rider's stop with the same GPS speeds. On 25 November, 94.6% of tickets were on routes with a live bus.

## Checks against known patterns

| What we checked | Result |
|---|---|
| Morning peak, 8 to 11 am, against midday | 4.2 times busier; busiest half hour 9:00 am |
| Evening peak, 5 to 9 pm, against midday | 2.9 times busier; slowest buses 6 to 8 pm, 11.2 km/h |
| Weekday, Saturday, Sunday or holiday | 100,028, 79,496 and 49,155 e-tickets a day |
| Holidays found from the data alone | 2 and 20 October |
| Week to week, riders by route and half hour | correlation 0.88 or more between any two weeks; morning peak 3.5 to 4.0 times midday every week |
| Stop order, independent of the tickets used to build it | 99.7% of 2.4 million tickets between two GTFS stops ride forwards |
| Speeds for 16 October predicted from 14 and 15 October | 9.7% typical error |

## Assumptions

- **Riders missing from the data.** The file has only ONDC e-tickets: no conductor tickets, passes or free travel. We assume those riders follow the same pattern by route and hour, so the index compares crowding rather than counting heads.
- **Where people get off.** We take the end stop on the ticket as where the rider leaves. People who get off a stop early or late move crowding by a stretch or two, not the shape of the day.
- **Bus size.** There's no bus type in the data, so all buses count as the same size. The same load on a 9 m bus is more crowded than the index shows.
- **A usual day.** The app shows the October average for that kind of day and half hour. Waits assume buses keep to the timetable, which real buses often don't.

## Where it's least reliable

- Routes with fewer than 600 e-tickets in October. They're labelled "Limited data" and only appear in trip results when nothing better exists.
- Ring routes like the Mudrikas, where the stop order is hard to pin down.
- About 1.6% of tickets are on routes the current GTFS doesn't list. They're ordered from tickets and timed from their end stops.
- Saturday speeds (the average of weekday and Sunday), late nights, and anything seasonal like festivals or the monsoon.
