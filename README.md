# Flock 🐦

Find the best destination for a group flying from different origin airports.

## What it does

Planning a trip when everyone is flying from a different city is painful. Flock lets you enter a group of travelers with their respective origin airports, a list of candidate destinations, and travel dates. It fans out flight searches across all combinations and aggregates the results so the group can make an informed decision about where to meet.

## How it works

Trip submissions are processed as background jobs. Flock queries the Amadeus Flight Offers API for every traveler × destination permutation, applies per-traveler filters, and computes group-level stats (total, average, median, cheapest, most expensive) per destination.

## Stack

- **Frontend** — React, TypeScript, Vite — deployed on Vercel
- **Backend** — Flask, Celery — deployed on Railway
- **Queue** — Redis via Upstash
- **Database** — PostgreSQL via Supabase
- **Flight data** — Amadeus Flight Offers Search API

## Status

Under construction.