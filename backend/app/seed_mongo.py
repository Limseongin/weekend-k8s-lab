"""Seeds product_details + reviews in Mongo, keyed by Postgres product ids.

Idempotent: product_details upsert on product_id; reviews insert only if no
review exists yet for that product. Re-running the Job leaves Mongo unchanged
once seeded.

Entrypoint: `python -m app.seed_mongo` (run from the backend image).
"""

import os
import random
import sys
import time

import psycopg
from pymongo import MongoClient


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


def _fetch_products(max_attempts: int = 60, sleep_s: float = 2.0):
    """Poll postgres until the products table has rows.

    The postgres-seed Job + mongo-seed Job have no native ordering; this loop
    is the same pattern postgres-seed itself uses to wait for the DB pod.
    """
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with psycopg.connect(_pg_dsn(), connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, name FROM products ORDER BY name"
                    )
                    rows = cur.fetchall()
                    if rows:
                        return rows
                    last_err = RuntimeError("products table empty")
        except Exception as e:  # noqa: BLE001
            last_err = e
        print(
            f"postgres products not ready ({attempt}/{max_attempts}): "
            f"{last_err!s}",
            flush=True,
        )
        time.sleep(sleep_s)
    raise RuntimeError(f"postgres products never appeared: {last_err!s}")


SPECS_TEMPLATE = [
    {"key": "sensor", "value": "Full-frame CMOS"},
    {"key": "megapixels", "value": "24.2"},
    {"key": "iso_range", "value": "100-51200"},
    {"key": "video", "value": "4K60"},
    {"key": "weight_g", "value": "650"},
]

AUTHORS = [
    "Alex K.", "Bo M.", "Cam R.", "Dani S.", "Eun J.",
    "Finn O.", "Gabi T.", "Han L.", "Ivy P.", "Jules V.",
]


def main() -> int:
    products = _fetch_products()
    print(f"fetched {len(products)} product ids from postgres", flush=True)

    mc = MongoClient(_mongo_uri())
    db = mc[os.environ["MONGO_DB"]]

    db.product_details.create_index("product_id", unique=True)
    db.reviews.create_index("product_id")

    upserted = 0
    for (pid, name) in products:
        db.product_details.update_one(
            {"product_id": str(pid)},
            {"$set": {
                "description": (
                    f"The {name} is a flagship-grade camera designed for both "
                    "stills and video. Compact weather-sealed magnesium body, "
                    "tilting touchscreen, and dual card slots make it a "
                    "versatile companion in the field."
                ),
                "specs": SPECS_TEMPLATE,
            }},
            upsert=True,
        )
        upserted += 1
    print(f"upserted {upserted} product_details docs", flush=True)

    # Deterministic dummy reviews: same Random seed → same dummy data on
    # every clean re-seed. Skip products that already have any review.
    rng = random.Random(42)
    inserted = 0
    skipped = 0
    for (pid, name) in products:
        if db.reviews.count_documents({"product_id": str(pid)}, limit=1) > 0:
            skipped += 1
            continue
        n = rng.randint(3, 10)
        batch = [
            {
                "product_id": str(pid),
                "author": rng.choice(AUTHORS),
                "rating": rng.randint(3, 5),
                "body": (
                    f"Solid build, sharp images. {name} delivers what it "
                    "promises — happy with the purchase."
                ),
            }
            for _ in range(n)
        ]
        db.reviews.insert_many(batch)
        inserted += n
    print(
        f"inserted {inserted} reviews (skipped {skipped} products already seeded)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
