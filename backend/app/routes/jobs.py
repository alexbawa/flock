import json
import logging
import uuid

from flask import Blueprint, jsonify, request

from app.db import get_db
from app.tasks import run_flock_job

bp = Blueprint("jobs", __name__)
logger = logging.getLogger(__name__)

_TIME_WINDOW_FIELDS = (
    "outbound_departure_window",
    "outbound_arrival_window",
    "return_departure_window",
    "return_arrival_window",
)


def _validate_filters(f: dict, path: str) -> None:
    if not isinstance(f.get("non_stop_only"), bool):
        raise ValueError(f"{path}.non_stop_only must be a boolean")
    if not isinstance(f.get("excluded_airlines"), list):
        raise ValueError(f"{path}.excluded_airlines must be a list")
    for field in _TIME_WINDOW_FIELDS:
        window = f.get(field)
        if window is not None:
            if not isinstance(window, dict) or "earliest" not in window or "latest" not in window:
                raise ValueError(f"{path}.{field} must have 'earliest' and 'latest' fields")


def _validate_submission(data: dict) -> None:
    for field in ("travelers", "destinations", "outbound_date", "return_date", "default_filters"):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    if not isinstance(data["travelers"], list) or len(data["travelers"]) == 0:
        raise ValueError("travelers must be a non-empty list")
    if not isinstance(data["destinations"], list) or len(data["destinations"]) == 0:
        raise ValueError("destinations must be a non-empty list")
    for i, traveler in enumerate(data["travelers"]):
        for field in ("name", "origin_airport", "filters"):
            if field not in traveler:
                raise ValueError(f"travelers[{i}] missing field: {field}")
        _validate_filters(traveler["filters"], f"travelers[{i}].filters")
    _validate_filters(data["default_filters"], "default_filters")


@bp.post("/jobs")
def create_job():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    try:
        _validate_submission(data)
    except ValueError as e:
        logger.warning("Validation failed: %s", e)
        return jsonify({"error": str(e)}), 400

    travelers = data["travelers"]
    destinations = data["destinations"]
    logger.info(
        "Job submission received: %d traveler(s), %d destination(s), %s -> %s",
        len(travelers),
        len(destinations),
        data.get("outbound_date"),
        data.get("return_date"),
    )

    job_id = str(uuid.uuid4())
    db = get_db()
    with db:
        with db.cursor() as cur:
            cur.execute(
                "insert into jobs (id, status, submission) values (%s, 'pending', %s)",
                (job_id, json.dumps(data)),
            )
    logger.info("Job %s written to database with status=pending", job_id)

    run_flock_job.delay(job_id)
    logger.info("Job %s enqueued", job_id)

    return jsonify({"job_id": job_id}), 201


@bp.get("/jobs/<job_id>")
def get_job(job_id: str):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "select id, status, created_at, completed_at, error from jobs where id = %s",
            (job_id,),
        )
        row = cur.fetchone()

    if row is None:
        logger.warning("Job %s not found", job_id)
        return jsonify({"error": "Job not found"}), 404

    job_id_db, status, created_at, completed_at, error = row
    response = {
        "job_id": str(job_id_db),
        "status": status,
        "created_at": created_at.isoformat() if created_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "error": error,
    }

    if status == "complete":
        with db.cursor() as cur:
            cur.execute("select data from results where job_id = %s", (job_id,))
            result_row = cur.fetchone()
        if result_row:
            response["result"] = result_row[0]

    return jsonify(response), 200
