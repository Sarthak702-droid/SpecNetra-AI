# Warehouse Inventory Service Requirements

## REQ-INV-001 — Item Creation
Priority: P0
- A store manager can register a new inventory item via POST /api/items.
- Successful creation returns HTTP 201 with generated item ID, SKU, and status 'active'.

## REQ-INV-002 — Item Retrieval & Listing
Priority: P0
- Registered items must be retrievable via GET /api/items and GET /api/items/{item_id}.
- Successfully returns HTTP 200 with matching inventory data.

## REQ-INV-003 — Validation of Item Payload
Priority: P1
- Item creation requests missing mandatory SKU or quantity must be rejected.
- Returns HTTP 422 with unprocessable entity error.
