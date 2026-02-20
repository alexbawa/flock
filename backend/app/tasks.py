import json
import logging
import re
import statistics

from amadeus import Client, ResponseError
from celery import shared_task
from flask import current_app

from app.db import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_duration_minutes(duration: str) -> int:
    """Convert an ISO 8601 duration string (e.g. 'PT10H30M') to minutes."""
    hours = int(re.search(r"(\d+)H", duration).group(1)) if "H" in duration else 0
    mins = int(re.search(r"(\d+)M", duration).group(1)) if "M" in duration else 0
    return hours * 60 + mins


def _in_time_window(dt_str: str, window: dict | None) -> bool:
    """Return True if the HH:MM portion of dt_str falls within window."""
    if window is None:
        return True
    time_part = dt_str.split("T")[1][:5]  # "2024-11-01T10:40:00" → "10:40"
    return window["earliest"] <= time_part <= window["latest"]


def _passes_filters(offer: dict, filters: dict) -> bool:
    """Return True if the offer satisfies all post-response filters."""
    itineraries = offer["itineraries"]
    outbound_segs = itineraries[0]["segments"]
    return_segs = itineraries[1]["segments"]

    if len(outbound_segs) - 1 > filters["max_stops"]:
        return False
    if len(return_segs) - 1 > filters["max_stops"]:
        return False

    if not _in_time_window(outbound_segs[0]["departure"]["at"], filters.get("outbound_departure_window")):
        return False
    if not _in_time_window(outbound_segs[-1]["arrival"]["at"], filters.get("outbound_arrival_window")):
        return False
    if not _in_time_window(return_segs[0]["departure"]["at"], filters.get("return_departure_window")):
        return False
    if not _in_time_window(return_segs[-1]["arrival"]["at"], filters.get("return_arrival_window")):
        return False

    return True


def _build_flight_option(itinerary: dict, price: float) -> dict:
    segments = itinerary["segments"]
    return {
        "departure_time": segments[0]["departure"]["at"],
        "arrival_time": segments[-1]["arrival"]["at"],
        "duration_minutes": _parse_duration_minutes(itinerary["duration"]),
        "stops": len(segments) - 1,
        "airline": segments[0]["carrierCode"],
        "flight_numbers": [seg["carrierCode"] + seg["number"] for seg in segments],
        "price": price,
    }


def _compute_group_stats(individual_totals: list, currency: str) -> dict:
    total = sum(individual_totals)
    return {
        "currency": currency,
        "individual_totals": individual_totals,
        "total": total,
        "average": total / len(individual_totals),
        "median": statistics.median(individual_totals),
        "cheapest": min(individual_totals),
        "most_expensive": max(individual_totals),
    }


