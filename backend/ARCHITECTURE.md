# Backend Architecture

## Two processes, one codebase

Running `bash run_dev.sh` starts two completely separate OS processes from the same Python codebase:

| Process | Command | Purpose |
|---|---|---|
| Flask | `python -m flask run` | HTTP server — handles requests from the frontend |
| Celery | `celery -A app worker` | Background worker — runs flight search jobs |

They share no memory. The only thing connecting them is **Redis**.

---

## How a job flows

```
Frontend
  │
  │  POST /jobs
  ▼
Flask process
  │  1. Validates the request
  │  2. Writes a pending job to Supabase
  │  3. Calls run_flock_job.delay(job_id)
  │     └─ serializes the call to JSON
  │     └─ does Redis LPUSH onto the "celery" queue
  │  4. Returns {"job_id": ...} immediately
  │
  │  (Flask is now done with this job)
  │
Redis queue ◄──────────────────────────┐
  │                                    │
  │  (Celery worker is blocked on      │
  │   Redis BLPOP, waiting for work)   │
  │                                    │
  ▼                                    │
Celery process                         │
  │  1. Redis unblocks, hands over     │
  │     the JSON message               │
  │  2. Deserializes → run_flock_job() │
  │  3. Fans out Amadeus API calls     │
  │  4. Writes results to Supabase     │
  │  5. Sets job status = complete     │
  │                                    │
  └────────────────────────────────────┘
              (loop — back to BLPOP)

Frontend polls GET /jobs/{id} every 3s until status = complete
```

The two processes **never talk to each other directly**. Flask doesn't know if the Celery worker is running. Celery doesn't know Flask exists. Redis is the only handoff point.

---

## How two processes share one `create_app()`

Both CLI commands import the same `app` module and call `create_app()` as initialization. What determines the process type is what the CLI does **after** `create_app()` returns — they diverge completely:

```
create_app() runs in both processes
       │
       ├─── python -m flask run
       │         └─ Flask CLI hands the app to Werkzeug
       │            → HTTP server starts on port 5000
       │            → routes registered, requests handled
       │            → Celery instance is used only to enqueue tasks
       │
       └─── celery -A app worker
                 └─ Celery CLI starts the worker loop
                    → connects to Redis, blocks on BLPOP
                    → Flask instance is used only for config + app_context()
                    → routes registered but never reachable (no HTTP server)
```

`create_app()` is shared initialization. Neither CLI cares about what the other sets up — Flask ignores the Celery consumer role, Celery ignores the routes and blueprints.

---

## Why Flask has a Celery instance

Flask needs to call `.delay()` to enqueue a task. `.delay()` is a Celery method — it serializes the task call and does the Redis write. So Flask needs a Celery instance configured with the Redis URL, but only as a **producer** (a Redis client with a specific message format). It has zero awareness of the Celery worker process.

This happens inside `_init_celery()`, called by `create_app()`.

---

## Why Celery has a Flask app

The Celery worker needs two things that are Flask concepts:

1. **`current_app.config`** — to read Amadeus credentials
2. **`g`** — Flask's per-context storage, used by `get_db()` to manage the DB connection lifecycle

To use these outside of an HTTP request, you push a **Flask app context** manually. That's what `FlaskTask` does:

```python
class FlaskTask(Task):
    def __call__(self, *args, **kwargs):
        with app.app_context():   # makes current_app and g available
            return self.run(*args, **kwargs)
```

This does **not** start an HTTP server or open any port. It just makes Flask's config and context utilities available inside the task function for the duration of its execution.

As a side effect, `create_app()` also registers routes and blueprints in the Celery process — that code runs but has no effect since no HTTP server is ever started.

---

## What each process actually uses

| | Flask process | Celery process |
|---|---|---|
| Flask app | HTTP server, routes, blueprints | Config + `g` only |
| Celery instance | Producer (enqueues tasks via Redis) | Consumer (executes tasks from Redis) |
| Supabase | Reads job status, writes pending job | Reads submission, writes results |
| Redis | Writes task messages | Reads task messages (blocking) |
| Amadeus API | Never | All calls happen here |
