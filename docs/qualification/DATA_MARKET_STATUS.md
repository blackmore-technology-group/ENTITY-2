# ENTITY 2 Data Commodity Market — Internal Qualification Status
Date: 2026-09-20/21 UTC
Status: `INTERNALLY_QUALIFIED_EXTERNAL_GATES_PENDING`

The Protocol 2 development branch now contains the complete internal data-commodity rights-market stack:

- sovereign `DATA_COMMODITY` registration and separate rights instruments;
- supply ceilings, reservation, consumption and deterministic price-time matching;
- local and federated signed-order ingestion with replay protection;
- external buyer-eligibility and collateral evidence gates;
- native or externally attested settlement before rights transfer;
- deterministic royalty allocation;
- signed/hash-chained market history and provider-independent evidence export;
- destructive encrypted recovery and Entity-scoped portable export coverage;
- fail-closed external authorized-venue adapter;
- standalone public market-package verifier.

Public branch qualification after integration: **22/22 pytest PASS** and **11/11 unittest PASS**.
## Source pins
- Exchange v2: `339846b249801c70763cfc016a72a2b458ae5517dca666926b79d81a821b6858`
- Compliance gate: `ccf77db14177cee85e21b4824f85fdc450c584708e6330c2ed6525224765b061`
- External venue adapter: `69337d4e875297af062c43eb1b6c9221dd05af17486d396bdd12e46c637862c0`
- Standalone public verifier: `f5aac4a62e97ec1effbfbd61e1fbebaeeb715e19eb4fb674332bffd033c38a9f`

## Claim boundary
ENTITY Protocol 1.0 remains frozen and unchanged. Protocol 2 external conformance is not claimed.
Independent external interoperability still requires an unrelated implementation/operator. Live provider credentials, venue authorization and jurisdiction-specific legal/regulatory determinations are external evidence/configuration gates, not claims made by this repository.
