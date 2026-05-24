import json
import os
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from psycopg_pool import ConnectionPool
from pymongo import MongoClient

# Thumbnails are deterministic per product id — see CONTEXT.md (Catalog).
THUMBNAIL_URL = "https://loremflickr.com/400/400/camera?lock={id}"


def _pg_dsn() -> str:
    return (
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']} "
        f"dbname={os.environ['POSTGRES_DB']}"
    )


def _mongo_uri() -> str:
    return (
        f"mongodb://{os.environ['MONGO_USER']}:{os.environ['MONGO_PASSWORD']}"
        f"@{os.environ['MONGO_HOST']}:{os.environ.get('MONGO_PORT', '27017')}/"
        f"?authSource=admin"
    )


pg_pool: ConnectionPool | None = None
mongo: MongoClient | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pg_pool, mongo
    pg_pool = ConnectionPool(_pg_dsn(), min_size=1, max_size=4, open=True)
    # MongoClient is lazy: it doesn't connect on construction, only on first
    # op. Keeps backend Ready even if mongo is briefly down — list endpoint
    # stays available; only the detail endpoint surfaces the error.
    mongo = MongoClient(_mongo_uri(), serverSelectionTimeoutMS=2000)
    try:
        yield
    finally:
        pg_pool.close()
        mongo.close()


app = FastAPI(lifespan=lifespan)


def _thumb(pid) -> str:
    return THUMBNAIL_URL.format(id=pid)


@app.get("/healthz")
def healthz():
    # Liveness + readiness per #4 AC. Pure process check — no DB calls.
    return {"status": "ok"}


@app.get("/api/products")
def list_products():
    assert pg_pool is not None
    with pg_pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, price_cents FROM products ORDER BY name"
        )
        # #5 moves the product_viewed event_log write to /api/products/{id};
        # the list endpoint is now read-only.
        return [
            {
                "id": str(pid),
                "name": name,
                "price_cents": price_cents,
                "thumbnail": _thumb(pid),
            }
            for (pid, name, price_cents) in cur.fetchall()
        ]


@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    assert pg_pool is not None and mongo is not None
    try:
        UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found")

    with pg_pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, price_cents FROM products WHERE id = %s",
            (product_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        pid, name, price_cents = row
        cur.execute(
            "INSERT INTO event_log (event_type, payload) VALUES (%s, %s::jsonb)",
            ("product_viewed", json.dumps({"product_id": str(pid)})),
        )
        conn.commit()

    # Mongo lookup is best-effort per #5 AC: missing detail/reviews return
    # empty fields, not 500.
    db = mongo[os.environ["MONGO_DB"]]
    detail = db.product_details.find_one({"product_id": str(pid)}) or {}
    reviews = list(
        db.reviews.find(
            {"product_id": str(pid)},
            {"_id": 0, "product_id": 0},
        )
    )

    return {
        "id": str(pid),
        "name": name,
        "price_cents": price_cents,
        "thumbnail": _thumb(pid),
        "description": detail.get("description", ""),
        "specs": detail.get("specs", []),
        "reviews": reviews,
    }
