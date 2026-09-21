# ENTITY Data Commodity & Exchange Requirements
Status: ENTITY 2 development extension; not part of frozen Protocol 1.0 and not yet an external-conformance claim.
Parent baseline: SERS-ENTITY-003 v2.2 Sections 151–172.

## Data Commodity Doctrine
- ENTITY SHALL support `DATA_COMMODITY` as a protocol/economic classification for sovereign digital assets with measurable utility, provenance, rights and economic use.
- Protocol classification SHALL NOT by itself establish legal commodity, security, property, tax or regulatory classification.
- Registration, hosting, indexing, custody, computation or market listing SHALL NOT by itself establish ownership or sovereign authority.
- A commodity SHALL remain bound to an underlying asset identifier, controller authority reference, unit definition, provenance and jurisdiction metadata.

## Commodity Units & Supply Integrity
- A commodity or instrument SHALL define its measurable unit; ENTITY SHALL NOT assume all data is fungible.
- Commodity quality/grade, divisibility and fungibility SHALL be explicit metadata.
- Tradable instrument supply SHALL have an authorized ceiling.
- Issuance SHALL be replay-resistant and SHALL NOT exceed authorized supply.
- Issued units SHALL reconcile to circulating plus consumed/retired units.

## Rights Instruments
- The underlying data commodity SHALL remain separate from the tradable instrument.
- A tradable instrument SHALL identify the exact rights class, quantity, transferability, resale policy, expiry, territory, purpose constraints and jurisdictional classification.
- Initial issuance SHALL require authority over the underlying commodity plus commercialization authority.
- Secondary resale SHALL occur only when the instrument explicitly permits transfer and resale.

## Rights Ledger & Reservation
- Positions SHALL distinguish available, reserved and consumed units.
- A sell order SHALL reserve the offered rights before it can enter the order book.
- Reserved units SHALL reconcile to open sell-order remainder plus pending-settlement trades.
- Cancellation or failed settlement SHALL release the appropriate reservation without manufacturing additional units.
- Consumption SHALL reduce circulating rights and preserve a replay-resistant usage reference.

## Exchange & Price Discovery
- ENTITY SHALL support deterministic price-time matching for qualified data-right instruments.
- A market operator SHALL match and attest transactions but SHALL NOT gain ownership merely by operating the venue.
- Executions SHALL preserve bid/ask/order/trade distinctions and SHALL NOT confuse modelled value with market-established price.
- Market history SHALL be strictly sequenced, signed and hash chained.
- Self-matching SHALL be rejected by the canonical matcher.
- Initial implementation scope is limit orders with GTC and IOC behavior; additional order types require separate qualification.

## Settlement Boundary
- A matched trade SHALL remain `PENDING_SETTLEMENT` until its settlement evidence is final.
- Rights SHALL NOT transfer merely because orders matched.
- Settlement SHALL bind the exact trade, buyer, seller, amount, currency and obligation reference before rights move.
- Failed settlement SHALL return reserved rights to the seller.
- Settlement providers remain external/abstracted; ENTITY records and verifies evidence rather than assuming possession equals payment.

## Jurisdiction & Market Policy
- Data-market actions SHALL use a separately versioned policy registry and SHALL fail closed when no applicable rule authorizes the operation.
- Policy actions SHALL distinguish issuance, listing, trading, consumption and trade settlement.
- Historical activity SHALL retain the policy/ruleset effective at execution where evidence packaging supports it.
- A technical `DATA_COMMODITY` designation SHALL coexist with a separate jurisdictional instrument classification.

## Sovereignty & Intelligence Boundaries
- Exchange functionality SHALL NOT weaken provider non-authority, portable state, recovery or independent-verification requirements.
- NIKI MAY discover, compare, estimate, explain and flag anomalies but SHALL NOT create ownership, override rights or manufacture canonical market price.
- ADAM MAY act only under explicit delegated capability and applicable exchange policy.
- The exchange SHALL trade defined rights instruments; raw data need not leave sovereign custody when compute-to-data or access-right models apply.

## Qualification Boundary
- Development qualification SHALL include primary trading, secondary resale, double-sale prevention, supply ceiling enforcement, consumption, settlement gating and market-chain verification.
- Destructive recovery/export verification, federation between unrelated market implementations, market-chaos campaigns, royalties, buyer-eligibility integrations and regulated live venue integration remain separate qualification gates.
- This extension SHALL NOT alter frozen ENTITY Protocol 1.0/conformance artifacts.
- This extension SHALL NOT imply that ENTITY core operates a public securities exchange, broker/dealer, transfer agent or regulated securities venue.
