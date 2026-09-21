# ADR-0005 — Data Commodity & Exchange Protocol
Status: ACCEPTED FOR ENTITY 2 DEVELOPMENT
Date: 2026-09-20
Parent baseline: SERS-ENTITY-003 / v2.2

## Decision
ENTITY 2 SHALL treat qualifying sovereign digital assets as `DATA_COMMODITY` at the protocol/economic layer and SHALL support separately defined tradable rights instruments against those commodities.

The underlying data, the commodity representation, the rights instrument, the market order and the settled rights position are distinct objects. None SHALL be silently substituted for another.

## Market Non-Authority
Operating, indexing, listing, matching, settling or observing a market SHALL NOT by itself confer ownership or sovereign authority over the underlying data.

The market operator provides deterministic matching and signed market evidence. Authority to issue or transfer rights derives from the underlying ENTITY authority chain and the instrument's transfer rules.

## Settlement Rule
A match creates a pending trade, not a completed rights transfer. Rights move only after settlement evidence binds the exact trade, parties, quantity, price/currency and obligation reference.

## Classification Boundary
`DATA_COMMODITY` is an ENTITY protocol classification. Legal/regulatory treatment remains separately represented by jurisdictional classification and policy evidence.
