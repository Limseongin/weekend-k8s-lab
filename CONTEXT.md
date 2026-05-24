# weekend-k8s-lab

A 1-day learning project: a minimal e-commerce slice for a **camera catalog** (browse cameras → add to cart) deployed end-to-end on Kubernetes, used to practice the Claude Code + oh-my-claudecode + Matt Pocock skills workflow before a 3-week academy team project.

## Language

**Product**:
A camera that can be browsed and added to a cart. Has a stable identity, a name, a price, and a thumbnail. Exists in the catalog whether or not anyone has it in their cart. The catalog is a single flat list — every Product has `category = "camera"`; sub-types (body / lens / accessory) are deliberately not modeled at this stage.
_Avoid_: Item, SKU, Listing

**Catalog**:
The set of all Products. Seeded once with 50–100 dummy camera entries; never edited from the UI. Product thumbnails are fetched from `loremflickr.com/400/400/camera?lock={product_id}` so the same Product always resolves to the same image without needing to store image URLs in the seed data.
_Avoid_: Inventory (suggests stock management, which is out of scope), Store

**Cart**:
A container for a shopper's intended purchases during a single browsing session. Identified by an opaque `cart_id` (UUID) stored in a browser cookie — there is no user account. A Cart holds zero or more **Cart Items**.
_Avoid_: Basket, Order (Order is explicitly out of scope), Bag

**Cart Item**:
A line in a Cart referencing one Product and a quantity. The Cart Item is owned by the Cart; deleting the Cart deletes its Items.
_Avoid_: Line item, Cart entry

**Shopper**:
The anonymous human using the site. Identified only by their `cart_id` cookie. Has no name, no email, no login. If they clear cookies, they become a different Shopper.
_Avoid_: User, Customer, Account (none of these exist — there is no identity beyond the cookie)

**Product Detail**:
The long-form, free-text part of a Product (description, specs, image gallery). Lives in MongoDB and is keyed by the same id as the Product. A Product is the master; Product Detail is supplementary. A Product can exist without a Product Detail (the UI just shows nothing in the detail section).
_Avoid_: Product description (too narrow), Product page

**Review**:
A Shopper's written rating of a Product. Stored in MongoDB with a free-form author name string (no Shopper identity is preserved). One Product can have many Reviews. Reviews are seeded as dummy data for this lab; no real write path from the UI.
_Avoid_: Rating (a Review *contains* a rating, it isn't one), Comment

**Event Log**:
An append-only audit trail of Shopper actions (`product_viewed`, `cart_item_added`, etc.) stored in a single Postgres table with a JSONB payload. Stands in for the real-project Kafka topic — same conceptual role (decoupled activity stream) without the operational weight.
_Avoid_: Audit log (suggests compliance), Analytics events (no aggregation happens here)

## Flagged ambiguities

_None yet — grilling in progress._

## Example dialogue

> **Dev:** "Should the cart endpoint require a user ID?"
> **Lead:** "There are no users. The Shopper is identified only by their `cart_id` cookie. If the cookie is missing, the backend mints a new Cart on first write."
> **Dev:** "So two browsers = two Carts, always?"
> **Lead:** "Right. There's no merging, no login, no account recovery. Clearing cookies loses the Cart — that's acceptable for this lab."
