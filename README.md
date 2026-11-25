# Seat Signal

A bus journey planner for Delhi that tells you how crowded each bus is likely to be, next to how long it takes and what it costs.

We built it for the Transport Stack Hackathon 2026, Delhi, Problem 2 (crowdedness-aware journey planner). Crowding comes from 2.5 million ONDC e-tickets from October 2026, and travel times from DTC bus GPS.

- Live app: https://dtc-seat-signal.vercel.app/
- Demo video: [docs/seat-signal-demo.mp4](docs/seat-signal-demo.mp4)
- Proposal: [docs/proposal.md](docs/proposal.md)
- Technical note: [docs/technical-note.md](docs/technical-note.md)
- Every check, with numbers: [docs/validation.md](docs/validation.md)

## Run it

You need Python 3.10 or newer. The built data (about 10 MB) is in the repo, so you don't need the raw data to run the app.

```bash
git clone https://github.com/devrishh/Seat-Signal.git
cd Seat-Signal
python -m pip install -r requirements.txt
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. To try it on a phone on the same Wi-Fi, open `http://<your computer's IP>:8000`. On Windows you can also double-click `run.bat`.

On some Windows machines `pip.exe` is blocked, which is why the commands use `python -m pip`.

Live bus positions need a Delhi Transport Stack API key for the GTFS-RT feed: put it in `ts_key.txt` (one line, kept out of git) or a `TS_API_KEY` environment variable. Without one, everything else works and the live parts stay hidden.

The map background comes from CARTO and needs an internet connection; everything else works offline. If you have a CARTO key, put it in `carto_key.txt` (one line) or in a `CARTO_KEY` environment variable. Without a key the maps still load.

### Hosting

The repo runs on Vercel as it is: `index.py` points Vercel to the app, and `.vercelignore` keeps the docs, pipeline and working files out of the deployment. For Render or Railway, `Procfile` has the start command: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`.

## What's in the app

- **Live buses.** When you plan for now, each trip shows where the next bus is ("4 stops away, due in about 6 min"), and route pages show the buses on the route, from the Delhi Transport Stack GTFS-Realtime feed.
- **Plan a trip.** Pick two stops and a time. Each bus option shows the trip time including the usual wait, how often the bus comes, how crowded it usually is, your chance of a seat, the fare, and a map with each stretch coloured by crowding. Sort by fastest, calmest or cheapest. If leaving a little earlier or later is much calmer, it tells you.
- **Best time to travel.** Your trip checked every half hour from 5:30 am to 11 pm.
- **Crowd right now.** The citywide crowding level, the busiest routes, the big routes with room, and the ones filling up fastest.
- **Routes and stops.** Crowding through the day for every route and stop, and along each route on a map.
- **How we know.** The checks behind the numbers, read live from the data.

The app follows the current time in Delhi. Use the time button at the top to plan for another day or time.

## Rebuild the data

You only need this if the raw data or the method changes. The raw files are too big for the repo: get the October ticket CSV, the GPS SQLite files and the Delhi bus GTFS from delhi.transportstack.in. Then, from the repo root:

```bash
python -m pip install -r requirements-pipeline.txt
export TICKETS_CSV=path/to/October-Delhi.csv        # Windows: set TICKETS_CSV=path\to\October-Delhi.csv

# 1. Bus speeds from GPS, one day at a time (about 45 s each), then combined
python pipeline/gps_speed.py path/to/bus_movements_2026_10_14.db work/gps/speed_2026_10_14.npz 3
#    repeat for the 15th, 16th and 18th
python pipeline/build_speeds.py

# 2. Crowding model from the tickets (about 30 s)
python pipeline/build_model.py

# 3. Stop order and distances from the GTFS (an unzipped GTFS folder)
python pipeline/build_geometry.py path/to/gtfs

# 4. Run the model again so it uses the GTFS stop order
python pipeline/build_model.py

# 5. Waiting times from the timetable, fares, and the week-to-week check
python pipeline/build_schedule.py path/to/gtfs
python pipeline/build_fares.py
python pipeline/check_weeks.py
```

The scripts write what the app reads into `data/`, and their working files into `work/`. The four GPS days and the stop order are already in `work/`, so steps 1 and 3 can be skipped if you only want to rerun the crowding.

## API

The app's data is also available as JSON. Interactive docs are at `/docs` on a running server.

| Endpoint | Returns |
|---|---|
| `/api/plan?from=&to=&time=HH:MM&day=weekday\|saturday\|sunday&prefer=balanced\|fastest\|comfort\|cheapest` | Trip options with time, crowding per stretch, seat chance, fare and a departure tip |
| `/api/besttime?from=&to=&day=` | The trip checked every half hour |
| `/api/stops?q=` | Stop search |
| `/api/stop/{key}?time=&day=` | Every route at a stop, with crowding |
| `/api/routes?q=` | Route search |
| `/api/route/{id}?time=&day=` | Crowding through the day and along the route |
| `/api/pulse?time=&day=` | Citywide crowding, busiest and calmest routes |
| `/api/validation` | All the checks |

## Project layout

```
backend/app.py       API and the website (FastAPI)
backend/travel.py    ride times from distances and GPS speeds
frontend/            HTML, CSS and JavaScript, no build step
data/                built data the app reads: crowding model, stop positions, speeds, fares, checks
pipeline/            scripts that build data/ from the raw files
work/                pipeline working files: GPS speeds per day, stop order
docs/                proposal, technical note, validation, demo video
index.py             entry point for Vercel
```

## Data and credits

- ONDC bus e-ticketing and DTC bus GPS, Delhi, October 2026: Transport Stack and IIIT Delhi.
- Delhi bus GTFS static, feed version 32 (DTC and DIMTS), from Delhi Transport Stack.
- Maps: [Leaflet](https://leafletjs.com) 1.9.4 (BSD-2-Clause), with CARTO basemap tiles of © OpenStreetMap contributors.
- Fonts: Hanken Grotesk and Archivo, SIL Open Font License.
