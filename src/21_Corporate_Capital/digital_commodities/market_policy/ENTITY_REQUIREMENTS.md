# ENTITY Data Market Policy Requirements
Status: ENTITY 2 development authority.

- Data-market policy SHALL be versioned, jurisdiction-scoped, instrument-class-scoped and effective-dated.
- Supported actions SHALL distinguish commodity registration, rights issuance, listing, trading, consumption and trade settlement.
- Missing policy SHALL resolve to authorized review rather than implicit permission.
- Explicit `DENY` SHALL fail closed.
- `ALLOW_EVIDENCE_ONLY` permits the canonical ENTITY evidence/runtime operation but SHALL NOT be represented as a legal determination.
- Policy records SHALL identify an authority reference and retain notes/evidence metadata.
- Expired rules SHALL not authorize later activity.
- This authority is separate from the existing qualified corporate-capital instrument classifier and SHALL NOT alter its READY binding.

## Compliance Evidence Gate
- Buyer eligibility, collateral/funds reservation and external trade settlement SHALL be accepted only through cryptographically verifiable external authority evidence when required.
- Eligibility evidence SHALL bind the buyer and applicable jurisdiction/purpose constraints.
- Collateral evidence SHALL bind buyer, currency, maximum order notional and expiry.
- External settlement evidence SHALL bind exact trade, buyer, seller, amount, currency, final status and settlement reference.
- These checks validate evidence attribution and configured policy; they SHALL NOT be represented as legal advice or an independent legal classification.
- External trust records needed for standalone verification SHALL be exportable as public verification material.