def _get_destination_name(client: Client, iata_code: str) -> str:
    try:
        response = client.reference_data.locations.get(keyword=iata_code, subType="AIRPORT")
        if response.data:
            return response.data[0].get("address", {}).get("cityName", iata_code)
    except Exception:
        logger.warning("Could not resolve city name for %s, using IATA code", iata_code)
    return iata_code


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@shared_task
def run_flock_job(job_id: str) -> None:
    logger.info("[%s] Worker picked up job", job_id)
    db = get_db()

    try:
        # Fetch submission
        with db.cursor() as cur:
            cur.execute("select submission from jobs where id = %s", (job_id,))
            row = cur.fetchone()
        if row is None:
            raise ValueError(f"Job {job_id} not found in database")
        submission = row[0]

        # Mark running
        with db:
            with db.cursor() as cur:
                cur.execute("update jobs set status = 'running' where id = %s", (job_id,))
        logger.info("[%s] Status set to running", job_id)

        # Init Amadeus client
        amadeus = Client(
            client_id=current_app.config["AMADEUS_CLIENT_ID"],
            client_secret=current_app.config["AMADEUS_CLIENT_SECRET"],
        )

        travelers = submission["travelers"]
        destinations = submission["destinations"]
        outbound_date = submission["outbound_date"]
        return_date = submission["return_date"]

        # Resolve destination city names
        dest_names = {dest: _get_destination_name(amadeus, dest) for dest in destinations}

        # Fan out: traveler × destination
        results_by_dest: dict[str, list] = {}

        for traveler in travelers:
            name = traveler["name"]
            origin = traveler["origin_airport"]
            filters = traveler["filters"]
            excluded = filters.get("excluded_airlines", [])

            for destination in destinations:
                call_kwargs = {
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "departureDate": outbound_date,
                    "returnDate": return_date,
                    "adults": 1,
                    "nonStop": filters["non_stop_only"],
                }
                if excluded:
                    call_kwargs["excludedAirlineCodes"] = ",".join(excluded)

                try:
                    response = amadeus.shopping.flight_offers_search.get(**call_kwargs)
                    logger.info("[%s] Amadeus call: %s -> %s on %s", job_id, origin, destination, outbound_date)
                except ResponseError as e:
                    logger.warning("[%s] Amadeus error for %s -> %s: %s", job_id, origin, destination, e)
                    continue

                valid = [o for o in response.data if _passes_filters(o, filters)]
                logger.info(
                    "[%s] %s -> %s: %d offer(s) returned, %d after filtering",
                    job_id, origin, destination, len(response.data), len(valid),
                )
                if not valid:
                    continue

                best = min(valid, key=lambda o: float(o["price"]["total"]))
                total_price = float(best["price"]["total"])
                currency = best["price"]["currency"]
                leg_price = total_price / 2

                traveler_flight = {
                    "traveler_name": name,
                    "origin": origin,
                    "outbound": _build_flight_option(best["itineraries"][0], leg_price),
                    "return": _build_flight_option(best["itineraries"][1], leg_price),
                    "total_price": total_price,
                    "currency": currency,
                }
                results_by_dest.setdefault(destination, []).append(traveler_flight)

        # Aggregate — only include destinations where every traveler has a flight
        destination_results = []
        for dest, traveler_flights in results_by_dest.items():
            if len(traveler_flights) != len(travelers):
                logger.warning(
                    "[%s] Excluding %s: only %d/%d travelers have valid flights",
                    job_id, dest, len(traveler_flights), len(travelers),
                )
                continue

            currencies = {tf["currency"] for tf in traveler_flights}
            if len(currencies) > 1:
                logger.warning("[%s] Mixed currencies for %s: %s", job_id, dest, currencies)
            currency = traveler_flights[0]["currency"]

            individual_totals = [tf["total_price"] for tf in traveler_flights]
            destination_results.append({
                "destination": dest,
                "destination_name": dest_names.get(dest, dest),
                "traveler_flights": traveler_flights,
                "group_stats": _compute_group_stats(individual_totals, currency),
            })

        job_result = {
            "job_id": job_id,
            "status": "complete",
            "completed_at": None,  # set by the DB timestamp below
            "error": None,
            "destinations": destination_results,
        }

        # Write results and mark complete
        with db:
            with db.cursor() as cur:
                cur.execute(
                    "insert into results (job_id, data) values (%s, %s)",
                    (job_id, json.dumps(job_result)),
                )
                cur.execute(
                    "update jobs set status = 'complete', completed_at = now() where id = %s",
                    (job_id,),
                )

        logger.info("[%s] Job complete — %d destination(s)", job_id, len(destination_results))

    except Exception:
        logger.exception("[%s] Job failed", job_id)
        try:
            import traceback
            error_msg = traceback.format_exc()
            with db:
                with db.cursor() as cur:
                    cur.execute(
                        "update jobs set status = 'failed', error = %s where id = %s",
                        (error_msg, job_id),
                    )
        except Exception:
            logger.exception("[%s] Failed to write failure status to DB", job_id)
        raise
