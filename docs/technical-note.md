# Seat Signal: technical note

Transport Stack Hackathon 2026, Delhi. Problem 2, Phase 1.

How we turn tickets into crowding, what we assume, and where the numbers are weakest. All checks are in `docs/validation.md` and on the app's "How we know" page.

## Method

**Cleaning.** The October file has 2,559,899 e-tickets. We clean stop names ("Bdr" becomes "Border", "(T)" is dropped) and keep 2,523,265 tickets (98.6%). The rest start and end at the same stop, ride against the stop order, or use a stop seen under 5 times on that route.

**Stop order.** Tickets carry stop names but no sequence. We match each route to the same route in the Delhi bus GTFS (the current feed, version 32, from Delhi Transport Stack), comparing names only against that route's own stops. Stops the GTFS can't place go where their riders' tickets put them. Routes the GTFS doesn't have get an order from ticket start and end pairs. 98.4% of tickets are on GTFS-ordered routes.

**Riders on board.** Each ticket adds its `passenger_count` to every stretch from its start stop to its end stop, moving forward about 2.5 minutes per stop. We sum this over October and divide by the number of days of each type (weekday, Saturday, Sunday or holiday). That gives the average riders on board for every route, direction, stretch and half hour.

The brief suggests a running count per bus trip, but about half the tickets have no vehicle number, so we keep it per route and half hour: the same answer averaged over that route's buses.

**Crowd index.** E-tickets are only part of the ridership, so raw counts aren't bus loads. We use a 0 to 100 index: `100 × log(1 + load) / log(1 + cap)`, where `cap` is 1.3 times the 99.9th percentile of daytime weekday stretch loads across the network. Under 35 is Comfortable, under 60 Moderate, under 80 Busy, and the rest Packed. The seat chance shown in the app comes from the index where you board.

**Travel time.** We followed every GPS-tracked bus trip on 14, 15, 16 and 18 October (about 280,000 trips, 4.4 million stop arrivals) along its route, noting when it reached and left each stop. Each stretch between two stops is timed by the median time buses really took there in that hour, stops at signals and bus stops included. Stretches no bus was seen on (2% of tickets' routes) fall back to the route's length and the area's GPS speed. The map draws each ride along the route's road path from the GTFS `shapes.txt`.

**Waiting.** When planning for now and the live feed shows the next bus coming, the wait is that bus's real arrival. Otherwise it comes from the GTFS timetable (65,116 departures, 98.4% of tickets): how often a bus comes and the average wait for someone arriving around their chosen time.

**Stops a short walk apart.** The same spot often has several names (968 spots in the data, about 40% of boardings), each with its own routes. Trips can start or end at any stop within 250 m and change buses between stops within 150 m, with the walk added. A change also adds a 3-minute walk and the wait for the next bus.

**Fare.** For each route, the fare for riding a given number of stops is the price most October e-tickets paid for that ride. It matches the exact price paid on 78.6% of tickets, with a typical error of ₹1.08.

**Live buses.** From the Transport Stack GTFS-Realtime feed (about 6,100 buses), each bus is placed at its nearest stop and the next one coming is timed with the same stop-to-stop times. On 25 November, 94.6% of tickets were on routes with a live bus.

## Checks against known patterns

| What we checked | Result |
|---|---|
| Morning peak, 8 to 11 am, against midday | 4.2 times busier; busiest half hour 9:00 am |
| Evening peak, 5 to 9 pm, against midday | 2.9 times busier; slowest buses 6 to 8 pm, 11.2 km/h |
| Weekday, Saturday, Sunday or holiday | 100,028, 79,496 and 49,155 e-tickets a day |
| Holidays found from the data alone | 2 and 20 October |
| Week to week, riders by route and half hour | correlation 0.88 or more between any two weeks; morning peak 3.5 to 4.0 times midday every week |
| Stop order, independent of the tickets used to build it | 99.7% of 2.4 million tickets between two GTFS stops ride forwards |
| Ride times for 6,000 real rides on 16 October, from a model built without that day | typical error 1.7 min (median ride 15 min); 80% within 5 min. The earlier speed-map method: 2.7 min, 70% |

## Assumptions

- **Riders missing from the data.** The file has only ONDC e-tickets: no conductor tickets, passes, or women riding free on the Pink pass. We assume those riders follow the same pattern by route and hour, so the index compares crowding rather than counting heads.
- **Where people get off.** We take the end stop on the ticket as where the rider leaves. People who get off a stop early or late move crowding by a stretch or two, not the shape of the day.
- **Bus size.** There's no bus type in the data, so all buses count as the same size. The same load on a 9 m bus is more crowded than the index shows.
- **A usual day.** The app shows the October average for that kind of day and half hour. Waits assume buses keep to the timetable, which real buses often don't.

## Where it's least reliable

- Routes with fewer than 600 e-tickets in October. They're labelled "Limited data" and only appear in trip results when nothing better exists.
- Ring routes like the Mudrikas, where the stop order is hard to pin down.
- About 1.6% of tickets are on routes the GTFS doesn't list, timed from their end stops; and Saturdays (weekday and Sunday averaged), late nights, unusual traffic, festivals and the monsoon.
