# Postgres owns the master data; Mongo holds the supplementary documents

The lab uses two databases deliberately, to practice containerising both. To keep the split from collapsing into "same data in two places", Postgres is the single source of truth for any record with a stable identity or that participates in transactions (`products`, `carts`, `cart_items`, `event_log`); MongoDB stores only the long-form, schema-free supplements that hang off a Product (`product_details`, `reviews`) keyed by the Postgres `products.id`.

## Consequences

- The BFF fetches a Product by reading Postgres for the master row and then Mongo for the detail/reviews — two queries, no cross-DB joins.
- If a Product is deleted from Postgres, the Mongo documents become orphans. Acceptable for this lab; would need a cleanup job in production.
- Reviews carry no Shopper identity (there are no Users) — they are seeded as dummy data only, not user-writable.
- Cart writes never touch Mongo, so cart consistency is a single-DB transaction.
