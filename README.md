# ENTITY-2

**BTG-controlled development line for future ENTITY market, integration and protocol experiments.**

> **Looking for the current release? Start with [ENTITY v3.4.0](https://github.com/blackmore-technology-group/ENTITY/releases/tag/v3.4.0) in the main [ENTITY](https://github.com/blackmore-technology-group/ENTITY) repository.**

`ENTITY-2` is a public development repository maintained by **Blackmore Technology Group Limited (BTG)**. It contains post-release engineering work and experiments around sovereign data commodities, rights-aware exchange, market evidence, integrations and related protocol research.

**This repository is not the current protected ENTITY release, not the authoritative external conformance target, and not an independent third-party implementation.**

## Public project map

| You want to… | Use |
| --- | --- |
| Evaluate or build against the current protected release | [ENTITY v3.4.0 — Global Passport & Continuous Provenance](https://github.com/blackmore-technology-group/ENTITY/releases/tag/v3.4.0) |
| Start as a developer | [ENTITY Developer Portal](https://github.com/blackmore-technology-group/ENTITY/blob/main/DEVELOPERS.md) |
| Try a Healthcare, Finance, Manufacturing, AI, Robotics or Defence package | [ENTITY v3.4 domain packages](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/v3.4/DOMAIN_PACKAGES.md) |
| Reproduce current v3.4 Global Passport evidence | [ENTITY engineering evidence](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/ENGINEERING_EVIDENCE.md) |
| Implement frozen Protocol 1.0 independently | [ENTITY Protocol 1.0 Conformance Kit](https://github.com/blackmore-technology-group/ENTITY-Protocol-1.0-Conformance-Kit) |
| Explore future/experimental engineering | **This repository (`ENTITY-2`)** |

Current protected release facts:

- release: **ENTITY v3.4.0 — Global Passport & Continuous Provenance**;
- protected release commit: `2db5bff64507b8d67642122a5ff2fc73dfef9152`;
- v3.4 sealed Global Passport vectors: **24/24 PASS** — 12 valid / 12 invalid;
- independent unrelated implementation: **OPEN / PENDING**.

The current authoritative Protocol 1.0 conformance-kit release remains a separate frozen target.

## What belongs here

Current development themes may include:

- sovereign data-commodity objects and rights-bearing instruments;
- listing, disclosure, order/RFQ/auction and price-discovery mechanics;
- clearing, settlement and entitlement state;
- usage evidence, derived outputs and economic consequences;
- rights-aware exchange and market recovery;
- ADAM/NIKI integration boundaries;
- provider-independent evidence and authority semantics;
- failure, rollback, recovery and portability testing.

The intended market lifecycle is:

**DCO → Instrument → Listing → Disclosure → Order/RFQ/Auction → Price Discovery → Trade → Clearing → Settlement → Entitlement → Usage → Derived Output → Economic Consequence**

Data economics in ENTITY concerns governed **rights and authority around data**, not artificial scarcity of byte copies.

## Claim boundary

Work in this repository can be incomplete, experimental, superseded or awaiting qualification. A branch, commit, pull request, passing local test or merged development change does **not** automatically become:

- a protected ENTITY release;
- a frozen protocol revision;
- external conformance evidence;
- independent interoperability evidence;
- an independent security review;
- a legal, regulatory, accounting or market determination.

Release claims belong with the evidence package and protected release in the main [ENTITY](https://github.com/blackmore-technology-group/ENTITY) repository.

BTG-controlled work—including clean-room work in other BTG repositories—is not described as unrelated third-party validation.

## Core invariants

Development work must preserve the project’s authority boundaries:

- identity is not an account;
- registration is not ownership;
- provenance is not truth;
- a valid signature is not objective external truth;
- possession, hosting and storage do not create sovereign authority;
- external evidence sources do not silently become protocol authority;
- generic application events cannot mutate protected authority, rights or economic state;
- historical signed state is superseded rather than silently rewritten;
- internal qualification is not independent external validation.

## Engineering workflow

`main` is protected. Changes should flow through pull requests and required checks. Development work should identify the exact branch/commit tested and should not describe an unqualified development branch as a release.

Python 3.11+ is recommended for the current reference/development runtime.

```bash
git clone https://github.com/blackmore-technology-group/ENTITY-2.git
cd ENTITY-2
python -m pip install -r requirements.txt
python -m compileall -q src sdk protocol
python -m unittest discover -s tests -v
```

Passing this local smoke path is useful engineering evidence for the checked-out commit. It is not by itself a release or interoperability qualification.

## External conformance and interoperability

Unrelated implementers should work from published sealed/specification material rather than using this development repository as their implementation source:

- [ENTITY Protocol 1.0 Conformance Kit](https://github.com/blackmore-technology-group/ENTITY-Protocol-1.0-Conformance-Kit)
- [ENTITY v3.4 independent classifier task](https://github.com/blackmore-technology-group/ENTITY/issues/27)
- [ENTITY interoperability challenge](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/INTEROPERABILITY_CHALLENGE.md)
- [Interoperability status](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/interoperability/STATUS.md)

Independent external implementation and live interoperability remain evidence-gated milestones and should be recorded only when an unrelated party produces the required evidence.

## Security

Never commit private signing/recovery keys, credentials/tokens, principal/device/application binding instances, `.entitybackup` files, production databases/runtime state, or unredacted user/customer/business data.

Security-sensitive findings should use the private reporting process described by the main ENTITY project's [SECURITY.md](https://github.com/blackmore-technology-group/ENTITY/blob/main/SECURITY.md).

## Governance

Public governance and release discipline live in the main ENTITY repository:

- [Developer Portal](https://github.com/blackmore-technology-group/ENTITY/blob/main/DEVELOPERS.md)
- [Governance](https://github.com/blackmore-technology-group/ENTITY/blob/main/GOVERNANCE.md)
- [Engineering Evidence](https://github.com/blackmore-technology-group/ENTITY/blob/main/docs/ENGINEERING_EVIDENCE.md)
- [Security](https://github.com/blackmore-technology-group/ENTITY/blob/main/SECURITY.md)

## License

ENTITY development material in this repository is published under the **Apache License 2.0** where the repository license applies. See [LICENSE](LICENSE).

---

**Blackmore Technology Group Limited**  
Repository: `blackmore-technology-group/ENTITY-2`  
Role: BTG-controlled future/development engineering line
