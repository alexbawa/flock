#!/usr/bin/env python3
"""Smoke-test for the Amadeus API connection.

Run from the backend/ directory:
    python test_amadeus.py

Requires AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET in the environment.
If python-dotenv is installed, values are also loaded from backend/.env.
"""
import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from amadeus import Client, ResponseError

client_id = os.environ.get("AMADEUS_CLIENT_ID")
client_secret = os.environ.get("AMADEUS_CLIENT_SECRET")

if not client_id or not client_secret:
    print("ERROR: AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET must be set in the environment.")
    sys.exit(1)

client = Client(client_id=client_id, client_secret=client_secret)

ORIGIN = "JFK"
DESTINATION = "CUN"
DEPARTURE_DATE = "2026-04-15"
RETURN_DATE = "2026-04-22"

print(f"Searching {ORIGIN} → {DESTINATION}  {DEPARTURE_DATE} / {RETURN_DATE} …")

try:
    response = client.shopping.flight_offers_search.get(
        originLocationCode=ORIGIN,
        destinationLocationCode=DESTINATION,
        departureDate=DEPARTURE_DATE,
        returnDate=RETURN_DATE,
        adults=1,
    )
except ResponseError as e:
    print(f"Amadeus API error: {e}")
    sys.exit(1)

offers = response.data
print(f"\n{len(offers)} offer(s) returned.")

if not offers:
    print("No offers — try a different date.")
    sys.exit(0)

print("\n--- First offer (pretty-printed) ---")
print(json.dumps(offers[0], indent=2))
