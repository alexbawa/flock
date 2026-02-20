# Flock — Claude Code Context

## What is Flock?

Flock is a personal tool for finding the best flight destination for a group of travelers flying from different origin airports. Users submit a trip (travelers + origins, candidate destinations, dates, filters), it fans out flight searches across all combinations via the Amadeus API, and surfaces aggregated results so the group can decide where to meet.

## Architecture

- **Frontend** — React, TypeScript, Vite (`frontend/`)
- **Backend** — Flask + Celery (`backend/`), same repo deployed as two separate processes
- **Queue** — Redis (Upstash) — message broker between Flask and Celery
- **Database** — PostgreSQL (Supabase)
- **Flight data** — Amadeus Flight Offers Search API v2

### How the pieces connect

```
React
  ↕ HTTP polling
Flask (Job Manager)
  ↕ reads/writes          ↕ enqueues
Supabase              Redis
                          ↕ picks up
                      Celery (Job Runner)
                          ↕ reads/writes
                      Supabase
```

Flask is the REST API the frontend talks to. Celery is a background worker that never handles HTTP — it picks jobs off the Redis queue, fans out Amadeus calls, and writes results back to Supabase.

## Data Flow

1. User submits a trip on the frontend
2. Frontend resolves per-traveler filters from group defaults and POSTs to Flask
3. Flask writes a `pending` job to Supabase and enqueues a Celery task
4. Frontend polls `GET /jobs/{id}` every 3 seconds
5. Celery fans out Amadeus Flight Offers Search calls for every traveler × destination permutation
6. Amadeus-native filters applied at query time; stop count and time window filters applied post-response
7. Results aggregated per destination, group stats computed, written to Supabase
8. Job status set to `complete`, frontend poll detects this and renders results

## Schemas

### TripSubmission

```typescript
type TripSubmission = {
  id: string
  created_at: string
  travelers: Traveler[]
  destinations: string[]        // IATA codes e.g. ["CUN", "MBJ"]
  outbound_date: string         // YYYY-MM-DD
  return_date: string           // YYYY-MM-DD
  default_filters: SearchFilters
}

type Traveler = {
  name: string
  origin_airport: string        // IATA code e.g. "JFK"
  filters: SearchFilters        // always fully populated — copied from default_filters, optionally overridden per traveler
}

type SearchFilters = {
  non_stop_only: boolean                        // maps directly to Amadeus `nonStop` query param
  excluded_airlines: string[]                   // maps to Amadeus `excludedAirlineCodes`, joined as comma-separated string at call time
  outbound_departure_window: TimeWindow | null  // post-response filter in Celery
  outbound_arrival_window: TimeWindow | null    // post-response filter in Celery
  return_departure_window: TimeWindow | null    // post-response filter in Celery
  return_arrival_window: TimeWindow | null      // post-response filter in Celery
}

type TimeWindow = {
  earliest: string              // "06:00"
  latest: string                // "22:00"
}
```

### JobResult

```typescript
type JobResult = {
  job_id: string
  status: "pending" | "running" | "complete" | "failed"
  completed_at: string | null
  error: string | null
  destinations: DestinationResult[]
}

type DestinationResult = {
  destination: string           // IATA code
  destination_name: string
  traveler_flights: TravelerFlight[]
  group_stats: GroupStats
}

type TravelerFlight = {
  traveler_name: string
  origin: string
  outbound: FlightOption
  return: FlightOption
  total_price: number
  currency: string
}

type FlightOption = {
  departure_time: string
  arrival_time: string
  duration_minutes: number
  stops: number
  airline: string
  flight_numbers: string[]
  price: number
}

type GroupStats = {
  currency: string
  individual_totals: number[]
  total: number
  average: number
  median: number
  cheapest: number
  most_expensive: number
}
```

## Filter Application

| Filter | Where applied |
|---|---|
| `non_stop_only` | Amadeus query param (`nonStop`) |
| `excluded_airlines` | Amadeus query param (`excludedAirlineCodes`) |
| `max_stops` | Post-response in Celery worker |
| `outbound_departure_window` | Post-response in Celery worker |
| `outbound_arrival_window` | Post-response in Celery worker |
| `return_departure_window` | Post-response in Celery worker |
| `return_arrival_window` | Post-response in Celery worker |

## Database Tables

### jobs
| column | type | notes |
|---|---|---|
| id | uuid | primary key |
| status | text | pending / running / complete / failed |
| created_at | timestamp | |
| completed_at | timestamp | nullable |
| submission | jsonb | full TripSubmission payload |
| error | text | nullable |

### results
| column | type | notes |
|---|---|---|
| job_id | uuid | foreign key → jobs.id |
| data | jsonb | full JobResult payload |

## Environment Variables

```
AMADEUS_CLIENT_ID
AMADEUS_CLIENT_SECRET
SUPABASE_DB_URL
REDIS_URL
```

## Key Decisions

- Each Amadeus call uses `adults=1` — travelers search independently, one call per traveler × destination
- The frontend is responsible for copying `default_filters` into each traveler's `filters` before submission — the backend always receives fully resolved per-traveler filters
- Job results are stored as a single JSONB blob — no normalization needed at this stage
- No authentication — this is a personal tool
- No destination ranking or flagging at this stage — raw data is surfaced to the frontend as-is
- `excludedAirlineCodes` is only passed to Amadeus when the list is non-empty — passing an empty string is invalid
- Destinations are excluded from results if any single traveler has no valid flight after filtering (the group can't all go there)
- Per-leg `price` on `FlightOption` = `total_price / 2` — Amadeus does not break down pricing per leg in the Flight Offers Search response; `total_price` on `TravelerFlight` is the authoritative figure
- Cheapest offer is selected per traveler × destination after post-response filtering
- Destination city names are resolved via `client.reference_data.locations.get(keyword=iata, subType='AIRPORT')` with fallback to the raw IATA code

## Conventions

### Database migrations
Every schema change requires a **new migration file** — never edit an existing one. Files live in `supabase/migrations/` and are named `NNNN_description.sql` (e.g. `0002_results_job_id_primary_key.sql`).

### Logging
- Never log credentials, passwords, or full connection URLs (they contain passwords). Use `urlparse` to log only `scheme://hostname`.
- Use `%s`-style format strings in all `logger.*()` calls (lazy evaluation — string is not formatted if the level is suppressed).
- Use `logger.exception()` inside `except` blocks to capture the full stack trace automatically.