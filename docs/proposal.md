# Seat Signal: proposal

Transport Stack Hackathon 2026, Delhi. Problem 2, crowdedness-aware journey planner.

Live app: https://dtc-seat-signal.vercel.app/  
Code: https://github.com/devrishh/Seat-Signal

## The problem we picked

Anyone who takes a DTC bus at 9 in the morning knows the question isn't only "which bus gets me there?" It's also "will I get on, and will I have to stand the whole way?" Journey planners in Delhi answer the first question and ignore the second.

We picked Problem 2 because the ticket data can answer the second one. Every ticket says where someone got on and where they meant to get off. Put a month of those together and you can see how full each bus usually is, stop by stop, at every time of day.

## What we built

Seat Signal is a website that works on phones and laptops. You pick two stops and a time, and it lists the bus options. Each option shows:

- how long the trip takes at that hour, including the usual wait for the bus (from the DTC timetable)
- how crowded the bus usually is, in words a commuter reads in a second (Comfortable, Moderate, Busy, Packed), and what that means for you ("seats likely", "expect to stand")
- your chance of getting a seat where you board
- the e-ticket fare
- when you plan for now, where the next bus is, from the live GPS feed
- a map with every stretch coloured by how full the bus is there

You can sort by fastest, calmest or cheapest. If leaving a bit earlier or later gives a much emptier bus, it says so. A separate page checks your trip every half hour of the day, so you can see the calm windows.

For people who run the buses, there's a page ranking the busiest routes at any hour, the big routes with room to spare, and the ones filling up fastest. Every route and stop has its own crowding strip for the whole day.


## How we estimate crowding

1. We clean the stop names in the 2.56 million October e-tickets ("Bdr" and "Border" are the same stop) and keep 2.52 million that make sense.
2. The tickets don't say which order the stops come in, so we line each route up with the same route in the Delhi bus GTFS. For routes the GTFS doesn't have, we work the order out from the tickets themselves, since nobody rides backwards.
3. Each ticket counts as one person on board on every stretch between their start and end stop, moving along the route in time.
4. We average that over October, separately for weekdays, Saturdays, and Sundays or holidays, giving riders on board for each route, direction, stretch and half hour.
5. E-tickets are only some of the riders, so we turn the load into a 0 to 100 crowd index calibrated across the whole network, then into the four levels above.

Travel times come from bus GPS: how fast buses really moved through each part of the city in each half hour, applied to the length of each stretch from the GTFS. Fares come from what people actually paid for the same ride.

## The data we used

- ONDC bus e-ticketing, 1 to 31 October 2026, from Transport Stack (2,559,899 tickets)
- DTC bus GPS for 14, 15, 16 and 18 October 2026, from Transport Stack
- Delhi bus GTFS, the current feed (version 32) from Delhi Transport Stack, for stop positions and stop order

## Does it hold up?

We checked the estimates against things we already know about Delhi's buses, and the app shows these checks on its "How we know" page:

- the morning rush (8 to 11 am) comes out 4.2 times busier than midday, and the busiest half hour is 9:00 am
- weekdays carry about twice the riders of Sundays, and the two October holidays (2 and 20 October) stand out on their own
- the four weeks of October look alike: riders by route and half hour correlate at 0.88 or more between any two weeks
- 99.7% of tickets between two timetable stops ride forwards along its order, so the stop order is right
- speeds for 16 October, predicted from the two days before, are off by 9.7% on a typical stretch

## What we'd do in Phase 2

- Add conductor (ETM) ticket counts to turn the crowd index into real numbers of people on board
- Rebuild individual bus trips from vehicle numbers where they exist, and use bus length (9 m or 12 m) so the same load reads right on both
- Learn real waits and today's delays from the live feed, instead of trusting the timetable
- Give operators a simple report of overloaded routes and hours, and where an extra bus would help most
