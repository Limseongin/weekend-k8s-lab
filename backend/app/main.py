import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

# Thumbnails are deterministic per product id — see CONTEXT.md (Catalog).
THUMBNAIL_URL = "https://loremflickr.com/400/400/camera?lock={id}"


def _make_dsn() -> str:
    return (
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']} "
        f"dbname={os.environ['POSTGRES_DB']}"
    )


pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(_make_dsn(), min_size=1, max_size=4, open=True)
    try:
        yield
    finally:
        pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    # Liveness + readiness per #4 AC. Intentionally does not touch the DB —
    # a DB blip should not restart the pod.
    return {"status": "ok"}


@app.get("/api/products")
def list_products():
    assert pool is not None
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, price_cents FROM products ORDER BY name"
        )
        products = [
            {
                "id": str(pid),
                "name": name,
                "price_cents": price_cents,
                "thumbnail": THUMBNAIL_URL.format(id=pid),
            }
            for (pid, name, price_cents) in cur.fetchall()
        ]
        # Batch event per #4. #5 will replace this with a per-product event
        # on the /api/products/{id} endpoint.
        cur.execute(
            "INSERT INTO event_log (event_type, payload) VALUES (%s, %s::jsonb)",
            ("product_viewed", json.dumps({"variant": "list", "count": len(products)})),
        )
        conn.commit()
    return products
